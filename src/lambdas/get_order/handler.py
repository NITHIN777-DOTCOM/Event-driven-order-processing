"""GET /orders/{id}: return an order with its statusHistory, plus a human-readable live feed and
AWS Console deep links for the storefront's order tracker.

Row-level isolation: only the order's owner (userId == the caller's JWT "sub") can read it. Anyone
else gets the SAME 404 as for an order that doesn't exist, not a 403: a 403 would confirm that the
orderId exists, letting a caller probe for other people's orders. Legacy orders from before step 1.2
have no userId, so they are 404 for everybody."""

from __future__ import annotations

import os
import re
from typing import Any

import boto3

from common.auth import Forbidden, Unauthorized, caller_from
from common.feed import build_feed, console_links
from common.http import response
from common.logger import get_logger
from common.orders import CANCELLABLE_STATUSES, public_lines
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
WORKFLOW_LOG_GROUP = os.environ.get("WORKFLOW_LOG_GROUP", "/aws/vendedlogs/states/order-saga-workflow")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
logger = get_logger("get_order")

ORDER_ID_PATTERN = re.compile(r"^ORD-\d{8}-[0-9a-f]{8}$")
# Internal attributes that the client doesn't need.
HIDDEN_ATTRIBUTES = ("gsi1pk", "gsi1sk", "idempotencyKey", "reservedItems", "userId", "walletId")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = (event.get("pathParameters") or {}).get("id", "")
    log = logger.bind(orderId=order_id, requestId=event.get("requestContext", {}).get("requestId"))
    try:
        caller = caller_from(event)
    except Unauthorized as err:
        return response(401, {"error": str(err)})
    except Forbidden as err:
        return response(403, {"error": str(err)})
    log = log.bind(userId=caller.user_id)

    if not ORDER_ID_PATTERN.match(order_id):
        log.warning("Malformed order id")
        return response(400, {"error": "Order id must look like ORD-YYYYMMDD-xxxxxxxx"})

    # A strongly consistent read means a client polling for status always sees the latest write.
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item")
    if order is None or order.get("userId") != caller.user_id:
        # Same response either way (see the module docstring); the log says which it was.
        log.info("Order not found" if order is None else "Order belongs to another user: answering 404")
        return response(404, {"error": f"Order {order_id} not found"})

    body = {key: value for key, value in order.items() if key not in HIDDEN_ATTRIBUTES}
    # Every line with its id and amount (derived the same way for pre-2.3 orders) and, after fulfillment,
    # its state (FULFILLED / WRITTEN_OFF) and refund.
    body["items"] = public_lines(order)
    body["feed"] = build_feed(order)
    # Step 2.4: whether the tracker shows the Cancel button. The cancel API decides for real (one conditional write);
    # this only hides the button when it would certainly be refused.
    body["canCancel"] = (
        order.get("cancellable") is True and order["status"] in CANCELLABLE_STATUSES and "cancelRequestedAt" not in order
    )
    body["consoleLinks"] = console_links(order, REGION, ORDERS_TABLE, WORKFLOW_LOG_GROUP)

    log.info("Order returned", status=order["status"])
    return response(200, body)
