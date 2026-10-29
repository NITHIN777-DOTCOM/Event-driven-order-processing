"""POST /webhooks/payment: signature checks, idempotency, resuming the saga, and the late-callback refund."""

from __future__ import annotations

import json
import time
from decimal import Decimal

import pytest

from conftest import USER_A, ledger, psp_request, seed_intent, seed_order, sqs_event, webhook_event

AMOUNT = Decimal("5097.00")


def callback(order, kind="payment.succeeded", **overrides) -> dict:
    body = {
        "eventId": "evt_test",
        "type": kind,
        "paymentIntentId": f"PI-{order['orderId']}",
        "orderId": order["orderId"],
        "paymentId": "PAY-test0000001",
        "amount": str(order["totalAmount"]),
        "currency": "INR",
    }
    if kind == "payment.declined":
        body["reason"] = "Card declined by issuer (simulated)"
    return {**body, **overrides}


def call(payments, event):
    result = payments.webhook.lambda_handler(event, None)
    return result["statusCode"], json.loads(result["body"])


def intent_of(aws, order):
    return aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]


def order_of(aws, order):
    return aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]


def charge_for_real(payments, order):
    """Make DemoPay actually take the money (without delivering its callback), like a callback still in flight."""
    payments.provider.charge_once(psp_request(order), "none", payments.provider.logger)


# --- authentication: the HMAC signature -----------------------------------------------------------------
@pytest.mark.parametrize(
    "make_event",
    [
        pytest.param(lambda body: webhook_event(body, headers={}), id="unsigned"),
        pytest.param(lambda body: webhook_event(body, secret="attacker-guess"), id="forged"),
        pytest.param(lambda body: webhook_event(body, timestamp=time.time() - 600), id="stale"),
        pytest.param(lambda body: webhook_event(body, timestamp=time.time() + 600), id="future"),
        pytest.param(lambda body: webhook_event(body, headers={"x-timestamp": str(int(time.time()))}), id="no-signature"),
    ],
)
def test_requests_without_a_valid_signature_get_401_and_change_nothing(aws, payments, capsys, make_event):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    status, body = call(payments, make_event(callback(order)))

    assert status == 401 and body == {"error": "invalid or missing signature"}
    assert intent_of(aws, order)["status"] == "REQUESTED" and payments.sfn.calls == []
    logged = capsys.readouterr().out
    assert '"event": "webhook_signature_rejected"' in logged  # feeds the WebhookSignatureFailures metric
    assert "test-webhook-secret" not in logged


def test_tampered_body_is_rejected(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    event = webhook_event(callback(order))
    event["body"] = event["body"].replace("5097.00", "1.00")

    assert call(payments, event)[0] == 401


def test_base64_encoded_bodies_are_verified_on_their_raw_bytes(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    assert call(payments, webhook_event(callback(order), base64_body=True))[0] == 200


def test_signed_callback_for_an_unknown_intent_is_a_404_no_op(aws, payments):
    order = seed_order(aws.orders)  # no intent

    status, body = call(payments, webhook_event(callback(order)))

    assert status == 404 and "unknown payment intent" in body["error"]
    assert payments.sfn.calls == [] and aws.payments.scan()["Count"] == 0


@pytest.mark.parametrize(
    "overrides",
    [{"amount": "1.00"}, {"orderId": "ORD-20261022-00000000"}],
    ids=["wrong amount", "wrong order"],
)
def test_callback_that_does_not_match_the_intent_is_rejected(aws, payments, overrides):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    assert call(payments, webhook_event(callback(order, **overrides)))[0] == 400
    assert intent_of(aws, order)["status"] == "REQUESTED"


@pytest.mark.parametrize(
    "raw, error",
    [(b"not json", "not JSON"), (b'{"type":"refund.created"}', "type must be"), (b'{"type":"payment.succeeded"}', "paymentIntentId"),
     (b'{"type":"payment.succeeded","paymentIntentId":"PI-x","amount":"abc"}', "amount")],
)
def test_signed_but_malformed_bodies_get_400(aws, payments, raw, error):
    status, body = call(payments, webhook_event(raw))
    assert status == 400 and error in body["error"]


# --- success / decline: record once, resume the saga once --------------------------------------------------
def test_success_captures_and_resumes_the_saga_with_the_stored_token(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order, token="token-from-attempt-3")

    status, body = call(payments, webhook_event(callback(order)))

    assert status == 200 and body["result"] == "resumed"
    [(kind, args)] = payments.sfn.calls
    assert kind == "success" and args["taskToken"] == "token-from-attempt-3"
    assert json.loads(args["output"]) == {"paymentIntentId": f"PI-{order['orderId']}", "paymentId": "PAY-test0000001", "status": "SUCCEEDED"}
    intent = intent_of(aws, order)
    assert intent["status"] == "SUCCEEDED" and intent["sagaResumedAt"]
    saved = order_of(aws, order)
    assert saved["status"] == "PAYMENT_CAPTURED" and saved["paymentId"] == "PAY-test0000001" and saved["paidAmount"] == AMOUNT


def test_duplicate_success_is_a_200_no_op(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    call(payments, webhook_event(callback(order)))
    status, body = call(payments, webhook_event(callback(order, eventId="evt_again")))

    assert status == 200 and body["result"] == "duplicate"
    assert len(payments.sfn.calls) == 1
    assert [e["status"] for e in order_of(aws, order)["statusHistory"]].count("PAYMENT_CAPTURED") == 1


def test_success_whose_resume_was_lost_is_resumed_on_the_retry(aws, payments):
    """Captured, but SendTaskSuccess failed with a transient error: the provider's retry only resumes."""
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    payments.sfn.error = "ServiceUnavailable"
    with pytest.raises(Exception):
        call(payments, webhook_event(callback(order)))  # -> 500 in Lambda; DemoPay will retry

    payments.sfn.error = None
    status, body = call(payments, webhook_event(callback(order)))

    assert (status, body["result"]) == (200, "resumed")
    assert [k for k, _ in payments.sfn.calls] == ["success", "success"]


def test_decline_fails_the_task_with_payment_declined(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    status, body = call(payments, webhook_event(callback(order, "payment.declined")))

    assert (status, body["result"]) == (200, "resumed")
    [(kind, args)] = payments.sfn.calls
    assert kind == "failure" and args["error"] == "PaymentDeclined" and "declined" in args["cause"]
    assert intent_of(aws, order)["status"] == "FAILED"
    assert order_of(aws, order)["status"] == "PAYMENT_DECLINED"
    # A duplicate decline: nothing more.
    assert call(payments, webhook_event(callback(order, "payment.declined")))[1]["result"] == "duplicate"
    assert len(payments.sfn.calls) == 1


def test_decline_for_an_intent_that_already_left_requested_does_nothing(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order, status="TIMED_OUT")

    assert call(payments, webhook_event(callback(order, "payment.declined")))[1]["result"] == "duplicate"
    assert payments.sfn.calls == [] and intent_of(aws, order)["status"] == "TIMED_OUT"


# --- the late callback ----------------------------------------------------------------------------------
@pytest.mark.parametrize("gave_up_as", ["TIMED_OUT", "FAILED"])
def test_late_success_after_the_saga_gave_up_is_refunded_automatically(aws, payments, gave_up_as):
    order = seed_order(aws.orders, status="FAILED")
    seed_intent(aws, order, status=gave_up_as)
    charge_for_real(payments, order)

    status, body = call(payments, webhook_event(callback(order)))

    assert (status, body["result"]) == (200, "late-refunded")
    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]  # net charge 0 (invariant I2)
    assert payments.sfn.calls == []  # nobody to resume
    intent = intent_of(aws, order)
    assert intent["status"] == "REFUNDED" and intent["refundId"].startswith("RF-")
    saved = order_of(aws, order)
    assert saved["status"] == "FAILED"  # a terminal status stays terminal
    assert saved["statusHistory"][-1]["status"] == "PAYMENT_REFUNDED" and saved["refunded"] is True

    # The same late callback again: no second refund (invariant I3).
    assert call(payments, webhook_event(callback(order)))[1]["result"] == "duplicate"
    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]


def test_success_racing_the_timeout_never_refunds_from_the_webhook(aws, payments):
    """Captured just before the timeout; SendTaskSuccess then says TaskTimedOut. The saga's compensation
    (which sees SUCCEEDED) owns the refund, so the webhook must not refund as well."""
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    charge_for_real(payments, order)
    payments.sfn.error = "TaskTimedOut"

    status, body = call(payments, webhook_event(callback(order)))

    assert (status, body["result"]) == (200, "saga-not-waiting")
    assert ledger(aws) == [("DEBIT", AMOUNT)]
    intent = intent_of(aws, order)
    assert intent["status"] == "SUCCEEDED" and intent["sagaResumeResult"] == "task closed (TaskTimedOut)"


def test_end_to_end_provider_to_webhook_in_process(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    payments.provider.lambda_handler(sqs_event(psp_request(order)), None)

    assert intent_of(aws, order)["status"] == "SUCCEEDED"
    assert ledger(aws, USER_A) == [("DEBIT", AMOUNT)]
    assert [k for k, _ in payments.sfn.calls] == ["success"]
