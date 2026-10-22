"""GET /products and GET /orders."""

import json

import pytest

from conftest import seed_order


@pytest.fixture
def products(load_handler):
    return load_handler("list_products")


@pytest.fixture
def orders(load_handler):
    return load_handler("list_orders")


def test_products_sorted_by_price_with_stock(aws, products):
    result = products.lambda_handler({}, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])["products"]
    assert [p["productId"] for p in body] == ["WIRELESS-MOUSE", "MECH-KEYBOARD"]  # 799 < 3499
    assert body[0] == {"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "price": 799, "stock": 100, "imageKey": None}


def test_orders_newest_first_with_limit(aws, orders):
    for index, created in enumerate(["2026-10-22T10:00:00.000Z", "2026-10-22T12:00:00.000Z", "2026-10-22T11:00:00.000Z"]):
        seed_order(aws.orders, orderId=f"ORD-20261022-0000000{index}", createdAt=created, gsi1pk="ORDER", gsi1sk=created)
    seed_order(aws.orders, orderId="ORD-20261022-0000000x")  # no GSI keys -> not listed

    result = orders.lambda_handler({"queryStringParameters": {"limit": "2"}}, None)

    body = json.loads(result["body"])["orders"]
    assert [o["orderId"] for o in body] == ["ORD-20261022-00000001", "ORD-20261022-00000002"]
    assert set(body[0]) == {
        "orderId", "createdAt", "status", "simulate", "totalAmount", "currency", "customerName", "deadLettered",
    }


@pytest.mark.parametrize("raw, expected", [(None, 20), ("5", 5), ("0", 1), ("999", 50), ("abc", 20)])
def test_limit_is_clamped(orders, raw, expected):
    event = {"queryStringParameters": {"limit": raw} if raw is not None else None}
    assert orders.parse_limit(event) == expected


def test_get_order_includes_feed_and_links_and_hides_internals(aws, load_handler):
    handler = load_handler("get_order")
    order = seed_order(aws.orders, gsi1pk="ORDER", gsi1sk="x", idempotencyKey="k", executionArn="arn:exec")

    body = json.loads(handler.lambda_handler({"pathParameters": {"id": order["orderId"]}}, None)["body"])

    assert body["feed"][0]["service"] == "API Gateway"
    assert body["consoleLinks"]["execution"].endswith("arn:exec")
    assert not {"gsi1pk", "gsi1sk", "idempotencyKey"} & set(body)
