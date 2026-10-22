"""GET /orders/{id}: return an order, including its statusHistory timeline."""

from __future__ import annotations

import os
import re
from typing import Any

import boto3

from common.http import response
from common.logger import get_logger

ORDERS_TABLE = os.environ["ORDERS_TABLE"]

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
logger = get_logger("get_order")

ORDER_ID_PATTERN = re.compile(r"^ORD-\d{8}-[0-9a-f]{8}$")


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

    log.info("Order returned", status=order["status"])
    return response(200, order)
