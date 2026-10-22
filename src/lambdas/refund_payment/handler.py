"""Saga compensation: refund a payment that was taken, back into the customer's DemoPay wallet.

It runs on every failure path after ProcessPayment, BEFORE ReleaseInventory. It is IDEMPOTENT:
  - nothing was debited (declined, insufficient balance, retries exhausted) -> no-op
  - already refunded                                                          -> no-op
  - otherwise ONE transaction: balance += paidAmount, CREDIT ledger entry, order.refunded = true
    (conditional on the order having a paymentId and NOT being refunded yet)
So a retried or repeated run can never refund twice.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import get_logger
from common.money import format_inr
from common.orders import PAYMENT_REFUNDED, cancellation_codes, status_update
from common.tracing import instrument_aws_sdk
from common.wallet import CREDIT, balance_update, ensure_wallet, txn_put

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
WALLETS_TABLE = os.environ["WALLETS_TABLE"]
WALLET_TXNS_TABLE = os.environ["WALLET_TXNS_TABLE"]

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(ORDERS_TABLE)
wallets_table = dynamodb.Table(WALLETS_TABLE)
logger = get_logger("refund_payment")

MAX_BALANCE_CONFLICTS = 3


class RefundConflict(Exception):
    """The wallet kept changing under us. Step Functions retries the step (it's idempotent)."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    order_id = event["orderId"]
    log = logger.bind(orderId=order_id)

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    if not order.get("paymentId") or not order.get("paidAmount"):
        log.info("Nothing was charged for this order; nothing to refund")
        return {"orderId": order_id, "refunded": False, "reason": "nothing charged"}
    if order.get("refunded"):
        log.info("Already refunded; nothing to do (idempotent no-op)")
        return {"orderId": order_id, "refunded": False, "reason": "already refunded"}

    amount, wid = Decimal(order["paidAmount"]), order["walletId"]
    for _ in range(MAX_BALANCE_CONFLICTS):
        before = Decimal(ensure_wallet(wallets_table, wid)["balance"])
        after = before + amount
        try:
            dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    balance_update(WALLETS_TABLE, wid, before, after),
                    txn_put(WALLET_TXNS_TABLE, wid, CREDIT, amount, after, order_id, f"Refund for {order_id}"),
                    {
                        "Update": {
                            "TableName": ORDERS_TABLE,
                            "Key": {"orderId": order_id},
                            **status_update(
                                PAYMENT_REFUNDED,
                                f"{format_inr(amount)} refunded to DemoPay · balance {format_inr(after)}",
                                {"refunded": True},
                                condition="attribute_exists(paymentId) AND attribute_not_exists(refunded)",
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
                log.info("A concurrent run already refunded this order (idempotent no-op)")
                return {"orderId": order_id, "refunded": False, "reason": "already refunded"}
            if codes and codes[0] == "ConditionalCheckFailed":
                continue  # balance changed concurrently: re-read and try again
            raise
        log.info("Payment refunded", amount=amount, balanceAfter=after, walletId=wid)
        return {"orderId": order_id, "refunded": True, "amount": str(amount)}

    raise RefundConflict("Wallet kept changing; retry the refund")
