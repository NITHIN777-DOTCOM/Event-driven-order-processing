"""Time helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with milliseconds, e.g. '2026-10-22T10:15:30.123Z'.

    This is the same format Step Functions uses for `$$.State.EnteredTime`, so timestamps written
    by Lambdas and by the state machine's direct DynamoDB integration sort correctly together.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
