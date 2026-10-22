import pytest

from conftest import seed_order


@pytest.fixture
def handler(load_handler):
    return load_handler("reserve_inventory")


def stock_of(aws, product_id):
    item = aws.inventory.get_item(Key={"productId": product_id})["Item"]
    return item["stock"], item["reserved"]


def test_reserves_every_item_and_marks_order_reserved(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler({"orderId": order["orderId"]}, None)

    assert stock_of(aws, "WIRELESS-MOUSE") == (98, 2)
    assert stock_of(aws, "MECH-KEYBOARD") == (1, 1)
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "RESERVED"
    assert [h["status"] for h in saved["statusHistory"]] == ["PENDING", "RESERVED"]
    assert result["totalAmount"] == "5097.00"
    assert "2 x Wireless Mouse @ INR 799.00" in result["itemsSummary"]


def test_insufficient_stock_raises_and_changes_nothing(aws, handler):
    # The keyboard has stock 2; asking for 3 must fail the WHOLE transaction.
    order = seed_order(
        aws.orders,
        items=[
            {"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "quantity": 1, "unitPrice": 799},
            {"productId": "MECH-KEYBOARD", "name": "Mechanical Keyboard", "quantity": 3, "unitPrice": 3499},
        ],
    )

    with pytest.raises(handler.OutOfStock):
        handler.lambda_handler({"orderId": order["orderId"]}, None)

    assert stock_of(aws, "WIRELESS-MOUSE") == (100, 0)  # not partially reserved
    assert stock_of(aws, "MECH-KEYBOARD") == (2, 0)
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "PENDING"
