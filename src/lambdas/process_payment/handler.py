"""Saga step 2: take the payment by debiting the customer's DemoPay wallet.

The debit is ONE DynamoDB transaction across three tables:
  wallets       balance -= total      (only if the balance is still what we read, and it covers the total)
  wallet-txns   + DEBIT ledger entry  {orderId, amount, balanceAfter}
  orders        paymentId, PAYMENT_CAPTURED in statusHistory   (only if the order has NO paymentId yet)
So money moves exactly once, together with its ledger entry and the order update, or not at all.

Failures:
  - balance too low          -> PaymentDeclined("Insufficient wallet balance ...")  a real, natural decline
  - simulate=payment_declined -> PaymentDeclined (card declined), before any money moves
  - simulate=payment_flaky   -> PaymentTransientError on attempts 1 and 2, then a normal debit on attempt 3
Step Functions retries PaymentTransientError and catches PaymentDeclined; it then runs compensation
(RefundPayment, then ReleaseInventory).

No double charge: an order that already has a paymentId returns that payment, and the order
condition in the transaction blocks a concurrent second debit.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Any, Callable

import boto3
from botocore.exceptions import ClientError

from common.logger import StructuredLogger, get_logger
from common.money import format_inr
from common.orders import PAYMENT_CAPTURED, PAYMENT_DECLINED, PAYMENT_RETRY, cancellation_codes, status_update
from common.tracing import instrument_aws_sdk
from common.wallet import DEBIT, balance_update, ensure_wallet, txn_put, wallet_id

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
WALLETS_TABLE = os.environ["WALLETS_TABLE"]
WALLET_TXNS_TABLE = os.environ["WALLET_TXNS_TABLE"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
wallets_table = dynamodb.Table(WALLETS_TABLE)
logger = get_logger("process_payment")

FLAKY_FAILURES = 2  # payment_flaky fails this many times before succeeding
MAX_BALANCE_CONFLICTS = 3  # concurrent payments from the same wallet: re-read and retry this often


class PaymentDeclined(Exception):
    """Permanent failure. Caught by the state machine, which compensates."""


class PaymentTransientError(Exception):
    """Temporary failure (e.g. a gateway timeout). The state machine retries it."""


# --- Demo simulations: they run BEFORE any money moves ------------------------------------------
def no_simulation(attempt: int) -> None:
    return None


def decline(attempt: int) -> None:
    raise PaymentDeclined("Card declined by issuer (simulated)")


def flaky(attempt: int) -> None:
    if attempt <= FLAKY_FAILURES:
        raise PaymentTransientError(f"Payment gateway timeout on attempt {attempt} (simulated)")


SIMULATIONS: dict[str, Callable[[int], None]] = {
    "none": no_simulation,
    "payment_declined": decline,
    "payment_flaky": flaky,
}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    order_id = event["orderId"]
    simulate = event.get("simulate") or "none"
    log = logger.bind(orderId=order_id, simulate=simulate)

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    if order.get("paymentId"):
        log.info("Order already paid; returning the existing payment (no second charge)", paymentId=order["paymentId"])
        return {"paymentId": order["paymentId"], "status": "CAPTURED"}

    attempt = record_attempt(order_id)
    log = log.bind(attempt=attempt)

    try:
        SIMULATIONS.get(simulate, no_simulation)(attempt)
        return debit_wallet(order, attempt, log)
    except PaymentTransientError as err:
        log.warning("Transient payment failure; Step Functions will retry", reason=str(err))
        orders_table.update_item(
            Key={"orderId": order_id},
            **status_update(PAYMENT_RETRY, f"Attempt {attempt} failed: {err} - retrying"),
        )
        raise
    except PaymentDeclined as err:
        log.warning("Payment declined; saga will compensate", reason=str(err))
        orders_table.update_item(
            Key={"orderId": order_id},
            **status_update(PAYMENT_DECLINED, f"Attempt {attempt}: {err}"),
        )
        raise


def record_attempt(order_id: str) -> int:
    """Atomically increment paymentAttempts and return the new value (1 on the first attempt)."""
    result = orders_table.update_item(
        Key={"orderId": order_id},
        UpdateExpression="ADD paymentAttempts :one",
        ConditionExpression="attribute_exists(orderId)",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"]["paymentAttempts"])


def debit_wallet(order: dict[str, Any], attempt: int, log: StructuredLogger) -> dict[str, str]:
    """Move the order total out of the customer's wallet: atomically, exactly once."""
    order_id = order["orderId"]
    amount = Decimal(order["totalAmount"])
    wid = wallet_id(order["customerEmail"])

    for _ in range(MAX_BALANCE_CONFLICTS):
        before = Decimal(ensure_wallet(wallets_table, wid)["balance"])
        if before < amount:
            raise PaymentDeclined(
                f"Insufficient wallet balance: {format_inr(before)} available, {format_inr(amount)} needed"
            )
        after = before - amount
        payment_id = f"PAY-{uuid.uuid4().hex[:12]}"
        detail = f"{format_inr(amount)} debited from DemoPay · balance {format_inr(after)} (attempt {attempt})"
        try:
            dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    balance_update(WALLETS_TABLE, wid, before, after),
                    txn_put(WALLET_TXNS_TABLE, wid, DEBIT, amount, after, order_id, f"Payment for {order_id}"),
                    {
                        "Update": {
                            "TableName": ORDERS_TABLE,
                            "Key": {"orderId": order_id},
                            **status_update(
                                PAYMENT_CAPTURED,
                                detail,
                                {"paymentId": payment_id, "paidAmount": amount, "walletId": wid},
                                condition="attribute_not_exists(paymentId)",
                            ),
                        }
                    },
                ]
            )
        except ClientError as err:
            if err.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = cancellation_codes(err.response)
            if len(codes) > 2 and codes[2] == "ConditionalCheckFailed":
                # A concurrent attempt paid first: return ITS payment and charge nothing.
                existing = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]["paymentId"]
                log.info("Concurrent attempt already paid; returning it", paymentId=existing)
                return {"paymentId": existing, "status": "CAPTURED"}
            if codes and codes[0] == "ConditionalCheckFailed":
                log.info("Wallet balance changed concurrently; re-reading")
                continue
            raise
        log.info("Wallet debited", paymentId=payment_id, amount=amount, balanceAfter=after, walletId=wid)
        return {"paymentId": payment_id, "status": "CAPTURED"}

    raise PaymentTransientError("Wallet is busy with other payments; retrying")
