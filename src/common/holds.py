"""Checkout holds: stock set aside for one user for a few minutes while they pay (step 2.2).

A hold lives in the holds table (order-saga-holds) and moves through exactly one transition out of ACTIVE:

    ACTIVE -> CONSUMED   the order was placed in time; reserve_inventory turns the held units into reserved ones
    ACTIVE -> RELEASED   the user left checkout, or created a newer hold (DELETE /holds/{id}, POST /holds)
    ACTIVE -> EXPIRED    its time ran out (the one-time EventBridge Scheduler schedule, or a lazy check on read)

Every transition is ONE DynamoDB transaction whose first item is the conditional status update
(`#s = ACTIVE`). If two of them race (an order consuming the hold at the same moment the schedule expires
it), exactly one transaction commits; the other is cancelled as a whole, so its stock changes never apply.
That is what keeps invariant I5 (stock conservation) true:

    I5  for each product: seeded stock = stock (available) + held (in ACTIVE holds) + reserved (in orders)

Inventory counters per product: `stock` (available to anyone), `held` (in ACTIVE holds), `reserved` (in orders
that weren't compensated). Creating a hold moves units stock -> held; release/expiry moves them back
held -> stock; consuming moves them held -> reserved.

One ACTIVE hold per user (anti-hoarding) is enforced by a pointer item in the same table,
holdId = "USER#<sub>" with {activeHoldId}. It is written and deleted in the same transactions as the hold, so
"the pointer exists" and "the user has an ACTIVE hold" can never disagree.

DynamoDB TTL (attribute purgeAt = expiry + 7 days) only deletes OLD records. TTL deletion can lag by days and
is never the release mechanism.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from common.orders import cancellation_codes
from common.timeutil import utc_now_iso

ACTIVE = "ACTIVE"
CONSUMED = "CONSUMED"
RELEASED = "RELEASED"
EXPIRED = "EXPIRED"
FINAL_STATUSES = frozenset({CONSUMED, RELEASED, EXPIRED})

DEFAULT_DURATION_SECONDS = 600  # what the storefront (spa client) always gets
MIN_DURATION_SECONDS = 30  # the automation client may ask for less, so e2e tests don't wait 10 minutes
MAX_HOLD_QUANTITY = 5  # per product: anti-hoarding (orders allow up to 50 without a hold)
MAX_HOLD_ITEMS = 10
PURGE_AFTER_SECONDS = 7 * 24 * 60 * 60  # TTL clean-up of finished holds, long after they stopped mattering


def pointer_key(user_id: str) -> str:
    """The holdId of the user's "current hold" pointer item."""
    return f"USER#{user_id}"


def epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def is_overdue(hold: dict[str, Any], now: float | None = None) -> bool:
    """An ACTIVE hold past its expiry is logically expired, even if its schedule hasn't fired yet."""
    return hold.get("status") == ACTIVE and float(hold["expiresAtEpoch"]) <= (time.time() if now is None else now)


def public_view(hold: dict[str, Any]) -> dict[str, Any]:
    """What the API returns. serverTime lets the client count down without trusting its own clock."""
    view = {
        key: hold[key]
        for key in ("holdId", "status", "items", "expiresAt", "durationSeconds", "createdAt", "orderId", "endedAt")
        if key in hold
    }
    view["secondsLeft"] = max(0, int(float(hold["expiresAtEpoch"]) - time.time())) if hold.get("status") == ACTIVE else 0
    view["serverTime"] = utc_now_iso()
    return view


def _end_transaction(
    holds_table: str, inventory_table: str, hold: dict[str, Any], new_status: str, stock_update: str, detail: dict[str, Any]
) -> list[dict[str, Any]]:
    """The items that move a hold out of ACTIVE. Item 0 is the hold's conditional status change."""
    now = utc_now_iso()
    values = {":active": ACTIVE, ":new": new_status, ":now": now}
    sets = ["#s = :new", "endedAt = :now", "updatedAt = :now"]
    for index, (name, value) in enumerate(detail.items()):
        sets.append(f"{name} = :d{index}")
        values[f":d{index}"] = value
    items: list[dict[str, Any]] = [
        {
            "Update": {
                "TableName": holds_table,
                "Key": {"holdId": hold["holdId"]},
                "UpdateExpression": "SET " + ", ".join(sets),
                "ConditionExpression": "#s = :active",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": values,
            }
        },
        {
            "Delete": {
                "TableName": holds_table,
                "Key": {"holdId": pointer_key(hold["userId"])},
                "ConditionExpression": "activeHoldId = :h",
                "ExpressionAttributeValues": {":h": hold["holdId"]},
            }
        },
    ]
    items += [
        {
            "Update": {
                "TableName": inventory_table,
                "Key": {"productId": item["productId"]},
                "UpdateExpression": stock_update,
                "ConditionExpression": "attribute_exists(productId) AND held >= :qty",
                "ExpressionAttributeValues": {":qty": item["quantity"]},
            }
        }
        for item in hold["items"]
    ]
    return items


def give_back_items(holds_table: str, inventory_table: str, hold: dict[str, Any], new_status: str, detail: dict[str, Any]) -> list[dict[str, Any]]:
    """RELEASED or EXPIRED: the held units go back to available stock."""
    return _end_transaction(holds_table, inventory_table, hold, new_status, "SET stock = stock + :qty, held = held - :qty", detail)


def consume_items(holds_table: str, inventory_table: str, hold: dict[str, Any], order_id: str) -> list[dict[str, Any]]:
    """CONSUMED: the held units become the order's reserved units (stock is NOT decremented a second time).

    Also requires the hold to be unexpired, so a late schedule can't let an expired hold be used."""
    items = _end_transaction(
        holds_table, inventory_table, hold, CONSUMED, "SET held = held - :qty, reserved = reserved + :qty", {"orderId": order_id}
    )
    update = items[0]["Update"]
    update["ConditionExpression"] = "#s = :active AND expiresAtEpoch > :epoch"
    update["ExpressionAttributeValues"][":epoch"] = int(time.time())
    return items


def lost_the_race(err: ClientError) -> bool:
    """True if a transaction built above was cancelled because the hold was no longer ACTIVE (item 0)."""
    if err.response["Error"]["Code"] != "TransactionCanceledException":
        return False
    codes = cancellation_codes(err.response)
    return bool(codes) and codes[0] == "ConditionalCheckFailed"


def end_hold(
    ddb_client: Any, holds_table: str, inventory_table: str, hold: dict[str, Any], new_status: str, detail: dict[str, Any] | None = None
) -> bool:
    """Release or expire an ACTIVE hold, giving its stock back. True if THIS call made the transition,
    False if the hold had already left ACTIVE (consumed, released or expired by someone else): a no-op."""
    try:
        ddb_client.transact_write_items(
            TransactItems=give_back_items(holds_table, inventory_table, hold, new_status, detail or {})
        )
    except ClientError as err:
        if lost_the_race(err):
            return False
        raise
    return True


def delete_schedule(scheduler: Any, group: str, hold_id: str, log: Any) -> None:
    """Best effort: once a hold has ended, its expiry schedule has nothing left to do. If this fails, the schedule
    still fires, finds the hold no longer ACTIVE and does nothing (expiry is idempotent)."""
    try:
        scheduler.delete_schedule(Name=hold_id, GroupName=group)
    except ClientError as err:
        code = err.response["Error"]["Code"]
        if code != "ResourceNotFoundException":  # already fired (ActionAfterCompletion DELETE) or never created
            log.warning("Could not delete the hold's expiry schedule; it will fire as a no-op", error=code)
