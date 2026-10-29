"""Expire one checkout hold: invoked by its one-time EventBridge Scheduler schedule at the hold's expiresAt.

Event: {"holdId": "HOLD-..."} (the schedule's Input).

In ONE transaction: hold ACTIVE -> EXPIRED, the user's pointer item deleted, and each product's held units go
back to available stock (common/holds.py). Idempotent and race-safe:
  - hold missing, or already CONSUMED / RELEASED / EXPIRED -> no-op (the schedule outlived the hold)
  - a consume or release committing at the same moment -> the conditional status update cancels this whole
    transaction, so stock is never returned twice (invariant I5)
It records how late it ran (expiryLagMs = now - expiresAt), the precision of EventBridge Scheduler.
Errors are raised: Scheduler invokes Lambda asynchronously, Lambda retries twice, and the
order-saga-hold-expiry-errors alarm fires.
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3

from common.holds import ACTIVE, EXPIRED, end_hold
from common.logger import get_logger
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

HOLDS_TABLE = os.environ["HOLDS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]

dynamodb = boto3.resource("dynamodb")
holds_table = dynamodb.Table(HOLDS_TABLE)
ddb_client = dynamodb.meta.client
logger = get_logger("hold_expiry")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    hold_id = event["holdId"]
    log = logger.bind(holdId=hold_id)

    hold = holds_table.get_item(Key={"holdId": hold_id}, ConsistentRead=True).get("Item")
    if not hold:
        log.info("Hold not found; nothing to expire (its creation failed after the schedule was made)")
        return {"holdId": hold_id, "expired": False, "reason": "not found"}
    if hold["status"] != ACTIVE:
        log.info("Hold already ended; nothing to expire (idempotent no-op)", holdStatus=hold["status"])
        return {"holdId": hold_id, "expired": False, "reason": f"already {hold['status']}"}

    lag_ms = int((time.time() - float(hold["expiresAtEpoch"])) * 1000)
    detail = {"endReason": "hold time ran out", "expiredBy": "schedule", "expiryLagMs": lag_ms}
    if not end_hold(ddb_client, HOLDS_TABLE, INVENTORY_TABLE, hold, EXPIRED, detail):
        log.info("Lost the race: the hold was consumed or released at the same moment (no-op)")
        return {"holdId": hold_id, "expired": False, "reason": "lost the race"}

    log.info(
        "Hold expired",
        holdEvent="expired",
        holdStatus=EXPIRED,
        expiryLagMs=lag_ms,
        items=[(i["productId"], i["quantity"]) for i in hold["items"]],
    )
    return {"holdId": hold_id, "expired": True, "expiryLagMs": lag_ms}
