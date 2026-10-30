"""refund_payment (saga compensation) through DemoPay's refund API: idempotent, finishes REQUESTED intents,
and shares the refund with the webhook's late-callback path without ever refunding twice."""

from __future__ import annotations

import io
import json
from decimal import Decimal

import pytest

from common.payments import invoke_provider_refund, provider_delay_seconds
from conftest import USER_A, ledger, psp_request, seed_intent, seed_order, sqs_event, wallet_of, webhook_event

AMOUNT = Decimal("5097.00")


@pytest.fixture
def refund(load_handler, payments, monkeypatch):
    handler = load_handler("refund_payment")
    monkeypatch.setattr(handler, "invoke_provider_refund", lambda _client, _fn, intent_id, note="": payments.provider.refund(intent_id, note))
    return handler


def compensate(refund, order):
    return refund.lambda_handler({"orderId": order["orderId"]}, None)


def intent_of(aws, order):
    return aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]


def history(aws, order):
    return [e["status"] for e in aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]["statusHistory"]]


def test_no_intent_means_nothing_to_refund(aws, refund):
    order = seed_order(aws.orders)

    assert compensate(refund, order) == {"orderId": order["orderId"], "refunded": False, "refundedAmount": "0.00", "reason": "no payment requested"}


def test_a_paid_order_is_refunded_exactly_once(aws, payments, refund):
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    payments.provider.lambda_handler(sqs_event(psp_request(order)), None)  # charged + webhook: SUCCEEDED

    first = compensate(refund, order)
    second = compensate(refund, order)

    assert first["refunded"] is True and first["refundId"].startswith("RF-")
    assert second["refunded"] is False and second["refundId"] == first["refundId"]
    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]
    assert wallet_of(aws, USER_A)[0] == Decimal("1000000")
    assert intent_of(aws, order)["status"] == "REFUNDED"
    assert history(aws, order).count("PAYMENT_REFUNDED") == 1


def test_a_declined_payment_has_nothing_to_refund(aws, payments, refund):
    order = seed_order(aws.orders, simulate="payment_declined")
    seed_intent(aws, order)
    payments.provider.lambda_handler(sqs_event(psp_request(order, "payment_declined")), None)

    result = compensate(refund, order)

    assert result["refunded"] is False and result["reason"] == "nothing charged"
    assert intent_of(aws, order)["status"] == "FAILED" and ledger(aws) == []


def test_a_requested_intent_is_abandoned_and_a_later_charge_is_refunded_by_the_webhook(aws, payments, refund):
    order = seed_order(aws.orders)
    seed_intent(aws, order)

    compensate(refund, order)  # the saga gives up before DemoPay answered
    assert intent_of(aws, order)["status"] == "FAILED"

    payments.provider.lambda_handler(sqs_event(psp_request(order)), None)  # DemoPay charges anyway, calls back

    assert payments.callbacks[-1]["result"]["result"] == "late-refunded"
    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]  # I2: net 0
    assert intent_of(aws, order)["status"] == "REFUNDED"


def test_timeout_race_compensation_refunds_a_payment_captured_just_before(aws, payments, refund):
    """The webhook captured (SUCCEEDED) a moment before the timeout; SendTaskSuccess was too late. The saga's
    MarkPaymentTimedOut condition failed, and RefundPayment must refund the capture."""
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    payments.sfn.error = "TaskTimedOut"
    payments.provider.lambda_handler(sqs_event(psp_request(order)), None)
    assert intent_of(aws, order)["status"] == "SUCCEEDED" and ledger(aws) == [("DEBIT", AMOUNT)]

    compensate(refund, order)

    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]
    assert intent_of(aws, order)["status"] == "REFUNDED"


def test_saga_refund_and_late_callback_refund_never_double_refund(aws, payments, refund):
    order = seed_order(aws.orders, status="FAILED")
    seed_intent(aws, order, status="TIMED_OUT")
    payments.provider.charge_once(psp_request(order), "none", payments.provider.logger)  # charged, callback in flight

    compensate(refund, order)  # the saga's compensation finds the charge first
    body = {"type": "payment.succeeded", "paymentIntentId": f"PI-{order['orderId']}", "orderId": order["orderId"],
            "paymentId": "PAY-x", "amount": "5097.00"}
    result = payments.webhook.lambda_handler(webhook_event(body), None)  # then the late callback arrives

    assert json.loads(result["body"])["result"] == "duplicate"
    assert ledger(aws) == [("DEBIT", AMOUNT), ("CREDIT", AMOUNT)]  # I3: one refund


# --- the provider client helpers in common/payments.py ----------------------------------------------------
class FakeLambda:
    def __init__(self, payload: dict, error: bool = False) -> None:
        self.payload, self.error, self.calls = payload, error, []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        out = {"Payload": io.BytesIO(json.dumps(self.payload).encode())}
        if self.error:
            out["FunctionError"] = "Unhandled"
        return out


def test_invoke_provider_refund_calls_the_refund_operation():
    client = FakeLambda({"refunded": True, "refundId": "RF-1"})

    assert invoke_provider_refund(client, "order-saga-payment-provider", "PI-ORD-1") == {"refunded": True, "refundId": "RF-1"}
    assert json.loads(client.calls[0]["Payload"]) == {"operation": "refund", "paymentIntentId": "PI-ORD-1"}
    assert client.calls[0]["InvocationType"] == "RequestResponse"


def test_invoke_provider_refund_raises_on_a_provider_error():
    with pytest.raises(RuntimeError, match="DemoPay refund failed: boom"):
        invoke_provider_refund(FakeLambda({"errorMessage": "boom"}, error=True), "fn", "PI-ORD-1")


def test_provider_delay():
    assert provider_delay_seconds("payment_late") == 150
    assert all(2 <= provider_delay_seconds("none") <= 5 for _ in range(50))
