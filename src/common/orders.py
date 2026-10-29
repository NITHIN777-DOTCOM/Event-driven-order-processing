"""Order domain helpers: status values and the shared "change status" DynamoDB update."""

from __future__ import annotations

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

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED})

# History-only events: appended to statusHistory WITHOUT changing `status` (the order stays PENDING).
DELIVERY_RETRY = "DELIVERY_RETRY"  # an SQS delivery attempt failed and SQS will retry it
DEAD_LETTERED = "DEAD_LETTERED"  # final attempt failed; SQS moves the message to the DLQ


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
