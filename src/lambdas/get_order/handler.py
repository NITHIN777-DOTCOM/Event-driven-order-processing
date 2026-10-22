"""GET /orders/{id}: return an order with its statusHistory, plus a human-readable live feed and
AWS Console deep links for the storefront's order tracker."""

from __future__ import annotations

import os
import re
from typing import Any

import boto3

from common.feed import build_feed, console_links
from common.http import response
from common.logger import get_logger
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
WORKFLOW_LOG_GROUP = os.environ.get("WORKFLOW_LOG_GROUP", "/aws/vendedlogs/states/order-saga-workflow")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
logger = get_logger("get_order")

ORDER_ID_PATTERN = re.compile(r"^ORD-\d{8}-[0-9a-f]{8}$")
# Internal attributes that the client doesn't need.
HIDDEN_ATTRIBUTES = ("gsi1pk", "gsi1sk", "idempotencyKey", "reservedItems")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = (event.get("pathParameters") or {}).get("id", "")
    log = logger.bind(orderId=order_id, requestId=event.get("requestContext", {}).get("requestId"))

    if not ORDER_ID_PATTERN.match(order_id):
        log.warning("Malformed order id")
        return response(400, {"error": "Order id must look like ORD-YYYYMMDD-xxxxxxxx"})

    # A strongly consistent read means a client polling for status always sees the latest write.
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item")
    if order is None:
        log.info("Order not found")
        return response(404, {"error": f"Order {order_id} not found"})

    body = {key: value for key, value in order.items() if key not in HIDDEN_ATTRIBUTES}
    body["feed"] = build_feed(order)
    body["consoleLinks"] = console_links(order, REGION, ORDERS_TABLE, WORKFLOW_LOG_GROUP)

    log.info("Order returned", status=order["status"])
    return response(200, body)
