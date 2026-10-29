"""Saga compensation: give back any money taken for this order, through the provider's refund API.

Runs on every failure path after RequestPayment (declined, timed out, a later step failed), BEFORE
ReleaseInventory. Idempotent end to end, so retries and re-runs can never refund twice:

  1. No payment intent -> nothing was ever requested: no-op.
  2. Intent still REQUESTED -> the saga is giving up before DemoPay answered: mark it FAILED ("abandoned"),
     conditionally. If DemoPay charges afterwards, its callback finds FAILED and the webhook refunds at once.
  3. Ask DemoPay to refund the intent. Its refund is idempotent per intent (REFUND#<intent> record), and a
     no-op when nothing was charged (declined, timed out before the charge).
  4. If money was returned (now or earlier): intent -> REFUNDED and PAYMENT_REFUNDED in the order's history,
     both conditional (record_refund in common/payments.py).

Timeout race: if the webhook captured the payment a moment before the 120 s timeout, the intent is SUCCEEDED
here and DemoPay has the charge, so this refunds it. The webhook deliberately never refunds a SUCCEEDED intent,
so exactly one of the two paths owns each refund (common/payments.py).
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import get_logger
from common.payments import FAILED, REFUNDED, REQUESTED, intent_id_for, invoke_provider_refund, money_returned, record_refund
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
PAYMENTS_TABLE = os.environ["PAYMENTS_TABLE"]
PROVIDER_FUNCTION = os.environ["PROVIDER_FUNCTION"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
payments_table = dynamodb.Table(PAYMENTS_TABLE)
lambda_client = boto3.client("lambda")
logger = get_logger("refund_payment")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = event["orderId"]
    intent_id = intent_id_for(order_id)
    log = logger.bind(orderId=order_id, paymentIntentId=intent_id)

    intent = payments_table.get_item(Key={"paymentIntentId": intent_id}, ConsistentRead=True).get("Item")
    if not intent:
        log.info("No payment was requested for this order; nothing to refund")
        return {"orderId": order_id, "refunded": False, "reason": "no payment requested"}

    if intent["status"] == REQUESTED:
        abandon(intent, log)

    refund = invoke_provider_refund(lambda_client, PROVIDER_FUNCTION, intent_id)
    if not money_returned(refund):
        log.info("Nothing was charged; nothing to refund", intentStatus=intent["status"])
        return {"orderId": order_id, "refunded": False, "reason": refund.get("reason", "nothing charged")}

    record_refund(payments_table, orders_table, intent, refund, "saga compensation")
    log.info(
        "Payment refunded" if refund.get("refunded") else "Already refunded (idempotent no-op)",
        intentStatus=REFUNDED,
        refundId=refund.get("refundId"),
        amount=refund.get("amount"),
    )
    return {"orderId": order_id, "refunded": bool(refund.get("refunded")), "refundId": refund.get("refundId")}


def abandon(intent: dict[str, Any], log: Any) -> None:
    """REQUESTED -> FAILED, only if nobody changed it meanwhile. Keeps invariant I4: no intent stays REQUESTED."""
    try:
        payments_table.update_item(
            Key={"paymentIntentId": intent["paymentIntentId"]},
            UpdateExpression="SET #s = :failed, failureReason = :why, failedAt = :now, updatedAt = :now",
            ConditionExpression="#s = :requested",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":failed": FAILED,
                ":requested": REQUESTED,
                ":why": "abandoned: the saga compensated before the provider answered",
                ":now": utc_now_iso(),
            },
        )
        intent["status"] = FAILED
        log.info("Payment intent abandoned", intentStatus=FAILED)
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
