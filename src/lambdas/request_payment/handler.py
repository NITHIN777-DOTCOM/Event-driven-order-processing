"""Saga step 2: ask the payment provider (DemoPay) to charge the order, then let the saga PAUSE.

The state machine invokes this with lambda:invoke.waitForTaskToken and TimeoutSeconds 120. Returning from this
function does NOT finish the step: Step Functions waits until someone calls SendTaskSuccess / SendTaskFailure
with the task token, which our webhook does when DemoPay calls back (payment_webhook), or until 120 s pass.

What it does, in order:
  1. Upsert the payment intent PI-<orderId> (order-saga-payments): status REQUESTED, amount, wallet, and the
     CURRENT task token. Conditional: only if the intent is new or still REQUESTED. A retried step gets a new
     token from Step Functions, and this overwrites the old one, but never on an intent that already finished.
  2. If the intent had already finished (a re-run after the outcome was known), answer the new token right here
     from the stored outcome instead of asking DemoPay again.
  3. simulate=payment_flaky: fail with PaymentTransientError on attempts 1 and 2 (the state machine retries,
     2 s then 4 s), succeed on attempt 3.
  4. Order -> PAYMENT_PENDING ("Awaiting payment confirmation"), then send the request to SQS
     order-saga-psp-requests with a 2-5 s delay (DemoPay's processing time; 150 s for payment_late).

Customer cancellation (step 2.4): if the order's cancel was committed (cancelRequestedAt), this step fails with
OrderCancelled instead of asking DemoPay to charge, and the state machine takes its cancel branch. The status
writes below are conditional on that too, so a cancel landing mid-way can never be overwritten by PAYMENT_PENDING.
(The cancel API also answers the stored task token with SendTaskFailure "OrderCancelled"; whichever arrives first
closes the task, the other is a no-op.)

The task token is stored on OUR intent only. DemoPay's message carries the intent id, order, wallet and amount,
never the token, so the provider can't complete our workflow step directly.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import StructuredLogger, get_logger
from common.money import format_inr
from common.orders import PAYMENT_PENDING, PAYMENT_RETRY, status_update
from common.payments import FAILED, REQUESTED, SUCCEEDED, intent_id_for, provider_delay_seconds
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
PAYMENTS_TABLE = os.environ["PAYMENTS_TABLE"]
PSP_QUEUE_URL = os.environ["PSP_QUEUE_URL"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
payments_table = dynamodb.Table(PAYMENTS_TABLE)
sqs = boto3.client("sqs")
sfn = boto3.client("stepfunctions")
logger = get_logger("request_payment")

FLAKY_FAILURES = 2  # payment_flaky fails this many times before succeeding


class PaymentTransientError(Exception):
    """Temporary failure (e.g. the gateway is busy). The state machine retries it with backoff."""


class OrderCancelled(Exception):
    """The customer cancelled before the payment was requested. The state machine catches it (cancel branch)."""


# Status writes on the order only apply while no cancel is committed (step 2.4).
NOT_CANCELLED = "attribute_not_exists(cancelRequestedAt)"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id, token = event["orderId"], event["taskToken"]
    simulate = event.get("simulate") or "none"
    intent_id = intent_id_for(order_id)
    log = logger.bind(orderId=order_id, paymentIntentId=intent_id, simulate=simulate)

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    if "cancelRequestedAt" in order:
        log.info("Order was cancelled before the payment was requested; not charging")
        raise OrderCancelled(f"Order {order_id} was cancelled by the customer")
    intent = upsert_intent(order, intent_id, token, simulate)
    if intent is None:
        return answer_from_finished_intent(intent_id, token, log)

    attempt = int(intent["requestAttempts"])
    log = log.bind(attempt=attempt)
    if simulate == "payment_flaky" and attempt <= FLAKY_FAILURES:
        reason = f"Payment gateway busy on attempt {attempt} (simulated)"
        log.warning("Transient payment failure; Step Functions will retry", reason=reason)
        update_order(order_id, status_update(PAYMENT_RETRY, f"Attempt {attempt} failed: {reason} - retrying", {"paymentAttempts": attempt}, condition=NOT_CANCELLED))
        raise PaymentTransientError(reason)

    amount = Decimal(order["totalAmount"])
    delay = provider_delay_seconds(simulate)
    update_order(
        order_id,
        status_update(
            PAYMENT_PENDING,
            f"Awaiting payment confirmation from DemoPay · {format_inr(amount)} · intent {intent_id}",
            {"paymentIntentId": intent_id, "paymentAttempts": attempt},
            condition=NOT_CANCELLED,
        ),
    )
    # Last, so a failure before this line can't leave DemoPay working on a request the saga never paused for.
    sqs.send_message(
        QueueUrl=PSP_QUEUE_URL,
        DelaySeconds=delay,
        MessageBody=json.dumps(
            {
                "paymentIntentId": intent_id,
                "orderId": order_id,
                "walletId": order.get("walletId"),
                "amount": str(amount),
                "currency": order.get("currency", "INR"),
                "simulate": simulate,
            }
        ),
    )
    log.info("Payment requested; saga paused until the webhook", intentStatus=REQUESTED, amount=amount, providerDelaySeconds=delay)
    return {"paymentIntentId": intent_id, "status": REQUESTED}


def update_order(order_id: str, update: dict[str, Any]) -> None:
    """Apply a status write that requires "no cancel committed"; if a cancel got there first, raise OrderCancelled."""
    try:
        orders_table.update_item(Key={"orderId": order_id}, **update)
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        raise OrderCancelled(f"Order {order_id} was cancelled by the customer") from None


def upsert_intent(order: dict[str, Any], intent_id: str, token: str, simulate: str) -> dict[str, Any] | None:
    """Create the intent, or refresh its task token while it's still REQUESTED. None if it already finished."""
    now = utc_now_iso()
    try:
        return payments_table.update_item(
            Key={"paymentIntentId": intent_id},
            UpdateExpression=(
                "SET taskToken = :token, updatedAt = :now, #s = if_not_exists(#s, :requested), "
                "orderId = :order, userId = :user, walletId = :wallet, amount = :amount, currency = :currency, "
                "simulate = :simulate, requestedAt = if_not_exists(requestedAt, :now), createdAt = if_not_exists(createdAt, :now) "
                "ADD requestAttempts :one"
            ),
            ConditionExpression="attribute_not_exists(paymentIntentId) OR #s = :requested",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":token": token,
                ":now": now,
                ":requested": REQUESTED,
                ":order": order["orderId"],
                ":user": order.get("userId", "-"),
                ":wallet": order.get("walletId") or "-",
                ":amount": Decimal(order["totalAmount"]),
                ":currency": order.get("currency", "INR"),
                ":simulate": simulate,
                ":one": 1,
            },
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return None


def answer_from_finished_intent(intent_id: str, token: str, log: StructuredLogger) -> dict[str, Any]:
    """The payment already has an outcome (e.g. this step re-ran after it): resume with it, don't charge again."""
    intent = payments_table.get_item(Key={"paymentIntentId": intent_id}, ConsistentRead=True)["Item"]
    status = intent["status"]
    log.info("Intent already finished; answering the new task token from the stored outcome", intentStatus=status)
    if status == SUCCEEDED:
        sfn.send_task_success(
            taskToken=token,
            output=json.dumps({"paymentIntentId": intent_id, "paymentId": intent.get("paymentId"), "status": SUCCEEDED}),
        )
    else:
        cause = intent.get("declineReason") if status == FAILED else None
        sfn.send_task_failure(taskToken=token, error="PaymentDeclined", cause=cause or f"Payment intent already {status}")
    return {"paymentIntentId": intent_id, "status": status}
