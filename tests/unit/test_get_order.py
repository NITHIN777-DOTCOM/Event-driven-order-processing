import json

import pytest

from conftest import EMAIL_B, USER_B, api_event, jwt_claims, seed_order


@pytest.fixture
def handler(load_handler):
    return load_handler("get_order")


def test_existing_order_is_returned_with_history(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler(api_event(path_parameters={"id": order["orderId"]}), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["orderId"] == order["orderId"]
    assert body["totalAmount"] == 5097  # Decimal serialised as a JSON number
    assert body["statusHistory"][0]["status"] == "PENDING"


def test_missing_order_returns_404(aws, handler):
    result = handler.lambda_handler(api_event(path_parameters={"id": "ORD-20261022-00000000"}), None)

    assert result["statusCode"] == 404


def test_another_users_order_is_404_exactly_like_a_missing_one(aws, handler):
    """Not 403: the answer must not reveal that the orderId exists."""
    order = seed_order(aws.orders)  # owned by user A
    as_b = jwt_claims(USER_B, EMAIL_B)

    other = handler.lambda_handler(api_event(path_parameters={"id": order["orderId"]}, claims=as_b), None)
    missing = handler.lambda_handler(api_event(path_parameters={"id": "ORD-20261022-00000000"}, claims=as_b), None)

    assert other["statusCode"] == missing["statusCode"] == 404
    assert json.loads(other["body"])["error"] == f"Order {order['orderId']} not found"  # same wording as missing


def test_legacy_order_without_owner_is_404(aws, handler):
    order = seed_order(aws.orders, orderId="ORD-20261022-1e9ac701")
    aws.orders.update_item(Key={"orderId": order["orderId"]}, UpdateExpression="REMOVE userId")

    result = handler.lambda_handler(api_event(path_parameters={"id": order["orderId"]}), None)

    assert result["statusCode"] == 404


def test_no_identity_is_401(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler(api_event(path_parameters={"id": order["orderId"]}, claims=None), None)

    assert result["statusCode"] == 401


def test_malformed_id_returns_400(aws, handler):
    result = handler.lambda_handler(api_event(path_parameters={"id": "../etc/passwd"}), None)

    assert result["statusCode"] == 400


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"status": "PAYMENT_PENDING", "cancellable": True}, True),
        ({"status": "PAYMENT_CAPTURED", "cancellable": True}, True),
        ({"status": "PAYMENT_PENDING"}, False),  # started on the old definition: no cancel branch to run
        ({"status": "FULFILLING", "cancellable": True}, False),  # too late
        ({"status": "PENDING", "cancellable": True}, False),  # not reserved yet
        ({"status": "CANCEL_REQUESTED", "cancellable": True, "cancelRequestedAt": "2026-10-30T10:00:00.000Z"}, False),
    ],
)
def test_can_cancel_only_inside_the_window(aws, handler, overrides, expected):
    order = seed_order(aws.orders, **overrides)

    body = json.loads(handler.lambda_handler(api_event(path_parameters={"id": order["orderId"]}), None)["body"])

    assert body["canCancel"] is expected
