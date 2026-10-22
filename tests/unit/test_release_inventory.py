import pytest

from conftest import seed_order, stock_of


@pytest.fixture
def reserve(load_handler):
    return load_handler("reserve_inventory")


@pytest.fixture
def handler(load_handler):
    return load_handler("release_inventory")


def test_release_returns_reserved_stock_and_marks_order(aws, reserve, handler):
    order = seed_order(aws.orders)
    reserve.lambda_handler({"orderId": order["orderId"]}, None)
    assert stock_of(aws, "WIRELESS-MOUSE") == (98, 2)

    result = handler.lambda_handler({"orderId": order["orderId"]}, None)

    assert result["released"] is True
    assert stock_of(aws, "WIRELESS-MOUSE") == (100, 0)
    assert stock_of(aws, "MECH-KEYBOARD") == (2, 0)
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["released"] is True
    assert saved["statusHistory"][-1]["status"] == "INVENTORY_RELEASED"


def test_second_release_is_a_no_op(aws, reserve, handler):
    order = seed_order(aws.orders)
    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    handler.lambda_handler({"orderId": order["orderId"]}, None)
    second = handler.lambda_handler({"orderId": order["orderId"]}, None)

    assert second == {"orderId": order["orderId"], "released": False, "reason": "already released"}
    assert stock_of(aws, "WIRELESS-MOUSE") == (100, 0)  # not 102
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert [h["status"] for h in saved["statusHistory"]].count("INVENTORY_RELEASED") == 1


def test_concurrent_release_loses_race_gracefully(aws, reserve, handler):
    """If another run released between our read and our write, the transaction condition stops us."""
    order = seed_order(aws.orders)
    reserve.lambda_handler({"orderId": order["orderId"]}, None)
    reserved_items = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]["reservedItems"]
    handler.lambda_handler({"orderId": order["orderId"]}, None)

    assert handler.release(order["orderId"], reserved_items) is False
    assert stock_of(aws, "WIRELESS-MOUSE") == (100, 0)


def test_nothing_reserved_means_nothing_released(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler({"orderId": order["orderId"]}, None)

    assert result["released"] is False
    assert stock_of(aws, "WIRELESS-MOUSE") == (100, 0)
