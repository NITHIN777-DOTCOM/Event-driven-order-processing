"""GET /orders?limit=20: the CALLER's most recent orders, newest first.

Queries the orders table's GSI "gsi1" (partition gsi1pk = "USER#<sub>", sort key gsi1sk =
"<createdAt>#<orderId>") with ScanIndexForward=False. One bounded Query in the caller's own partition:
no scan, no filter, and other users' orders are never even read. One partition per user also removes
the old single "ORDER" partition that every order wrote to (a hot key at scale).
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from common.auth import Forbidden, Unauthorized, caller_from
from common.http import response
from common.logger import get_logger
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
ORDERS_INDEX = os.environ.get("ORDERS_INDEX", "gsi1")

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
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
    logger.info("Orders listed", userId=caller.user_id, count=len(orders), limit=limit)
    return response(200, {"orders": orders})
