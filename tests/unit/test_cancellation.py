"""Customer cancellation (step 2.4): the cancel API, the race against the payment webhook (both orders), the race
against BeginFulfillment, the DemoPay void, refund-what's-left, checkout holds, and the stamp that keeps orders on
an older definition non-cancellable. Invariants checked: I5 (stock), I7 (refunds <= charge), I8 (a CANCELLED order:
net 0, all its stock back) and I9 (cancel and payment never both win)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from conftest import USER_A, USER_B, FakeSfn, api_event, jwt_claims, ledger, psp_request, seed_order, sqs_event
from test_fulfillment import SEEDED, assert_i5, counters
from test_request_payment import RecordingSqs

TOTAL = Decimal("5097.00")
ORDER_ID = "ORD-20261022-abcdef12"


# --- fixtures ----------------------------------------------------------------------------------------------
@pytest.fixture
def cancel(load_handler, monkeypatch):
    handler = load_handler("cancel_order")
    monkeypatch.setattr(handler, "CANCEL_ENABLED", True)
    monkeypatch.setattr(handler, "sfn", FakeSfn())
    return handler


@pytest.fixture
def step(load_handler, monkeypatch):
    """request_payment with its SQS send and Step Functions client recorded."""
    handler = load_handler("request_payment")
    monkeypatch.setattr(handler, "sqs", RecordingSqs())
    monkeypatch.setattr(handler, "sfn", FakeSfn())
    return handler


@pytest.fixture
def refund(load_handler, payments, monkeypatch):
    """refund_payment whose DemoPay calls (refund, line refund, void) go straight to the provider handler."""
    handler = load_handler("refund_payment")

    def call_refund(_client, _fn, intent_id, line=None, note=""):
        request = {"operation": "refund", "paymentIntentId": intent_id, **({"note": note} if note else {})}
        if line:
            request.update(lineId=line["lineId"], amount=str(line["amount"]), note=line.get("note", ""))
        return payments.provider.lambda_handler(request, None)

    def call_void(_client, _fn, intent):
        return payments.provider.lambda_handler(
            {"operation": "void", "paymentIntentId": intent["paymentIntentId"], "orderId": intent["orderId"],
             "walletId": intent["walletId"], "amount": str(intent["amount"]), "currency": "INR"},
            None,
        )

    monkeypatch.setattr(handler, "invoke_provider_refund", call_refund)
    monkeypatch.setattr(handler, "invoke_provider_void", call_void)
    return handler


@pytest.fixture
def saga(aws, load_handler, step, refund, payments):
    """The saga's steps, called in the order the state machine calls them."""

    class Saga:
        reserve = load_handler("reserve_inventory")
        begin = load_handler("begin_fulfillment")
        release = load_handler("release_inventory")

        def placed(self, cancellable=True, **overrides):
            """Reserved (stamped by the new definition unless cancellable=False) and PAYMENT_PENDING."""
            order = seed_order(aws.orders, **overrides)
            event = {"orderId": order["orderId"], **({"cancellable": True} if cancellable else {})}
            self.reserve.lambda_handler(event, None)
            step.lambda_handler({"orderId": order["orderId"], "taskToken": "token-1", "simulate": "none"}, None)
            return order

        def demopay_charges(self, order):
            """DemoPay processes the queued request: charges the wallet and calls the webhook (in-process)."""
            payments.provider.lambda_handler(sqs_event(psp_request(order)), None)
            return payments.callbacks[-1]["result"]["result"] if payments.callbacks else None

        def cancel_branch(self, order):
            """RefundWhatIsLeft -> ReleaseInventory -> MarkOrderCancelled (the state machine's direct DynamoDB write)."""
            result = refund.lambda_handler({"orderId": order["orderId"], "cancelled": True}, None)
            self.release.lambda_handler({"orderId": order["orderId"]}, None)
            aws.orders.update_item(Key={"orderId": order["orderId"]}, UpdateExpression="SET #s = :c", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": "CANCELLED"})
            return result

    return Saga()


def call(cancel, order_id=ORDER_ID, user=None, body=None):
    claims = jwt_claims() if user is None else jwt_claims(user_id=user, email="b@example.com")
    result = cancel.lambda_handler(api_event(body, path_parameters={"id": order_id}, claims=claims), None)
    return result["statusCode"], json.loads(result["body"])


def stored(aws, order_id=ORDER_ID):
    return aws.orders.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]


def intent(aws, order_id=ORDER_ID):
    return aws.payments.get_item(Key={"paymentIntentId": f"PI-{order_id}"}, ConsistentRead=True).get("Item")


def history(aws, order_id=ORDER_ID):
    return [e["status"] for e in stored(aws, order_id)["statusHistory"]]


def net_charge(aws):
    entries = ledger(aws)
    return sum(a for t, a in entries if t == "DEBIT") - sum(a for t, a in entries if t == "CREDIT")


def assert_i8(aws):
    """A CANCELLED order: net charge 0, its stock back in `stock` (nothing reserved/sold/written off), released."""
    assert stored(aws)["status"] == "CANCELLED"
    assert net_charge(aws) == 0
    for product, seeded in SEEDED.items():
        assert counters(aws, product) == {"stock": seeded, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 0}
    assert stored(aws)["released"] is True


# --- cancel vs the payment webhook (I9: exactly one winner) --------------------------------------------------
def test_cancel_first_then_the_charge_lands_the_webhook_refunds_it_and_never_resumes(aws, saga, cancel, payments):
    order = saga.placed()

    code, body = call(cancel)
    assert code == 202 and body["status"] == "CANCEL_REQUESTED"
    assert cancel.sfn.calls[0][0] == "failure" and cancel.sfn.calls[0][1]["error"] == "OrderCancelled"

    # DemoPay had already sent its charge before our void: it lands now, after the cancel was committed.
    assert saga.demopay_charges(order) == "cancelled-refunded"
    # The webhook lost: it never resumes the saga with success; it answers the token with OrderCancelled (a no-op
    # here in reality, the cancel API answered it first).
    assert [(kind, call["error"]) for kind, call in payments.sfn.calls] == [("failure", "OrderCancelled")]
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", TOTAL)]

    result = saga.cancel_branch(order)
    assert result["refunded"] is False  # already refunded by the webhook: DemoPay replays, no second CREDIT (I7)
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", TOTAL)]
    assert intent(aws)["status"] == "REFUNDED" and intent(aws)["cancelled"] is True
    assert stored(aws)["refundedAmount"] == TOTAL
    assert_i8(aws)
    assert_i5(aws)


def test_payment_first_then_cancel_before_fulfillment_refunds_everything(aws, saga, cancel, payments):
    order = saga.placed()
    assert saga.demopay_charges(order) == "resumed"
    assert stored(aws)["status"] == "PAYMENT_CAPTURED" and payments.sfn.calls[0][0] == "success"

    code, body = call(cancel)  # paid, but the warehouse hasn't started: still cancellable
    assert code == 202
    assert cancel.sfn.calls == []  # nothing waits on a token now: BeginFulfillment will see the cancel

    assert saga.begin.lambda_handler({"orderId": ORDER_ID}, None)["outcome"] == "CANCEL_REQUESTED"
    result = saga.cancel_branch(order)
    assert result["refunded"] is True and Decimal(result["refundedAmount"]) == TOTAL
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", TOTAL)]
    assert_i8(aws)
    # The wallet says what the CREDIT was for.
    credit = next(t for t in aws.wallet_txns.query(KeyConditionExpression="walletId = :w", ExpressionAttributeValues={":w": USER_A})["Items"] if t["type"] == "CREDIT")
    assert credit["note"] == f"Refund for {ORDER_ID} (order cancelled)"


def test_payment_and_fulfillment_first_then_cancel_is_too_late_and_the_order_carries_on(aws, saga, cancel):
    order = saga.placed()
    saga.demopay_charges(order)
    assert saga.begin.lambda_handler({"orderId": ORDER_ID}, None)["outcome"] == "FULFILLING"

    code, body = call(cancel)

    assert (code, body) == (409, {"error": "TOO_LATE_TO_CANCEL", "status": "FULFILLING"})
    assert "cancelRequestedAt" not in stored(aws) and stored(aws)["status"] == "FULFILLING"
    assert ledger(aws) == [("DEBIT", TOTAL)]  # the payment won: charged once, nothing refunded


def test_cancel_before_demopay_charged_voids_the_payment_so_nothing_is_ever_taken(aws, saga, cancel, payments):
    order = saga.placed()
    call(cancel)
    result = saga.cancel_branch(order)  # the saga's cancel branch runs before DemoPay's queued request

    assert result == {"orderId": ORDER_ID, "refunded": False, "refundedAmount": "0.00", "reason": "nothing charged"}
    assert intent(aws)["status"] == "FAILED" and intent(aws)["cancelled"] is True

    saga.demopay_charges(order)  # the queued request arrives: the intent is VOIDED at DemoPay
    assert ledger(aws) == [] and payments.callbacks == []  # no debit, no callback
    assert_i8(aws)


def test_a_decline_that_loses_to_the_cancel_does_not_resume_the_saga(aws, saga, cancel, payments):
    order = saga.placed(simulate="payment_declined")
    call(cancel)

    payments.provider.lambda_handler(sqs_event(psp_request(order, simulate="payment_declined")), None)

    assert payments.callbacks[-1]["result"]["result"] == "cancelled-declined"
    assert [(kind, call["error"]) for kind, call in payments.sfn.calls] == [("failure", "OrderCancelled")]
    assert intent(aws)["status"] == "FAILED"
    assert stored(aws)["status"] == "CANCEL_REQUESTED"  # not overwritten with PAYMENT_DECLINED


# --- the cancel API ----------------------------------------------------------------------------------------
def test_a_repeated_cancel_returns_the_same_result(aws, saga, cancel):
    order = saga.placed()
    first = call(cancel)
    cancel.sfn.error = "TaskTimedOut"  # the repeat answers the token again; it was already answered
    second = call(cancel)

    assert first == second and first[0] == 202
    assert history(aws).count("CANCEL_REQUESTED") == 1

    saga.cancel_branch(order)
    third, fourth = call(cancel), call(cancel)
    assert third == fourth and third[0] == 200 and third[1]["status"] == "CANCELLED"


@pytest.mark.parametrize("error", ["TaskTimedOut", "InvalidToken", "TaskDoesNotExist"])
def test_a_token_that_was_already_answered_is_a_lost_race_not_a_crash(aws, saga, cancel, error):
    saga.placed()
    cancel.sfn.error = error

    assert call(cancel)[0] == 202
    assert stored(aws)["status"] == "CANCEL_REQUESTED"


def test_an_unexpected_step_functions_error_is_a_500_and_the_retry_answers_the_token_again(aws, saga, cancel):
    saga.placed()
    cancel.sfn.error = "ThrottlingException"
    with pytest.raises(Exception, match="ThrottlingException"):
        call(cancel)

    cancel.sfn.error = None
    assert call(cancel)[0] == 202
    assert [kind for kind, _ in cancel.sfn.calls] == ["failure", "failure"]


def test_another_users_order_is_404_not_403(aws, saga, cancel):
    saga.placed()

    assert call(cancel, user=USER_B) == (404, {"error": f"Order {ORDER_ID} not found"})
    assert "cancelRequestedAt" not in stored(aws)


def test_an_order_on_the_old_definition_is_not_cancellable(aws, saga, cancel):
    saga.placed(cancellable=False)  # the pre-2.4 definition doesn't pass the stamp

    assert call(cancel) == (409, {"error": "NOT_CANCELLABLE", "status": "PAYMENT_PENDING"})
    assert cancel.sfn.calls == []


@pytest.mark.parametrize("status", ["COMPLETED", "PARTIALLY_FULFILLED", "FAILED", "FULFILLING", "INVENTORY_RELEASED"])
def test_too_late_is_409_and_recorded_once(aws, cancel, status):
    seed_order(aws.orders, status=status, cancellable=True)

    assert call(cancel) == (409, {"error": "TOO_LATE_TO_CANCEL", "status": status})
    assert call(cancel)[0] == 409
    assert history(aws).count("CANCEL_REJECTED") == 1


@pytest.mark.parametrize("status", ["PENDING", "PROCESSING"])
def test_before_the_stock_is_reserved_the_answer_is_try_again(aws, cancel, status):
    seed_order(aws.orders, status=status)

    assert call(cancel) == (409, {"error": "NOT_CANCELLABLE_YET", "status": status})


def test_switched_off_until_the_new_definition_is_live(aws, saga, cancel, monkeypatch):
    saga.placed()
    monkeypatch.setattr(cancel, "CANCEL_ENABLED", False)

    assert call(cancel)[0] == 503
    assert stored(aws)["status"] == "PAYMENT_PENDING"


@pytest.mark.parametrize(
    ("order_id", "body"),
    [("not-an-order", None), (ORDER_ID, json.dumps({"reason": ""})), (ORDER_ID, json.dumps({"reason": "x" * 201}))],
)
def test_bad_requests_are_400(aws, cancel, order_id, body):
    assert call(cancel, order_id=order_id, body=body)[0] == 400


def test_the_reason_is_stored(aws, saga, cancel):
    saga.placed()
    call(cancel, body=json.dumps({"reason": "Ordered the wrong size"}))

    assert stored(aws)["cancelReason"] == "Ordered the wrong size"


def test_unauthenticated_requests_are_401(aws, cancel):
    result = cancel.lambda_handler(api_event(None, path_parameters={"id": ORDER_ID}, claims=None), None)
    assert result["statusCode"] == 401


# --- BeginFulfillment ----------------------------------------------------------------------------------------
def test_begin_fulfillment_is_idempotent(aws, saga):
    order = saga.placed()
    saga.demopay_charges(order)

    first = saga.begin.lambda_handler({"orderId": ORDER_ID}, None)
    again = saga.begin.lambda_handler({"orderId": ORDER_ID}, None)

    assert first["outcome"] == again["outcome"] == "FULFILLING"
    assert history(aws).count("FULFILLING") == 1


def test_begin_fulfillment_refuses_an_order_that_was_never_paid(aws, saga):
    saga.placed()  # PAYMENT_PENDING

    with pytest.raises(RuntimeError, match="refusing to start fulfillment"):
        saga.begin.lambda_handler({"orderId": ORDER_ID}, None)


# --- request_payment never overwrites a committed cancel -----------------------------------------------------
def test_request_payment_after_a_cancel_fails_with_order_cancelled_and_charges_nothing(aws, saga, cancel, step):
    seed_order(aws.orders)
    saga.reserve.lambda_handler({"orderId": ORDER_ID, "cancellable": True}, None)
    assert call(cancel)[0] == 202  # RESERVED: no payment requested yet

    with pytest.raises(step.OrderCancelled):
        step.lambda_handler({"orderId": ORDER_ID, "taskToken": "token-1", "simulate": "none"}, None)
    assert step.sqs.sent == [] and intent(aws) is None


def test_a_cancel_landing_mid_request_is_not_overwritten(aws, saga, step, monkeypatch):
    seed_order(aws.orders)
    saga.reserve.lambda_handler({"orderId": ORDER_ID, "cancellable": True}, None)
    upsert = step.upsert_intent

    def upsert_then_cancel(*args):
        result = upsert(*args)
        aws.orders.update_item(Key={"orderId": ORDER_ID}, UpdateExpression="SET #s = :c, cancelRequestedAt = :t",
                               ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": "CANCEL_REQUESTED", ":t": "now"})
        return result

    monkeypatch.setattr(step, "upsert_intent", upsert_then_cancel)
    with pytest.raises(step.OrderCancelled):
        step.lambda_handler({"orderId": ORDER_ID, "taskToken": "token-1", "simulate": "none"}, None)
    assert step.sqs.sent == [] and stored(aws)["status"] == "CANCEL_REQUESTED"


# --- the stamp, refund-what's-left, holds --------------------------------------------------------------------
def test_only_the_new_definition_stamps_the_order(aws, load_handler):
    reserve = load_handler("reserve_inventory")
    seed_order(aws.orders)
    seed_order(aws.orders, orderId="ORD-20261022-00000002")

    reserve.lambda_handler({"orderId": ORDER_ID, "cancellable": True}, None)
    reserve.lambda_handler({"orderId": "ORD-20261022-00000002"}, None)

    assert stored(aws)["cancellable"] is True
    assert "cancellable" not in stored(aws, "ORD-20261022-00000002")


def test_refund_what_is_left_never_refunds_more_than_was_charged(aws, saga, refund):
    order = saga.placed()
    saga.demopay_charges(order)
    refund.lambda_handler({"orderId": ORDER_ID, "lineIds": ["L1"]}, None)  # 2 mice (1,598) refunded already

    first = refund.lambda_handler({"orderId": ORDER_ID, "cancelled": True}, None)
    second = refund.lambda_handler({"orderId": ORDER_ID, "cancelled": True}, None)

    assert Decimal(first["refundedAmount"]) == TOTAL - Decimal("1598.00")  # only the remainder
    assert second["refunded"] is False
    credits = [a for t, a in ledger(aws) if t == "CREDIT"]
    assert sum(credits) == TOTAL and len(credits) == 2  # I7: refunds == the charge, never more
    assert stored(aws)["refundedAmount"] == TOTAL


def test_cancelling_an_order_placed_from_a_hold_returns_its_stock_exactly_once(aws, load_handler, saga, cancel):
    from test_holds import hold

    _, held = hold(load_handler("holds_api"))  # 2 mice: stock -> held
    items = [{"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "quantity": 2, "unitPrice": Decimal("799.00")}]
    seed_order(aws.orders, items=items, totalAmount=Decimal("1598.00"), holdId=held["holdId"])
    saga.reserve.lambda_handler({"orderId": ORDER_ID, "cancellable": True}, None)  # consumes the hold
    assert aws.holds.get_item(Key={"holdId": held["holdId"]})["Item"]["status"] == "CONSUMED"
    order = stored(aws)

    call(cancel)
    saga.cancel_branch(order)
    after_cancel = counters(aws, "WIRELESS-MOUSE")
    # The hold's expiry schedule fires late (or is retried): the hold is CONSUMED, so it gives nothing back again.
    expired = load_handler("hold_expiry").lambda_handler({"holdId": held["holdId"]}, None)

    assert expired["expired"] is False
    assert after_cancel == counters(aws, "WIRELESS-MOUSE") == {"stock": 100, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 0}
    assert_i5(aws)


# --- the cancel Lambda dies between its conditional write and SendTaskFailure ----------------------------------
class LambdaDied(Exception):
    """Stands in for a crash/timeout of the cancel Lambda right after the CANCEL_REQUESTED write."""


@pytest.fixture
def dying_cancel(cancel, monkeypatch):
    def die(**_kwargs):
        raise LambdaDied("cancel Lambda timed out before SendTaskFailure")

    monkeypatch.setattr(cancel.sfn, "send_task_failure", die)
    return cancel


def test_if_the_cancel_lambda_dies_the_losing_webhook_answers_the_token(aws, saga, dying_cancel, payments):
    order = saga.placed()
    with pytest.raises(LambdaDied):
        call(dying_cancel)
    assert stored(aws)["status"] == "CANCEL_REQUESTED"  # the write committed; nobody answered the token yet

    assert saga.demopay_charges(order) == "cancelled-refunded"

    assert [(kind, c["taskToken"], c["error"]) for kind, c in payments.sfn.calls] == [("failure", "token-1", "OrderCancelled")]
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", TOTAL)]  # the charge that won the race went back
    assert intent(aws)["sagaResumedAt"]


def test_if_the_cancel_lambda_dies_a_losing_decline_answers_the_token_too(aws, saga, dying_cancel, payments):
    order = saga.placed(simulate="payment_declined")
    with pytest.raises(LambdaDied):
        call(dying_cancel)

    payments.provider.lambda_handler(sqs_event(psp_request(order, simulate="payment_declined")), None)

    assert [(kind, c["error"]) for kind, c in payments.sfn.calls] == [("failure", "OrderCancelled")]


def test_a_redelivered_decline_after_a_cancel_is_still_order_cancelled_never_payment_declined(aws, saga, dying_cancel, payments):
    order = saga.placed(simulate="payment_declined")
    with pytest.raises(LambdaDied):
        call(dying_cancel)
    payments.sfn.error = "ThrottlingException"  # the webhook's own SendTaskFailure fails: 500, DemoPay redelivers
    with pytest.raises(Exception, match="ThrottlingException"):
        payments.webhook.on_declined(intent(aws), {"reason": "declined"}, payments.webhook.logger)

    payments.sfn.error = None
    payments.webhook.on_declined(intent(aws), {"reason": "declined"}, payments.webhook.logger)

    assert [c["error"] for _, c in payments.sfn.calls] == ["OrderCancelled", "OrderCancelled"]


def test_a_retried_cancel_answers_the_token_even_after_the_webhook_closed_the_intent(aws, saga, dying_cancel, payments, monkeypatch):
    order = saga.placed()
    with pytest.raises(LambdaDied):
        call(dying_cancel)
    payments.sfn.error = "ThrottlingException"  # suppose the webhook could not answer it either (500 to DemoPay)
    saga.demopay_charges(order)
    assert intent(aws)["status"] in ("FAILED", "REFUNDED") and intent(aws)["cancelled"] is True

    fresh = FakeSfn()
    monkeypatch.setattr(dying_cancel, "sfn", fresh)
    assert call(dying_cancel)[0] == 202  # the customer (or the UI) retries: same answer, and the token is answered

    assert [(kind, c["error"]) for kind, c in fresh.calls] == [("failure", "OrderCancelled")]


def test_payment_manual_with_no_trigger_charges_nothing_and_sends_no_callback(aws, saga, payments):
    order = saga.placed(simulate="payment_manual")

    payments.provider.lambda_handler(sqs_event(psp_request(order, simulate="payment_manual")), None)

    assert ledger(aws) == [] and payments.callbacks == []
    assert intent(aws)["status"] == "REQUESTED"  # left to the saga's 120 s timeout, exactly like payment_timeout
