"""Saga step: start fulfillment, the point after which the customer can no longer cancel (step 2.4).

Runs after the payment succeeded and before the FulfillItems Map. ONE conditional UpdateItem on the order:

    PAYMENT_CAPTURED -> FULFILLING   only if no cancel was committed (attribute_not_exists(cancelRequestedAt))

The cancel API writes the same item with the opposite condition (the order must not be FULFILLING yet), so
DynamoDB decides the race: exactly one of the two writes applies.

  {"outcome": "FULFILLING"}         we won: the warehouse starts; a later cancel gets 409 TOO_LATE_TO_CANCEL
  {"outcome": "CANCEL_REQUESTED"}   the customer won: the state machine's Choice takes the cancel branch
                                    (refund everything, release the stock, CANCELLED)

Idempotent: a retry after a successful attempt finds fulfillmentStartedAt and answers FULFILLING again. Any other
state means the saga's bookkeeping is broken, so it raises (the execution fails loudly, alarm
order-saga-cancellation-errors) instead of guessing.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common import chaos
from common.logger import get_logger
from common.orders import CANCEL_REQUESTED, FULFILLING, PAYMENT_CAPTURED, status_update
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
logger = get_logger("begin_fulfillment")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = event["orderId"]
    log = logger.bind(orderId=order_id)
    chaos.inject_fault(  # E1 fault injection (common/chaos.py); the order is read only while a fault targets us
        "begin_fulfillment",
        lambda: orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item", {}).get("chaosRun"),
        log,
    )
    try:
        orders_table.update_item(
            Key={"orderId": order_id},
            **status_update(
                FULFILLING,
                "Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled",
                {"fulfillmentStartedAt": utc_now_iso()},
                condition="#status = :captured AND attribute_not_exists(cancelRequestedAt)",
                condition_values={":captured": PAYMENT_CAPTURED},
            ),
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return lost_or_repeated(order_id, log)
    log.info("Fulfillment started; cancellation closed", cancelEvent="fulfillment_started")
    return {"orderId": order_id, "outcome": FULFILLING}


def lost_or_repeated(order_id: str, log: Any) -> dict[str, Any]:
    """The condition failed: find out why from the order itself."""
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    if "cancelRequestedAt" in order:
        log.info("Customer cancelled before fulfillment started; taking the cancel branch", status=order["status"])
        return {"orderId": order_id, "outcome": CANCEL_REQUESTED}
    if "fulfillmentStartedAt" in order:
        log.info("Fulfillment already started (retry); idempotent no-op")
        return {"orderId": order_id, "outcome": FULFILLING}
    raise RuntimeError(f"Order {order_id} is {order['status']}, not {PAYMENT_CAPTURED}; refusing to start fulfillment")
