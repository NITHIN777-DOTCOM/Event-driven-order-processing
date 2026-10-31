"""Saga step: write off the units of order lines that couldn't be fulfilled (damaged or lost in the warehouse).

A written-off unit does NOT go back on sale: it moves from `reserved` to `writtenOff` on the product, so stock
conservation still adds up (I5: seeded = available + held + reserved + sold + writtenOff). Every write-off leaves
an audit record in order-saga-write-offs (orderId, lineId, productId, quantity, reason, writtenOffAt).

Idempotent per (orderId, lineId): the audit record is put with attribute_not_exists in the SAME transaction as the
stock move and the order update, so a retry or a re-run can't write off a unit twice.

Input: {"orderId", "lines": [{"lineId", "reason"}]} (the unavailable lines from the Map, with why).
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
from common.orders import ITEM_WRITTEN_OFF, LINE_FULFILLED, LINE_WRITTEN_OFF, cancellation_codes, find_line, history_entry
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]
WRITE_OFFS_TABLE = os.environ["WRITE_OFFS_TABLE"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
ddb_client = dynamodb.meta.client
logger = get_logger("write_off_lines")

CONFLICT_ATTEMPTS = 4


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = event["orderId"]
    log = logger.bind(orderId=order_id)
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    chaos.inject_fault("write_off_lines", lambda: order.get("chaosRun"), log)  # E1/E5 fault injection (common/chaos.py)

    written_off, units = [], 0
    for request in event["lines"]:
        line = find_line(order, request["lineId"])
        if line.get("fulfillment") == LINE_FULFILLED:
            # A delivered line is never written off; if this happens, the Map's result is wrong. Fail loudly.
            raise RuntimeError(f"Line {line['lineId']} of {order_id} was fulfilled; it can't be written off")
        reason = str(request.get("reason") or "unavailable")[:300]
        if write_off(order_id, line, reason, log.bind(lineId=line["lineId"])):
            units += int(line["quantity"])
        written_off.append(line["lineId"])
    if units:
        chaos.crash_after_write(order, "write_off", log)  # E3 test switch (only when this call wrote something off)
    return {"orderId": order_id, "writtenOffLineIds": written_off, "unitsWrittenOff": units}


def write_off(order_id: str, line: dict[str, Any], reason: str, log: StructuredLogger) -> bool:
    """Audit record + reserved -> writtenOff + the line marked WRITTEN_OFF, atomically. False = done before."""
    index, quantity, now = line["index"], line["quantity"], utc_now_iso()
    detail = f"{quantity} x {line['name']} (line {line['lineId']}) written off: {reason}"
    transact_items = [
        {
            "Put": {
                "TableName": WRITE_OFFS_TABLE,
                "Item": {
                    "orderId": order_id,
                    "lineId": line["lineId"],
                    "productId": line["productId"],
                    "quantity": quantity,
                    "unitPrice": line["unitPrice"],
                    "reason": reason,
                    "writtenOffAt": now,
                },
                "ConditionExpression": "attribute_not_exists(lineId)",
            }
        },
        {
            "Update": {
                "TableName": INVENTORY_TABLE,
                "Key": {"productId": line["productId"]},
                "UpdateExpression": "SET reserved = reserved - :qty, writtenOff = if_not_exists(writtenOff, :zero) + :qty",
                "ConditionExpression": "attribute_exists(productId) AND reserved >= :qty",
                "ExpressionAttributeValues": {":qty": quantity, ":zero": 0},
            }
        },
        {
            "Update": {
                "TableName": ORDERS_TABLE,
                "Key": {"orderId": order_id},
                "UpdateExpression": (
                    f"SET #items[{index}].fulfillment = :writtenOff, #items[{index}].writeOffReason = :reason, "
                    "updatedAt = :now, statusHistory = list_append(statusHistory, :entry)"
                ),
                "ConditionExpression": f"attribute_exists(orderId) AND attribute_not_exists(#items[{index}].fulfillment)",
                "ExpressionAttributeNames": {"#items": "items"},
                "ExpressionAttributeValues": {
                    ":writtenOff": LINE_WRITTEN_OFF,
                    ":reason": reason,
                    ":now": now,
                    ":entry": [history_entry(ITEM_WRITTEN_OFF, detail, now)],
                },
            }
        },
    ]
    for attempt in range(1, CONFLICT_ATTEMPTS + 1):
        try:
            ddb_client.transact_write_items(TransactItems=transact_items)
            log.info("Line written off", fulfillmentEvent="written_off", productId=line["productId"], quantity=int(quantity), reason=reason)
            return True
        except ClientError as err:
            if err.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = cancellation_codes(err.response)
            if codes and codes[0] == "ConditionalCheckFailed":
                log.info("Line already written off; idempotent no-op")
                return False
            if "TransactionConflict" not in codes:
                raise
            log.info("Transaction conflict; retrying", attempt=attempt)
            time.sleep(random.uniform(0.05, 0.2) * attempt)
    raise RuntimeError(f"Write-off of line {line['lineId']} kept conflicting with other updates of order {order_id}")
