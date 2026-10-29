"""POST /webhooks/payment: DemoPay tells us how a payment intent ended, and we resume the paused saga.

No JWT on this route: the caller is a server, not a signed-in user. Instead every request must carry a valid
HMAC-SHA256 signature over "<X-Timestamp>.<raw body>" made with the shared webhook secret, and a timestamp no
more than 5 minutes old (common/signing.py). Anything else gets 401 and is counted (metric
WebhookSignatureFailures, alarmed: a burst means someone is probing the endpoint).

Then, for the intent named in the body (our payments table, conditional writes throughout):

  "payment.succeeded"
    REQUESTED -> SUCCEEDED (+ order PAYMENT_CAPTURED, paymentId) in one transaction, then SendTaskSuccess with
                 the task token we stored: the saga continues to MarkOrderCompleted.
    SUCCEEDED -> a duplicate: 200 no-op (or, if the saga was never told, tell it now).
    TIMED_OUT / FAILED -> LATE CALLBACK: the saga already gave up, but money moved. Refund it through DemoPay's
                 refund API right away and mark the intent REFUNDED (the customer must never pay for a failed order).
    REFUNDED  -> a duplicate: 200 no-op.
  "payment.declined"
    REQUESTED -> FAILED (+ order PAYMENT_DECLINED), then SendTaskFailure with error "PaymentDeclined", which the
                 state machine's existing Catch turns into compensation. Anything else: 200 no-op (nothing moved).

A valid signature for an intent we don't know -> 404, nothing changes. Errors we can't handle -> 500, so DemoPay
retries (its retries are bounded; then the request lands in order-saga-psp-dlq and an alarm fires).

Never logged: the secret, the signature, the task token.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.http import response
from common.logger import StructuredLogger, get_logger
from common.money import format_inr
from common.orders import PAYMENT_CAPTURED, PAYMENT_DECLINED, cancellation_codes, status_update
from common.payments import (
    FAILED,
    REFUNDED,
    REQUESTED,
    SUCCEEDED,
    TIMED_OUT,
    invoke_provider_refund,
    money_returned,
    record_refund,
)
from common.secrets import get_secret
from common.signing import SignatureError, verify
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

PAYMENTS_TABLE = os.environ["PAYMENTS_TABLE"]
ORDERS_TABLE = os.environ["ORDERS_TABLE"]
PROVIDER_FUNCTION = os.environ.get("PROVIDER_FUNCTION", "")
WEBHOOK_SECRET_PARAMETER = os.environ.get("WEBHOOK_SECRET_PARAMETER", "")

dynamodb = boto3.resource("dynamodb")
payments_table = dynamodb.Table(PAYMENTS_TABLE)
orders_table = dynamodb.Table(ORDERS_TABLE)
sfn = boto3.client("stepfunctions")
lambda_client = boto3.client("lambda")
logger = get_logger("payment_webhook")

EVENT_TYPES = ("payment.succeeded", "payment.declined")
# SendTaskSuccess/Failure errors meaning "nobody is waiting on this token any more" (timed out, already
# answered, or the execution ended). Anything else is unexpected and gets a 500, so DemoPay retries.
TASK_CLOSED = ("TaskTimedOut", "TaskDoesNotExist")


class BadRequest(Exception):
    """Signed correctly, but the body is unusable. Maps to 400."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    log = logger.bind(requestId=(event.get("requestContext") or {}).get("requestId"))
    raw = raw_body(event)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    try:
        verify(get_secret(WEBHOOK_SECRET_PARAMETER), headers.get("x-timestamp"), headers.get("x-signature"), raw)
    except SignatureError as err:
        # "event" feeds the WebhookSignatureFailures metric filter. Only the reason is logged, never the signature.
        log.warning(
            "Webhook signature rejected",
            event="webhook_signature_rejected",
            reason=err.reason,
            sourceIp=((event.get("requestContext") or {}).get("http") or {}).get("sourceIp"),
        )
        return response(401, {"error": "invalid or missing signature"})

    try:
        callback = parse(raw)
    except BadRequest as err:
        log.warning("Signed webhook with an unusable body", reason=str(err))
        return response(400, {"error": str(err)})

    intent_id = callback["paymentIntentId"]
    log = log.bind(orderId=callback.get("orderId"), paymentIntentId=intent_id, eventType=callback["type"], eventId=callback.get("eventId"))
    intent = payments_table.get_item(Key={"paymentIntentId": intent_id}, ConsistentRead=True).get("Item")
    if not intent:
        log.warning("Webhook for an unknown payment intent; ignored")
        return response(404, {"error": f"unknown payment intent {intent_id}"})
    if callback.get("orderId") != intent["orderId"] or Decimal(callback["amount"]) != Decimal(intent["amount"]):
        log.error("Webhook does not match the payment intent; ignored", intentAmount=intent["amount"], callbackAmount=callback["amount"])
        return response(400, {"error": "callback does not match the payment intent"})

    log = log.bind(callbackDelayMs=delay_ms(intent))
    if callback["type"] == "payment.succeeded":
        result = on_succeeded(intent, callback, log)
    else:
        result = on_declined(intent, callback, log)
    log.info("Webhook processed", result=result)
    return response(200, {"result": result, "paymentIntentId": intent_id})


def raw_body(event: dict[str, Any]) -> bytes:
    """The exact bytes DemoPay signed (API Gateway may base64-encode them)."""
    body = event.get("body") or ""
    return base64.b64decode(body) if event.get("isBase64Encoded") else body.encode()


def parse(raw: bytes) -> dict[str, Any]:
    try:
        callback = json.loads(raw)
    except ValueError:
        raise BadRequest("body is not JSON") from None
    if not isinstance(callback, dict) or callback.get("type") not in EVENT_TYPES:
        raise BadRequest(f"type must be one of {', '.join(EVENT_TYPES)}")
    if not isinstance(callback.get("paymentIntentId"), str) or not callback["paymentIntentId"]:
        raise BadRequest("paymentIntentId is required")
    try:
        Decimal(str(callback.get("amount")))
    except InvalidOperation:
        raise BadRequest("amount must be a number") from None
    return callback


def delay_ms(intent: dict[str, Any]) -> int | None:
    """Time from our payment request to this callback (the dashboard's webhook latency)."""
    try:
        requested = datetime.fromisoformat(intent["requestedAt"].replace("Z", "+00:00"))
        return int((datetime.fromisoformat(utc_now_iso().replace("Z", "+00:00")) - requested).total_seconds() * 1000)
    except (KeyError, ValueError):
        return None


# --- payment.succeeded ------------------------------------------------------------------------------------
def on_succeeded(intent: dict[str, Any], callback: dict[str, Any], log: StructuredLogger) -> str:
    status = intent["status"]
    if status == REQUESTED:
        if capture(intent, callback, log):
            return resume(intent, "success", callback, log)
        # Lost a race (the saga timed out, or a duplicate got here first): decide again on the fresh intent.
        intent = payments_table.get_item(Key={"paymentIntentId": intent["paymentIntentId"]}, ConsistentRead=True)["Item"]
        return on_succeeded(intent, callback, log)
    if status == SUCCEEDED:
        if intent.get("sagaResumedAt"):
            log.info("Duplicate success callback; already applied (no-op)", intentStatus=status)
            return "duplicate"
        return resume(intent, "success", callback, log)  # captured earlier, but the saga was never told
    if status in (TIMED_OUT, FAILED):
        return refund_late_payment(intent, callback, log)
    log.info("Duplicate success callback for a refunded intent (no-op)", intentStatus=status)
    return "duplicate"


def capture(intent: dict[str, Any], callback: dict[str, Any], log: StructuredLogger) -> bool:
    """REQUESTED -> SUCCEEDED and order PAYMENT_CAPTURED, atomically. False if the intent is no longer REQUESTED."""
    now = utc_now_iso()
    amount = Decimal(callback["amount"])
    try:
        dynamodb.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": PAYMENTS_TABLE,
                        "Key": {"paymentIntentId": intent["paymentIntentId"]},
                        "UpdateExpression": "SET #s = :succeeded, paymentId = :pid, succeededAt = :now, updatedAt = :now",
                        "ConditionExpression": "#s = :requested",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {":succeeded": SUCCEEDED, ":requested": REQUESTED, ":pid": callback["paymentId"], ":now": now},
                    }
                },
                {
                    "Update": {
                        "TableName": ORDERS_TABLE,
                        "Key": {"orderId": intent["orderId"]},
                        **status_update(
                            PAYMENT_CAPTURED,
                            f"{format_inr(amount)} captured by DemoPay · {callback['paymentId']} (confirmed by webhook)",
                            {"paymentId": callback["paymentId"], "paidAmount": amount},
                            condition="attribute_not_exists(paymentId)",
                        ),
                    }
                },
            ]
        )
    except ClientError as err:
        # Only the INTENT's condition (item 0) means "someone else moved it first"; anything else is a real error.
        if err.response["Error"]["Code"] == "TransactionCanceledException" and cancellation_codes(err.response)[:1] == ["ConditionalCheckFailed"]:
            return False
        raise
    intent.update(status=SUCCEEDED, paymentId=callback["paymentId"])
    log.info("Payment captured", intentStatus=SUCCEEDED, paymentId=callback["paymentId"], amount=amount)
    return True


def refund_late_payment(intent: dict[str, Any], callback: dict[str, Any], log: StructuredLogger) -> str:
    """The saga gave up (timeout or compensation) before this success arrived: give the money back now."""
    log.warning("LATE success callback: the saga no longer waits for this payment; refunding it", intentStatus=intent["status"])
    refund = invoke_provider_refund(lambda_client, PROVIDER_FUNCTION, intent["paymentIntentId"])
    if not money_returned(refund):
        # DemoPay says nothing was charged after all (it only reported success): nothing to give back.
        log.error("Late success callback, but DemoPay has no charge to refund", refund=refund)
        return "late-nothing-to-refund"
    record_refund(payments_table, orders_table, intent, refund, f"late payment {callback['paymentId']}, the order had already failed")
    log.info("Late payment refunded automatically", intentStatus=REFUNDED, refundId=refund.get("refundId"))
    return "late-refunded"


# --- payment.declined -------------------------------------------------------------------------------------
def on_declined(intent: dict[str, Any], callback: dict[str, Any], log: StructuredLogger) -> str:
    status = intent["status"]
    if status == REQUESTED:
        reason = str(callback.get("reason") or "declined")
        try:
            dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": PAYMENTS_TABLE,
                            "Key": {"paymentIntentId": intent["paymentIntentId"]},
                            "UpdateExpression": "SET #s = :failed, declineReason = :reason, failedAt = :now, updatedAt = :now",
                            "ConditionExpression": "#s = :requested",
                            "ExpressionAttributeNames": {"#s": "status"},
                            "ExpressionAttributeValues": {":failed": FAILED, ":requested": REQUESTED, ":reason": reason, ":now": utc_now_iso()},
                        }
                    },
                    {"Update": {"TableName": ORDERS_TABLE, "Key": {"orderId": intent["orderId"]}, **status_update(PAYMENT_DECLINED, reason)}},
                ]
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "TransactionCanceledException" and cancellation_codes(err.response)[:1] == ["ConditionalCheckFailed"]:
                log.info("Decline arrived after the intent left REQUESTED; nothing to do (no money moved)")
                return "duplicate"
            raise
        intent.update(status=FAILED, declineReason=reason)
        log.info("Payment declined", intentStatus=FAILED, reason=reason)
        return resume(intent, "failure", callback, log)
    if status == FAILED and not intent.get("sagaResumedAt") and intent.get("declineReason"):
        return resume(intent, "failure", callback, log)
    log.info("Duplicate or late decline; no money moved, nothing to do", intentStatus=status)
    return "duplicate"


# --- resuming the saga ------------------------------------------------------------------------------------
def resume(intent: dict[str, Any], outcome: str, callback: dict[str, Any], log: StructuredLogger) -> str:
    """SendTaskSuccess / SendTaskFailure with the token stored on the intent, then remember that we did."""
    try:
        if outcome == "success":
            sfn.send_task_success(
                taskToken=intent["taskToken"],
                output=json.dumps({"paymentIntentId": intent["paymentIntentId"], "paymentId": intent["paymentId"], "status": SUCCEEDED}),
            )
        else:
            sfn.send_task_failure(taskToken=intent["taskToken"], error="PaymentDeclined", cause=intent.get("declineReason", "declined"))
    except ClientError as err:
        code = err.response["Error"]["Code"]
        if code not in TASK_CLOSED:
            raise  # 500: DemoPay retries; the intent is already updated, so the retry only resumes
        # Nobody waits on this token any more. For a SUCCEEDED intent that means the saga timed out at the same
        # moment (its compensation sees SUCCEEDED and refunds) or we resumed it before. Never refund here.
        log.warning("Saga was not waiting any more; compensation owns any refund", sfnError=code, intentStatus=intent["status"])
        mark_resumed(intent, f"task closed ({code})")
        return "saga-not-waiting"
    mark_resumed(intent, outcome)
    log.info("Saga resumed", outcome=outcome, intentStatus=intent["status"])
    return "resumed"


def mark_resumed(intent: dict[str, Any], result: str) -> None:
    try:
        payments_table.update_item(
            Key={"paymentIntentId": intent["paymentIntentId"]},
            UpdateExpression="SET sagaResumedAt = :now, sagaResumeResult = :r",
            ConditionExpression="attribute_not_exists(sagaResumedAt)",
            ExpressionAttributeValues={":now": utc_now_iso(), ":r": result},
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
