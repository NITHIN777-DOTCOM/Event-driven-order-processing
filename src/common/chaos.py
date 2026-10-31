"""Test-only chaos switches (step 3.2, experiment E3 "crash after write").

What FIS can't do: AWS FIS makes a random percentage of ALL invocations of a function fail or slow down. It can't pick
one order, and it can't pick a point INSIDE a handler, such as "right after the DynamoDB transaction committed, before
the function returns". That moment is the dangerous one: the write happened, but the caller (Step Functions, SQS,
API Gateway) sees a failure and retries. Exactly-once effects then depend on every write being idempotent.

How a switch fires (both conditions, or nothing happens):
  1. the function's environment has CHAOS_ENABLED=true (Terraform variable chaos_enabled, default false), and
  2. the order carries chaos = "crash_after:<point>" (accepted by POST /orders only while chaos is enabled, and
     passed along like `simulate`: to the payment intent and to DemoPay's request).
The function performs its write, then raises ChaosCrashAfterWrite before returning. It fires only in the invocation
that actually performed the write: the retry finds the write done, takes its idempotent path, and returns normally.

With CHAOS_ENABLED unset or "false", crash_after_write() returns at once and nothing else in the handlers changes.
"""

from __future__ import annotations

import os
from typing import Any

# Where a crash can be injected: the write that has just committed when it fires.
POINTS = {
    "reserve": "reserve_inventory: stock reserved (order RESERVED)",
    "debit": "DemoPay: wallet debited (CHARGE record + ledger DEBIT), before the webhook callback",
    "line_refund": "refund_payment: unavailable lines refunded and recorded on the order",
    "full_refund": "refund_payment: the whole remaining charge refunded and recorded",
    "fulfill": "fulfill_item: line picked (reserved -> sold)",
    "write_off": "write_off_lines: lines written off (reserved -> writtenOff + audit record)",
    "release": "release_inventory: reserved stock returned",
    "webhook_capture": "payment_webhook: intent SUCCEEDED + order PAYMENT_CAPTURED, before resuming the saga",
}
PREFIX = "crash_after:"


class ChaosCrashAfterWrite(Exception):
    """Injected on purpose (E3). Step Functions sees the error name "ChaosCrashAfterWrite"."""


def enabled() -> bool:
    """Read on every call (not at import), so a configuration change takes effect on the next invocation."""
    return os.environ.get("CHAOS_ENABLED", "false").lower() == "true"


def valid_value(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX) and value[len(PREFIX):] in POINTS


def crash_point(item: dict[str, Any] | None) -> str | None:
    """The point this order (or intent / DemoPay request) asks to crash at, if chaos is enabled."""
    if not item or not enabled():
        return None
    value = item.get("chaos")
    return value[len(PREFIX):] if valid_value(value) else None


def crash_after_write(item: dict[str, Any] | None, point: str, log: Any = None) -> None:
    """Raise ChaosCrashAfterWrite if `item` asks for a crash at `point` and chaos is enabled. Call it right after the
    write commits, and only in the code path that performed the write."""
    if crash_point(item) != point:
        return
    if log is not None:
        log.warning("CHAOS: crashing after the write, before returning", chaosEvent="crash_after_write", chaosPoint=point)
    raise ChaosCrashAfterWrite(f"Injected crash after write at '{point}' ({POINTS[point]})")
