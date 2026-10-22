"""Order domain helpers: status values and the shared "change status" DynamoDB update."""

from __future__ import annotations

from typing import Any

from common.timeutil import utc_now_iso

# Order lifecycle. Every change is also appended to the order's statusHistory list.
PENDING = "PENDING"  # accepted by the API, waiting on the queue
PROCESSING = "PROCESSING"  # Step Functions execution started
RESERVED = "RESERVED"  # stock reserved for every item
PAYMENT_CAPTURED = "PAYMENT_CAPTURED"  # (simulated) payment succeeded
COMPLETED = "COMPLETED"  # terminal: success (written by the state machine itself)
FAILED = "FAILED"  # terminal: failure (Phase 2)

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED})


def history_entry(status: str, detail: str, timestamp: str | None = None) -> dict[str, str]:
    """One element of statusHistory: {status, timestamp, detail}."""
    return {"status": status, "timestamp": timestamp or utc_now_iso(), "detail": detail}


def status_update(status: str, detail: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build UpdateItem arguments that change an order's status.

    In one atomic write it sets `status`, bumps `updatedAt`, appends a statusHistory entry and
    sets any `extra` attributes (e.g. executionArn, paymentId). The result can be passed to
    `Table.update_item(Key=..., **status_update(...))` or used as a TransactWriteItems "Update".
    The condition stops a stray message from creating a half-empty "ghost" order.
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

    return {
        "UpdateExpression": "SET " + ", ".join(assignments),
        "ConditionExpression": "attribute_exists(orderId)",
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": values,
    }
