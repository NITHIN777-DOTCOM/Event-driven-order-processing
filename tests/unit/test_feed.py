"""The tracker's live feed: statusHistory -> plain-English rows."""

import sys

from conftest import SRC  # noqa: F401  (puts src/ on sys.path)

assert str(SRC) in sys.path
from common.feed import build_feed, console_links  # noqa: E402


def entry(status, detail="", timestamp="2026-10-22T10:00:00.000Z"):
    return {"status": status, "detail": detail, "timestamp": timestamp}


def feed(*entries, **order):
    return build_feed({"orderId": "ORD-20261022-abcdef12", "statusHistory": list(entries), **order})


def test_happy_path_feed():
    rows = feed(
        entry("PENDING", "Order received via API"),
        entry("PROCESSING", "Saga workflow started"),
        entry("RESERVED", "Reserved stock for 2 product(s)"),
        entry("PAYMENT_CAPTURED", "Payment PAY-1 captured: INR 10.00 (attempt 1)"),
        entry("COMPLETED", "Order fulfilled"),
    )

    assert [(r["service"], r["message"]) for r in rows] == [
        ("API Gateway", "Order received and queued for processing"),
        ("SQS → Step Functions", "Picked up from the queue, saga workflow started"),
        ("Lambda · inventory", "Stock reserved for 2 products"),
        ("Lambda · payment", "Payment captured"),
        ("DynamoDB", "Order marked COMPLETED"),
        ("SNS", "Confirmation email sent"),
    ]
    assert {r["level"] for r in rows} == {"info"}


def test_payment_retries_show_backoff_and_attempt():
    rows = feed(
        entry("PAYMENT_RETRY", "Attempt 1 failed: timeout - retrying"),
        entry("PAYMENT_RETRY", "Attempt 2 failed: timeout - retrying"),
        entry("PAYMENT_CAPTURED", "Payment PAY-1 captured: INR 10.00 (attempt 3)"),
    )

    assert rows[0] == {
        "time": "2026-10-22T10:00:00.000Z",
        "service": "Step Functions",
        "message": "Payment glitch, retrying in 2s",
        "level": "retry",
        "note": "attempt 1",
    }
    assert rows[1]["message"] == "Payment glitch, retrying in 4s"  # exponential backoff (x2)
    assert rows[2]["message"] == "Payment captured on attempt 3"


def test_compensation_and_failure_rows():
    rows = feed(
        entry("PAYMENT_DECLINED", "Attempt 1: Card declined"),
        entry("INVENTORY_RELEASED", "Compensation: released stock for 1 product(s)"),
        entry("FAILED", "PaymentDeclined: Card declined by issuer (simulated)"),
        failureReason="PaymentDeclined: Card declined by issuer (simulated)",
    )

    assert [(r["message"], r["level"]) for r in rows] == [
        ("Payment declined by the card issuer", "error"),
        ("Stock released back to inventory", "info"),
        ("Order marked FAILED: Card declined by issuer (simulated)", "error"),
        ("Failure email sent", "info"),
    ]


def test_out_of_stock_and_dead_letter_rows():
    rows = feed(
        entry("OUT_OF_STOCK", "Insufficient stock for: 4K-MONITOR (simulated)"),
        entry("DELIVERY_RETRY", "Delivery attempt 1 of 3 failed; SQS will retry"),
        entry("DEAD_LETTERED", "Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue"),
        entry("SOMETHING_NEW", "custom detail"),
    )

    assert rows[0]["message"] == "Out of stock: 4K-MONITOR (simulated)"
    assert (rows[1]["level"], rows[1]["note"]) == ("retry", "attempt 1")
    assert (rows[2]["message"], rows[2]["level"]) == ("Moved to dead-letter queue after 3 attempts", "error")
    assert rows[3]["message"] == "custom detail"  # unknown events still show up


def test_console_links():
    order = {
        "orderId": "ORD-20261022-abcdef12",
        "executionArn": "arn:aws:states:ap-south-1:1:execution:wf:ORD-20261022-abcdef12",
    }

    links = console_links(order, "ap-south-1", "order-saga-orders", "/aws/vendedlogs/states/wf")

    assert links["execution"].endswith("#/v2/executions/details/" + order["executionArn"])
    assert "table=order-saga-orders" in links["dynamodbItem"] and "pk=ORD-20261022-abcdef12" in links["dynamodbItem"]
    assert "log-group/$252Faws$252Fvendedlogs$252Fstates$252Fwf/log-events" in links["logs"]
    assert links["logs"].endswith("$3FfilterPattern$3D$2522ORD-20261022-abcdef12$2522")
    assert console_links({"orderId": "ORD-1"}, "ap-south-1", "t", "/g")["execution"] is None
