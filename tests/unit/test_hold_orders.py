"""Orders that use a checkout hold (step 2.2, commit B): create_order's holdId rules and ReserveInventory's
consume path, its fallback when the hold has ended, and compensation afterwards. I5 is checked throughout."""

from __future__ import annotations

import json

import pytest

from conftest import USER_A, USER_B, api_event, jwt_claims, seed_order
from test_holds import SEEDED, assert_i5, counters, hold, make_overdue, schedules, stored

ITEMS = [{"productId": "WIRELESS-MOUSE", "quantity": 2}]


@pytest.fixture
def api(load_handler):
    return load_handler("holds_api")


@pytest.fixture
def create(load_handler):
    return load_handler("create_order")


@pytest.fixture
def reserve(load_handler):
    return load_handler("reserve_inventory")


def place(create, hold_id, user=USER_A, items=ITEMS):
    body = {"customerName": "Asha", "items": items, "holdId": hold_id}
    result = create.lambda_handler(api_event(body, claims=jwt_claims(user_id=user)), None)
    return result["statusCode"], json.loads(result["body"])


def order_with_hold(aws, hold_id, **overrides):
    """A PENDING order for 2 mice that names the hold (as create_order would have written it)."""
    items = [{"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "quantity": 2, "unitPrice": 799}]
    return seed_order(aws.orders, orderId="ORD-20261029-hold0001", items=items, holdId=hold_id, **overrides)


def history(aws, order_id):
    return aws.orders.get_item(Key={"orderId": order_id})["Item"]["statusHistory"]


# --- create_order: holdId rules -----------------------------------------------------------------------------
def test_an_order_with_its_own_active_hold_is_accepted(aws, api, create):
    _, mine = hold(api)

    code, body = place(create, mine["holdId"])

    assert code == 202
    assert aws.orders.get_item(Key={"orderId": body["orderId"]})["Item"]["holdId"] == mine["holdId"]


def test_another_users_hold_is_rejected(aws, api, create):
    _, theirs = hold(api, user=USER_B)

    code, body = place(create, theirs["holdId"])

    assert code == 400 and body["error"] == "holdId is not one of your checkout holds"
    assert stored(aws, theirs["holdId"])["status"] == "ACTIVE"  # untouched


def test_a_missing_or_malformed_hold_is_rejected(aws, create):
    assert place(create, "HOLD-20261029-0123456789")[1]["error"] == "holdId is not one of your checkout holds"
    assert place(create, "not-a-hold")[0] == 400


def test_items_must_match_the_hold(aws, api, create):
    _, mine = hold(api)

    code, body = place(create, mine["holdId"], items=[{"productId": "WIRELESS-MOUSE", "quantity": 3}])

    assert code == 400 and "don't match" in body["error"]


def test_a_consumed_hold_cannot_be_used_again(aws, api, create):
    _, mine = hold(api)
    aws.holds.update_item(Key={"holdId": mine["holdId"]}, UpdateExpression="SET #s = :c, orderId = :o",
                          ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": "CONSUMED", ":o": "ORD-1"})

    code, body = place(create, mine["holdId"])

    assert code == 400 and "already used by order ORD-1" in body["error"]


def test_an_expired_hold_is_accepted_and_reserved_afresh_later(aws, api, create):
    _, mine = hold(api)
    call_delete = api.lambda_handler(api_event(claims=jwt_claims(), route_key="DELETE /holds/{holdId}", path_parameters={"holdId": mine["holdId"]}), None)
    assert json.loads(call_delete["body"])["status"] == "RELEASED"

    assert place(create, mine["holdId"])[0] == 202


# --- reserve_inventory: consume, fall back -----------------------------------------------------------------
def test_reserve_consumes_the_hold_instead_of_decrementing_stock_again(aws, api, reserve):
    _, mine = hold(api)
    order = order_with_hold(aws, mine["holdId"])

    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    assert counters(aws, "WIRELESS-MOUSE") == (98, 0, 2)  # held -> reserved; stock decremented ONCE (at hold time)
    item = stored(aws, mine["holdId"])
    assert item["status"] == "CONSUMED" and item["orderId"] == order["orderId"]
    assert "Item" not in aws.holds.get_item(Key={"holdId": f"USER#{USER_A}"})
    assert schedules(aws) == []  # its expiry schedule was deleted
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "RESERVED" and saved["reservedItems"] == [{"productId": "WIRELESS-MOUSE", "quantity": 2}]
    assert history(aws, order["orderId"])[-1]["detail"] == f"Reserved stock for 1 product(s) from checkout hold {mine['holdId']}"
    assert_i5(aws)


def test_reserve_falls_back_when_the_hold_had_ended(aws, api, reserve):
    _, mine = hold(api)
    api.lambda_handler(api_event(claims=jwt_claims(), route_key="DELETE /holds/{holdId}", path_parameters={"holdId": mine["holdId"]}), None)
    order = order_with_hold(aws, mine["holdId"])

    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    assert counters(aws, "WIRELESS-MOUSE") == (98, 0, 2)  # a normal, fresh reservation
    assert "had ended, so reserved afresh" in history(aws, order["orderId"])[-1]["detail"]
    assert stored(aws, mine["holdId"])["status"] == "RELEASED"
    assert_i5(aws)


def test_reserve_expires_an_overdue_hold_then_reserves_afresh(aws, api, reserve):
    _, mine = hold(api)
    make_overdue(aws, mine["holdId"])  # its schedule hasn't fired yet
    order = order_with_hold(aws, mine["holdId"])

    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    item = stored(aws, mine["holdId"])
    assert item["status"] == "EXPIRED" and item["expiredBy"] == "reserve_inventory"
    assert counters(aws, "WIRELESS-MOUSE") == (98, 0, 2)
    assert_i5(aws)


def test_after_expiry_someone_else_can_take_the_stock_and_the_order_is_out_of_stock(aws, api, reserve):
    _, mine = hold(api, items=(("MECH-KEYBOARD", 2),))
    make_overdue(aws, mine["holdId"])
    api.lambda_handler(api_event(claims=jwt_claims(), route_key="GET /holds/current"), None)  # lazily expired
    hold(api, items=(("MECH-KEYBOARD", 2),), user=USER_B)  # B takes both keyboards
    items = [{"productId": "MECH-KEYBOARD", "name": "Mechanical Keyboard", "quantity": 2, "unitPrice": 3499}]
    order = seed_order(aws.orders, orderId="ORD-20261029-hold0002", items=items, holdId=mine["holdId"])

    with pytest.raises(reserve.OutOfStock, match="MECH-KEYBOARD"):
        reserve.lambda_handler({"orderId": order["orderId"]}, None)

    assert counters(aws, "MECH-KEYBOARD") == (0, 2, 0)  # B's hold intact
    assert_i5(aws)


def test_reserve_loses_a_race_with_expiry_and_falls_back(aws, api, reserve, monkeypatch):
    """The hold is read as ACTIVE, then released before the consume transaction commits."""
    _, mine = hold(api)
    stale = stored(aws, mine["holdId"])
    api.lambda_handler(api_event(claims=jwt_claims(), route_key="DELETE /holds/{holdId}", path_parameters={"holdId": mine["holdId"]}), None)
    monkeypatch.setattr(reserve.holds_table, "get_item", lambda **_: {"Item": stale})
    order = order_with_hold(aws, mine["holdId"])

    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    assert stored(aws, mine["holdId"])["status"] == "RELEASED"  # the consume was cancelled as a whole
    assert counters(aws, "WIRELESS-MOUSE") == (98, 0, 2)  # and the fallback reserved once
    assert_i5(aws)


def test_compensation_after_a_consumed_hold_returns_the_stock(aws, api, reserve, load_handler):
    _, mine = hold(api)
    order = order_with_hold(aws, mine["holdId"])
    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    load_handler("release_inventory").lambda_handler({"orderId": order["orderId"]}, None)

    assert counters(aws, "WIRELESS-MOUSE") == (SEEDED["WIRELESS-MOUSE"], 0, 0)
    assert_i5(aws)


def test_an_order_without_a_hold_takes_the_old_path(aws, reserve):
    order = seed_order(aws.orders)  # 2 mice + 1 keyboard, no holdId

    reserve.lambda_handler({"orderId": order["orderId"]}, None)

    assert counters(aws, "WIRELESS-MOUSE") == (98, 0, 2) and counters(aws, "MECH-KEYBOARD") == (1, 0, 1)
    assert "checkout hold" not in history(aws, order["orderId"])[-1]["detail"]
