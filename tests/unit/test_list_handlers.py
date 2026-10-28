"""GET /products and GET /orders."""

import json

import pytest

from conftest import EMAIL_B, USER_A, USER_B, api_event, jwt_claims, seed_order


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
    assert {k: body[0][k] for k in ("productId", "name", "price", "stock")} == {
        "productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "price": 799, "stock": 100,
    }
    assert set(body[0]) >= {"category", "mrp", "rating", "ratingCount", "highlights", "description", "imageKey"}


def seed_user_order(aws, user, order_id, created):
    return seed_order(
        aws.orders, orderId=order_id, userId=user, walletId=user, createdAt=created,
        gsi1pk=f"USER#{user}", gsi1sk=f"{created}#{order_id}",
    )


def test_orders_newest_first_with_limit(aws, orders):
    for index, created in enumerate(["2026-10-22T10:00:00.000Z", "2026-10-22T12:00:00.000Z", "2026-10-22T11:00:00.000Z"]):
        seed_user_order(aws, USER_A, f"ORD-20261022-0000000{index}", created)
    seed_order(aws.orders, orderId="ORD-20261022-0000000x")  # no GSI keys -> not listed

    result = orders.lambda_handler(api_event(query={"limit": "2"}), None)

    body = json.loads(result["body"])["orders"]
    assert [o["orderId"] for o in body] == ["ORD-20261022-00000001", "ORD-20261022-00000002"]
    assert set(body[0]) == {
        "orderId", "createdAt", "status", "simulate", "totalAmount", "currency", "customerName", "deadLettered",
    }


def test_orders_lists_only_the_callers_orders(aws, orders):
    seed_user_order(aws, USER_A, "ORD-20261022-aaaaaaa1", "2026-10-22T10:00:00.000Z")
    seed_user_order(aws, USER_B, "ORD-20261022-bbbbbbb1", "2026-10-22T11:00:00.000Z")
    seed_user_order(aws, USER_B, "ORD-20261022-bbbbbbb2", "2026-10-22T12:00:00.000Z")
    seed_order(aws.orders, orderId="ORD-20261022-1e9ac702", gsi1pk="ORDER", gsi1sk="2026-10-22T13:00:00.000Z")  # legacy

    as_a = json.loads(orders.lambda_handler(api_event(), None)["body"])["orders"]
    as_b = json.loads(orders.lambda_handler(api_event(claims=jwt_claims(USER_B, EMAIL_B)), None)["body"])["orders"]

    assert [o["orderId"] for o in as_a] == ["ORD-20261022-aaaaaaa1"]
    assert [o["orderId"] for o in as_b] == ["ORD-20261022-bbbbbbb2", "ORD-20261022-bbbbbbb1"]


def test_orders_without_identity_is_401(aws, orders):
    assert orders.lambda_handler(api_event(claims=None), None)["statusCode"] == 401


@pytest.mark.parametrize("raw, expected", [(None, 20), ("5", 5), ("0", 1), ("999", 50), ("abc", 20)])
def test_limit_is_clamped(orders, raw, expected):
    event = {"queryStringParameters": {"limit": raw} if raw is not None else None}
    assert orders.parse_limit(event) == expected


def test_get_order_includes_feed_and_links_and_hides_internals(aws, load_handler):
    handler = load_handler("get_order")
    order = seed_order(aws.orders, gsi1pk="USER#x", gsi1sk="x", idempotencyKey="k", executionArn="arn:exec")

    body = json.loads(handler.lambda_handler(api_event(path_parameters={"id": order["orderId"]}), None)["body"])

    assert body["feed"][0]["service"] == "API Gateway"
    assert body["consoleLinks"]["execution"].endswith("arn:exec")
    assert not {"gsi1pk", "gsi1sk", "idempotencyKey", "userId", "walletId"} & set(body)
