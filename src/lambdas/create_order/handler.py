"""POST /orders: validate and accept a new order, exactly once per Idempotency-Key.

Flow: read or generate the Idempotency-Key -> validate the body -> replay check -> price the items
from the inventory table -> atomically save {idempotency record + PENDING order} -> 202 Accepted.

Transactional outbox: this function makes exactly ONE write, the DynamoDB transaction. It never sends
to SQS itself. The new order row is the outbox record: the table's stream feeds the EventBridge pipe
order-saga-orders-outbox, which delivers {orderId} to the orders queue (infra/main/outbox.tf). So if
this function crashes right after the commit, the order is still delivered; there is no second write
that can be lost (the old "dual write" was DynamoDB, then SQS SendMessage).

Reserving stock and taking payment happen later, asynchronously, in the Step Functions saga.
That keeps this API fast, and the queue absorbs traffic spikes.

Idempotency: when a client retries (a network timeout, a double-click, a load balancer retry)
with the same Idempotency-Key, it gets the ORIGINAL order back (200, duplicate=true). A second
order is never created (so no second stream INSERT), so it can never be charged twice.
Keys are scoped per user (stored as "<sub>#<key>"): two users who happen to send the same key get
their own orders, and nobody can replay (or probe) someone else's order by guessing a key.

Checkout hold (step 2.2): an optional "holdId" names the caller's checkout hold for exactly these items.
It is rejected (400) if it isn't one of the caller's holds (someone else's looks the same as a missing one), if
its items differ from the order's, or if it was already used by another order. An EXPIRED or RELEASED hold is
accepted: ReserveInventory then reserves the stock afresh (or fails with OutOfStock), so paying a second
after the countdown ends doesn't lose the order.

Identity: the customer is the signed-in caller (userId = JWT "sub", email = the verified "email"
claim), never a field in the body. Any customerEmail the client sends is ignored.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.auth import Caller, Forbidden, Unauthorized, caller_from
from common.http import BadRequest, get_header, parse_json_body, response
from common.logger import StructuredLogger, get_logger
from common.orders import PENDING, cancellation_codes, history_entry, line_amount, line_id_for
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk
from common.wallet import wallet_id_for

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]
IDEMPOTENCY_TABLE = os.environ["IDEMPOTENCY_TABLE"]
HOLDS_TABLE = os.environ["HOLDS_TABLE"]

# Clients are created once per Lambda container and reused across invocations.
dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
inventory_table = dynamodb.Table(INVENTORY_TABLE)
idempotency_table = dynamodb.Table(IDEMPOTENCY_TABLE)
holds_table = dynamodb.Table(HOLDS_TABLE)

logger = get_logger("create_order")

CURRENCY = "INR"
MAX_ITEMS = 20  # well under the DynamoDB transaction limit used by reserve_inventory
MAX_QUANTITY = 50
IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
HOLD_ID_PATTERN = re.compile(r"^HOLD-\d{8}-[0-9a-f]{10}$")
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60  # DynamoDB TTL deletes the record after 24 h
# Demo control: lets the presenter force each failure path of the saga.
SIMULATE_MODES = (
    "none", "payment_declined", "payment_flaky", "out_of_stock", "poison",
    # step 2.1: the asynchronous payment and its webhook
    "payment_timeout", "payment_late", "webhook_duplicate", "webhook_bad_signature",
    # step 2.3: one line (simulateLine: 1..n or "all"; default the last line) is found damaged after payment
    "item_unavailable",
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    log = logger.bind(requestId=event.get("requestContext", {}).get("requestId"))
    try:
        caller = caller_from(event)
    except Unauthorized as err:
        return response(401, {"error": str(err)})
    except Forbidden as err:
        return response(403, {"error": str(err)})
    log = log.bind(userId=caller.user_id)
    try:
        key = idempotency_key_from(event)
        request = validate_request(parse_json_body(event))
    except BadRequest as err:
        log.warning("Rejected order request", reason=str(err))
        return response(400, {"error": str(err)})

    log = log.bind(idempotencyKey=key)
    fingerprint = request_fingerprint(request)
    scoped = scoped_key(caller, key)

    # Fast path: a replayed key returns the original order without touching inventory or the orders table.
    record = idempotency_table.get_item(Key={"idempotencyKey": scoped}, ConsistentRead=True).get("Item")
    if record:
        return replay(record, fingerprint, key, log)

    try:
        check_hold(request, caller)
        order = build_order(request, scoped, caller)
    except BadRequest as err:
        log.warning("Rejected order request", reason=str(err))
        return response(400, {"error": str(err)})

    log = log.bind(orderId=order["orderId"])
    try:
        if not save_order_once(order, scoped, fingerprint):
            # Lost a race with a concurrent request that used the same key: replay the winner.
            record = idempotency_table.get_item(Key={"idempotencyKey": scoped}, ConsistentRead=True)["Item"]
            return replay(record, fingerprint, key, log)
        # No SQS call here: the committed order row reaches the queue via the stream + outbox pipe.
    except Exception:
        log.exception("Failed to accept order")
        return response(500, {"error": "Internal error, please retry with the same Idempotency-Key"})

    log.info(
        "Order accepted",
        totalAmount=order["totalAmount"],
        itemCount=len(order["items"]),
        simulate=order["simulate"],
    )
    return response(
        202,
        {"orderId": order["orderId"], "status": PENDING, "idempotencyKey": key, "duplicate": False},
        headers={IDEMPOTENCY_HEADER: key},
    )


def idempotency_key_from(event: dict[str, Any]) -> str:
    """Return the client's Idempotency-Key header, or generate one (the response returns it)."""
    key = get_header(event, IDEMPOTENCY_HEADER)
    if key is None:
        return str(uuid.uuid4())
    if not IDEMPOTENCY_KEY_PATTERN.match(key):
        raise BadRequest("Idempotency-Key must be 1-128 characters: letters, digits, _ . : -")
    return key


def scoped_key(caller: Caller, key: str) -> str:
    """The idempotency record's real key: per user, so users can't collide with (or replay) each other."""
    return f"{caller.user_id}#{key}"


def request_fingerprint(request: dict[str, Any]) -> str:
    """Hash of the normalised request, so a reused key with a DIFFERENT body can be detected."""
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


def replay(record: dict[str, Any], fingerprint: str, key: str, log: StructuredLogger) -> dict[str, Any]:
    """Answer a repeated Idempotency-Key with the original order (never a new one)."""
    log = log.bind(orderId=record["orderId"])
    if record.get("requestHash") != fingerprint:
        log.warning("Idempotency-Key reused with a different request body")
        return response(409, {"error": "Idempotency-Key was already used with a different request"})

    order = orders_table.get_item(Key={"orderId": record["orderId"]}, ConsistentRead=True)["Item"]
    log.info("Duplicate request: returning the original order", status=order["status"])
    return response(
        200,
        {"orderId": order["orderId"], "status": order["status"], "idempotencyKey": key, "duplicate": True},
        headers={IDEMPOTENCY_HEADER: key, "Idempotent-Replayed": "true"},
    )


def validate_request(body: dict[str, Any]) -> dict[str, Any]:
    """Check the request shape and return a normalised copy. Raises BadRequest.

    customerName is only the delivery name shown on the order. Identity fields (customerEmail, userId,
    walletId) are NOT read from the body: they come from the caller's token in build_order.
    """
    name = body.get("customerName")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise BadRequest("customerName is required (1-100 characters)")

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

    simulate_line = body.get("simulateLine")
    if simulate_line is not None:
        if simulate != "item_unavailable":
            raise BadRequest('simulateLine is only used with simulate "item_unavailable"')
        line_ok = simulate_line == "all" or (
            isinstance(simulate_line, int) and not isinstance(simulate_line, bool) and 1 <= simulate_line <= len(normalised_items)
        )
        if not line_ok:
            raise BadRequest(f'simulateLine must be a line number from 1 to {len(normalised_items)}, or "all"')

    hold_id = body.get("holdId")
    if hold_id is not None and (not isinstance(hold_id, str) or not HOLD_ID_PATTERN.match(hold_id)):
        raise BadRequest("holdId must look like HOLD-YYYYMMDD-<10 hex characters>")

    normalised: dict[str, Any] = {"customerName": name.strip(), "items": normalised_items, "simulate": simulate}
    if simulate_line is not None:
        normalised["simulateLine"] = simulate_line
    if hold_id:
        normalised["holdId"] = hold_id
    return normalised


def check_hold(request: dict[str, Any], caller: Caller) -> None:
    """The holdId must be the caller's own hold, for exactly the order's items, and not already used."""
    hold_id = request.get("holdId")
    if not hold_id:
        return
    hold = holds_table.get_item(Key={"holdId": hold_id}, ConsistentRead=True).get("Item")
    if not hold or hold.get("userId") != caller.user_id:
        raise BadRequest("holdId is not one of your checkout holds")
    held = {i["productId"]: int(i["quantity"]) for i in hold["items"]}
    if held != {i["productId"]: i["quantity"] for i in request["items"]}:
        raise BadRequest("The order's items don't match the checkout hold; hold the cart again")
    if hold["status"] == "CONSUMED":
        raise BadRequest(f"This checkout hold was already used by order {hold.get('orderId')}")


def price_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the product name and current unit price from the inventory table, and number the lines.

    Prices always come from the server and never from the client, so the client can't
    change what it pays. Each line also stores its id (L1, L2, ...) and its amount (quantity x unit price):
    a partial refund (step 2.3) refunds exactly that stored amount, never a figure sent by anyone later.
    """
    priced, unknown = [], []
    for index, item in enumerate(items):
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
                "lineId": line_id_for(index),
                "lineAmount": line_amount({"quantity": item["quantity"], "unitPrice": product["price"]}),
            }
        )
    if unknown:
        raise BadRequest(f"Unknown productId(s): {', '.join(unknown)}")
    return priced


def new_order_id() -> str:
    """Return a readable, sortable ID such as ORD-20261022-1a2b3c4d. It also names the SFN execution."""
    return f"ORD-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"


def build_order(request: dict[str, Any], idempotency_key: str, caller: Caller) -> dict[str, Any]:
    items = price_items(request["items"])
    total = sum((i["lineAmount"] for i in items), Decimal("0"))  # the order total is the sum of its lines
    now = utc_now_iso()
    order_id = new_order_id()
    return {
        "orderId": order_id,
        "idempotencyKey": idempotency_key,
        # Owner, from the verified token only. DemoPay (request_payment, payment_provider) uses walletId, never the email.
        "userId": caller.user_id,
        "walletId": wallet_id_for(caller.user_id),
        "customerName": request["customerName"],
        "customerEmail": caller.email,  # where the SNS confirmation is addressed (verified by Cognito)
        "items": items,
        "totalAmount": total.quantize(Decimal("0.01")),
        "currency": CURRENCY,
        "status": PENDING,
        "statusHistory": [history_entry(PENDING, "Order received via API", now)],
        "simulate": request["simulate"],
        **({"simulateLine": request["simulateLine"]} if "simulateLine" in request else {}),
        **({"holdId": request["holdId"]} if request.get("holdId") else {}),
        "createdAt": now,
        "updatedAt": now,
        # GSI "gsi1": one partition per user, newest first, for GET /orders (no scan, no shared hot key).
        # The orderId suffix keeps two orders in the same millisecond distinct and in a stable order.
        "gsi1pk": f"USER#{caller.user_id}",
        "gsi1sk": f"{now}#{order_id}",
    }


def save_order_once(order: dict[str, Any], key: str, fingerprint: str) -> bool:
    """Atomically claim the idempotency key AND write the order. Returns False if the key is taken.

    Because both writes are in one transaction, there can never be an order without its key
    record, or a key record pointing at an order that doesn't exist.
    """
    try:
        dynamodb.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": IDEMPOTENCY_TABLE,
                        "Item": {
                            "idempotencyKey": key,
                            "orderId": order["orderId"],
                            "requestHash": fingerprint,
                            "createdAt": order["createdAt"],
                            "expiresAt": int(time.time()) + IDEMPOTENCY_TTL_SECONDS,
                        },
                        "ConditionExpression": "attribute_not_exists(idempotencyKey)",
                    }
                },
                {
                    "Put": {
                        "TableName": ORDERS_TABLE,
                        "Item": order,
                        # Protects against a (very unlikely) orderId collision.
                        "ConditionExpression": "attribute_not_exists(orderId)",
                    }
                },
            ]
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "TransactionCanceledException":
            codes = cancellation_codes(err.response)
            if codes and codes[0] == "ConditionalCheckFailed":
                return False
        raise
    return True
