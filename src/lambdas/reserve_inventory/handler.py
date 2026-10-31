"""Saga step 1: reserve stock for every item in the order.

All the stock decrements, plus the order's RESERVED status change, go in ONE DynamoDB
transaction. Either every item is reserved or nothing changes, so stock is never left
partly reserved.

The order records exactly what it reserved (`reservedItems`). The compensation step
(release_inventory) gives back only that, and only once.

Checkout hold (step 2.2): if the order names a holdId, the hold's units are already set aside, so the step
CONSUMES the hold instead of decrementing stock again: one transaction moves the hold ACTIVE -> CONSUMED, its
units held -> reserved, and the order to RESERVED (common/holds.py, consume_items). If the hold is no longer
ACTIVE (expired, released) or loses a race with its expiry at this very moment, the transaction is cancelled as a
whole and the step falls back to the normal reservation below (which may raise OutOfStock). An ACTIVE hold that is
already past its expiry is expired here first, so its units are available to the fresh reservation.
Orders without a holdId take exactly the old path.

Cancellation stamp (step 2.4): the state machine definition that has a cancel branch passes "cancellable": true,
and only then is the order stamped `cancellable = true` (in the same write that marks it RESERVED). The cancel API
refuses unstamped orders (409 NOT_CANCELLABLE). The stamp therefore records which definition the execution really
runs: an execution that started on an older definition (no cancel branch) can never be cancelled, even if it is
still running after the new definition is deployed.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common import chaos
from common.holds import ACTIVE, EXPIRED, consume_items, delete_schedule, end_hold, is_overdue, lost_the_race
from common.logger import StructuredLogger, get_logger
from common.orders import OUT_OF_STOCK, RESERVED, cancellation_codes, order_lines, status_update
from common.tracing import instrument_aws_sdk
from common.transact import transact_write

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]
HOLDS_TABLE = os.environ["HOLDS_TABLE"]
SCHEDULE_GROUP = os.environ["SCHEDULE_GROUP"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
holds_table = dynamodb.Table(HOLDS_TABLE)
scheduler = boto3.client("scheduler")
# The resource's client accepts plain Python values (no {"S": ...} type wrappers).
ddb_client = dynamodb.meta.client
logger = get_logger("reserve_inventory")


class OutOfStock(Exception):
    """Not enough stock for at least one item.

    Step Functions sees the class name as the error name ("OutOfStock"). The state machine
    catches it and fails the order without running ReleaseInventory, because nothing was reserved.
    """


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = event["orderId"]
    log = logger.bind(orderId=order_id)

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    stamp = {"cancellable": True} if event.get("cancellable") is True else {}

    if order.get("reservedItems"):
        # Step Functions retried after a successful attempt (e.g. a Lambda service error on the
        # response). The stock is already reserved, so don't reserve it again.
        log.info("Stock already reserved for this order; skipping")
    elif order.get("simulate") == "out_of_stock":
        log.warning("Simulated out-of-stock")
        raise record_out_of_stock(order_id, f"Insufficient stock for: {order['items'][0]['productId']} (simulated)")
    elif order.get("holdId") and consume_hold(order, log, stamp):
        chaos.crash_after_write(order, "reserve", log)  # E3 test switch: inert unless CHAOS_ENABLED (common/chaos.py)
    else:
        try:
            reserve_stock(order, fresh_after_hold=bool(order.get("holdId")), stamp=stamp)
        except OutOfStock as err:
            log.warning("Out of stock", reason=str(err))
            raise record_out_of_stock(order_id, str(err)) from err
        log.info("Inventory reserved", items=[(i["productId"], i["quantity"]) for i in order["items"]])
        chaos.crash_after_write(order, "reserve", log)

    # Only what later states need goes back to the state machine.
    return {
        "orderId": order_id,
        "customerName": order["customerName"],
        "currency": order["currency"],
        "totalAmount": f"{order['totalAmount']:.2f}",
        "itemsSummary": format_items(order),
        "simulate": order.get("simulate", "none"),
        # The fulfillment Map iterates over these (step 2.3): one iteration per line.
        "lines": [{"lineId": line["lineId"], "productId": line["productId"], "quantity": line["quantity"]} for line in order_lines(order)],
    }


def record_out_of_stock(order_id: str, reason: str) -> OutOfStock:
    """Append OUT_OF_STOCK to the timeline (so the tracker shows WHAT failed) and return the error to raise."""
    orders_table.update_item(Key={"orderId": order_id}, **status_update(OUT_OF_STOCK, reason))
    return OutOfStock(reason)


def consume_hold(order: dict[str, Any], log: StructuredLogger, stamp: dict[str, Any] | None = None) -> bool:
    """Turn the order's ACTIVE checkout hold into its reservation. False = fall back to a fresh reservation."""
    hold_id = order["holdId"]
    hlog = log.bind(holdId=hold_id)
    hold = holds_table.get_item(Key={"holdId": hold_id}, ConsistentRead=True).get("Item")
    if not hold or hold["status"] != ACTIVE:
        hlog.info("Checkout hold no longer active; reserving stock afresh", holdStatus=(hold or {}).get("status"))
        return False
    if is_overdue(hold):
        # Past its expiry but the schedule hasn't fired yet: expire it now so its units can be reserved afresh.
        detail = {"endReason": "expired before the order was reserved", "expiredBy": "reserve_inventory"}
        if end_hold(ddb_client, HOLDS_TABLE, INVENTORY_TABLE, hold, EXPIRED, detail):
            hlog.info("Hold expired", holdEvent="expired", holdStatus=EXPIRED, reason="overdue at reservation")
        return False

    reserved_items = [{"productId": i["productId"], "quantity": i["quantity"]} for i in order["items"]]
    order_update = {
        "Update": {
            "TableName": ORDERS_TABLE,
            "Key": {"orderId": order["orderId"]},
            **status_update(
                RESERVED,
                f"Reserved stock for {len(reserved_items)} product(s) from checkout hold {hold_id}",
                {"reservedItems": reserved_items, "released": False, **(stamp or {})},
            ),
        }
    }
    try:
        transact_write(ddb_client, [*consume_items(HOLDS_TABLE, INVENTORY_TABLE, hold, order["orderId"]), order_update], hlog)
    except ClientError as err:
        if lost_the_race(err):  # expired or released at this very moment: exactly one of us won
            hlog.info("Hold ended while consuming it (lost the race); reserving stock afresh")
            return False
        raise
    hlog.info("Checkout hold consumed", holdEvent="consumed", holdStatus="CONSUMED", items=[(i["productId"], i["quantity"]) for i in reserved_items])
    delete_schedule(scheduler, SCHEDULE_GROUP, hold_id, hlog)
    return True


def reserve_stock(order: dict[str, Any], fresh_after_hold: bool = False, stamp: dict[str, Any] | None = None) -> None:
    items = order["items"]
    reserved_items = [{"productId": i["productId"], "quantity": i["quantity"]} for i in items]
    transact_items: list[dict[str, Any]] = [
        {
            "Update": {
                "TableName": INVENTORY_TABLE,
                "Key": {"productId": item["productId"]},
                "UpdateExpression": "SET stock = stock - :qty, reserved = reserved + :qty",
                "ConditionExpression": "attribute_exists(productId) AND stock >= :qty",
                "ExpressionAttributeValues": {":qty": item["quantity"]},
            }
        }
        for item in reserved_items
    ]
    transact_items.append(
        {
            "Update": {
                "TableName": ORDERS_TABLE,
                "Key": {"orderId": order["orderId"]},
                **status_update(
                    RESERVED,
                    f"Reserved stock for {len(items)} product(s)"
                    + (f" (checkout hold {order['holdId']} had ended, so reserved afresh)" if fresh_after_hold else ""),
                    {"reservedItems": reserved_items, "released": False, **(stamp or {})},
                ),
            }
        }
    )

    try:
        # Many orders for one product reserve at the same moment: conflicts are retried (common/transact.py).
        transact_write(ddb_client, transact_items, logger.bind(orderId=order["orderId"]))
    except ClientError as err:
        codes = cancellation_codes(err.response)[: len(items)] if err.response["Error"]["Code"] == "TransactionCanceledException" else []
        if "ConditionalCheckFailed" not in codes:
            raise  # not a stock answer (e.g. conflicts that never cleared): fail loudly, never claim "out of stock"
        raise OutOfStock(_describe_shortage(err, items)) from err


def _describe_shortage(err: ClientError, items: list[dict[str, Any]]) -> str:
    """Name the product(s) whose stock condition failed, when DynamoDB reports them."""
    codes = cancellation_codes(err.response)[: len(items)]
    short = [items[i]["productId"] for i, code in enumerate(codes) if code == "ConditionalCheckFailed"]
    return f"Insufficient stock for: {', '.join(short) if short else 'one or more items'}"


def format_items(order: dict[str, Any]) -> str:
    """Return the items as human-readable lines for the customer notification email."""
    currency = order["currency"]
    return "\n".join(
        f"- {item['quantity']} x {item['name']} @ {currency} {item['unitPrice']:.2f}"
        for item in order["items"]
    )
