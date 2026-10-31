"""Saga compensation: give back the stock this order reserved.

Step Functions runs this step when a later step (payment) fails after stock was reserved.
It must be IDEMPOTENT, because Step Functions may retry it and a person may re-run it:
  - it releases only what the order recorded in `reservedItems`
  - one transaction does the release and sets `released = true`, and the transaction only
    goes through if the order is not already released
So running it twice never double-releases stock.

Per-line fulfillment (step 2.3): a line can already have left `reserved` when this runs (only if a step after the
Map fails). A FULFILLED line's units are taken back from `sold`; a WRITTEN_OFF line's units stay written off (they
were damaged, not resellable). Every other line goes `reserved` -> `stock` as before.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common import chaos
from common.logger import get_logger
from common.orders import INVENTORY_RELEASED, LINE_FULFILLED, LINE_WRITTEN_OFF, cancellation_codes, order_lines, status_update
from common.tracing import instrument_aws_sdk
from common.transact import transact_write

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
ddb_client = dynamodb.meta.client
logger = get_logger("release_inventory")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = event["orderId"]
    log = logger.bind(orderId=order_id)

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    reserved_items = order.get("reservedItems") or []

    if order.get("released"):
        log.info("Inventory already released; nothing to do (idempotent no-op)")
        return {"orderId": order_id, "released": False, "reason": "already released"}
    if not reserved_items:
        log.info("Nothing was reserved for this order; nothing to release")
        return {"orderId": order_id, "released": False, "reason": "nothing reserved"}

    if not release(order_id, reserved_items, line_states(order)):
        log.info("A concurrent run already released this order (idempotent no-op)")
        return {"orderId": order_id, "released": False, "reason": "already released"}

    log.info("Inventory released", items=[(i["productId"], i["quantity"]) for i in reserved_items])
    chaos.crash_after_write(order, "release", log)  # E3 test switch: inert unless CHAOS_ENABLED
    return {"orderId": order_id, "released": True, "itemCount": len(reserved_items)}


def line_states(order: dict[str, Any]) -> dict[str, str]:
    """productId -> the line's fulfillment state (an order has at most one line per product)."""
    return {line["productId"]: line.get("fulfillment", "") for line in order_lines(order)}


def release(order_id: str, reserved_items: list[dict[str, Any]], states: dict[str, str] | None = None) -> bool:
    """Return the reserved (or already sold) stock and mark the order released, atomically.

    Returns False if the order turned out to be already released (another run won the race).
    """
    states = states or {}
    transact_items: list[dict[str, Any]] = []
    for item in reserved_items:
        state = states.get(item["productId"], "")
        if state == LINE_WRITTEN_OFF:
            continue  # damaged units stay written off
        source = "sold" if state == LINE_FULFILLED else "reserved"
        transact_items.append(
            {
                "Update": {
                    "TableName": INVENTORY_TABLE,
                    "Key": {"productId": item["productId"]},
                    "UpdateExpression": f"SET stock = stock + :qty, {source} = {source} - :qty",
                    "ConditionExpression": f"attribute_exists(productId) AND {source} >= :qty",
                    "ExpressionAttributeValues": {":qty": item["quantity"]},
                }
            }
        )
    transact_items.append(
        {
            "Update": {
                "TableName": ORDERS_TABLE,
                "Key": {"orderId": order_id},
                **status_update(
                    INVENTORY_RELEASED,
                    f"Compensation: released stock for {len(reserved_items)} product(s)",
                    {"released": True},
                    condition="attribute_not_exists(released) OR released = :notReleased",
                    condition_values={":notReleased": False},
                ),
            }
        }
    )

    try:
        transact_write(ddb_client, transact_items)  # retries TransactionConflict (common/transact.py)
    except ClientError as err:
        if err.response["Error"]["Code"] == "TransactionCanceledException":
            codes = cancellation_codes(err.response)
            if codes and codes[-1] == "ConditionalCheckFailed":  # the order condition: already released
                return False
        raise
    return True
