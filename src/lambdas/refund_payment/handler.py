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

Line refunds (step 2.3): with {"orderId", "lineIds": [...]} it refunds only those order lines (items that could
not be fulfilled after payment). Each line's amount is the one stored on the order when it was created (server-side
prices), never a figure from the input. DemoPay refunds each line at most once and never above the amount charged
(I7). Each refund is recorded on its line (`refundedAmount`, `refundId`), added to the order's `refundedAmount`, and
shown in the history as LINE_REFUNDED, all in one conditional write per line. When the lines add up to the whole
charge, the intent becomes REFUNDED; otherwise it stays SUCCEEDED with its `refundedAmount`.

Cancellation (step 2.4): with {"orderId", "cancelled": true} (the saga's RefundWhatIsLeft step) it first VOIDS the
intent at DemoPay, so a charge still queued there takes nothing, and marks the intent `cancelled`. It then refunds
whatever is left of a charge that did happen, exactly as above: DemoPay refunds the remainder once, so a cancel
can never refund more than was charged (I7), even if the webhook refunds the same late charge at the same moment.
It returns the amount refunded ("0.00" when nothing was charged) for the cancellation email.

Timeout race: if the webhook captured the payment a moment before the 120 s timeout, the intent is SUCCEEDED
here and DemoPay has the charge, so this refunds it. The webhook deliberately never refunds a SUCCEEDED intent,
so exactly one of the two paths owns each refund (common/payments.py).
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common import chaos
from common.logger import StructuredLogger, get_logger
from common.money import format_inr
from common.orders import LINE_FULFILLED, LINE_REFUNDED, find_line, history_entry, order_lines
from common.payments import (
    FAILED,
    REFUNDED,
    REQUESTED,
    SUCCEEDED,
    intent_id_for,
    invoke_provider_refund,
    invoke_provider_void,
    money_returned,
    record_refund,
)
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
    if "lineIds" in event:
        return refund_lines(order_id, event["lineIds"], log)
    cancelled = bool(event.get("cancelled"))
    if cancelled:
        log = log.bind(cancelled=True)

    intent = payments_table.get_item(Key={"paymentIntentId": intent_id}, ConsistentRead=True).get("Item")
    if not intent:
        log.info("No payment was requested for this order; nothing to refund", **cancel_event(cancelled, "nothing_charged"))
        return {"orderId": order_id, "refunded": False, "refundedAmount": "0.00", "reason": "no payment requested"}

    if intent["status"] == REQUESTED:
        abandon(intent, log, cancelled)
    if cancelled:
        void = invoke_provider_void(lambda_client, PROVIDER_FUNCTION, intent)
        log.info("Payment intent voided at DemoPay" if void.get("voided") else "DemoPay had already decided the intent", outcome=void.get("outcome"))

    refund = invoke_provider_refund(lambda_client, PROVIDER_FUNCTION, intent_id, note="order cancelled" if cancelled else "")
    if not money_returned(refund):
        log.info("Nothing was charged; nothing to refund", intentStatus=intent["status"], **cancel_event(cancelled, "nothing_charged"))
        return {"orderId": order_id, "refunded": False, "refundedAmount": "0.00", "reason": refund.get("reason", "nothing charged")}

    record_refund(payments_table, orders_table, intent, refund, "order cancelled" if cancelled else "saga compensation")
    log.info(
        "Payment refunded" if refund.get("refunded") else "Already refunded (idempotent no-op)",
        intentStatus=REFUNDED,
        refundId=refund.get("refundId"),
        amount=refund.get("amount"),
        **cancel_event(cancelled, "refunded"),
    )
    if refund.get("refunded") and chaos.enabled():  # E3 test switch: the order is read only while chaos is on
        chaos.crash_after_write(orders_table.get_item(Key={"orderId": order_id}).get("Item"), "full_refund", log)
    return {
        "orderId": order_id,
        "refunded": bool(refund.get("refunded")),
        "refundId": refund.get("refundId"),
        "refundedAmount": f"{Decimal(str(refund.get('amount', '0'))):.2f}",
    }


def cancel_event(cancelled: bool, outcome: str) -> dict[str, str]:
    """Log field for the OrderSaga/CancelEvents metric, only on the cancel path."""
    return {"cancelEvent": outcome} if cancelled else {}


def abandon(intent: dict[str, Any], log: Any, cancelled: bool = False) -> None:
    """REQUESTED -> FAILED, only if nobody changed it meanwhile. Keeps invariant I4: no intent stays REQUESTED.
    On a cancellation the intent is also marked `cancelled`, so a late charge is refunded as one (webhook)."""
    why = "cancelled by the customer before the provider answered" if cancelled else "abandoned: the saga compensated before the provider answered"
    try:
        payments_table.update_item(
            Key={"paymentIntentId": intent["paymentIntentId"]},
            UpdateExpression="SET #s = :failed, failureReason = :why, failedAt = :now, updatedAt = :now"
            + (", cancelled = :true" if cancelled else ""),
            ConditionExpression="#s = :requested",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":failed": FAILED,
                ":requested": REQUESTED,
                ":why": why,
                ":now": utc_now_iso(),
                **({":true": True} if cancelled else {}),
            },
        )
        intent["status"] = FAILED
        log.info("Payment intent abandoned", intentStatus=FAILED)
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


# --- Line refunds (step 2.3) -----------------------------------------------------------------------
def refund_lines(order_id: str, line_ids: list[str], log: StructuredLogger) -> dict[str, Any]:
    """Refund exactly these lines of a PAID order. Safe to re-run: every line is refunded and recorded once."""
    intent_id = intent_id_for(order_id)
    intent = payments_table.get_item(Key={"paymentIntentId": intent_id}, ConsistentRead=True).get("Item")
    if not intent or intent["status"] not in (SUCCEEDED, REFUNDED):
        # Lines are only refunded after the payment succeeded. Anything else is a bug: fail loudly (alarm).
        raise RuntimeError(f"Payment intent {intent_id} is {(intent or {}).get('status', 'missing')}; can't refund lines")
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]

    refunded = Decimal("0")
    newly_refunded = 0  # metrics count each line once, not again on a re-run
    charge_amount = charge_refunded = None
    for line_id in line_ids:
        line = find_line(order, line_id)
        if line.get("fulfillment") == LINE_FULFILLED:
            # A shipped line is never refunded. If the Map called it unavailable (e.g. fulfill_item timed out
            # after its transaction committed), stop here, before any money moves: an alarm, not a free item.
            raise RuntimeError(f"Line {line_id} of {order_id} was fulfilled; refusing to refund it")
        note = f"{line['quantity']} x {line['name']}"
        result = invoke_provider_refund(
            lambda_client, PROVIDER_FUNCTION, intent_id, {"lineId": line_id, "amount": line["lineAmount"], "note": note}
        )
        if not money_returned(result):
            raise RuntimeError(f"DemoPay refunded nothing for line {line_id}: {result.get('reason')}")
        record_line_refund(order, line, result, log)
        refunded += line["lineAmount"]
        charge_amount, charge_refunded = Decimal(result["chargeAmount"]), Decimal(result["chargeRefundedTotal"])
        if result.get("refunded"):
            newly_refunded += 1
            log.info("Line refunded", fulfillmentEvent="line_refunded", lineId=line_id, amount=float(line["lineAmount"]), refundId=result["refundId"])
        else:
            log.info("Line already refunded (idempotent no-op)", lineId=line_id, refundId=result["refundId"])

    if charge_amount is not None:
        record_intent_refunds(intent, charge_amount, charge_refunded)
    refunded_ids = set(line_ids)
    kept = [line for line in order_lines(order) if line["lineId"] not in refunded_ids]
    lost = [line for line in order_lines(order) if line["lineId"] in refunded_ids]
    outcome = {"fulfillmentEvent": "partially_fulfilled" if kept else "all_unavailable"} if newly_refunded else {}
    log.info("Unavailable lines refunded", refundedAmount=float(refunded), refundedLines=len(lost), keptLines=len(kept), **outcome)
    if newly_refunded:
        chaos.crash_after_write(order, "line_refund", log)  # E3 test switch: inert unless CHAOS_ENABLED
    return {
        "orderId": order_id,
        "refunded": True,
        "refundedAmount": f"{refunded:.2f}",
        "refundedLineIds": line_ids,
        "refundedItemsSummary": summary(lost),
        "keptItemsSummary": summary(kept) or "(none)",
        "keptAmount": f"{sum((line['lineAmount'] for line in kept), Decimal('0')):.2f}",
        "lineCount": len(kept) + len(lost),
        "keptCount": len(kept),
    }


def record_line_refund(order: dict[str, Any], line: dict[str, Any], result: dict[str, Any], log: StructuredLogger) -> None:
    """On the order, once: the line's refundedAmount + refundId, the order's running refundedAmount, LINE_REFUNDED."""
    index, amount = line["index"], line["lineAmount"]
    detail = f"{format_inr(amount)} refunded to DemoPay for {line['quantity']} x {line['name']} (line {line['lineId']})"
    try:
        orders_table.update_item(
            Key={"orderId": order["orderId"]},
            UpdateExpression=(
                f"SET #items[{index}].refundedAmount = :amount, #items[{index}].refundId = :rid, "
                "refundedAmount = if_not_exists(refundedAmount, :zero) + :amount, updatedAt = :now, "
                "statusHistory = list_append(statusHistory, :entry)"
            ),
            ConditionExpression=f"attribute_exists(orderId) AND attribute_not_exists(#items[{index}].refundedAmount)",
            ExpressionAttributeNames={"#items": "items"},
            ExpressionAttributeValues={
                ":amount": amount,
                ":rid": result["refundId"],
                ":zero": Decimal("0"),
                ":now": utc_now_iso(),
                ":entry": [history_entry(LINE_REFUNDED, detail)],
            },
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        log.info("Line refund already recorded on the order", lineId=line["lineId"])


def record_intent_refunds(intent: dict[str, Any], charge_amount: Decimal, refunded_total: Decimal) -> None:
    """The intent mirrors DemoPay's running total; once every rupee is back it becomes REFUNDED (I4 stays final)."""
    fully = refunded_total >= charge_amount
    update = "SET refundedAmount = :total, updatedAt = :now"
    values: dict[str, Any] = {":total": refunded_total, ":now": utc_now_iso()}
    extra: dict[str, Any] = {}
    if fully:
        update += ", #s = :refunded, refundedAt = :now"
        values[":refunded"] = REFUNDED
        extra["ExpressionAttributeNames"] = {"#s": "status"}
    payments_table.update_item(
        Key={"paymentIntentId": intent["paymentIntentId"]},
        UpdateExpression=update,
        ConditionExpression="attribute_not_exists(refundedAmount) OR refundedAmount <= :total",  # never goes backwards
        ExpressionAttributeValues=values,
        **extra,
    )


def summary(lines: list[dict[str, Any]]) -> str:
    """Lines for the customer email, e.g. "- 2 x Wireless Mouse (L2): ₹1,598"."""
    return "\n".join(f"- {line['quantity']} x {line['name']} ({line['lineId']}): {format_inr(line['lineAmount'])}" for line in lines)
