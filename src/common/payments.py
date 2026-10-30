"""Payment intents: OUR record of a payment we asked the provider (DemoPay) to take.

Table order-saga-payments, PK paymentIntentId. One intent per order, with a DETERMINISTIC id (PI-<orderId>),
so a retried saga step, a duplicate SQS message or a re-run can never create a second intent, and so a
second charge is impossible on our side as well as on the provider's (which keys its charges by intent id).

Lifecycle (every arrow is a conditional write, so two writers can't both win):

    REQUESTED --webhook "succeeded"--------------> SUCCEEDED --saga compensation------------> REFUNDED
        |------webhook "declined"----------------> FAILED    --late "succeeded" callback-----> REFUNDED
        |------saga gave up (compensation)-------> FAILED
        `------no callback within 120 s (saga)---> TIMED_OUT --late "succeeded" callback-----> REFUNDED

FINAL_STATUSES are the states an intent must reach (invariant I4). SUCCEEDED, FAILED and TIMED_OUT can still
become REFUNDED, but only when the provider reports money actually moved (refund = exactly that charge, once).

Who refunds what, so a charge is refunded at most once and never left behind (invariants I2, I3):
  - SUCCEEDED intents: only the saga's compensation (RefundPayment). The saga knows whether the order failed.
  - TIMED_OUT / FAILED intents that later turn out to be charged: the webhook (late callback), immediately.
  - Both call the provider's refund, which is idempotent per intent, and record_refund() writes once.

Customer cancellation (step 2.4): the cancel branch first VOIDS the intent at the provider (invoke_provider_void).
If DemoPay hasn't charged yet, the charge it still has queued becomes a no-op, so nothing is ever taken. If it
charged first, the void changes nothing and the refund below returns the money. The intent is marked `cancelled`,
so a charge that slips through is recognisable as a late charge on a cancelled order.
"""

from __future__ import annotations

import json
import random
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from common.money import format_inr
from common.orders import PAYMENT_REFUNDED, history_event
from common.timeutil import utc_now_iso

REQUESTED = "REQUESTED"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
TIMED_OUT = "TIMED_OUT"
REFUNDED = "REFUNDED"
FINAL_STATUSES = frozenset({SUCCEEDED, FAILED, TIMED_OUT, REFUNDED})

PAYMENT_TIMEOUT_SECONDS = 120  # the state machine's TimeoutSeconds on RequestPayment (kept in sync by hand)
LATE_CALLBACK_DELAY_SECONDS = 150  # simulate=payment_late: the provider answers after the saga gave up
SLOW_PAYMENT_DELAY_SECONDS = 20  # simulate=payment_slow: time to cancel while the payment is still pending (2.4)


def intent_id_for(order_id: str) -> str:
    """Deterministic: the same order always maps to the same intent."""
    return f"PI-{order_id}"


def provider_delay_seconds(simulate: str) -> int:
    """How long DemoPay "takes" before it processes a request (an SQS DelaySeconds; SQS allows up to 900).

    A real gateway answers in a few seconds; payment_late makes it answer after our 120 s timeout, payment_slow
    within it but slowly enough to press Cancel first.
    """
    if simulate == "payment_late":
        return LATE_CALLBACK_DELAY_SECONDS
    if simulate == "payment_slow":
        return SLOW_PAYMENT_DELAY_SECONDS
    return random.randint(2, 5)


def invoke_provider_refund(
    lambda_client: Any, function_name: str, intent_id: str, line: dict[str, Any] | None = None, note: str = ""
) -> dict[str, Any]:
    """Call DemoPay's refund API (a synchronous, IAM-authorised Lambda invoke). Idempotent per intent.

    Returns {"refunded": bool, "alreadyRefunded": bool, "refundId", "amount", "paymentId"} or, when nothing was
    charged, {"refunded": False, "reason": "nothing charged"}. With `line` ({"lineId", "amount", "note"}) it refunds
    that one order line instead, idempotent per (intent, line) and capped at the amount charged. `note` says why
    (e.g. "order cancelled"); the customer sees it on the wallet CREDIT.
    """
    request: dict[str, Any] = {"operation": "refund", "paymentIntentId": intent_id}
    if line:
        request.update(lineId=line["lineId"], amount=str(line["amount"]), note=line.get("note", ""))
    elif note:
        request["note"] = note
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(request).encode(),
    )
    payload = json.loads(response["Payload"].read() or b"{}")
    if response.get("FunctionError"):
        raise RuntimeError(f"DemoPay refund failed: {payload.get('errorMessage', payload)}")
    return payload


def invoke_provider_void(lambda_client: Any, function_name: str, intent: dict[str, Any]) -> dict[str, Any]:
    """Call DemoPay's void API: "don't take this payment". Idempotent, race-safe with its own charge.

    Returns {"voided": True} if the payment can no longer be taken, or {"voided": False, "outcome": ...} if DemoPay
    had already decided it (SUCCEEDED: it charged, so the caller refunds; DECLINED: nothing to do)."""
    request = {
        "operation": "void",
        "paymentIntentId": intent["paymentIntentId"],
        "orderId": intent["orderId"],
        "walletId": intent.get("walletId", "-"),
        "amount": str(intent["amount"]),
        "currency": intent.get("currency", "INR"),
    }
    response = lambda_client.invoke(FunctionName=function_name, InvocationType="RequestResponse", Payload=json.dumps(request).encode())
    payload = json.loads(response["Payload"].read() or b"{}")
    if response.get("FunctionError"):
        raise RuntimeError(f"DemoPay void failed: {payload.get('errorMessage', payload)}")
    return payload


def money_returned(refund: dict[str, Any]) -> bool:
    """True if the provider refunded now or had refunded before: either way the charge is reversed."""
    return bool(refund.get("refunded") or refund.get("alreadyRefunded"))


def record_refund(payments_table: Any, orders_table: Any, intent: dict[str, Any], refund: dict[str, Any], note: str) -> None:
    """Mark the intent REFUNDED and add PAYMENT_REFUNDED to the order's history. Safe to call any number of times.

    The order's `status` is NOT changed: this can run after the order already FAILED (a late callback), and a
    terminal status must stay terminal. Each write is conditional, so a second call changes nothing. The amount
    is added to the order's `refundedAmount` (step 2.4: the tracker shows "Cancelled - refunded ₹X" from it).
    """
    now = utc_now_iso()
    try:
        payments_table.update_item(
            Key={"paymentIntentId": intent["paymentIntentId"]},
            UpdateExpression="SET #s = :refunded, refundId = :rid, refundedAt = :now, updatedAt = :now, "
            "paymentId = if_not_exists(paymentId, :pid)",
            ConditionExpression="#s <> :refunded",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":refunded": REFUNDED,
                ":rid": refund.get("refundId", "-"),
                ":pid": refund.get("paymentId", "-"),
                ":now": now,
            },
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
    amount = Decimal(str(refund.get("amount", intent.get("amount", "0"))))
    update = history_event(
        PAYMENT_REFUNDED,
        f"{format_inr(amount)} refunded to DemoPay ({note})",
        {"refunded": True, "refundId": refund.get("refundId", "-")},
        condition="attribute_not_exists(refunded)",
    )
    # Added, not set: line refunds (step 2.3) may already have refunded part of the charge.
    update["UpdateExpression"] += ", refundedAmount = if_not_exists(refundedAmount, :zero) + :refundAmount"
    update["ExpressionAttributeValues"].update({":zero": Decimal("0"), ":refundAmount": amount})
    try:
        orders_table.update_item(Key={"orderId": intent["orderId"]}, **update)
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
