"""Turn an order's statusHistory into the storefront tracker's "live feed" and its AWS Console links.

Each statusHistory entry becomes one or more feed rows {time, service, message, level, note?}:
  service: the AWS component that did the work (API Gateway, SQS -> Step Functions, Lambda, ...)
  level:   info | retry | error, which sets the row colour in the UI
Rows are returned oldest first. The UI shows them newest first.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

# Service labels shown in the feed.
API = "API Gateway"
QUEUE = "SQS → Step Functions"
INVENTORY = "Lambda · inventory"
PAYMENT = "Lambda · payment"
WEBHOOK = "Webhook · DemoPay"
WORKFLOW = "Step Functions"
DATABASE = "DynamoDB"
EMAIL = "SNS"

# Must match the RequestPayment Retry block in statemachine/order_saga.asl.json.
PAYMENT_RETRY_INTERVAL_SECONDS = 2
PAYMENT_RETRY_BACKOFF = 2

_ATTEMPT = re.compile(r"[Aa]ttempt (\d+)")
_COUNT = re.compile(r"for (\d+) product")
_AVAILABLE = re.compile(r"(₹[\d,.]+) available")
_ATTEMPT_SUFFIX = re.compile(r" \(attempt \d+\)$")


def _attempt(detail: str) -> int | None:
    match = _ATTEMPT.search(detail)
    return int(match.group(1)) if match else None


def _reason(order: dict[str, Any]) -> str:
    """'PaymentDeclined: Card declined by issuer (simulated)' -> 'Card declined by issuer (simulated)'."""
    reason = str(order.get("failureReason") or "")
    return reason.split(": ", 1)[-1] if reason else "unknown reason"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def rows_for(entry: dict[str, Any], order: dict[str, Any]) -> list[dict[str, Any]]:
    """Feed rows for ONE statusHistory entry, in plain English."""
    status, detail = entry["status"], entry.get("detail", "")

    def row(service: str, message: str, level: str = "info", note: str | None = None) -> dict[str, Any]:
        result = {"time": entry["timestamp"], "service": service, "message": message, "level": level}
        if note:
            result["note"] = note
        return result

    if status == "PENDING":
        return [row(API, "Order received and queued for processing")]
    if status == "PROCESSING":
        return [row(QUEUE, "Picked up from the queue, saga workflow started")]
    if status == "DELIVERY_RETRY":
        return [row(QUEUE, "Message could not be processed, SQS will retry in 60s", "retry", f"attempt {_attempt(detail)}")]
    if status == "DEAD_LETTERED":
        return [row(QUEUE, f"Moved to dead-letter queue after {_attempt(detail) or 3} attempts", "error")]
    if status == "RESERVED":
        count = _COUNT.search(detail)
        what = _plural(int(count.group(1)), "product") if count else "all items"
        return [row(INVENTORY, f"Stock reserved for {what}")]
    if status == "OUT_OF_STOCK":
        return [row(INVENTORY, detail.replace("Insufficient stock for:", "Out of stock:").strip(), "error")]
    if status == "PAYMENT_RETRY":
        attempt = _attempt(detail) or 1
        wait = PAYMENT_RETRY_INTERVAL_SECONDS * PAYMENT_RETRY_BACKOFF ** (attempt - 1)
        return [row(WORKFLOW, f"Payment glitch, retrying in {wait}s", "retry", f"attempt {attempt}")]
    if status == "PAYMENT_PENDING":
        return [row(PAYMENT, "Payment requested from DemoPay, awaiting confirmation (saga paused until the webhook)")]
    if status == "PAYMENT_DECLINED":
        if "Insufficient wallet balance" in detail:
            available = _AVAILABLE.search(detail)
            suffix = f" ({available.group(1)} available)" if available else ""
            return [row(PAYMENT, f"Declined: not enough DemoPay balance{suffix}", "error")]
        return [row(PAYMENT, "Payment declined by the card issuer", "error")]
    if status == "PAYMENT_CAPTURED":
        attempt = _attempt(detail) or 1
        note = f"attempt {attempt}" if attempt > 1 else None
        if "confirmed by webhook" in detail:  # step 2.1: "₹7,597 captured by DemoPay · PAY-... (confirmed by webhook)"
            return [row(WEBHOOK, detail.replace(" (confirmed by webhook)", ""), note=note)]
        if detail.startswith("₹"):  # wallet debit: "₹7,597 debited from DemoPay · balance ₹9,92,403 (attempt 1)"
            return [row(PAYMENT, _ATTEMPT_SUFFIX.sub("", detail), note=note)]
        return [row(PAYMENT, "Payment captured" + (f" on attempt {attempt}" if attempt > 1 else ""))]
    if status == "PAYMENT_REFUNDED":
        return [row(PAYMENT, detail.replace("refunded to DemoPay", "refunded to wallet"))]
    if status == "INVENTORY_RELEASED":
        return [row(INVENTORY, "Stock released back to inventory")]
    if status == "COMPLETED":
        return [row(DATABASE, "Order marked COMPLETED"), row(EMAIL, "Confirmation email sent")]
    if status == "FAILED":
        return [row(DATABASE, f"Order marked FAILED: {_reason(order)}", "error"), row(EMAIL, "Failure email sent")]
    return [row(WORKFLOW, detail or status)]


def build_feed(order: dict[str, Any]) -> list[dict[str, Any]]:
    """All feed rows for an order, oldest first."""
    return [row for entry in order.get("statusHistory", []) for row in rows_for(entry, order)]


def console_links(order: dict[str, Any], region: str, orders_table: str, workflow_log_group: str) -> dict[str, str | None]:
    """Deep links into the AWS Console for this order (each opens in a new tab in the UI)."""
    console = f"https://{region}.console.aws.amazon.com"
    order_id = order["orderId"]
    execution_arn = order.get("executionArn")
    # The CloudWatch console escapes its URL fragments: "/" -> "$252F", "?" -> "$3F", "=" -> "$3D", '"' -> "$2522".
    log_group = quote(workflow_log_group, safe="").replace("%", "$25")
    log_filter = f"$3FfilterPattern$3D$2522{order_id}$2522"
    return {
        "execution": (
            f"{console}/states/home?region={region}#/v2/executions/details/{execution_arn}" if execution_arn else None
        ),
        "dynamodbItem": (
            f"{console}/dynamodbv2/home?region={region}#edit-item?itemMode=2&pk={quote(order_id)}"
            f"&route=ROUTE_ITEM_EXPLORER&sk=&table={orders_table}"
        ),
        "logs": f"{console}/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group}/log-events{log_filter}",
    }
