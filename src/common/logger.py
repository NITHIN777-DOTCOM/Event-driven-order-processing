"""Structured JSON logging shared by every Lambda.

Each call writes ONE JSON object per line to stdout, which Lambda forwards to CloudWatch Logs.
That makes the logs queryable in CloudWatch Logs Insights, for example:

    fields @timestamp, service, level, message
    | filter orderId = "ORD-20261022-1a2b3c4d"
    | sort @timestamp asc

`orderId` is present on every line (null until it is known), so one order can be traced across
create_order -> start_workflow -> reserve_inventory -> process_payment.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from common.timeutil import utc_now_iso


class StructuredLogger:
    """Minimal JSON logger that carries bound context (orderId, requestId, ...)."""

    def __init__(self, service: str, **context: Any) -> None:
        self.service = service
        self._context = {"orderId": None, **context}

    def bind(self, **context: Any) -> StructuredLogger:
        """Return a new logger that adds `context` to every line it writes."""
        return StructuredLogger(self.service, **{**self._context, **context})

    def info(self, message: str, **fields: Any) -> None:
        self._emit("INFO", message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit("WARNING", message, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit("ERROR", message, fields)

    def exception(self, message: str, **fields: Any) -> None:
        """Log at ERROR level and include the traceback of the exception being handled."""
        self._emit("ERROR", message, {**fields, "traceback": traceback.format_exc()})

    def _emit(self, level: str, message: str, fields: dict[str, Any]) -> None:
        record = {
            "timestamp": utc_now_iso(),
            "level": level,
            "service": self.service,
            "message": message,
            **self._context,
            **fields,
        }
        # default=str handles Decimal (from DynamoDB) and other non-JSON types.
        sys.stdout.write(json.dumps(record, default=str) + "\n")
        sys.stdout.flush()


def get_logger(service: str) -> StructuredLogger:
    return StructuredLogger(service)
