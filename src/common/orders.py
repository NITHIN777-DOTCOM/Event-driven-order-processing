"""Order domain helpers: status values, order lines, and the shared "change status" DynamoDB update."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.timeutil import utc_now_iso

# Order lifecycle. Every change is also appended to the order's statusHistory list.
PENDING = "PENDING"  # accepted by the API, waiting on the queue
PROCESSING = "PROCESSING"  # Step Functions execution started
RESERVED = "RESERVED"  # stock reserved for every item
PAYMENT_RETRY = "PAYMENT_RETRY"  # a transient payment failure; Step Functions will retry
PAYMENT_PENDING = "PAYMENT_PENDING"  # payment requested from the provider; the saga waits for its webhook
PAYMENT_CAPTURED = "PAYMENT_CAPTURED"  # (simulated) payment succeeded
PAYMENT_DECLINED = "PAYMENT_DECLINED"  # permanent payment failure; compensation follows
OUT_OF_STOCK = "OUT_OF_STOCK"  # reservation impossible; nothing was reserved
PAYMENT_REFUNDED = "PAYMENT_REFUNDED"  # compensation: wallet debit refunded
INVENTORY_RELEASED = "INVENTORY_RELEASED"  # compensation: reserved stock given back
COMPLETED = "COMPLETED"  # terminal: success (written by the state machine itself)
FAILED = "FAILED"  # terminal: failure (written by the state machine itself)

PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"  # terminal: some lines delivered, the others refunded (step 2.3)

# Customer cancellation (step 2.4).
FULFILLING = "FULFILLING"  # BeginFulfillment: the warehouse started; from here on the order can't be cancelled
CANCEL_REQUESTED = "CANCEL_REQUESTED"  # the customer cancelled; the saga is refunding and releasing the stock
CANCELLED = "CANCELLED"  # terminal: cancelled by the customer, nothing charged (or all of it refunded), stock back

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, PARTIALLY_FULFILLED, CANCELLED})

# The cancel window. Before payment: no money has moved yet. Paid but not yet fulfilling: refund everything.
# PENDING / PROCESSING are not in it: the saga hasn't reserved the stock yet (that takes well under a second).
AWAITING_PAYMENT = frozenset({RESERVED, PAYMENT_RETRY, PAYMENT_PENDING})
CANCELLABLE_STATUSES = AWAITING_PAYMENT | {PAYMENT_CAPTURED}

# History-only events: appended to statusHistory WITHOUT changing `status` (the order stays PENDING).
DELIVERY_RETRY = "DELIVERY_RETRY"  # an SQS delivery attempt failed and SQS will retry it
DEAD_LETTERED = "DEAD_LETTERED"  # final attempt failed; SQS moves the message to the DLQ
ITEM_FULFILLED = "ITEM_FULFILLED"  # one line picked and packed (step 2.3)
LINE_REFUNDED = "LINE_REFUNDED"  # one line's amount refunded to the wallet
ITEM_WRITTEN_OFF = "ITEM_WRITTEN_OFF"  # one line's units written off (damaged / lost), not back on sale
CANCEL_REJECTED = "CANCEL_REJECTED"  # a cancel arrived after fulfillment started (recorded once, step 2.4)

# Per-line fulfillment, stored on the order line as `fulfillment` (absent = reserved, not handled yet).
LINE_FULFILLED = "FULFILLED"
LINE_WRITTEN_OFF = "WRITTEN_OFF"


def line_id_for(index: int) -> str:
    """Line ids are positional and stable: the first line is L1. They name the line in refunds and write-offs."""
    return f"L{index + 1}"


def line_amount(item: dict[str, Any]) -> Decimal:
    """What the customer paid for one line: quantity x the unit price the SERVER stored when the order was created."""
    return (Decimal(item["quantity"]) * Decimal(str(item["unitPrice"]))).quantize(Decimal("0.01"))


def order_lines(order: dict[str, Any]) -> list[dict[str, Any]]:
    """The order's lines with their index, id and amount. Orders created before step 2.3 have no stored lineId or
    lineAmount; for them both are derived exactly the same way, so every order can be fulfilled line by line."""
    lines = []
    for index, item in enumerate(order["items"]):
        lines.append(
            {
                **item,
                "index": index,
                "lineId": item.get("lineId") or line_id_for(index),
                "lineAmount": Decimal(str(item.get("lineAmount") or line_amount(item))),
            }
        )
    return lines


def public_lines(order: dict[str, Any]) -> list[dict[str, Any]]:
    """The lines as the API returns them (GET /orders, GET /orders/{id}): id, amount, fulfillment, refund."""
    return [{key: value for key, value in line.items() if key != "index"} for line in order_lines(order)]


def find_line(order: dict[str, Any], line_id: str) -> dict[str, Any]:
    for line in order_lines(order):
        if line["lineId"] == line_id:
            return line
    raise KeyError(f"Order {order['orderId']} has no line {line_id}")


def history_entry(status: str, detail: str, timestamp: str | None = None) -> dict[str, str]:
    """One element of statusHistory: {status, timestamp, detail}."""
    return {"status": status, "timestamp": timestamp or utc_now_iso(), "detail": detail}


def status_update(
    status: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    condition: str | None = None,
    condition_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build UpdateItem arguments that change an order's status.

    In one atomic write it sets `status`, bumps `updatedAt`, appends a statusHistory entry and
    sets any `extra` attributes (e.g. executionArn, paymentId). The result can be passed to
    `Table.update_item(Key=..., **status_update(...))` or used as a TransactWriteItems "Update".

    The update only applies if the order exists, which stops a stray message from creating a
    half-empty "ghost" order. Callers can AND in their own `condition` (it may use `#status`)
    to make the write idempotent, e.g. "only if still PENDING".
    """
    now = utc_now_iso()
    names = {"#status": "status"}
    values: dict[str, Any] = {
        ":status": status,
        ":now": now,
        ":entry": [history_entry(status, detail, now)],
    }
    assignments = [
        "#status = :status",
        "updatedAt = :now",
        "statusHistory = list_append(statusHistory, :entry)",
    ]
    for index, (attribute, value) in enumerate((extra or {}).items()):
        names[f"#x{index}"] = attribute
        values[f":x{index}"] = value
        assignments.append(f"#x{index} = :x{index}")

    condition_expression = "attribute_exists(orderId)"
    if condition:
        condition_expression += f" AND ({condition})"
        values.update(condition_values or {})

    return {
        "UpdateExpression": "SET " + ", ".join(assignments),
        "ConditionExpression": condition_expression,
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": values,
    }


def history_event(
    event: str, detail: str, extra: dict[str, Any] | None = None, condition: str | None = None
) -> dict[str, Any]:
    """UpdateItem arguments that append one statusHistory entry WITHOUT changing `status`.

    Used for events that the tracker should show, but that aren't order states, such as failed
    SQS delivery attempts of a poison message, or a refund recorded after the order already FAILED.
    `condition` is ANDed in (e.g. "attribute_not_exists(refunded)" makes the write happen once).
    """
    now = utc_now_iso()
    names: dict[str, str] = {}
    values: dict[str, Any] = {":now": now, ":entry": [history_entry(event, detail, now)]}
    assignments = ["updatedAt = :now", "statusHistory = list_append(statusHistory, :entry)"]
    for index, (attribute, value) in enumerate((extra or {}).items()):
        names[f"#x{index}"] = attribute
        values[f":x{index}"] = value
        assignments.append(f"#x{index} = :x{index}")
    args: dict[str, Any] = {
        "UpdateExpression": "SET " + ", ".join(assignments),
        "ConditionExpression": "attribute_exists(orderId)" + (f" AND ({condition})" if condition else ""),
        "ExpressionAttributeValues": values,
    }
    if names:
        args["ExpressionAttributeNames"] = names
    return args


def cancellation_codes(error_response: dict[str, Any]) -> list[str]:
    """Per-item failure codes from a TransactionCanceledException, in TransactItems order."""
    return [reason.get("Code", "None") for reason in error_response.get("CancellationReasons") or []]
