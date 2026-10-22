import json

import pytest

from conftest import api_event, seed_order


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


def test_malformed_id_returns_400(aws, handler):
    result = handler.lambda_handler(api_event(path_parameters={"id": "../etc/passwd"}), None)

    assert result["statusCode"] == 400
