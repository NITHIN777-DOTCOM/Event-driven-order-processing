"""DemoPay: a mock EXTERNAL payment provider (think Razorpay or Stripe), with two entry points.

1. SQS queue order-saga-psp-requests  ->  "charge this payment intent"
   Debits the customer's DemoPay wallet (or declines), then reports the outcome to OUR webhook over HTTPS,
   signed with HMAC-SHA256 (common/signing.py). A non-2xx answer raises, so SQS redelivers the message
   (5 receives, then order-saga-psp-dlq + an alarm).

2. Direct invoke {"operation": "refund", "paymentIntentId"}  ->  DemoPay's refund API, used by our
   compensation (refund_payment) and by the webhook's late-callback path. Idempotent. It refunds whatever of the
   charge has not been refunded yet.
   With "lineId" and "amount" (step 2.3) it refunds ONE order line: idempotent per (intent, line), and capped so
   the running refund total can never exceed the amount charged (invariant I7).

3. Direct invoke {"operation": "void", "paymentIntentId", ...}  ->  "don't take this payment" (step 2.4, the order
   was cancelled). Writes the intent's CHARGE record with outcome VOIDED, on the same condition the charge uses
   (the record must not exist yet). So exactly one of the two wins: if the void wins, the charge request still in
   the queue replays VOIDED and takes nothing (and sends no callback); if the charge won, the void is a no-op and
   the caller refunds.

What DemoPay knows: the intent id, order id, wallet and amount. It never sees the Step Functions task token;
the token stays inside our system (payments table), so the provider can't resume or fail our workflow directly.

Exactly-once money movement: DemoPay keeps its OWN records in order-saga-psp-transactions, keyed by
"CHARGE#<intent id>" and "REFUND#<intent id>". The wallet update, the ledger entry and that record are written in
ONE DynamoDB transaction, conditional on the record not existing yet. So a redelivered SQS message, a duplicate
request or a concurrent run can't debit (or refund) twice: the second attempt finds the record and replays the
outcome it already decided (same paymentId, same decision), including a decline.

Refund cap: the CHARGE record keeps `refundedAmount`, the running total of every refund of that charge. Each refund
adds to it in the same transaction, on the condition that the total before it is at most (charged - this refund).
DynamoDB can't evaluate "a + b <= c" in a condition, so the limit (c - b) is computed here; the charged amount is
immutable, so that is exact. Line refunds ("REFUND#<intent>#<lineId>") and the whole-remainder refund
("REFUND#<intent>") all go through the same counter, so in any order and any interleaving the total is capped.

Demo behaviour (the order's simulate flag travels in the request, like a test card number would):
  payment_declined       decline ("Card declined by issuer"); no money moves
  payment_timeout        DemoPay accepts the request but never answers (an outage): the saga times out
  payment_late           (delayed 150 s by the sender) charges normally, after our timeout: auto-refund follows
  webhook_duplicate      sends the success callback twice
  webhook_bad_signature  first sends a callback signed with the WRONG secret (expects 401), then the real one
  payment_slow           (delayed 20 s by the sender) charges normally, slowly enough to cancel while it's pending
  payment_manual         TEST ONLY: ignores the queued request; the test harness invokes the charge itself (with
                         "manualTrigger": true) at the exact moment it cancels, to race the two (e2e_test.py)
A wallet that can't cover the amount is declined for real ("Insufficient wallet balance").
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
import uuid
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import StructuredLogger, get_logger
from common.money import format_inr
from common.orders import cancellation_codes
from common.secrets import get_secret
from common.signing import signed_headers
from common.timeutil import utc_now_iso
from common.tracing import instrument_aws_sdk
from common.wallet import CREDIT, DEBIT, balance_update, ensure_wallet, txn_put

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

PSP_TABLE = os.environ["PSP_TABLE"]
WALLETS_TABLE = os.environ["WALLETS_TABLE"]
WALLET_TXNS_TABLE = os.environ["WALLET_TXNS_TABLE"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_SECRET_PARAMETER = os.environ.get("WEBHOOK_SECRET_PARAMETER", "")

dynamodb = boto3.resource("dynamodb")
psp_table = dynamodb.Table(PSP_TABLE)
wallets_table = dynamodb.Table(WALLETS_TABLE)
logger = get_logger("payment_provider")

SUCCEEDED, DECLINED, VOIDED = "SUCCEEDED", "DECLINED", "VOIDED"
MAX_BALANCE_CONFLICTS = 3
CALLBACK_TIMEOUT_SECONDS = 8


class WebhookDeliveryError(Exception):
    """Our webhook didn't accept the callback (non-2xx or unreachable). SQS will redeliver the request."""


class BalanceConflict(Exception):
    """The wallet kept changing under us. Raising lets SQS redeliver; the charge record makes that safe."""


class RefundRejected(Exception):
    """The refund would take the charge's refunded total above the amount charged (I7), or isn't valid at all.
    A bug upstream, never a normal outcome: it surfaces as a Lambda error (and an alarm), not as money moved."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if event.get("operation") == "refund":
        if event.get("lineId"):
            return refund_line(event["paymentIntentId"], event["lineId"], Decimal(str(event["amount"])), event.get("note", ""))
        return refund(event["paymentIntentId"], event.get("note", ""))
    if event.get("operation") == "void":
        return void(event)
    return handle_sqs_batch(event)


# --- 1. Charges (SQS) ------------------------------------------------------------------------------
def handle_sqs_batch(event: dict[str, Any]) -> dict[str, Any]:
    """Process each request on its own; report only the failed ones, so only those are redelivered."""
    failures = []
    for record in event.get("Records", []):
        request = json.loads(record["body"])
        log = logger.bind(orderId=request.get("orderId"), paymentIntentId=request.get("paymentIntentId"))
        try:
            process_request(request, int(record.get("attributes", {}).get("ApproximateReceiveCount", "1")), log)
        except Exception as err:  # noqa: BLE001 - any failure: let SQS retry this one message
            log.error("Payment request failed; SQS will redeliver it", error=type(err).__name__, reason=str(err))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def process_request(request: dict[str, Any], receive_count: int, log: StructuredLogger) -> None:
    simulate = request.get("simulate") or "none"
    log = log.bind(simulate=simulate, receiveCount=receive_count)
    if simulate == "payment_timeout":
        log.warning("Simulated provider outage: request accepted, no callback will ever be sent")
        return
    if simulate == "payment_manual" and not request.get("manualTrigger"):
        log.info("payment_manual: waiting for the test harness to trigger this charge")
        return

    charge = charge_once(request, simulate, log)
    if charge["outcome"] == VOIDED:
        # The merchant voided the intent (the order was cancelled) before we got to it: take nothing, say nothing.
        log.info("Intent was voided before it was charged; nothing taken, no callback")
        return
    callback = callback_body(request, charge)

    if simulate == "webhook_bad_signature":
        # An attacker's (or a misconfigured sender's) callback: same body, wrong key. Our webhook must say 401.
        status = post_callback(callback, secrets.token_hex(32))
        log.info("Sent a callback signed with the WRONG secret", webhookStatus=status, expected=401)
    copies = 2 if simulate == "webhook_duplicate" else 1
    for copy in range(1, copies + 1):
        status = post_callback(callback, get_secret(WEBHOOK_SECRET_PARAMETER))
        log.info("Webhook callback delivered", outcome=charge["outcome"], webhookStatus=status, copy=copy, copies=copies)
        if not 200 <= status < 300:
            raise WebhookDeliveryError(f"webhook answered HTTP {status}")


def charge_once(request: dict[str, Any], simulate: str, log: StructuredLogger) -> dict[str, Any]:
    """The charge decision for this intent: made once, then replayed forever (idempotency per intent id)."""
    key = f"CHARGE#{request['paymentIntentId']}"
    existing = psp_table.get_item(Key={"pspTxnId": key}, ConsistentRead=True).get("Item")
    if existing:
        log.info("Intent already processed; replaying the same outcome (no second debit)", outcome=existing["outcome"])
        return existing

    amount = Decimal(request["amount"])
    wid = request.get("walletId")
    if simulate == "payment_declined":
        return record_decline(request, "Card declined by issuer (simulated)", log)
    if not wid:
        return record_decline(request, "Order has no wallet (created before sign-in was required)", log)

    for _ in range(MAX_BALANCE_CONFLICTS):
        before = Decimal(ensure_wallet(wallets_table, wid)["balance"])
        if before < amount:
            return record_decline(
                request, f"Insufficient wallet balance: {format_inr(before)} available, {format_inr(amount)} needed", log
            )
        after = before - amount
        charge = charge_record(request, SUCCEEDED, balance_after=after)
        try:
            dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    balance_update(WALLETS_TABLE, wid, before, after),
                    txn_put(
                        WALLET_TXNS_TABLE, wid, DEBIT, amount, after, request["orderId"],
                        f"Payment for {request['orderId']}", {"paymentIntentId": request["paymentIntentId"]},
                    ),
                    {"Put": {"TableName": PSP_TABLE, "Item": charge, "ConditionExpression": "attribute_not_exists(pspTxnId)"}},
                ]
            )
        except ClientError as err:
            if err.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = cancellation_codes(err.response)
            if len(codes) > 2 and codes[2] == "ConditionalCheckFailed":
                log.info("A concurrent delivery charged this intent first; replaying its outcome")
                return psp_table.get_item(Key={"pspTxnId": charge["pspTxnId"]}, ConsistentRead=True)["Item"]
            if codes and codes[0] == "ConditionalCheckFailed":
                continue  # the balance changed between read and write: re-read
            raise
        log.info("Wallet debited", paymentId=charge["paymentId"], amount=amount, balanceAfter=after, walletId=wid)
        return charge
    raise BalanceConflict("Wallet is busy with other payments")


def charge_record(request: dict[str, Any], outcome: str, reason: str = "", balance_after: Decimal | None = None) -> dict[str, Any]:
    item = {
        "pspTxnId": f"CHARGE#{request['paymentIntentId']}",
        "kind": "CHARGE",
        "paymentIntentId": request["paymentIntentId"],
        "orderId": request["orderId"],
        "walletId": request.get("walletId") or "-",
        "amount": Decimal(request["amount"]),
        "currency": request.get("currency", "INR"),
        "outcome": outcome,
        "paymentId": f"PAY-{uuid.uuid4().hex[:12]}",
        "createdAt": utc_now_iso(),
    }
    if reason:
        item["reason"] = reason
    if balance_after is not None:
        item["balanceAfter"] = balance_after
    return item


def record_decline(request: dict[str, Any], reason: str, log: StructuredLogger) -> dict[str, Any]:
    """Store the decline too, so a redelivered request replays "declined" even if the balance changed since."""
    item = charge_record(request, DECLINED, reason)
    try:
        psp_table.put_item(Item=item, ConditionExpression="attribute_not_exists(pspTxnId)")
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return psp_table.get_item(Key={"pspTxnId": item["pspTxnId"]}, ConsistentRead=True)["Item"]
    log.warning("Payment declined", reason=reason)
    return item


def void(request: dict[str, Any]) -> dict[str, Any]:
    """Void the intent unless it was already charged or declined. Idempotent (a repeat finds VOIDED again)."""
    log = logger.bind(orderId=request.get("orderId"), paymentIntentId=request["paymentIntentId"], operation="void")
    item = charge_record(request, VOIDED, "voided by the merchant: the order was cancelled")
    try:
        psp_table.put_item(Item=item, ConditionExpression="attribute_not_exists(pspTxnId)")
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        existing = psp_table.get_item(Key={"pspTxnId": item["pspTxnId"]}, ConsistentRead=True)["Item"]
        log.info("Void found the intent already decided", outcome=existing["outcome"])
        return {"voided": existing["outcome"] == VOIDED, "outcome": existing["outcome"]}
    log.info("Payment intent voided before any charge")
    return {"voided": True, "outcome": VOIDED}


def callback_body(request: dict[str, Any], charge: dict[str, Any]) -> bytes:
    succeeded = charge["outcome"] == SUCCEEDED
    body = {
        "eventId": f"evt_{uuid.uuid4().hex[:16]}",
        "type": "payment.succeeded" if succeeded else "payment.declined",
        "paymentIntentId": request["paymentIntentId"],
        "orderId": request["orderId"],
        "paymentId": charge["paymentId"],
        "amount": str(charge["amount"]),
        "currency": charge.get("currency", "INR"),
        "createdAt": utc_now_iso(),
    }
    if not succeeded:
        body["reason"] = charge.get("reason", "declined")
    return json.dumps(body, separators=(",", ":")).encode()


def post_callback(body: bytes, secret: str) -> int:
    """POST the signed callback to our webhook; return the HTTP status (0 if unreachable)."""
    request = urllib.request.Request(
        WEBHOOK_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "DemoPay-Webhooks/1.0", **signed_headers(secret, body)},
    )
    try:
        with urllib.request.urlopen(request, timeout=CALLBACK_TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code
    except (urllib.error.URLError, TimeoutError):
        return 0


# --- 2. Refunds (direct invoke) ------------------------------------------------------------------
def refund(intent_id: str, note: str = "") -> dict[str, Any]:
    """Refund what is left of the charge of `intent_id` (all of it, unless lines were refunded already): once.
    Safe to call before a charge, after, and repeatedly. `note` (why) goes on the wallet CREDIT."""
    log = logger.bind(paymentIntentId=intent_id, operation="refund")
    charge = successful_charge(intent_id, log)
    if not charge:
        return {"refunded": False, "reason": "nothing charged"}
    log = log.bind(orderId=charge["orderId"])

    for _ in range(MAX_BALANCE_CONFLICTS):
        done = psp_table.get_item(Key={"pspTxnId": f"REFUND#{intent_id}"}, ConsistentRead=True).get("Item")
        if done:  # a repeat call: replay the refund that already happened
            log.info("Already refunded; idempotent no-op", refundId=done["refundId"])
            return refund_result(done, refunded=False)
        already = refunded_so_far(charge)
        remaining = Decimal(charge["amount"]) - already
        if remaining <= 0:
            log.info("Every line of this charge was refunded already; nothing left to refund", refundedAmount=already)
            return {"refunded": False, "reason": "already refunded line by line"}
        refund_item = refund_record(charge, f"REFUND#{intent_id}", remaining)
        description = f"Refund for {charge['orderId']}" + (f" ({note})" if note else "")
        outcome = move_refund(charge, refund_item, description, log, already_refunded=already)
        if outcome == "done":
            return refund_result(refund_item, refunded=True)
        if outcome == "duplicate":
            done = psp_table.get_item(Key={"pspTxnId": refund_item["pspTxnId"]}, ConsistentRead=True)["Item"]
            log.info("Already refunded; idempotent no-op", refundId=done["refundId"])
            return refund_result(done, refunded=False)
        charge = psp_table.get_item(Key={"pspTxnId": charge["pspTxnId"]}, ConsistentRead=True)["Item"]  # re-read, retry
    raise BalanceConflict("Wallet is busy; retry the refund")


def refund_line(intent_id: str, line_id: str, amount: Decimal, note: str = "") -> dict[str, Any]:
    """Refund ONE order line of the charge: idempotent per (intent, line), never above what was charged (I7)."""
    log = logger.bind(paymentIntentId=intent_id, operation="refund_line", lineId=line_id)
    charge = successful_charge(intent_id, log)
    if not charge:
        return {"refunded": False, "reason": "nothing charged"}
    log = log.bind(orderId=charge["orderId"])
    if not Decimal("0") < amount <= Decimal(charge["amount"]):
        raise RefundRejected(f"Line refund of {amount} is not between 0 and the charged {charge['amount']}")

    refund_item = refund_record(charge, f"REFUND#{intent_id}#{line_id}", amount, lineId=line_id)
    description = f"Refund for {charge['orderId']} line {line_id}" + (f" ({note})" if note else "")
    for _ in range(MAX_BALANCE_CONFLICTS):
        outcome = move_refund(charge, refund_item, description, log, cap=Decimal(charge["amount"]) - amount)
        if outcome in ("done", "duplicate"):
            record = refund_item
            if outcome == "duplicate":
                record = psp_table.get_item(Key={"pspTxnId": refund_item["pspTxnId"]}, ConsistentRead=True)["Item"]
                log.info("Line already refunded; idempotent no-op", refundId=record["refundId"])
            total = refunded_so_far(psp_table.get_item(Key={"pspTxnId": charge["pspTxnId"]}, ConsistentRead=True)["Item"])
            return {
                **refund_result(record, refunded=outcome == "done"),
                "lineId": line_id,
                "chargeAmount": str(charge["amount"]),
                "chargeRefundedTotal": str(total),
            }
        if outcome == "over_cap":
            raise RefundRejected(f"Refunding {amount} for line {line_id} would exceed the {charge['amount']} charged for {intent_id}")
    raise BalanceConflict("Wallet is busy; retry the refund")


def successful_charge(intent_id: str, log: StructuredLogger) -> dict[str, Any] | None:
    charge = psp_table.get_item(Key={"pspTxnId": f"CHARGE#{intent_id}"}, ConsistentRead=True).get("Item")
    if not charge or charge["outcome"] != SUCCEEDED:
        log.info("Nothing was charged for this intent; nothing to refund", chargeOutcome=(charge or {}).get("outcome"))
        return None
    return charge


def refunded_so_far(charge: dict[str, Any]) -> Decimal:
    return Decimal(str(charge.get("refundedAmount", "0")))


def refund_record(charge: dict[str, Any], key: str, amount: Decimal, **extra: Any) -> dict[str, Any]:
    return {
        "pspTxnId": key,
        "kind": "REFUND",
        "paymentIntentId": charge["paymentIntentId"],
        "orderId": charge["orderId"],
        "walletId": charge["walletId"],
        "amount": amount,
        "paymentId": charge["paymentId"],
        "refundId": f"RF-{uuid.uuid4().hex[:12]}",
        "createdAt": utc_now_iso(),
        **extra,
    }


def move_refund(
    charge: dict[str, Any],
    refund_item: dict[str, Any],
    description: str,
    log: StructuredLogger,
    cap: Decimal | None = None,
    already_refunded: Decimal | None = None,
) -> str:
    """ONE transaction: wallet credit + ledger CREDIT + refund record + the charge's running refund total.

    The charge record is guarded by `cap` (a line refund: the total before must be <= cap) or by `already_refunded`
    (the whole remainder: the total must still be exactly what we read). Returns "done", "duplicate" (this refund
    record exists already), "over_cap", or "retry" (the wallet balance or the charge's total changed: re-read).
    """
    wid, amount = charge["walletId"], refund_item["amount"]
    if cap is not None:
        guard, guard_values = "attribute_not_exists(refundedAmount) OR refundedAmount <= :limit", {":limit": cap}
    else:
        guard, guard_values = "attribute_not_exists(refundedAmount) OR refundedAmount = :seen", {":seen": already_refunded}
    before = Decimal(ensure_wallet(wallets_table, wid)["balance"])
    after = before + amount
    ledger_extra = {"paymentIntentId": charge["paymentIntentId"]}
    if "lineId" in refund_item:
        ledger_extra["lineId"] = refund_item["lineId"]
    try:
        dynamodb.meta.client.transact_write_items(
            TransactItems=[
                balance_update(WALLETS_TABLE, wid, before, after),
                txn_put(WALLET_TXNS_TABLE, wid, CREDIT, amount, after, charge["orderId"], description, ledger_extra),
                {"Put": {"TableName": PSP_TABLE, "Item": refund_item, "ConditionExpression": "attribute_not_exists(pspTxnId)"}},
                {
                    "Update": {
                        "TableName": PSP_TABLE,
                        "Key": {"pspTxnId": charge["pspTxnId"]},
                        "UpdateExpression": "SET refundedAmount = if_not_exists(refundedAmount, :zero) + :amount",
                        "ConditionExpression": guard,
                        "ExpressionAttributeValues": {":zero": Decimal("0"), ":amount": amount, **guard_values},
                    }
                },
            ]
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        codes = cancellation_codes(err.response)
        if len(codes) > 2 and codes[2] == "ConditionalCheckFailed":
            return "duplicate"
        if len(codes) > 3 and codes[3] == "ConditionalCheckFailed":
            return "over_cap" if cap is not None else "retry"
        if codes and codes[0] == "ConditionalCheckFailed":
            return "retry"
        raise
    log.info("Refunded", refundId=refund_item["refundId"], amount=amount, balanceAfter=after, walletId=wid)
    return "done"


def refund_result(item: dict[str, Any], refunded: bool) -> dict[str, Any]:
    return {
        "refunded": refunded,
        "alreadyRefunded": not refunded,
        "refundId": item["refundId"],
        "paymentId": item["paymentId"],
        "amount": str(item["amount"]),
    }
