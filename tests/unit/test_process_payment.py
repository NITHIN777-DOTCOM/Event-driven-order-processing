import pytest

from conftest import seed_order


@pytest.fixture
def handler(load_handler):
    return load_handler("process_payment")


def payment_event(order_id, simulate="none"):
    return {"orderId": order_id, "amount": "5097.00", "currency": "INR", "simulate": simulate}


def load(aws, order_id):
    return aws.orders.get_item(Key={"orderId": order_id})["Item"]


def test_simulate_none_captures_payment(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler(payment_event(order["orderId"]), None)

    assert result["status"] == "CAPTURED"
    assert result["paymentId"].startswith("PAY-")
    saved = load(aws, order["orderId"])
    assert saved["status"] == "PAYMENT_CAPTURED"
    assert saved["paymentId"] == result["paymentId"]
    assert saved["paymentAttempts"] == 1
    assert saved["statusHistory"][-1]["detail"] == f"Payment {result['paymentId']} captured: INR 5097.00 (attempt 1)"


def test_payment_declined_raises_permanent_error(aws, handler):
    order = seed_order(aws.orders, simulate="payment_declined")

    with pytest.raises(handler.PaymentDeclined, match="declined"):
        handler.lambda_handler(payment_event(order["orderId"], "payment_declined"), None)

    assert "paymentId" not in load(aws, order["orderId"])


def test_payment_flaky_fails_twice_then_succeeds(aws, handler):
    order = seed_order(aws.orders, simulate="payment_flaky")
    event = payment_event(order["orderId"], "payment_flaky")

    # Step Functions would retry; here we call the handler 3 times by hand.
    for _ in range(2):
        with pytest.raises(handler.PaymentTransientError):
            handler.lambda_handler(event, None)
    result = handler.lambda_handler(event, None)

    assert result["status"] == "CAPTURED"
    saved = load(aws, order["orderId"])
    assert saved["paymentAttempts"] == 3
    statuses = [h["status"] for h in saved["statusHistory"]]
    assert statuses == ["PENDING", "PAYMENT_RETRY", "PAYMENT_RETRY", "PAYMENT_CAPTURED"]
    assert "Attempt 2 failed" in saved["statusHistory"][2]["detail"]


def test_already_paid_order_is_not_charged_again(aws, handler):
    order = seed_order(aws.orders, paymentId="PAY-existing0001")

    result = handler.lambda_handler(payment_event(order["orderId"]), None)

    assert result == {"paymentId": "PAY-existing0001", "status": "CAPTURED"}
    saved = load(aws, order["orderId"])
    assert "paymentAttempts" not in saved  # not even counted as an attempt
    assert len(saved["statusHistory"]) == 1  # nothing appended


def test_capture_race_returns_the_winning_payment(aws, handler):
    """Two attempts in flight at once: the second capture write is refused by its condition."""
    order = seed_order(aws.orders)
    first = handler.lambda_handler(payment_event(order["orderId"]), None)

    result = handler.save_capture(
        order["orderId"], {"paymentId": "PAY-loser", "status": "CAPTURED"}, "5097.00", "INR", 2, handler.logger
    )

    assert result["paymentId"] == first["paymentId"]
    assert load(aws, order["orderId"])["paymentId"] == first["paymentId"]
