"""POST /orders: validate and accept a new order.

Flow: validate the body -> price the items from the inventory table -> save the order as PENDING
-> enqueue {orderId} on SQS -> return 202 Accepted.

Reserving stock and taking payment happen later, asynchronously, in the Step Functions saga.
That keeps this API fast, and the queue absorbs traffic spikes.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

from common.http import BadRequest, parse_json_body, response
from common.logger import get_logger
from common.orders import PENDING, history_entry
from common.timeutil import utc_now_iso

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]
ORDERS_QUEUE_URL = os.environ["ORDERS_QUEUE_URL"]

# Clients are created once per Lambda container and reused across invocations.
dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
inventory_table = dynamodb.Table(INVENTORY_TABLE)
sqs = boto3.client("sqs")

logger = get_logger("create_order")

CURRENCY = "INR"
MAX_ITEMS = 20  # well under the DynamoDB transaction limit used by reserve_inventory
MAX_QUANTITY = 50
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Demo control: lets the presenter force each failure path. Phase 2 implements the non-"none" modes.
SIMULATE_MODES = ("none", "payment_declined", "payment_flaky", "out_of_stock", "poison")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    log = logger.bind(requestId=event.get("requestContext", {}).get("requestId"))
    try:
        request = validate_request(parse_json_body(event))
        order = build_order(request)
    except BadRequest as err:
        log.warning("Rejected order request", reason=str(err))
        return response(400, {"error": str(err)})

    # Phase 2: the Idempotency-Key header is checked here, before anything is written.

    log = log.bind(orderId=order["orderId"])
    try:
        save_order(order)
        enqueue_order(order["orderId"])
    except Exception:
        log.exception("Failed to accept order")
        return response(500, {"error": "Internal error, please retry"})

    log.info(
        "Order accepted",
        totalAmount=order["totalAmount"],
        itemCount=len(order["items"]),
        simulate=order["simulate"],
    )
    return response(202, {"orderId": order["orderId"], "status": PENDING})


def validate_request(body: dict[str, Any]) -> dict[str, Any]:
    """Check the request shape and return a normalised copy. Raises BadRequest."""
    name = body.get("customerName")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise BadRequest("customerName is required (1-100 characters)")

    email = body.get("customerEmail")
    if not isinstance(email, str) or not EMAIL_PATTERN.match(email) or len(email) > 254:
        raise BadRequest("customerEmail must be a valid email address")

    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise BadRequest(f"items must be a list of 1-{MAX_ITEMS} entries")

    normalised_items = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise BadRequest(f"items[{index}] must be an object")
        product_id = item.get("productId")
        quantity = item.get("quantity")
        if not isinstance(product_id, str) or not product_id:
            raise BadRequest(f"items[{index}].productId is required")
        # bool is a subclass of int in Python, so reject it explicitly.
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
            raise BadRequest(f"items[{index}].quantity must be an integer from 1 to {MAX_QUANTITY}")
        # One line per product keeps the stock reservation a simple, single update per product.
        if product_id in seen:
            raise BadRequest(f"productId {product_id} appears more than once; combine the quantities")
        seen.add(product_id)
        normalised_items.append({"productId": product_id, "quantity": quantity})

    simulate = body.get("simulate", "none")
    if simulate not in SIMULATE_MODES:
        raise BadRequest(f"simulate must be one of: {', '.join(SIMULATE_MODES)}")

    return {
        "customerName": name.strip(),
        "customerEmail": email.strip().lower(),
        "items": normalised_items,
        "simulate": simulate,
    }


def price_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the product name and current unit price from the inventory table.

    Prices always come from the server and never from the client, so the client can't
    change what it pays.
    """
    priced, unknown = [], []
    for item in items:
        product = inventory_table.get_item(Key={"productId": item["productId"]}).get("Item")
        if product is None:
            unknown.append(item["productId"])
            continue
        priced.append(
            {
                "productId": item["productId"],
                "name": product["name"],
                "quantity": item["quantity"],
                "unitPrice": product["price"],
            }
        )
    if unknown:
        raise BadRequest(f"Unknown productId(s): {', '.join(unknown)}")
    return priced


def new_order_id() -> str:
    """Return a readable, sortable ID such as ORD-20261022-1a2b3c4d. It also names the SFN execution."""
    return f"ORD-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"


def build_order(request: dict[str, Any]) -> dict[str, Any]:
    items = price_items(request["items"])
    total = sum((Decimal(i["quantity"]) * i["unitPrice"] for i in items), Decimal("0"))
    now = utc_now_iso()
    return {
        "orderId": new_order_id(),
        "customerName": request["customerName"],
        "customerEmail": request["customerEmail"],
        "items": items,
        "totalAmount": total.quantize(Decimal("0.01")),
        "currency": CURRENCY,
        "status": PENDING,
        "statusHistory": [history_entry(PENDING, "Order received via API", now)],
        "simulate": request["simulate"],
        "createdAt": now,
        "updatedAt": now,
    }


def save_order(order: dict[str, Any]) -> None:
    # The condition protects against a (very unlikely) orderId collision overwriting an order.
    orders_table.put_item(Item=order, ConditionExpression="attribute_not_exists(orderId)")


def enqueue_order(order_id: str) -> None:
    sqs.send_message(QueueUrl=ORDERS_QUEUE_URL, MessageBody=json.dumps({"orderId": order_id}))
