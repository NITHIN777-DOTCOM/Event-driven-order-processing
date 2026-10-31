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

Fault injection (experiments E1, E2, E5): the same contract as AWS FIS's Lambda actions, built here because FIS is
not available on this account's AWS Free plan (every FIS call answers SubscriptionRequiredException). The chaos
harness writes ONE fault configuration, s3://<CHAOS_FAULT_BUCKET>/faults/active.json:

    {"run": "E1-1a2b3c", "functions": ["reserve_inventory", ...], "action": "error" | "delay",
     "percent": 30, "delayMs": 25000, "startsAt": "<ISO>", "expiresAt": "<ISO>"}

and a target function, at the start of its work, fails ("error", like FIS invocation-error with preventExecution:
nothing has been written yet) or sleeps ("delay", like FIS invocation-add-delay) for `percent` of its invocations.
Differences from FIS, on purpose:
  * blast radius: only orders created by that harness run are affected (order field chaosRun == run), never a
    storefront order; FIS hits a percentage of ALL invocations;
  * a hard expiry: a configuration running longer than 15 minutes, or past its expiresAt, is ignored, so faults turn
    themselves off even if the harness dies (FIS: the experiment's duration);
  * stop condition: the harness deletes the configuration when the order-saga-invariant-violation alarm fires
    (FIS: a stop-condition alarm on the template). Functions re-read it every 30 s, so a stop takes effect within
    30 s (the FIS extension polls every 60 s).
Also gated by CHAOS_ENABLED: while it is false, inject_fault() returns at once without reading S3 or the order.
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable

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


# ---------------------------------------------------------------------------------------------------------------------
# Fault injection (E1, E2, E5): see the module docstring.
# ---------------------------------------------------------------------------------------------------------------------
FAULT_KEY = "faults/active.json"
MAX_FAULT_SECONDS = 15 * 60  # a configuration may run for 15 minutes at most
MAX_DELAY_MS = 60_000
CACHE_SECONDS = 30  # how often a warm container re-reads the configuration
RUN_ID_MAX = 40

_cache: dict[str, Any] = {"read_at": float("-inf"), "config": None}
_s3 = None


class ChaosInjectedFault(Exception):
    """Injected on purpose (E1/E5). Step Functions sees the error name "ChaosInjectedFault"."""


def valid_run_id(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= RUN_ID_MAX and all(c.isalnum() or c == "-" for c in value)


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def usable_config(config: Any, now: datetime) -> dict[str, Any] | None:
    """The configuration if it is well formed and live right now; None otherwise (never raises)."""
    if not isinstance(config, dict) or not valid_run_id(config.get("run")):
        return None
    starts, expires = _parse_time(config.get("startsAt")), _parse_time(config.get("expiresAt"))
    if starts is None or expires is None or (expires - starts).total_seconds() > MAX_FAULT_SECONDS:
        return None
    if not starts <= now < expires:
        return None
    if config.get("action") not in ("error", "delay") or not isinstance(config.get("functions"), list):
        return None
    percent, delay = config.get("percent"), config.get("delayMs", 0)
    if not isinstance(percent, (int, float)) or not 0 <= percent <= 100:
        return None
    if not isinstance(delay, int) or not 0 <= delay <= MAX_DELAY_MS:
        return None
    return config


def _read_config() -> Any:
    """The raw configuration from S3, or None when there is none (missing object, no access, bad JSON)."""
    global _s3
    bucket = os.environ.get("CHAOS_FAULT_BUCKET")
    if not bucket:
        return None
    if _s3 is None:
        import boto3  # only when chaos is enabled: an idle function never creates the client

        _s3 = boto3.client("s3")
    try:
        return json.loads(_s3.get_object(Bucket=bucket, Key=FAULT_KEY)["Body"].read())
    except Exception:  # noqa: BLE001 - NoSuchKey / AccessDenied (no ListBucket grant) / bad JSON all mean "no fault"
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def active_fault(function: str, now: datetime | None = None, clock: Callable[[], float] = time.monotonic) -> dict[str, Any] | None:
    """The live configuration that targets `function`, if chaos is enabled. Cached for CACHE_SECONDS per container."""
    if not enabled():
        return None
    if clock() - _cache["read_at"] >= CACHE_SECONDS:
        _cache.update(read_at=clock(), config=_read_config())
    config = usable_config(_cache["config"], now or _now())
    return config if config and function in config["functions"] else None


def inject_fault(function: str, run_of: Callable[[], Any], log: Any = None,
                 roll: Callable[[], float] = random.random, sleep: Callable[[float], None] = time.sleep) -> None:
    """Call at the start of a target function's work, before any write. `run_of` returns the order's chaosRun; it is
    only called (it may read DynamoDB) when a live fault targets this function."""
    config = active_fault(function)
    if config is None:
        return
    run = run_of()
    if run != config["run"]:
        return  # not an order of this chaos run: storefront orders are never touched
    if roll() * 100 >= config["percent"]:
        return
    detail = dict(chaosEvent="injected_fault", chaosRun=run, chaosAction=config["action"], chaosFunction=function)
    if config["action"] == "error":
        if log is not None:
            log.warning("CHAOS: injected error before any write", **detail)
        raise ChaosInjectedFault(f"Injected fault in {function} (chaos run {run})")
    if log is not None:
        log.warning("CHAOS: injected start-up delay", delayMs=config["delayMs"], **detail)
    sleep(config["delayMs"] / 1000)
