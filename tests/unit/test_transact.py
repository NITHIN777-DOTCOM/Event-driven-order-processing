"""TransactionConflict handling on the stock paths (step 3.1, found by the live oversell race test).

A transaction cancelled ONLY because another transaction held one of its items applied nothing, and says nothing about
the stock. It must be retried, and it must never come back to the buyer as "out of stock".
"""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError

from common import transact
from conftest import USER_A, api_event, jwt_claims, seed_order


def cancelled(*codes: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "cancelled"}, "CancellationReasons": [{"Code": c} for c in codes]},
        "TransactWriteItems",
    )


class Contended:
    """Wraps a DynamoDB client: the first `conflicts` transactions are cancelled with TransactionConflict
    (on every item), then the real client takes over. Everything else passes straight through."""

    def __init__(self, client, conflicts: int) -> None:
        self.client, self.conflicts, self.calls = client, conflicts, 0

    def transact_write_items(self, TransactItems):
        self.calls += 1
        if self.calls <= self.conflicts:
            raise cancelled(*["TransactionConflict"] * len(TransactItems))
        return self.client.transact_write_items(TransactItems=TransactItems)

    def __getattr__(self, name):
        return getattr(self.client, name)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(transact.time, "sleep", lambda _: None)


def test_conflicts_are_retried_until_the_transaction_commits(aws):
    client = Contended(aws.inventory.meta.client, conflicts=3)
    item = {"Update": {"TableName": "test-inventory", "Key": {"productId": "MECH-KEYBOARD"}, "UpdateExpression": "SET stock = stock - :q",
                       "ConditionExpression": "stock >= :q", "ExpressionAttributeValues": {":q": 1}}}

    assert transact.transact_write(client, [item]) == 3  # three conflicts retried
    assert client.calls == 4
    assert aws.inventory.get_item(Key={"productId": "MECH-KEYBOARD"})["Item"]["stock"] == 1  # applied exactly once


def test_a_failed_condition_is_raised_at_once(aws):
    class Refusing:
        calls = 0

        def transact_write_items(self, TransactItems):
            Refusing.calls += 1
            raise cancelled("ConditionalCheckFailed", "None")

    with pytest.raises(ClientError):
        transact.transact_write(Refusing(), [{}, {}])
    assert Refusing.calls == 1  # a real "no" is never retried


def test_conflicts_that_never_clear_are_raised_after_the_last_attempt(aws):
    client = Contended(aws.inventory.meta.client, conflicts=99)

    with pytest.raises(ClientError) as err:
        transact.transact_write(client, [{}])
    assert transact.is_conflict(err.value) and client.calls == transact.CONFLICT_ATTEMPTS


# --- reserve_inventory ------------------------------------------------------------------------------
def reserve_setup(aws, load_handler, conflicts):
    reserve = load_handler("reserve_inventory")
    reserve.ddb_client = Contended(reserve.ddb_client, conflicts)
    order = seed_order(aws.orders, status="PROCESSING", items=[{"productId": "MECH-KEYBOARD", "name": "Keyboard", "quantity": 1, "unitPrice": 3499}])
    return reserve, order


def test_reserve_retries_a_conflict_instead_of_answering_out_of_stock(aws, load_handler):
    reserve, order = reserve_setup(aws, load_handler, conflicts=2)

    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    stored = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert stored["status"] == "RESERVED" and stored["reservedItems"] == [{"productId": "MECH-KEYBOARD", "quantity": 1}]
    assert aws.inventory.get_item(Key={"productId": "MECH-KEYBOARD"})["Item"]["stock"] == 1


def test_reserve_never_reports_endless_conflicts_as_out_of_stock(aws, load_handler):
    reserve, order = reserve_setup(aws, load_handler, conflicts=99)

    with pytest.raises(ClientError):  # a Lambda error (the saga's Catch fails the order), not OutOfStock
        reserve.lambda_handler({"orderId": order["orderId"]}, None)

    assert aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]["status"] == "PROCESSING"  # no OUT_OF_STOCK entry


def test_reserve_still_answers_a_real_shortage_with_out_of_stock(aws, load_handler):
    reserve = load_handler("reserve_inventory")
    order = seed_order(aws.orders, status="PROCESSING", items=[{"productId": "MECH-KEYBOARD", "name": "Keyboard", "quantity": 3, "unitPrice": 3499}])

    with pytest.raises(reserve.OutOfStock, match="MECH-KEYBOARD"):
        reserve.lambda_handler({"orderId": order["orderId"]}, None)


# --- holds_api ---------------------------------------------------------------------------------------
def post_hold(api):
    event = api_event(body={"items": [{"productId": "MECH-KEYBOARD", "quantity": 1}]}, claims=jwt_claims(user_id=USER_A), route_key="POST /holds")
    result = api.lambda_handler(event, None)
    return result["statusCode"], json.loads(result["body"]), result["headers"]


def test_hold_retries_a_conflict_and_is_created(aws, load_handler):
    api = load_handler("holds_api")
    api.ddb_client = Contended(api.ddb_client, conflicts=2)

    code, body, _ = post_hold(api)

    assert code == 201 and body["status"] == "ACTIVE"
    item = aws.inventory.get_item(Key={"productId": "MECH-KEYBOARD"})["Item"]
    assert (item["stock"], item["held"]) == (1, 1)


def test_hold_answers_busy_not_out_of_stock_when_conflicts_never_clear(aws, load_handler):
    api = load_handler("holds_api")
    api.ddb_client = Contended(api.ddb_client, conflicts=99)

    code, body, headers = post_hold(api)

    assert code == 503 and "productId" not in body and headers["Retry-After"] == "1"
    assert aws.inventory.get_item(Key={"productId": "MECH-KEYBOARD"})["Item"]["stock"] == 2  # nothing held
    assert aws.scheduler.list_schedules(GroupName="test-holds")["Schedules"] == []  # its schedule was removed
