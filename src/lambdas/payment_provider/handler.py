"""DemoPay: a mock EXTERNAL payment provider (think Razorpay or Stripe), with two entry points.

1. SQS queue order-saga-psp-requests  ->  "charge this payment intent"
   Debits the customer's DemoPay wallet (or declines), then reports the outcome to OUR webhook over HTTPS,
   signed with HMAC-SHA256 (common/signing.py). A non-2xx answer raises, so SQS redelivers the message
   (5 receives, then order-saga-psp-dlq + an alarm).

2. Direct invoke {"operation": "refund", "paymentIntentId"}  ->  DemoPay's refund API, used by our
   compensation (refund_payment) and by the webhook's late-callback path. Idempotent.

What DemoPay knows: the intent id, order id, wallet and amount. It never sees the Step Functions task token;
the token stays inside our system (payments table), so the provider can't resume or fail our workflow directly.

Exactly-once money movement: DemoPay keeps its OWN records in order-saga-psp-transactions, keyed by
"CHARGE#<intent id>" and "REFUND#<intent id>". The wallet update, the ledger entry and that record are written in
ONE DynamoDB transaction, conditional on the record not existing yet. So a redelivered SQS message, a duplicate
request or a concurrent run can't debit (or refund) twice: the second attempt finds the record and replays the
outcome it already decided (same paymentId, same decision), including a decline.

Demo behaviour (the order's simulate flag travels in the request, like a test card number would):
  payment_declined       decline ("Card declined by issuer"); no money moves
  payment_timeout        DemoPay accepts the request but never answers (an outage): the saga times out
  payment_late           (delayed 150 s by the sender) charges normally, after our timeout: auto-refund follows
  webhook_duplicate      sends the success callback twice
  webhook_bad_signature  first sends a callback signed with the WRONG secret (expects 401), then the real one
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

SUCCEEDED, DECLINED = "SUCCEEDED", "DECLINED"
MAX_BALANCE_CONFLICTS = 3
CALLBACK_TIMEOUT_SECONDS = 8


class WebhookDeliveryError(Exception):
    """Our webhook didn't accept the callback (non-2xx or unreachable). SQS will redeliver the request."""


class BalanceConflict(Exception):
    """The wallet kept changing under us. Raising lets SQS redeliver; the charge record makes that safe."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if event.get("operation") == "refund":
        return refund(event["paymentIntentId"])
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

    charge = charge_once(request, simulate, log)
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
def refund(intent_id: str) -> dict[str, Any]:
    """Refund the charge of `intent_id`: exactly once. Safe to call before a charge, after, and repeatedly."""
    log = logger.bind(paymentIntentId=intent_id, operation="refund")
    charge = psp_table.get_item(Key={"pspTxnId": f"CHARGE#{intent_id}"}, ConsistentRead=True).get("Item")
    if not charge or charge["outcome"] != SUCCEEDED:
        log.info("Nothing was charged for this intent; nothing to refund", chargeOutcome=(charge or {}).get("outcome"))
        return {"refunded": False, "reason": "nothing charged"}
    log = log.bind(orderId=charge["orderId"])

    amount, wid = Decimal(charge["amount"]), charge["walletId"]
    refund_item = {
        "pspTxnId": f"REFUND#{intent_id}",
        "kind": "REFUND",
        "paymentIntentId": intent_id,
        "orderId": charge["orderId"],
        "walletId": wid,
        "amount": amount,
        "paymentId": charge["paymentId"],
        "refundId": f"RF-{uuid.uuid4().hex[:12]}",
        "createdAt": utc_now_iso(),
    }
    for _ in range(MAX_BALANCE_CONFLICTS):
        before = Decimal(ensure_wallet(wallets_table, wid)["balance"])
        after = before + amount
        try:
            dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    balance_update(WALLETS_TABLE, wid, before, after),
                    txn_put(
                        WALLET_TXNS_TABLE, wid, CREDIT, amount, after, charge["orderId"],
                        f"Refund for {charge['orderId']}", {"paymentIntentId": intent_id},
                    ),
                    {"Put": {"TableName": PSP_TABLE, "Item": refund_item, "ConditionExpression": "attribute_not_exists(pspTxnId)"}},
                ]
            )
        except ClientError as err:
            if err.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = cancellation_codes(err.response)
            if len(codes) > 2 and codes[2] == "ConditionalCheckFailed":
                done = psp_table.get_item(Key={"pspTxnId": refund_item["pspTxnId"]}, ConsistentRead=True)["Item"]
                log.info("Already refunded; idempotent no-op", refundId=done["refundId"])
                return refund_result(done, refunded=False)
            if codes and codes[0] == "ConditionalCheckFailed":
                continue
            raise
        log.info("Refunded", refundId=refund_item["refundId"], amount=amount, balanceAfter=after, walletId=wid)
        return refund_result(refund_item, refunded=True)
    raise BalanceConflict("Wallet is busy; retry the refund")


def refund_result(item: dict[str, Any], refunded: bool) -> dict[str, Any]:
    return {
        "refunded": refunded,
        "alreadyRefunded": not refunded,
        "refundId": item["refundId"],
        "paymentId": item["paymentId"],
        "amount": str(item["amount"]),
    }
