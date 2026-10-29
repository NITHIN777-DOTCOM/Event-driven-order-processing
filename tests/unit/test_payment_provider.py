"""DemoPay (payment_provider): one debit per intent however often a request is delivered, declines, callbacks,
and an idempotent refund API. Callbacks go straight into the webhook handler (see the `payments` fixture)."""

from __future__ import annotations

from decimal import Decimal

from conftest import USER_A, ledger, psp_request, seed_intent, seed_order, sqs_event, wallet_of

AMOUNT = Decimal("5097.00")


def charge(payments, order, simulate="none", receive_count=1, **overrides):
    return payments.provider.lambda_handler(sqs_event(psp_request(order, simulate, **overrides), receive_count=receive_count), None)


def psp_record(aws, kind, order):
    return aws.psp.get_item(Key={"pspTxnId": f"{kind}#PI-{order['orderId']}"}).get("Item")


# --- charges -------------------------------------------------------------------------------------------
def test_charge_debits_once_and_calls_the_webhook(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    assert charge(payments, order) == {"batchItemFailures": []}

    assert ledger(aws) == [("DEBIT", AMOUNT)]
    assert wallet_of(aws, USER_A)[0] == Decimal("1000000") - AMOUNT
    record = psp_record(aws, "CHARGE", order)
    assert record["outcome"] == "SUCCEEDED" and record["paymentId"].startswith("PAY-")
    [callback] = payments.callbacks
    assert callback["status"] == 200 and callback["body"]["type"] == "payment.succeeded"
    assert callback["body"]["paymentId"] == record["paymentId"]
    assert "taskToken" not in callback["body"]  # the provider never sees our task token


def test_redelivered_request_never_debits_twice(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    for receive in (1, 2, 3):
        charge(payments, order, receive_count=receive)

    assert ledger(aws) == [("DEBIT", AMOUNT)]
    ids = {c["body"]["paymentId"] for c in payments.callbacks}
    assert len(ids) == 1  # the same outcome replayed, same paymentId
    assert [c["result"]["result"] for c in payments.callbacks] == ["resumed", "duplicate", "duplicate"]


def test_concurrent_delivery_that_lost_the_race_replays_the_winner(aws, payments, monkeypatch):
    """Two deliveries read "no charge yet" at the same time; the transaction's condition stops the second."""
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    charge(payments, order)  # the "winner"
    real_get = payments.provider.psp_table.get_item
    calls = {"n": 0}

    def stale_first_read(**kwargs):
        calls["n"] += 1
        return {} if calls["n"] == 1 else real_get(**kwargs)  # the loser's first read missed the winner

    monkeypatch.setattr(payments.provider.psp_table, "get_item", stale_first_read)
    charge(payments, order)

    assert ledger(aws) == [("DEBIT", AMOUNT)]


def test_simulated_decline_moves_no_money_and_is_replayed(aws, payments):
    order = seed_order(aws.orders, simulate="payment_declined")
    seed_intent(aws, order)

    charge(payments, order, "payment_declined")
    charge(payments, order, "payment_declined", receive_count=2)

    assert wallet_of(aws, USER_A) == (None, [])
    assert psp_record(aws, "CHARGE", order)["outcome"] == "DECLINED"
    assert [c["body"]["type"] for c in payments.callbacks] == ["payment.declined", "payment.declined"]
    assert payments.callbacks[0]["body"]["reason"] == "Card declined by issuer (simulated)"


def test_low_balance_is_a_real_decline_and_stays_declined_after_a_top_up(aws, payments):
    aws.wallets.put_item(Item={"walletId": USER_A, "balance": Decimal("1000"), "currency": "INR"})
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    charge(payments, order)
    aws.wallets.put_item(Item={"walletId": USER_A, "balance": Decimal("1000000"), "currency": "INR"})
    charge(payments, order, receive_count=2)  # redelivery after the top-up: the decision doesn't change

    assert ledger(aws) == []
    assert "₹1,000 available, ₹5,097 needed" in payments.callbacks[0]["body"]["reason"]
    assert payments.callbacks[1]["body"]["type"] == "payment.declined"


def test_order_without_a_wallet_is_declined(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    charge(payments, order, walletId=None)

    assert payments.callbacks[0]["body"]["type"] == "payment.declined"
    assert "no wallet" in payments.callbacks[0]["body"]["reason"]


def test_payment_timeout_never_calls_back_and_charges_nothing(aws, payments):
    order = seed_order(aws.orders, simulate="payment_timeout")
    seed_intent(aws, order)

    assert charge(payments, order, "payment_timeout") == {"batchItemFailures": []}

    assert payments.callbacks == [] and ledger(aws) == []


def test_webhook_duplicate_sends_the_success_twice_but_debits_once(aws, payments):
    order = seed_order(aws.orders, simulate="webhook_duplicate")
    seed_intent(aws, order)

    charge(payments, order, "webhook_duplicate")

    assert [c["result"]["result"] for c in payments.callbacks] == ["resumed", "duplicate"]
    assert ledger(aws) == [("DEBIT", AMOUNT)]
    assert len(payments.sfn.calls) == 1  # the saga was resumed exactly once


def test_webhook_bad_signature_sends_a_forged_callback_first(aws, payments):
    order = seed_order(aws.orders, simulate="webhook_bad_signature")
    seed_intent(aws, order)

    charge(payments, order, "webhook_bad_signature")

    assert [c["status"] for c in payments.callbacks] == [401, 200]
    assert aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]["status"] == "SUCCEEDED"


def test_rejected_callback_fails_the_message_so_sqs_redelivers(aws, payments, monkeypatch):
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    monkeypatch.setattr(payments.provider, "post_callback", lambda body, secret: 503)

    result = charge(payments, order)

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-0"}]}
    assert ledger(aws) == [("DEBIT", AMOUNT)]  # the debit stands; the redelivery will only re-send the callback


# --- refunds -------------------------------------------------------------------------------------------
def test_refund_credits_exactly_once(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    charge(payments, order)

    first = payments.provider.lambda_handler({"operation": "refund", "paymentIntentId": f"PI-{order['orderId']}"}, None)
    second = payments.provider.lambda_handler({"operation": "refund", "paymentIntentId": f"PI-{order['orderId']}"}, None)

    assert first["refunded"] is True and first["refundId"].startswith("RF-")
    assert second == {**first, "refunded": False, "alreadyRefunded": True}
    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]
    assert wallet_of(aws, USER_A)[0] == Decimal("1000000")


def test_refund_before_any_charge_or_after_a_decline_is_a_no_op(aws, payments):
    order = seed_order(aws.orders)

    assert payments.provider.refund(f"PI-{order['orderId']}") == {"refunded": False, "reason": "nothing charged"}
    seed_intent(aws, order)
    charge(payments, order, "payment_declined")
    assert payments.provider.refund(f"PI-{order['orderId']}")["refunded"] is False
    assert ledger(aws) == []


def test_ledger_entries_carry_the_intent_id(aws, payments):
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    charge(payments, order)
    payments.provider.refund(f"PI-{order['orderId']}")

    items = aws.wallet_txns.query(KeyConditionExpression="walletId = :w", ExpressionAttributeValues={":w": USER_A})["Items"]
    assert {t["paymentIntentId"] for t in items} == {f"PI-{order['orderId']}"}
    assert {t["orderId"] for t in items} == {order["orderId"]}
