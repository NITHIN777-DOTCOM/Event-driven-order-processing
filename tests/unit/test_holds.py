"""Checkout holds (step 2.2): the holds API, the expiry Lambda and the race rules in common/holds.py.

Inventory in the fixture: WIRELESS-MOUSE stock 100, MECH-KEYBOARD stock 2 (reserved 0, no `held` yet).
Every test that moves stock also checks invariant I5: stock + held + reserved never changes.
"""

from __future__ import annotations

import json
import time

import pytest
from botocore.exceptions import ClientError

from common import holds as model
from conftest import AUTOMATION_CLIENT, USER_A, USER_B, api_event, jwt_claims

SEEDED = {"WIRELESS-MOUSE": 100, "MECH-KEYBOARD": 2}


@pytest.fixture
def api(load_handler):
    return load_handler("holds_api")


@pytest.fixture
def expiry(load_handler):
    return load_handler("hold_expiry")


def call(api, route, body=None, user=USER_A, client=None, hold_id=None):
    claims = jwt_claims(user_id=user, client_id=client) if client else jwt_claims(user_id=user)
    event = api_event(body=body, claims=claims, route_key=route, path_parameters={"holdId": hold_id} if hold_id else None)
    result = api.lambda_handler(event, None)
    return result["statusCode"], json.loads(result["body"])


def hold(api, items=(("WIRELESS-MOUSE", 2),), **kwargs):
    return call(api, "POST /holds", {"items": [{"productId": p, "quantity": q} for p, q in items], **kwargs.pop("extra", {})}, **kwargs)


def counters(aws, product):
    item = aws.inventory.get_item(Key={"productId": product}, ConsistentRead=True)["Item"]
    return int(item["stock"]), int(item.get("held", 0)), int(item["reserved"])


def assert_i5(aws):
    for product, seeded in SEEDED.items():
        stock, held, reserved = counters(aws, product)
        assert stock + held + reserved == seeded, f"I5 broken for {product}: {stock}+{held}+{reserved} != {seeded}"


def stored(aws, hold_id):
    return aws.holds.get_item(Key={"holdId": hold_id}, ConsistentRead=True)["Item"]


def schedules(aws):
    return [s["Name"] for s in aws.scheduler.list_schedules(GroupName="test-holds")["Schedules"]]


def make_overdue(aws, hold_id):
    aws.holds.update_item(Key={"holdId": hold_id}, UpdateExpression="SET expiresAtEpoch = :past", ExpressionAttributeValues={":past": int(time.time()) - 5})


# --- POST /holds -----------------------------------------------------------------------------------------
def test_a_hold_moves_stock_to_held_and_schedules_its_exact_expiry(aws, api):
    code, body = hold(api)

    assert code == 201 and body["status"] == "ACTIVE" and body["durationSeconds"] == 600
    assert 598 <= body["secondsLeft"] <= 600 and body["serverTime"].endswith("Z")
    assert counters(aws, "WIRELESS-MOUSE") == (98, 2, 0)
    assert aws.holds.get_item(Key={"holdId": f"USER#{USER_A}"})["Item"]["activeHoldId"] == body["holdId"]
    schedule = aws.scheduler.get_schedule(Name=body["holdId"], GroupName="test-holds")
    assert schedule["ScheduleExpression"] == f"at({body['expiresAt'][:19]})" and schedule["ScheduleExpressionTimezone"] == "UTC"
    assert schedule["Target"]["Arn"].endswith(":function:test-hold-expiry")
    assert json.loads(schedule["Target"]["Input"]) == {"holdId": body["holdId"]}
    assert schedule["ActionAfterCompletion"] == "DELETE" and schedule["FlexibleTimeWindow"] == {"Mode": "OFF"}
    item = stored(aws, body["holdId"])
    assert item["purgeAt"] == item["expiresAtEpoch"] + 7 * 24 * 3600  # TTL: clean-up a week later, never the release
    assert_i5(aws)


def test_partial_stock_holds_nothing_and_names_the_short_item(aws, api):
    code, body = hold(api, items=(("WIRELESS-MOUSE", 2), ("MECH-KEYBOARD", 3)))

    assert code == 409 and body["productId"] == "MECH-KEYBOARD" and body["available"] == 2
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)  # all-or-nothing: the mice weren't held either
    assert counters(aws, "MECH-KEYBOARD") == (2, 0, 0)
    assert schedules(aws) == []  # the schedule made in step 2 was removed again
    assert "Item" not in aws.holds.get_item(Key={"holdId": f"USER#{USER_A}"})


def test_one_active_hold_per_user_a_new_hold_releases_the_old_one(aws, api):
    _, first = hold(api, items=(("MECH-KEYBOARD", 2),))
    code, second = hold(api, items=(("MECH-KEYBOARD", 1),))

    assert code == 201
    assert stored(aws, first["holdId"])["status"] == "RELEASED"
    assert stored(aws, first["holdId"])["endReason"] == "replaced by a new hold"
    assert counters(aws, "MECH-KEYBOARD") == (1, 1, 0)
    assert schedules(aws) == [second["holdId"]]
    assert_i5(aws)


@pytest.mark.parametrize(
    "items, message",
    [
        ([{"productId": "WIRELESS-MOUSE", "quantity": 6}], "1 to 5 (hold limit per product)"),
        ([{"productId": "WIRELESS-MOUSE", "quantity": 1}, {"productId": "WIRELESS-MOUSE", "quantity": 1}], "more than once"),
        ([{"productId": "NOPE", "quantity": 1}], "Unknown productId"),
        ([], "1-10 entries"),
    ],
)
def test_invalid_requests_are_400(aws, api, items, message):
    code, body = call(api, "POST /holds", {"items": items})

    assert code == 400 and message in body["error"]


# --- duration rules (client_id) ------------------------------------------------------------------------------
def test_the_storefront_cannot_choose_a_duration(aws, api):
    code, body = hold(api, extra={"durationSeconds": 30})

    assert code == 400 and "automation client" in body["error"]


def test_the_automation_client_may_ask_for_a_short_hold(aws, api):
    code, body = hold(api, extra={"durationSeconds": 30}, client=AUTOMATION_CLIENT)

    assert code == 201 and body["durationSeconds"] == 30 and 28 <= body["secondsLeft"] <= 30


@pytest.mark.parametrize("duration", [29, 601, "60", True])
def test_the_automation_client_stays_within_30_to_600_seconds(aws, api, duration):
    code, _ = hold(api, extra={"durationSeconds": duration}, client=AUTOMATION_CLIENT)

    assert code == 400


def test_the_automation_client_defaults_to_600_seconds(aws, api):
    assert hold(api, client=AUTOMATION_CLIENT)[1]["durationSeconds"] == 600


# --- GET /holds/current, DELETE /holds/{id}, ownership ----------------------------------------------------
def test_current_hold_is_the_callers_own(aws, api):
    _, mine = hold(api)

    assert call(api, "GET /holds/current")[1]["hold"]["holdId"] == mine["holdId"]
    assert call(api, "GET /holds/current", user=USER_B)[1]["hold"] is None


def test_another_users_hold_is_a_404_and_stays_held(aws, api):
    _, mine = hold(api)

    code, body = call(api, "DELETE /holds/{holdId}", user=USER_B, hold_id=mine["holdId"])

    assert code == 404 and body == {"error": "Hold not found"}
    assert stored(aws, mine["holdId"])["status"] == "ACTIVE"
    assert call(api, "DELETE /holds/{holdId}", hold_id="HOLD-20261029-doesnotexist")[0] == 404


def test_delete_releases_the_hold_once(aws, api):
    _, mine = hold(api)

    first = call(api, "DELETE /holds/{holdId}", hold_id=mine["holdId"])
    second = call(api, "DELETE /holds/{holdId}", hold_id=mine["holdId"])

    assert first[0] == second[0] == 200 and first[1]["status"] == second[1]["status"] == "RELEASED"
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)  # released once, not twice
    assert schedules(aws) == []
    assert call(api, "GET /holds/current")[1]["hold"] is None
    assert_i5(aws)


def test_an_overdue_hold_is_expired_lazily_on_read(aws, api):
    _, mine = hold(api)
    make_overdue(aws, mine["holdId"])  # its schedule hasn't fired yet

    assert call(api, "GET /holds/current")[1]["hold"] is None
    item = stored(aws, mine["holdId"])
    assert item["status"] == "EXPIRED" and item["expiredBy"] == "lazy check"
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)
    assert_i5(aws)


def test_a_stale_pointer_never_blocks_new_holds(aws, api):
    aws.holds.put_item(Item={"holdId": f"USER#{USER_A}", "activeHoldId": "HOLD-20261029-gone"})

    code, body = hold(api)

    assert code == 201
    assert aws.holds.get_item(Key={"holdId": f"USER#{USER_A}"})["Item"]["activeHoldId"] == body["holdId"]


def test_unauthenticated_and_unknown_routes(aws, api):
    assert api.lambda_handler(api_event(claims=None, route_key="GET /holds/current"), None)["statusCode"] == 401
    assert call(api, "PATCH /holds")[0] == 404


# --- hold_expiry ---------------------------------------------------------------------------------------------
def test_expiry_returns_the_stock_once_and_records_its_lag(aws, api, expiry):
    _, mine = hold(api)
    make_overdue(aws, mine["holdId"])

    first = expiry.lambda_handler({"holdId": mine["holdId"]}, None)
    second = expiry.lambda_handler({"holdId": mine["holdId"]}, None)

    assert first["expired"] is True and first["expiryLagMs"] >= 5000
    assert second == {"holdId": mine["holdId"], "expired": False, "reason": "already EXPIRED"}
    item = stored(aws, mine["holdId"])
    assert item["status"] == "EXPIRED" and item["expiredBy"] == "schedule"
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)
    assert "Item" not in aws.holds.get_item(Key={"holdId": f"USER#{USER_A}"})
    assert_i5(aws)


def test_expiry_of_a_released_or_missing_hold_is_a_no_op(aws, api, expiry):
    _, mine = hold(api)
    call(api, "DELETE /holds/{holdId}", hold_id=mine["holdId"])

    assert expiry.lambda_handler({"holdId": mine["holdId"]}, None)["reason"] == "already RELEASED"
    assert expiry.lambda_handler({"holdId": "HOLD-20261029-never"}, None)["reason"] == "not found"
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)


# --- races: exactly one transition out of ACTIVE wins ----------------------------------------------------------
def consume(aws, hold_item, order_id="ORD-20261029-race0001"):
    client = aws.holds.meta.client
    client.transact_write_items(TransactItems=model.consume_items("test-holds", "test-inventory", hold_item, order_id))


def test_consume_then_expire_the_expiry_is_a_no_op(aws, api, expiry):
    _, mine = hold(api)
    consume(aws, stored(aws, mine["holdId"]))

    assert expiry.lambda_handler({"holdId": mine["holdId"]}, None)["expired"] is False
    assert counters(aws, "WIRELESS-MOUSE") == (98, 0, 2)  # held -> reserved, stock not decremented twice
    assert stored(aws, mine["holdId"])["orderId"] == "ORD-20261029-race0001"
    assert_i5(aws)


def test_expire_wins_then_consume_is_cancelled_as_a_whole(aws, api, expiry):
    _, mine = hold(api)
    snapshot = stored(aws, mine["holdId"])  # read by the consumer before the expiry committed
    make_overdue(aws, mine["holdId"])
    expiry.lambda_handler({"holdId": mine["holdId"]}, None)

    with pytest.raises(ClientError) as err:
        consume(aws, snapshot)

    assert model.lost_the_race(err.value)
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)
    assert_i5(aws)


def test_release_wins_then_expire_is_a_no_op_even_with_a_stale_read(aws, api):
    _, mine = hold(api)
    snapshot = stored(aws, mine["holdId"])
    call(api, "DELETE /holds/{holdId}", hold_id=mine["holdId"])

    won = model.end_hold(aws.holds.meta.client, "test-holds", "test-inventory", snapshot, model.EXPIRED)

    assert won is False
    assert counters(aws, "WIRELESS-MOUSE") == (100, 0, 0)  # not given back twice
    assert_i5(aws)


def test_an_overdue_hold_cannot_be_consumed_even_before_its_schedule_fires(aws, api):
    _, mine = hold(api)
    make_overdue(aws, mine["holdId"])

    with pytest.raises(ClientError) as err:
        consume(aws, stored(aws, mine["holdId"]))

    assert model.lost_the_race(err.value)
    assert counters(aws, "WIRELESS-MOUSE") == (98, 2, 0)


def test_two_users_race_for_the_last_units_exactly_one_hold(aws, api):
    a = hold(api, items=(("MECH-KEYBOARD", 2),), user=USER_A)
    b = hold(api, items=(("MECH-KEYBOARD", 2),), user=USER_B)

    assert sorted([a[0], b[0]]) == [201, 409]
    assert counters(aws, "MECH-KEYBOARD") == (0, 2, 0)
    assert_i5(aws)


def test_public_view_and_overdue_helpers():
    item = {"holdId": "HOLD-1", "status": "EXPIRED", "items": [], "expiresAt": "x", "expiresAtEpoch": 1}
    assert model.public_view(item)["secondsLeft"] == 0
    assert model.is_overdue({"status": "ACTIVE", "expiresAtEpoch": 10}, now=10)
    assert not model.is_overdue({"status": "CONSUMED", "expiresAtEpoch": 10}, now=99)
