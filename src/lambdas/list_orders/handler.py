"""GET /orders?limit=20: the CALLER's most recent orders, newest first.

Queries the orders table's GSI "gsi1" (partition gsi1pk = "USER#<sub>", sort key gsi1sk =
"<createdAt>#<orderId>") with ScanIndexForward=False. One bounded Query in the caller's own partition:
no scan, no filter, and other users' orders are never even read. One partition per user also removes
the old single "ORDER" partition that every order wrote to (a hot key at scale).

Line details (step 2.3: each line's amount, fulfillment and refund) are not projected into the index, so they
come from ONE BatchGetItem on the base table, for exactly the orderIds that Query returned. The keys only ever
come from the caller's own partition, so this can't read anyone else's order. (Adding them to the projection
would mean rebuilding the index, during which the list would be unavailable.)
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from common.auth import Forbidden, Unauthorized, caller_from
from common.http import response
from common.logger import get_logger
from common.orders import public_lines
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
ORDERS_INDEX = os.environ.get("ORDERS_INDEX", "gsi1")

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
logger = get_logger("list_orders")

DEFAULT_LIMIT, MAX_LIMIT = 20, 50
# Exactly the attributes the GSI projects (see infra/main/dynamodb.tf).
FIELDS = ("orderId", "createdAt", "status", "simulate", "totalAmount", "currency", "customerName", "deadLettered")


def parse_limit(event: dict[str, Any]) -> int:
    raw = (event.get("queryStringParameters") or {}).get("limit")
    try:
        return max(1, min(MAX_LIMIT, int(raw))) if raw is not None else DEFAULT_LIMIT
    except ValueError:
        return DEFAULT_LIMIT


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        caller = caller_from(event)
    except Unauthorized as err:
        return response(401, {"error": str(err)})
    except Forbidden as err:
        return response(403, {"error": str(err)})
    limit = parse_limit(event)
    page = orders_table.query(
        IndexName=ORDERS_INDEX,
        KeyConditionExpression=Key("gsi1pk").eq(f"USER#{caller.user_id}"),
        ScanIndexForward=False,  # newest first
        Limit=limit,
    )
    orders = [{field: item.get(field) for field in FIELDS} for item in page["Items"]]
    details = line_details([order["orderId"] for order in orders])
    for order in orders:
        detail = details.get(order["orderId"])
        order["items"] = public_lines(detail) if detail else []
        order["refundedAmount"] = (detail or {}).get("refundedAmount")
    logger.info("Orders listed", userId=caller.user_id, count=len(orders), limit=limit)
    return response(200, {"orders": orders})


def line_details(order_ids: list[str]) -> dict[str, dict[str, Any]]:
    """orderId -> {orderId, items, refundedAmount} from the base table (at most 50 keys: one BatchGetItem)."""
    if not order_ids:
        return {}
    request: dict[str, Any] = {
        ORDERS_TABLE: {
            "Keys": [{"orderId": order_id} for order_id in order_ids],
            "ProjectionExpression": "orderId, #items, refundedAmount",
            "ExpressionAttributeNames": {"#items": "items"},
        }
    }
    found: dict[str, dict[str, Any]] = {}
    for attempt in range(1, 4):
        result = dynamodb.batch_get_item(RequestItems=request)
        for item in result["Responses"].get(ORDERS_TABLE, []):
            found[item["orderId"]] = item
        request = result.get("UnprocessedKeys") or {}
        if not request:
            break
        time.sleep(0.05 * attempt)  # throttled keys come back as UnprocessedKeys: retry them shortly
    return found
