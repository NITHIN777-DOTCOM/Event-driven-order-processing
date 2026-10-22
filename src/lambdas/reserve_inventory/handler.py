"""Saga step 1: reserve stock for every item in the order.

All the stock decrements, plus the order's RESERVED status change, go in ONE DynamoDB
transaction. Either every item is reserved or nothing changes, so stock is never left
partly reserved.

The order records exactly what it reserved (`reservedItems`). The compensation step
(release_inventory) gives back only that, and only once.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import get_logger
from common.orders import OUT_OF_STOCK, RESERVED, cancellation_codes, status_update
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
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

    if order.get("reservedItems"):
        # Step Functions retried after a successful attempt (e.g. a Lambda service error on the
        # response). The stock is already reserved, so don't reserve it again.
        log.info("Stock already reserved for this order; skipping")
    elif order.get("simulate") == "out_of_stock":
        log.warning("Simulated out-of-stock")
        raise record_out_of_stock(order_id, f"Insufficient stock for: {order['items'][0]['productId']} (simulated)")
    else:
        try:
            reserve_stock(order)
        except OutOfStock as err:
            log.warning("Out of stock", reason=str(err))
            raise record_out_of_stock(order_id, str(err)) from err
        log.info("Inventory reserved", items=[(i["productId"], i["quantity"]) for i in order["items"]])

    # Only what later states need goes back to the state machine.
    return {
        "orderId": order_id,
        "customerName": order["customerName"],
        "currency": order["currency"],
        "totalAmount": f"{order['totalAmount']:.2f}",
        "itemsSummary": format_items(order),
        "simulate": order.get("simulate", "none"),
    }


def record_out_of_stock(order_id: str, reason: str) -> OutOfStock:
    """Append OUT_OF_STOCK to the timeline (so the tracker shows WHAT failed) and return the error to raise."""
    orders_table.update_item(Key={"orderId": order_id}, **status_update(OUT_OF_STOCK, reason))
    return OutOfStock(reason)


def reserve_stock(order: dict[str, Any]) -> None:
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
                    f"Reserved stock for {len(items)} product(s)",
                    {"reservedItems": reserved_items, "released": False},
                ),
            }
        }
    )

    try:
        ddb_client.transact_write_items(TransactItems=transact_items)
    except ClientError as err:
        if err.response["Error"]["Code"] != "TransactionCanceledException":
            raise
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
