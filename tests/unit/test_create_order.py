import json
import re
from decimal import Decimal

import pytest

from conftest import api_event

VALID_BODY = {
    "customerName": "Asha Rao",
    "customerEmail": "Asha@Example.com",
    "items": [
        {"productId": "WIRELESS-MOUSE", "quantity": 2},
        {"productId": "MECH-KEYBOARD", "quantity": 1},
    ],
}


@pytest.fixture
def handler(load_handler):
    return load_handler("create_order")


def test_valid_order_is_saved_pending_and_enqueued(aws, handler):
    result = handler.lambda_handler(api_event(VALID_BODY), None)

    assert result["statusCode"] == 202
    body = json.loads(result["body"])
    assert body["status"] == "PENDING"
    assert re.fullmatch(r"ORD-\d{8}-[0-9a-f]{8}", body["orderId"])

    order = aws.orders.get_item(Key={"orderId": body["orderId"]})["Item"]
    assert order["totalAmount"] == Decimal("5097.00")  # 2 x 799 + 1 x 3499, priced server-side
    assert order["currency"] == "INR"
    assert order["customerEmail"] == "asha@example.com"
    assert order["simulate"] == "none"
    assert [h["status"] for h in order["statusHistory"]] == ["PENDING"]
    assert order["items"][0]["name"] == "Wireless Mouse"

    messages = aws.sqs.receive_message(QueueUrl=aws.queue_url)["Messages"]
    assert json.loads(messages[0]["Body"]) == {"orderId": body["orderId"]}


@pytest.mark.parametrize(
    "body, expected_error",
    [
        ("not json", "valid JSON"),
        ({**VALID_BODY, "customerName": ""}, "customerName"),
        ({**VALID_BODY, "customerEmail": "nope"}, "customerEmail"),
        ({**VALID_BODY, "items": []}, "items"),
        ({**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": 0}]}, "quantity"),
        ({**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": True}]}, "quantity"),
        ({**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": 1}] * 2}, "more than once"),
        ({**VALID_BODY, "simulate": "explode"}, "simulate"),
    ],
)
def test_invalid_input_returns_400(aws, handler, body, expected_error):
    result = handler.lambda_handler(api_event(body), None)

    assert result["statusCode"] == 400
    assert expected_error in json.loads(result["body"])["error"]
    assert aws.orders.scan()["Count"] == 0
    assert "Messages" not in aws.sqs.receive_message(QueueUrl=aws.queue_url)


def test_unknown_product_returns_400(aws, handler):
    body = {**VALID_BODY, "items": [{"productId": "DOES-NOT-EXIST", "quantity": 1}]}

    result = handler.lambda_handler(api_event(body), None)

    assert result["statusCode"] == 400
    assert "Unknown productId(s): DOES-NOT-EXIST" in json.loads(result["body"])["error"]
    assert aws.orders.scan()["Count"] == 0
