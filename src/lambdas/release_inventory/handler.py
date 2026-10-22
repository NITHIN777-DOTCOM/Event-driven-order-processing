"""Saga compensation: give back the stock this order reserved.

Step Functions runs this step when a later step (payment) fails after stock was reserved.
It must be IDEMPOTENT, because Step Functions may retry it and a person may re-run it:
  - it releases only what the order recorded in `reservedItems`
  - one transaction does the release and sets `released = true`, and the transaction only
    goes through if the order is not already released
So running it twice never double-releases stock.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import get_logger
from common.orders import INVENTORY_RELEASED, cancellation_codes, status_update
from common.tracing import instrument_aws_sdk

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

    if not release(order_id, reserved_items):
        log.info("A concurrent run already released this order (idempotent no-op)")
        return {"orderId": order_id, "released": False, "reason": "already released"}

    log.info("Inventory released", items=[(i["productId"], i["quantity"]) for i in reserved_items])
    return {"orderId": order_id, "released": True, "itemCount": len(reserved_items)}


def release(order_id: str, reserved_items: list[dict[str, Any]]) -> bool:
    """Return the reserved stock and mark the order released, atomically.

    Returns False if the order turned out to be already released (another run won the race).
    """
    transact_items: list[dict[str, Any]] = [
        {
            "Update": {
                "TableName": INVENTORY_TABLE,
                "Key": {"productId": item["productId"]},
                "UpdateExpression": "SET stock = stock + :qty, reserved = reserved - :qty",
                "ConditionExpression": "attribute_exists(productId) AND reserved >= :qty",
                "ExpressionAttributeValues": {":qty": item["quantity"]},
            }
        }
        for item in reserved_items
    ]
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
        ddb_client.transact_write_items(TransactItems=transact_items)
    except ClientError as err:
        if err.response["Error"]["Code"] == "TransactionCanceledException":
            codes = cancellation_codes(err.response)
            if codes and codes[-1] == "ConditionalCheckFailed":  # the order condition: already released
                return False
        raise
    return True
