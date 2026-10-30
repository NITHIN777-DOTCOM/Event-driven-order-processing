"""POST /orders/{id}/cancel: the customer cancels their own order, until fulfillment starts (step 2.4).

Owner only: anyone else gets the same 404 as for an order that doesn't exist (like GET /orders/{id}).
Switched off by CANCEL_ENABLED (503) until the state machine with the cancel branch is deployed.

The window, checked in this order:
  already cancelled (cancelRequestedAt set) -> the SAME answer again: 202 while it is in progress, 200 once CANCELLED
  terminal, or FULFILLING, or failing     -> 409 TOO_LATE_TO_CANCEL (recorded once in the history as CANCEL_REJECTED)
  PENDING / PROCESSING                     -> 409 NOT_CANCELLABLE_YET (stock not reserved yet; a second later it is)
  no `cancellable` stamp                   -> 409 NOT_CANCELLABLE (its execution runs a definition without a cancel
                                              branch; see reserve_inventory)
  RESERVED / PAYMENT_RETRY / PAYMENT_PENDING (waiting for payment) or PAYMENT_CAPTURED (paid, not fulfilling yet)
                                           -> cancel: 202 CANCEL_REQUESTED

The race is decided by ONE conditional UpdateItem on the order: status still in the window, no cancel committed,
stamped -> status CANCEL_REQUESTED + cancelRequestedAt. The payment webhook's capture and BeginFulfillment both
require "no cancelRequestedAt" on the same item, so exactly one side wins (common/orders.py, CANCELLABLE_STATUSES).

Reaching a saga that is waiting for the payment: SendTaskFailure with error "OrderCancelled" on the task token
stored on the payment intent. The state machine catches it and runs the cancel branch (refund what's left, release
the stock, CANCELLED, email). TaskTimedOut / InvalidToken / TaskDoesNotExist mean the token was already answered
(the webhook, a retry, a timeout): the race was lost or is already handled, not an error. StopExecution is never
used: it would end the execution without running any compensation, leaving the stock reserved and the money taken.
A paid order isn't waiting on a token: BeginFulfillment sees the cancel and takes the same branch.

Never logged: the task token.
"""

from __future__ import annotations

import os
import re
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.auth import Forbidden, Unauthorized, caller_from
from common.http import BadRequest, parse_json_body, response
from common.logger import StructuredLogger, get_logger
from common.orders import (
    AWAITING_PAYMENT,
    CANCEL_REJECTED,
    CANCEL_REQUESTED,
    CANCELLABLE_STATUSES,
    CANCELLED,
    PENDING,
    PROCESSING,
    history_event,
    status_update,
)
from common.payments import SUCCEEDED, intent_id_for
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
PAYMENTS_TABLE = os.environ["PAYMENTS_TABLE"]
CANCEL_ENABLED = os.environ.get("CANCEL_ENABLED", "false").lower() == "true"

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
payments_table = dynamodb.Table(PAYMENTS_TABLE)
sfn = boto3.client("stepfunctions")
logger = get_logger("cancel_order")

ORDER_ID_PATTERN = re.compile(r"^ORD-\d{8}-[0-9a-f]{8}$")
MAX_REASON_LENGTH = 200
DEFAULT_REASON = "Cancelled by the customer"
# SendTaskFailure errors meaning "nobody waits on this token any more": the race was lost or already handled.
TOKEN_ALREADY_ANSWERED = ("TaskTimedOut", "InvalidToken", "TaskDoesNotExist")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = (event.get("pathParameters") or {}).get("id", "")
    log = logger.bind(orderId=order_id, requestId=(event.get("requestContext") or {}).get("requestId"))
    try:
        caller = caller_from(event)
    except Unauthorized as err:
        return response(401, {"error": str(err)})
    except Forbidden as err:
        return response(403, {"error": str(err)})
    log = log.bind(userId=caller.user_id)

    if not CANCEL_ENABLED:
        return response(503, {"error": "CANCEL_DISABLED", "message": "Cancelling orders is not switched on yet"})
    if not ORDER_ID_PATTERN.match(order_id):
        return response(400, {"error": "Order id must look like ORD-YYYYMMDD-xxxxxxxx"})
    try:
        reason = reason_from(event)
    except BadRequest as err:
        return response(400, {"error": str(err)})

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item")
    if order is None or order.get("userId") != caller.user_id:
        log.info("Order not found" if order is None else "Order belongs to another user: answering 404")
        return response(404, {"error": f"Order {order_id} not found"})
    return decide(order, reason, log)


def reason_from(event: dict[str, Any]) -> str:
    """Optional {"reason": "..."}; an empty body is fine."""
    if not event.get("body"):
        return DEFAULT_REASON
    reason = parse_json_body(event).get("reason", DEFAULT_REASON)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_LENGTH:
        raise BadRequest(f"reason must be 1-{MAX_REASON_LENGTH} characters")
    return reason.strip()


def decide(order: dict[str, Any], reason: str, log: StructuredLogger) -> dict[str, Any]:
    status = order["status"]
    if "cancelRequestedAt" in order:
        return repeated(order, log)
    if status in (PENDING, PROCESSING):
        log.info("Cancel before the stock was reserved; try again in a moment", cancelEvent="not_cancellable_yet", status=status)
        return response(409, {"error": "NOT_CANCELLABLE_YET", "status": status})
    if status not in CANCELLABLE_STATUSES:
        return too_late(order, log)
    if order.get("cancellable") is not True:
        log.info("Order runs on a definition without a cancel branch", cancelEvent="not_cancellable", status=status)
        return response(409, {"error": "NOT_CANCELLABLE", "status": status})
    return request_cancel(order, reason, log)


def request_cancel(order: dict[str, Any], reason: str, log: StructuredLogger) -> dict[str, Any]:
    """The conditional write that decides the race, then (if the saga waits for the payment) answer its token."""
    order_id, now = order["orderId"], utc_now_iso()
    window = sorted(CANCELLABLE_STATUSES)
    placeholders = {f":w{i}": status for i, status in enumerate(window)}
    try:
        old = orders_table.update_item(
            Key={"orderId": order_id},
            ReturnValues="UPDATED_OLD",
            **status_update(
                CANCEL_REQUESTED,
                # No reason given: don't repeat the default ("... by the customer: Cancelled by the customer").
                "Cancellation requested by the customer" + ("" if reason == DEFAULT_REASON else f": {reason}"),
                {"cancelRequestedAt": now, "cancelReason": reason},
                condition=f"#status IN ({', '.join(placeholders)}) AND attribute_not_exists(cancelRequestedAt) AND cancellable = :true",
                condition_values={**placeholders, ":true": True},
            ),
        )["Attributes"]
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Lost the race: fulfillment started, the payment failed, or another cancel got here first. Decide again.
        fresh = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
        log.info("Cancel lost the race; deciding again on the fresh order", status=fresh["status"])
        return decide(fresh, reason, log)

    prior = old["status"]
    log.info("Cancellation accepted", cancelEvent="accepted", priorStatus=prior)
    if prior in AWAITING_PAYMENT:
        fail_payment_task(order_id, log)
    return response(202, {"orderId": order_id, "status": CANCEL_REQUESTED, "cancelRequestedAt": now})


def fail_payment_task(order_id: str, log: StructuredLogger) -> None:
    """SendTaskFailure("OrderCancelled") on the payment task token, if the saga may still be waiting on it."""
    intent = payments_table.get_item(Key={"paymentIntentId": intent_id_for(order_id)}, ConsistentRead=True).get("Item")
    if not intent or not intent.get("taskToken") or intent.get("status") == SUCCEEDED:
        # No payment requested yet (request_payment sees the cancel and fails with OrderCancelled itself), or the
        # payment was captured before the cancel (no task waits; BeginFulfillment sees the cancel). Any other intent
        # (REQUESTED, or already closed by the webhook) is answered: if the token was answered already, it's a no-op.
        log.info("No payment task to answer; the saga will see the cancel by itself", intentStatus=(intent or {}).get("status"))
        return
    try:
        sfn.send_task_failure(taskToken=intent["taskToken"], error="OrderCancelled", cause="Cancelled by the customer")
    except ClientError as err:
        code = err.response["Error"]["Code"]
        if code not in TOKEN_ALREADY_ANSWERED:
            raise  # 500: the client retries, and a repeated cancel answers the token again (repeated())
        log.info("Payment task already answered (race lost or already handled)", sfnError=code)
        return
    log.info("Payment wait failed with OrderCancelled; the saga takes its cancel branch")


def repeated(order: dict[str, Any], log: StructuredLogger) -> dict[str, Any]:
    """Idempotent: a second cancel gets the same result as the first. While the cancel is still in progress it
    answers the payment token again, in case the first SendTaskFailure never got through."""
    body = {"orderId": order["orderId"], "status": CANCEL_REQUESTED, "cancelRequestedAt": order["cancelRequestedAt"]}
    if order["status"] == CANCELLED:
        log.info("Repeated cancel: already CANCELLED", cancelEvent="repeated")
        return response(200, {**body, "status": CANCELLED, "refundedAmount": order.get("refundedAmount", 0)})
    if order["status"] == CANCEL_REQUESTED:
        fail_payment_task(order["orderId"], log)
    log.info("Repeated cancel: cancellation in progress", cancelEvent="repeated", status=order["status"])
    return response(202, body)


def too_late(order: dict[str, Any], log: StructuredLogger) -> dict[str, Any]:
    """409, and one CANCEL_REJECTED entry in the order's history (so the tracker shows it), best effort."""
    status = order["status"]
    log.info("Cancel rejected: too late", cancelEvent="rejected_too_late", status=status)
    try:
        orders_table.update_item(
            Key={"orderId": order["orderId"]},
            **history_event(
                CANCEL_REJECTED,
                f"Cancel request rejected: the order was already {status}",
                {"cancelRejectedAt": utc_now_iso()},
                condition="attribute_not_exists(cancelRejectedAt)",
            ),
        )
    except ClientError as err:
        # Already recorded, or the item is inside a fulfillment transaction this instant: the 409 stands either way.
        log.info("Rejection not recorded in the history", reason=err.response["Error"]["Code"])
    return response(409, {"error": "TOO_LATE_TO_CANCEL", "status": status})
