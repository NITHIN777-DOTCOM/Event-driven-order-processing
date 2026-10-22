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


# --- Idempotency -------------------------------------------------------------------------------


def test_missing_idempotency_key_is_generated_and_returned(aws, handler):
    result = handler.lambda_handler(api_event(VALID_BODY), None)

    body = json.loads(result["body"])
    assert body["duplicate"] is False
    assert result["headers"]["Idempotency-Key"] == body["idempotencyKey"]
    record = aws.idempotency.get_item(Key={"idempotencyKey": body["idempotencyKey"]})["Item"]
    assert record["orderId"] == body["orderId"]
    assert record["expiresAt"] > 0


def test_same_key_returns_original_order_and_creates_nothing_new(aws, handler):
    headers = {"idempotency-key": "checkout-42"}

    first = handler.lambda_handler(api_event(VALID_BODY, headers=headers), None)
    second = handler.lambda_handler(api_event(VALID_BODY, headers=headers), None)
    third = handler.lambda_handler(api_event(VALID_BODY, headers=headers), None)

    assert first["statusCode"] == 202
    assert second["statusCode"] == third["statusCode"] == 200
    first_body, second_body = json.loads(first["body"]), json.loads(second["body"])
    assert second_body == {
        "orderId": first_body["orderId"],
        "status": "PENDING",
        "idempotencyKey": "checkout-42",
        "duplicate": True,
    }
    assert second["headers"]["Idempotent-Replayed"] == "true"
    assert aws.orders.scan()["Count"] == 1
    messages = aws.sqs.receive_message(QueueUrl=aws.queue_url, MaxNumberOfMessages=10)["Messages"]
    assert len(messages) == 1  # enqueued once, so the saga runs (and charges) once


def test_same_key_with_different_body_is_rejected(aws, handler):
    headers = {"Idempotency-Key": "checkout-43"}
    handler.lambda_handler(api_event(VALID_BODY, headers=headers), None)

    other = {**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": 5}]}
    result = handler.lambda_handler(api_event(other, headers=headers), None)

    assert result["statusCode"] == 409
    assert aws.orders.scan()["Count"] == 1


def test_lost_race_on_key_replays_the_winner(aws, handler):
    """Two identical requests pass the fast-path check at once; the transaction lets only one win."""
    request = handler.validate_request(VALID_BODY)
    fingerprint = handler.request_fingerprint(request)
    winner = handler.build_order(request, "race-key")
    loser = handler.build_order(request, "race-key")

    assert handler.save_order_once(winner, "race-key", fingerprint) is True
    assert handler.save_order_once(loser, "race-key", fingerprint) is False
    assert aws.orders.scan()["Count"] == 1


def test_malformed_idempotency_key_returns_400(aws, handler):
    result = handler.lambda_handler(api_event(VALID_BODY, headers={"Idempotency-Key": "bad key!"}), None)

    assert result["statusCode"] == 400
