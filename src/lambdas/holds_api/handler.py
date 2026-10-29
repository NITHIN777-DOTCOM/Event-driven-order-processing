"""Checkout holds API (JWT; always the CALLER's own holds). See common/holds.py for the model and invariant I5.

  POST   /holds             {items: [{productId, quantity}], durationSeconds?}  -> 201 the new ACTIVE hold
  GET    /holds/current                                                       -> 200 {hold: ... or null}
  DELETE /holds/{holdId}                                                      -> 200 the hold (released)

POST /holds, in order:
  1. Anti-hoarding: the caller's current hold (if any) is released first; one ACTIVE hold per user.
  2. The one-time EventBridge Scheduler schedule is created FIRST (group order-saga-holds, at(expiresAt),
     ActionAfterCompletion DELETE), targeting Lambda order-saga-hold-expiry with {"holdId"}. If we crash after
     this, the schedule fires on a hold that doesn't exist: a no-op. The reverse order could leave a hold with no
     schedule, holding stock forever.
  3. ONE TransactWriteItems: the user's pointer item (must not exist), the hold (ACTIVE), and per product
     stock -= qty, held += qty with the condition stock >= qty. All-or-nothing: if any product is short, nothing
     is held and the answer is 409 naming that product.

Duration: the storefront (spa client) always gets 600 s. Only the automation client (scripts, e2e tests) may ask
for a shorter hold, 30-600 s. The client is the token's verified client_id claim, compared with the two app
client ids in SSM (/order-saga/auth/client-ids, written by Terraform; read at run time because passing them as
env vars would create a Terraform dependency cycle through the Cognito pre-token trigger).

Someone else's hold is a 404, the same as a missing one: we don't reveal that it exists.
An ACTIVE hold that is past its expiry (schedule not fired yet) is expired lazily when it is next read.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.auth import Caller, Forbidden, Unauthorized, caller_from
from common.holds import (
    ACTIVE,
    DEFAULT_DURATION_SECONDS,
    EXPIRED,
    MAX_HOLD_ITEMS,
    MAX_HOLD_QUANTITY,
    MIN_DURATION_SECONDS,
    PURGE_AFTER_SECONDS,
    RELEASED,
    delete_schedule,
    end_hold,
    epoch_to_iso,
    is_overdue,
    pointer_key,
    public_view,
)
from common.http import BadRequest, parse_json_body, response
from common.logger import StructuredLogger, get_logger
from common.orders import cancellation_codes
from common.secrets import get_secret
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

HOLDS_TABLE = os.environ["HOLDS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]
SCHEDULE_GROUP = os.environ["SCHEDULE_GROUP"]
EXPIRY_FUNCTION_ARN = os.environ["EXPIRY_FUNCTION_ARN"]
SCHEDULER_ROLE_ARN = os.environ["SCHEDULER_ROLE_ARN"]
CLIENT_IDS_PARAMETER = os.environ["CLIENT_IDS_PARAMETER"]

dynamodb = boto3.resource("dynamodb")
holds_table = dynamodb.Table(HOLDS_TABLE)
inventory_table = dynamodb.Table(INVENTORY_TABLE)
ddb_client = dynamodb.meta.client
scheduler = boto3.client("scheduler")
logger = get_logger("holds_api")

CREATE_ATTEMPTS = 3  # retries only when the same user creates two holds at the same moment


class Conflict(Exception):
    """409: e.g. not enough stock. Carries extra fields for the response body."""

    def __init__(self, message: str, **fields: Any) -> None:
        super().__init__(message)
        self.fields = fields


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "")
    log = logger.bind(requestId=(event.get("requestContext") or {}).get("requestId"))
    try:
        caller = caller_from(event)
        log = log.bind(userId=caller.user_id)
        if route == "POST /holds":
            return response(201, create_hold(caller, parse_json_body(event), log))
        if route == "GET /holds/current":
            return response(200, {"hold": current_hold(caller, log), "serverTime": utc_now_iso()})
        if route == "DELETE /holds/{holdId}":
            hold_id = (event.get("pathParameters") or {}).get("holdId", "")
            return release_hold(caller, hold_id, log)
        return response(404, {"error": f"Unknown route {route}"})
    except Unauthorized as err:
        return response(401, {"error": str(err)})
    except Forbidden as err:
        return response(403, {"error": str(err)})
    except BadRequest as err:
        log.warning("Rejected hold request", reason=str(err))
        return response(400, {"error": str(err)})
    except Conflict as err:
        return response(409, {"error": str(err), **err.fields})


# --------------------------------------------------------------------------------------------
# Request validation
# --------------------------------------------------------------------------------------------
def validate_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_HOLD_ITEMS:
        raise BadRequest(f"items must be a list of 1-{MAX_HOLD_ITEMS} entries")
    normalised, seen = [], set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise BadRequest(f"items[{index}] must be an object")
        product_id, quantity = item.get("productId"), item.get("quantity")
        if not isinstance(product_id, str) or not product_id:
            raise BadRequest(f"items[{index}].productId is required")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_HOLD_QUANTITY:
            raise BadRequest(f"items[{index}].quantity must be an integer from 1 to {MAX_HOLD_QUANTITY} (hold limit per product)")
        if product_id in seen:
            raise BadRequest(f"productId {product_id} appears more than once; combine the quantities")
        seen.add(product_id)
        normalised.append({"productId": product_id, "quantity": quantity})
    return normalised


def client_ids() -> dict[str, str]:
    return json.loads(get_secret(CLIENT_IDS_PARAMETER))


def hold_duration(caller: Caller, body: dict[str, Any]) -> int:
    """600 s for the storefront. Only the automation client may choose 30-600 s (decided by the token's client_id)."""
    requested = body.get("durationSeconds")
    if requested is None:
        return DEFAULT_DURATION_SECONDS
    if caller.client_id != client_ids().get("automation"):
        raise BadRequest("durationSeconds can only be set by the automation client; the storefront's holds last 600 s")
    if isinstance(requested, bool) or not isinstance(requested, int) or not MIN_DURATION_SECONDS <= requested <= DEFAULT_DURATION_SECONDS:
        raise BadRequest(f"durationSeconds must be an integer from {MIN_DURATION_SECONDS} to {DEFAULT_DURATION_SECONDS}")
    return requested


def price_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Name and unit price from the inventory table (shown at checkout; the order is priced again when placed)."""
    priced, unknown = [], []
    for item in items:
        product = inventory_table.get_item(Key={"productId": item["productId"]}).get("Item")
        if product is None:
            unknown.append(item["productId"])
            continue
        priced.append({**item, "name": product["name"], "unitPrice": product["price"]})
    if unknown:
        raise BadRequest(f"Unknown productId(s): {', '.join(unknown)}")
    return priced


# --------------------------------------------------------------------------------------------
# POST /holds
# --------------------------------------------------------------------------------------------
def create_hold(caller: Caller, body: dict[str, Any], log: StructuredLogger) -> dict[str, Any]:
    items = price_items(validate_items(body))
    duration = hold_duration(caller, body)
    for _ in range(CREATE_ATTEMPTS):
        release_current(caller, "replaced by a new hold", log)
        hold = new_hold(caller, items, duration)
        hlog = log.bind(holdId=hold["holdId"])
        create_schedule(hold)
        if write_hold(hold, hlog):
            hlog.info(
                "Hold created",
                holdEvent="created",
                holdStatus=ACTIVE,
                durationSeconds=duration,
                items=[(i["productId"], i["quantity"]) for i in items],
            )
            return public_view(hold)
        # Another request by the same user created a hold at the same moment: release it and try again.
        delete_schedule(scheduler, SCHEDULE_GROUP, hold["holdId"], hlog)
    raise Conflict("Another hold was being created for you at the same time; please retry")


def new_hold(caller: Caller, items: list[dict[str, Any]], duration: int) -> dict[str, Any]:
    now = time.time()
    expires = int(now) + duration  # whole seconds: at() schedules take second precision
    return {
        "holdId": f"HOLD-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:10]}",
        "userId": caller.user_id,
        "items": items,
        "status": ACTIVE,
        "durationSeconds": duration,
        "expiresAtEpoch": expires,
        "expiresAt": epoch_to_iso(expires),
        "createdAt": utc_now_iso(),
        "updatedAt": utc_now_iso(),
        "purgeAt": expires + PURGE_AFTER_SECONDS,  # DynamoDB TTL: clean-up only, never the release mechanism
    }


def create_schedule(hold: dict[str, Any]) -> None:
    at = datetime.fromtimestamp(int(hold["expiresAtEpoch"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    scheduler.create_schedule(
        Name=hold["holdId"],
        GroupName=SCHEDULE_GROUP,
        Description=f"Expire checkout hold {hold['holdId']} and return its stock",
        ScheduleExpression=f"at({at})",
        ScheduleExpressionTimezone="UTC",
        FlexibleTimeWindow={"Mode": "OFF"},  # fire at the exact time, not within a window
        ActionAfterCompletion="DELETE",  # the schedule removes itself after it fires
        Target={
            "Arn": EXPIRY_FUNCTION_ARN,
            "RoleArn": SCHEDULER_ROLE_ARN,
            "Input": json.dumps({"holdId": hold["holdId"]}),
            "RetryPolicy": {"MaximumRetryAttempts": 10, "MaximumEventAgeInSeconds": 3600},
        },
    )


def write_hold(hold: dict[str, Any], log: StructuredLogger) -> bool:
    """The all-or-nothing hold transaction. False = the user's pointer appeared meanwhile (a concurrent create)."""
    stock_updates = [
        {
            "Update": {
                "TableName": INVENTORY_TABLE,
                "Key": {"productId": item["productId"]},
                "UpdateExpression": "SET stock = stock - :qty, held = if_not_exists(held, :zero) + :qty",
                "ConditionExpression": "attribute_exists(productId) AND stock >= :qty",
                "ExpressionAttributeValues": {":qty": item["quantity"], ":zero": 0},
            }
        }
        for item in hold["items"]
    ]
    try:
        ddb_client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": HOLDS_TABLE,
                        "Item": {"holdId": pointer_key(hold["userId"]), "activeHoldId": hold["holdId"], "updatedAt": hold["createdAt"]},
                        "ConditionExpression": "attribute_not_exists(holdId)",
                    }
                },
                {"Put": {"TableName": HOLDS_TABLE, "Item": hold, "ConditionExpression": "attribute_not_exists(holdId)"}},
                *stock_updates,
            ]
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        codes = cancellation_codes(err.response)
        if codes and codes[0] == "ConditionalCheckFailed":
            return False
        delete_schedule(scheduler, SCHEDULE_GROUP, hold["holdId"], log)
        short = [hold["items"][i]["productId"] for i, code in enumerate(codes[2:]) if code == "ConditionalCheckFailed"]
        product_id = short[0] if short else hold["items"][0]["productId"]
        available = int(inventory_table.get_item(Key={"productId": product_id}, ConsistentRead=True)["Item"]["stock"])
        log.info("Hold refused: not enough stock", productId=product_id, available=available)
        raise Conflict(f"Not enough stock to hold {product_id} (available: {available})", productId=product_id, available=available) from err
    return True


# --------------------------------------------------------------------------------------------
# GET /holds/current, DELETE /holds/{holdId}
# --------------------------------------------------------------------------------------------
def load_current(caller: Caller) -> dict[str, Any] | None:
    pointer = holds_table.get_item(Key={"holdId": pointer_key(caller.user_id)}, ConsistentRead=True).get("Item")
    if not pointer:
        return None
    return holds_table.get_item(Key={"holdId": pointer["activeHoldId"]}, ConsistentRead=True).get("Item")


def current_hold(caller: Caller, log: StructuredLogger) -> dict[str, Any] | None:
    hold = load_current(caller)
    if hold and is_overdue(hold):
        finish(hold, EXPIRED, "expired (checked on read, before its schedule fired)", log)
        return None
    return public_view(hold) if hold and hold["status"] == ACTIVE else None


def release_current(caller: Caller, reason: str, log: StructuredLogger) -> None:
    pointer = holds_table.get_item(Key={"holdId": pointer_key(caller.user_id)}, ConsistentRead=True).get("Item")
    if not pointer:
        return
    hold = holds_table.get_item(Key={"holdId": pointer["activeHoldId"]}, ConsistentRead=True).get("Item")
    if hold and hold["status"] == ACTIVE:
        finish(hold, EXPIRED if is_overdue(hold) else RELEASED, reason, log)
        return
    # The pointer and the hold always change in one transaction, so this "can't happen"; if it ever does, a
    # stale pointer must not block the user's holds forever. Delete it only if it still names that hold.
    log.warning("Removing a stale hold pointer", activeHoldId=pointer["activeHoldId"])
    try:
        holds_table.delete_item(
            Key={"holdId": pointer_key(caller.user_id)},
            ConditionExpression="activeHoldId = :h",
            ExpressionAttributeValues={":h": pointer["activeHoldId"]},
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def release_hold(caller: Caller, hold_id: str, log: StructuredLogger) -> dict[str, Any]:
    hold = holds_table.get_item(Key={"holdId": hold_id}, ConsistentRead=True).get("Item") if hold_id.startswith("HOLD-") else None
    if not hold or hold.get("userId") != caller.user_id:
        return response(404, {"error": "Hold not found"})  # someone else's hold looks exactly like a missing one
    if hold["status"] == ACTIVE:
        finish(hold, EXPIRED if is_overdue(hold) else RELEASED, "released by the user", log)
        hold = holds_table.get_item(Key={"holdId": hold_id}, ConsistentRead=True)["Item"]
    return response(200, public_view(hold))


def finish(hold: dict[str, Any], status: str, reason: str, log: StructuredLogger) -> None:
    """End an ACTIVE hold (stock back) and drop its schedule. Losing the race to another transition is fine."""
    hlog = log.bind(holdId=hold["holdId"])
    detail: dict[str, Any] = {"endReason": reason}
    if status == EXPIRED:
        detail.update(expiredBy="lazy check", expiryLagMs=int((time.time() - float(hold["expiresAtEpoch"])) * 1000))
    if end_hold(ddb_client, HOLDS_TABLE, INVENTORY_TABLE, hold, status, detail):
        hlog.info(
            f"Hold {status.lower()}",
            holdEvent=status.lower(),
            holdStatus=status,
            reason=reason,
            items=[(i["productId"], i["quantity"]) for i in hold["items"]],
        )
    else:
        hlog.info("Hold had already ended (no-op)", wanted=status)
    delete_schedule(scheduler, SCHEDULE_GROUP, hold["holdId"], hlog)

