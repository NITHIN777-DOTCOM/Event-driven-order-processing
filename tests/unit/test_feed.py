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


def test_wallet_debit_refund_and_insufficient_balance_rows():
    rows = feed(
        entry("PAYMENT_CAPTURED", "₹7,597 debited from DemoPay · balance ₹9,92,403 (attempt 3)"),
        entry("PAYMENT_REFUNDED", "₹7,597 refunded to DemoPay · balance ₹10,00,000"),
        entry("PAYMENT_DECLINED", "Attempt 1: Insufficient wallet balance: ₹1,000 available, ₹3,499 needed"),
    )

    assert (rows[0]["message"], rows[0]["note"]) == ("₹7,597 debited from DemoPay · balance ₹9,92,403", "attempt 3")
    assert rows[1]["message"] == "₹7,597 refunded to wallet · balance ₹10,00,000"
    assert (rows[2]["message"], rows[2]["level"]) == ("Declined: not enough DemoPay balance (₹1,000 available)", "error")


def test_indian_rupee_formatting():
    from common.money import format_inr

    assert format_inr(992403) == "₹9,92,403"
    assert format_inr("1000000") == "₹10,00,000"
    assert format_inr("1234.5") == "₹1,234.50"
    assert format_inr(799) == "₹799"
    assert format_inr(-3499) == "-₹3,499"


def test_async_payment_rows():
    rows = feed(
        entry("PAYMENT_PENDING", "Awaiting payment confirmation from DemoPay · ₹5,097 · intent PI-ORD-1"),
        entry("PAYMENT_CAPTURED", "₹5,097 captured by DemoPay · PAY-abc (confirmed by webhook)"),
    )

    assert [(r["service"], r["message"]) for r in rows] == [
        ("Lambda · payment", "Payment requested from DemoPay, awaiting confirmation (saga paused until the webhook)"),
        ("Webhook · DemoPay", "₹5,097 captured by DemoPay · PAY-abc"),
    ]


def test_payment_timeout_reason():
    rows = feed(entry("FAILED", "x"), failureReason="PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s")

    assert rows[0]["message"] == "Order marked FAILED: payment timeout - DemoPay did not confirm the payment within 120 s"


def test_per_item_fulfillment_rows():
    rows = feed(
        entry("ITEM_FULFILLED", "Picked and packed 2 x Desk Mat (line L1)"),
        entry("LINE_REFUNDED", "₹3,499 refunded to DemoPay for 1 x Mechanical Keyboard (line L2)"),
        entry("ITEM_WRITTEN_OFF", "1 x Mechanical Keyboard (line L2) written off: found damaged"),
        entry("PARTIALLY_FULFILLED", "1 of 2 items delivered - INR 3499.00 refunded for the unavailable items"),
    )

    assert [(r["service"], r["message"], r["level"]) for r in rows] == [
        ("Lambda · fulfillment", "Packed 2 x Desk Mat (line L1)", "info"),
        ("Lambda · payment", "₹3,499 refunded to wallet for 1 x Mechanical Keyboard (line L2)", "retry"),
        ("Lambda · fulfillment", "Unavailable: 1 x Mechanical Keyboard (line L2) written off: found damaged", "error"),
        ("DynamoDB", "Order marked PARTIALLY_FULFILLED: 1 of 2 items delivered - INR 3499.00 refunded for the unavailable items", "retry"),
        ("SNS", "Partial delivery email sent", "info"),
    ]


def test_write_off_row_names_the_item_once():
    detail = "1 x Desk Mat (line L2) written off: Desk Mat (line L2) was found damaged in the warehouse (simulated)"

    assert feed(entry("ITEM_WRITTEN_OFF", detail))[0]["message"] == (
        "Unavailable: 1 x Desk Mat (line L2) written off: found damaged in the warehouse (simulated)"
    )


def test_cancellation_rows():
    rows = feed(
        entry("FULFILLING", "Fulfillment started"),
        entry("CANCEL_REQUESTED", "Cancellation requested by the customer: changed my mind"),
        entry("CANCEL_REJECTED", "Cancel request rejected: the order was already FULFILLING"),
        entry("CANCELLED", "Cancelled by the customer - INR 5097.00 refunded to the DemoPay wallet"),
    )

    assert [(r["service"], r["message"], r["level"]) for r in rows] == [
        ("Lambda · fulfillment", "Fulfillment started: the order can no longer be cancelled", "info"),
        ("API Gateway", "Cancellation requested by the customer: changed my mind", "retry"),
        ("API Gateway", "Cancel rejected (too late): the order was already FULFILLING", "error"),
        ("DynamoDB", "Order marked CANCELLED: ₹5,097 refunded to the DemoPay wallet", "retry"),
        ("SNS", "Cancellation email sent", "info"),
    ]


def test_cancelled_with_nothing_charged():
    rows = feed(entry("CANCELLED", "Cancelled by the customer - nothing was charged"))

    assert rows[0]["message"] == "Order marked CANCELLED: nothing was charged"
