import pytest

from conftest import seed_order


@pytest.fixture
def handler(load_handler):
    return load_handler("process_payment")


def test_simulate_none_captures_payment(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler(
        {"orderId": order["orderId"], "amount": "5097.00", "currency": "INR", "simulate": "none"}, None
    )

    assert result["status"] == "CAPTURED"
    assert result["paymentId"].startswith("PAY-")
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "PAYMENT_CAPTURED"
    assert saved["paymentId"] == result["paymentId"]
    assert saved["statusHistory"][-1]["detail"] == f"Payment {result['paymentId']} captured: INR 5097.00"
