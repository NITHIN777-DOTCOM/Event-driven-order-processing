"""request_payment (waitForTaskToken step): one intent per order, token refreshed only while REQUESTED,
payment_flaky retries, and the request to DemoPay never carries the task token."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from conftest import FakeSfn, seed_intent, seed_order


class RecordingSqs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": f"m-{len(self.sent)}"}


@pytest.fixture
def step(load_handler, monkeypatch):
    handler = load_handler("request_payment")
    monkeypatch.setattr(handler, "sqs", RecordingSqs())
    monkeypatch.setattr(handler, "sfn", FakeSfn())
    return handler


def run(step, order, token="token-1", simulate=None):
    return step.lambda_handler({"orderId": order["orderId"], "taskToken": token, "simulate": simulate or order.get("simulate", "none")}, None)


def intent_of(aws, order):
    return aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]


def test_creates_the_intent_marks_the_order_pending_and_asks_demopay(aws, step):
    order = seed_order(aws.orders)

    result = run(step, order)

    assert result == {"paymentIntentId": f"PI-{order['orderId']}", "status": "REQUESTED"}
    intent = intent_of(aws, order)
    assert intent["status"] == "REQUESTED" and intent["taskToken"] == "token-1" and intent["requestAttempts"] == 1
    assert intent["amount"] == Decimal("5097.00") and intent["walletId"] == order["walletId"]
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "PAYMENT_PENDING" and saved["paymentIntentId"] == intent["paymentIntentId"]
    assert saved["statusHistory"][-1]["detail"].startswith("Awaiting payment confirmation from DemoPay · ₹5,097")
    [message] = step.sqs.sent
    assert 2 <= message["DelaySeconds"] <= 5
    body = json.loads(message["MessageBody"])
    assert body == {"paymentIntentId": f"PI-{order['orderId']}", "orderId": order["orderId"], "walletId": order["walletId"],
                    "amount": "5097.00", "currency": "INR", "simulate": "none"}
    assert "token-1" not in message["MessageBody"]  # the task token never leaves our system


def test_a_retry_refreshes_the_token_on_the_same_intent(aws, step):
    order = seed_order(aws.orders)

    run(step, order, token="token-1")
    run(step, order, token="token-2")

    assert aws.payments.scan()["Count"] == 1  # deterministic id: never a second intent
    intent = intent_of(aws, order)
    assert intent["taskToken"] == "token-2" and intent["requestAttempts"] == 2
    assert intent["requestedAt"] == intent["createdAt"]  # first request time kept


def test_payment_flaky_fails_twice_then_requests_once(aws, step):
    order = seed_order(aws.orders, simulate="payment_flaky")

    for attempt in (1, 2):
        with pytest.raises(step.PaymentTransientError, match=f"attempt {attempt}"):
            run(step, order, token=f"token-{attempt}")
    run(step, order, token="token-3")

    assert len(step.sqs.sent) == 1  # DemoPay was asked once, on the attempt that went through
    assert intent_of(aws, order)["taskToken"] == "token-3"
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert [e["status"] for e in saved["statusHistory"]][-3:] == ["PAYMENT_RETRY", "PAYMENT_RETRY", "PAYMENT_PENDING"]
    assert saved["paymentAttempts"] == 3


def test_payment_late_is_sent_with_a_delay_past_the_timeout(aws, step):
    order = seed_order(aws.orders, simulate="payment_late")

    run(step, order)

    assert step.sqs.sent[0]["DelaySeconds"] == 150 > 120


def test_a_finished_intent_is_never_requested_again_and_its_token_is_not_overwritten(aws, step):
    order = seed_order(aws.orders)
    seed_intent(aws, order, status="SUCCEEDED", token="old-token", paymentId="PAY-done")

    result = run(step, order, token="new-token")

    assert result["status"] == "SUCCEEDED" and step.sqs.sent == []
    assert intent_of(aws, order)["taskToken"] == "old-token"
    [(kind, args)] = step.sfn.calls
    assert kind == "success" and args["taskToken"] == "new-token"
    assert json.loads(args["output"])["paymentId"] == "PAY-done"


@pytest.mark.parametrize(
    "status, extra, cause",
    [("FAILED", {"declineReason": "Card declined"}, "Card declined"), ("TIMED_OUT", {}, "Payment intent already TIMED_OUT")],
)
def test_a_failed_or_timed_out_intent_fails_the_new_token(aws, step, status, extra, cause):
    order = seed_order(aws.orders)
    seed_intent(aws, order, status=status, **extra)

    run(step, order, token="new-token")

    [(kind, args)] = step.sfn.calls
    assert kind == "failure" and args["error"] == "PaymentDeclined" and args["cause"] == cause
