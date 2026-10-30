import json
import re
from decimal import Decimal

import pytest

from conftest import EMAIL_A, EMAIL_B, USER_A, USER_B, api_event, jwt_claims

VALID_BODY = {
    "customerName": "Asha Rao",
    "items": [
        {"productId": "WIRELESS-MOUSE", "quantity": 2},
        {"productId": "MECH-KEYBOARD", "quantity": 1},
    ],
}


@pytest.fixture
def handler(load_handler):
    return load_handler("create_order")


def test_valid_order_is_saved_pending(aws, handler):
    result = handler.lambda_handler(api_event(VALID_BODY), None)

    assert result["statusCode"] == 202
    body = json.loads(result["body"])
    assert body["status"] == "PENDING"
    assert re.fullmatch(r"ORD-\d{8}-[0-9a-f]{8}", body["orderId"])

    order = aws.orders.get_item(Key={"orderId": body["orderId"]})["Item"]
    assert order["totalAmount"] == Decimal("5097.00")  # 2 x 799 + 1 x 3499, priced server-side
    assert order["currency"] == "INR"
    assert order["simulate"] == "none"
    assert [h["status"] for h in order["statusHistory"]] == ["PENDING"]
    assert order["items"][0]["name"] == "Wireless Mouse"
    # Owner and wallet come from the token; the GSI partition is per user, newest first.
    assert order["userId"] == USER_A and order["walletId"] == USER_A and order["customerEmail"] == EMAIL_A
    assert order["gsi1pk"] == f"USER#{USER_A}"
    assert order["gsi1sk"] == f"{order['createdAt']}#{order['orderId']}"


# --- Identity comes ONLY from the verified JWT claims ------------------------------------------


def test_identity_fields_in_the_body_are_ignored(aws, handler):
    spoofed = {**VALID_BODY, "customerEmail": "victim@example.com", "userId": USER_B, "walletId": USER_B}

    result = handler.lambda_handler(api_event(spoofed), None)

    assert result["statusCode"] == 202
    order = aws.orders.get_item(Key={"orderId": json.loads(result["body"])["orderId"]})["Item"]
    assert (order["userId"], order["walletId"], order["customerEmail"]) == (USER_A, USER_A, EMAIL_A)


@pytest.mark.parametrize(
    "claims, status",
    [
        (None, 401),  # no authorizer context at all: fail closed
        ({"email": EMAIL_A, "email_verified": "true"}, 401),  # no sub
        (jwt_claims(email=None), 403),  # an access token without the trigger's email claim
        (jwt_claims(verified="false"), 403),  # email not verified
    ],
)
def test_missing_or_unusable_identity_is_rejected(aws, handler, claims, status):
    result = handler.lambda_handler(api_event(VALID_BODY, claims=claims), None)

    assert result["statusCode"] == status
    assert aws.orders.scan()["Count"] == 0



# --- Transactional outbox: the DynamoDB transaction is the ONLY write -------------------------


def test_create_order_never_sends_to_sqs(aws, handler):
    result = handler.lambda_handler(api_event(VALID_BODY), None)

    assert result["statusCode"] == 202
    # The order row exists (its stream INSERT is what the outbox pipe delivers)...
    assert aws.orders.scan()["Count"] == 1
    # ...and nothing was published directly: no message in any queue.
    for url in aws.sqs.list_queues().get("QueueUrls", []):
        assert "Messages" not in aws.sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10)


def test_handler_needs_no_queue_configuration(aws, load_handler, monkeypatch):
    monkeypatch.delenv("ORDERS_QUEUE_URL", raising=False)

    module = load_handler("create_order")  # would raise KeyError if it still read ORDERS_QUEUE_URL

    assert not hasattr(module, "sqs") and not hasattr(module, "enqueue_order")
    assert module.lambda_handler(api_event(VALID_BODY), None)["statusCode"] == 202


@pytest.mark.parametrize(
    "body, expected_error",
    [
        ("not json", "valid JSON"),
        ({**VALID_BODY, "customerName": ""}, "customerName"),
        ({**VALID_BODY, "items": []}, "items"),
        ({**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": 0}]}, "quantity"),
        ({**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": True}]}, "quantity"),
        ({**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": 1}] * 2}, "more than once"),
        ({**VALID_BODY, "simulate": "explode"}, "simulate"),
        ({**VALID_BODY, "simulateLine": 1}, "only used with"),
        ({**VALID_BODY, "simulate": "item_unavailable", "simulateLine": 3}, "line number from 1 to 2"),
        ({**VALID_BODY, "simulate": "item_unavailable", "simulateLine": True}, "line number"),
        ({**VALID_BODY, "simulate": "item_unavailable", "simulateLine": "L1"}, "line number"),
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
    record = aws.idempotency.get_item(Key={"idempotencyKey": f"{USER_A}#{body['idempotencyKey']}"})["Item"]
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
    assert aws.orders.scan()["Count"] == 1  # one row = one stream INSERT, so the saga runs (and charges) once


def test_same_key_with_different_body_is_rejected(aws, handler):
    headers = {"Idempotency-Key": "checkout-43"}
    handler.lambda_handler(api_event(VALID_BODY, headers=headers), None)

    other = {**VALID_BODY, "items": [{"productId": "WIRELESS-MOUSE", "quantity": 5}]}
    result = handler.lambda_handler(api_event(other, headers=headers), None)

    assert result["statusCode"] == 409
    assert aws.orders.scan()["Count"] == 1


def test_same_key_from_another_user_creates_their_own_order(aws, handler):
    """Idempotency keys are scoped per user: B reusing A's key gets B's own new order, not A's."""
    headers = {"Idempotency-Key": "checkout-44"}
    a = handler.lambda_handler(api_event(VALID_BODY, headers=headers), None)
    b = handler.lambda_handler(api_event(VALID_BODY, headers=headers, claims=jwt_claims(USER_B, EMAIL_B)), None)

    assert a["statusCode"] == b["statusCode"] == 202  # both are NEW orders, no replay across users
    a_id, b_id = json.loads(a["body"])["orderId"], json.loads(b["body"])["orderId"]
    assert a_id != b_id
    assert aws.orders.get_item(Key={"orderId": b_id})["Item"]["userId"] == USER_B
    stored = {item["idempotencyKey"] for item in aws.idempotency.scan()["Items"]}
    assert stored == {f"{USER_A}#checkout-44", f"{USER_B}#checkout-44"}


def test_lost_race_on_key_replays_the_winner(aws, handler):
    """Two identical requests pass the fast-path check at once; the transaction lets only one win."""
    request = handler.validate_request(VALID_BODY)
    fingerprint = handler.request_fingerprint(request)
    caller = handler.caller_from(api_event(VALID_BODY))
    winner = handler.build_order(request, "race-key", caller)
    loser = handler.build_order(request, "race-key", caller)

    assert handler.save_order_once(winner, "race-key", fingerprint) is True
    assert handler.save_order_once(loser, "race-key", fingerprint) is False
    assert aws.orders.scan()["Count"] == 1


def test_malformed_idempotency_key_returns_400(aws, handler):
    result = handler.lambda_handler(api_event(VALID_BODY, headers={"Idempotency-Key": "bad key!"}), None)

    assert result["statusCode"] == 400


@pytest.mark.parametrize("simulate_line", [1, 2, "all", None])
def test_item_unavailable_stores_the_target_line(aws, handler, simulate_line):
    body = {**VALID_BODY, "simulate": "item_unavailable", **({} if simulate_line is None else {"simulateLine": simulate_line})}

    result = handler.lambda_handler(api_event(body), None)

    assert result["statusCode"] == 202
    order = aws.orders.get_item(Key={"orderId": json.loads(result["body"])["orderId"]})["Item"]
    assert order["simulate"] == "item_unavailable"
    assert order.get("simulateLine") == simulate_line
