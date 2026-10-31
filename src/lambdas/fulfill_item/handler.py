"""Saga step (one Map iteration): pick and pack ONE order line in the (simulated) warehouse.

Runs after the payment succeeded, once per line, inside the state machine's inline Map "FulfillItems". Reservation
stays atomic and all-or-nothing (ReserveInventory); fulfillment is per line, because in a real warehouse one item
can turn out damaged or missing after the customer has paid. That line is then refunded and written off on its own,
and the rest of the order still ships.

  Picked  -> ONE transaction: the line's `fulfillment` = FULFILLED (+ ITEM_FULFILLED in the history), and the
             product's units move `reserved` -> `sold`. Conditional on the line not being handled yet, so a retry
             (or a re-run of the execution) never moves stock twice: it just reports FULFILLED again.
  Missing -> raises ItemUnavailable. The Map iteration catches it and returns {lineId, status: UNAVAILABLE, reason};
             the refund and the write-off happen after the Map, for all unavailable lines together.

Demo control: simulate = "item_unavailable" makes the line named by the order's `simulateLine` unavailable
(1 = the first line, L1; "all" = every line; default: the last line).

Concurrency: up to MaxConcurrency lines of the SAME order update that order item at once. DynamoDB rejects a
transaction that collides with another one in flight (TransactionConflict); those are retried here with jitter, and
FulfillmentTransientError (retried by Step Functions) is raised only if they keep colliding.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common import chaos
from common.logger import StructuredLogger, get_logger
from common.orders import ITEM_FULFILLED, LINE_FULFILLED, LINE_WRITTEN_OFF, cancellation_codes, find_line, history_entry, order_lines
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
ddb_client = dynamodb.meta.client
logger = get_logger("fulfill_item")

CONFLICT_ATTEMPTS = 4


class ItemUnavailable(Exception):
    """This line can't be fulfilled (damaged, missing). Caught by its own Map iteration, never by the whole Map."""


class FulfillmentTransientError(Exception):
    """A temporary failure (here: transaction conflicts that kept recurring). Step Functions retries it."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id, line_id = event["orderId"], event["lineId"]
    log = logger.bind(orderId=order_id, lineId=line_id)
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    line = find_line(order, line_id)

    if line.get("fulfillment") == LINE_FULFILLED:
        log.info("Line already fulfilled (retry or re-run); nothing to do")
        return {"orderId": order_id, "lineId": line_id, "status": LINE_FULFILLED}
    if line.get("fulfillment") == LINE_WRITTEN_OFF:
        raise ItemUnavailable(f"{line['name']} (line {line_id}) was already written off")
    if line_id in simulated_unavailable(order):
        log.warning("Item unavailable (simulated)", fulfillmentEvent="unavailable")
        raise ItemUnavailable(f"{line['name']} (line {line_id}) was found damaged in the warehouse (simulated)")

    if pick(order_id, line, log):
        log.info("Line fulfilled", fulfillmentEvent="fulfilled", productId=line["productId"], quantity=line["quantity"])
        chaos.crash_after_write(order, "fulfill", log)  # E3 test switch: inert unless CHAOS_ENABLED
    return {"orderId": order_id, "lineId": line_id, "status": LINE_FULFILLED}


def simulated_unavailable(order: dict[str, Any]) -> set[str]:
    """The line ids the demo flag makes unavailable: simulateLine 1..n, "all", or (default) the last line."""
    if order.get("simulate") != "item_unavailable":
        return set()
    line_ids = [line["lineId"] for line in order_lines(order)]
    target = order.get("simulateLine")
    if target == "all":
        return set(line_ids)
    if target is None:
        return {line_ids[-1]}
    return {line_ids[int(target) - 1]}


def pick(order_id: str, line: dict[str, Any], log: StructuredLogger) -> bool:
    """reserved -> sold for this line, and the line marked FULFILLED, atomically. False = it was already handled."""
    index, quantity = line["index"], line["quantity"]
    now = utc_now_iso()
    detail = f"Picked and packed {quantity} x {line['name']} (line {line['lineId']})"
    transact_items = [
        {
            "Update": {
                "TableName": ORDERS_TABLE,
                "Key": {"orderId": order_id},
                "UpdateExpression": (
                    f"SET #items[{index}].fulfillment = :fulfilled, #items[{index}].fulfilledAt = :now, "
                    "updatedAt = :now, statusHistory = list_append(statusHistory, :entry)"
                ),
                "ConditionExpression": f"attribute_exists(orderId) AND attribute_not_exists(#items[{index}].fulfillment)",
                "ExpressionAttributeNames": {"#items": "items"},
                "ExpressionAttributeValues": {":fulfilled": LINE_FULFILLED, ":now": now, ":entry": [history_entry(ITEM_FULFILLED, detail, now)]},
            }
        },
        {
            "Update": {
                "TableName": INVENTORY_TABLE,
                "Key": {"productId": line["productId"]},
                "UpdateExpression": "SET reserved = reserved - :qty, sold = if_not_exists(sold, :zero) + :qty",
                "ConditionExpression": "attribute_exists(productId) AND reserved >= :qty",
                "ExpressionAttributeValues": {":qty": quantity, ":zero": 0},
            }
        },
    ]
    for attempt in range(1, CONFLICT_ATTEMPTS + 1):
        try:
            ddb_client.transact_write_items(TransactItems=transact_items)
            return True
        except ClientError as err:
            if err.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = cancellation_codes(err.response)
            if codes and codes[0] == "ConditionalCheckFailed":
                log.info("Line was handled by an earlier attempt; idempotent no-op")
                return False
            if len(codes) > 1 and codes[1] == "ConditionalCheckFailed":
                # Not reserved: the stock bookkeeping is broken for this order. Never sell what isn't reserved.
                raise RuntimeError(f"{line['productId']}: fewer than {quantity} units reserved; refusing to pick") from err
            if "TransactionConflict" not in codes:
                raise
            log.info("Transaction conflict with another line of this order; retrying", attempt=attempt)
            time.sleep(random.uniform(0.05, 0.2) * attempt)
    raise FulfillmentTransientError(f"Line {line['lineId']} kept conflicting with other updates of order {order_id}")
