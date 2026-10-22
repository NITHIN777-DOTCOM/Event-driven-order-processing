"""Helpers for API Gateway HTTP API (payload format 2.0) Lambda integrations."""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any


class BadRequest(Exception):
    """Client error. The message is returned to the caller as {"error": message} with HTTP 400."""


def _json_default(value: Any) -> Any:
    # DynamoDB returns every number as Decimal, which json can't serialise.
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable")


def to_json(body: Any) -> str:
    return json.dumps(body, default=_json_default)


def response(status_code: int, body: Any) -> dict[str, Any]:
    """Build an HTTP API proxy response. CORS headers are added by the API's CORS configuration."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": to_json(body),
    }


def parse_json_body(event: dict[str, Any]) -> dict[str, Any]:
    """Decode the request body into a dict, or raise BadRequest."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise BadRequest("Request body must be valid JSON") from None
    if not isinstance(body, dict):
        raise BadRequest("Request body must be a JSON object")
    return body
