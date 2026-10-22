"""DemoPay wallet API.

  GET  /wallet?email=...                  -> balance + the 20 most recent transactions (newest first)
  POST /wallet/reset {email, balance?}    -> set the balance (default ₹10,00,000; demo helper)

A wallet is created with ₹10,00,000 the first time it's seen. This is DEMO money with no
authentication: anyone who knows an email can view or reset that wallet. That's acceptable for a
course demo and is documented. The API's stage throttling caps abuse.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from common.http import BadRequest, parse_json_body, response
from common.logger import get_logger
from common.money import format_inr
from common.tracing import instrument_aws_sdk
from common.wallet import (
    ADJUST,
    EMAIL_PATTERN,
    INITIAL_BALANCE,
    MAX_DEMO_BALANCE,
    balance_update,
    ensure_wallet,
    txn_put,
    wallet_id,
)

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

WALLETS_TABLE = os.environ["WALLETS_TABLE"]
WALLET_TXNS_TABLE = os.environ["WALLET_TXNS_TABLE"]

dynamodb = boto3.resource("dynamodb")
wallets_table = dynamodb.Table(WALLETS_TABLE)
txns_table = dynamodb.Table(WALLET_TXNS_TABLE)
logger = get_logger("wallet_api")

RECENT_TXNS = 20
MAX_SET_ATTEMPTS = 3


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "")
    try:
        if route == "GET /wallet":
            email = (event.get("queryStringParameters") or {}).get("email", "")
            return response(200, wallet_view(valid_email(email)))
        if route == "POST /wallet/reset":
            body = parse_json_body(event)
            return response(200, set_balance(valid_email(body.get("email", "")), parse_balance(body.get("balance"))))
        return response(404, {"error": f"Unknown route {route}"})
    except BadRequest as err:
        return response(400, {"error": str(err)})


def valid_email(email: Any) -> str:
    if not isinstance(email, str) or not EMAIL_PATTERN.match(email.strip()):
        raise BadRequest("A valid email is required")
    return wallet_id(email)


def parse_balance(raw: Any) -> Decimal:
    if raw is None:
        return INITIAL_BALANCE
    try:
        value = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise BadRequest("balance must be a number") from None
    if not Decimal("0") <= value <= MAX_DEMO_BALANCE:
        raise BadRequest(f"balance must be between ₹0 and {format_inr(MAX_DEMO_BALANCE)}")
    return value


def wallet_view(wid: str) -> dict[str, Any]:
    wallet = ensure_wallet(wallets_table, wid)
    txns = txns_table.query(
        KeyConditionExpression=Key("walletId").eq(wid),
        ScanIndexForward=False,  # txnId starts with the timestamp: newest first
        Limit=RECENT_TXNS,
    )["Items"]
    logger.info("Wallet viewed", walletId=wid, balance=wallet["balance"])
    return {
        "walletId": wid,
        "balance": wallet["balance"],
        "currency": wallet["currency"],
        "transactions": [
            {k: t.get(k) for k in ("txnId", "type", "amount", "balanceAfter", "orderId", "ts", "note")} for t in txns
        ],
    }


def set_balance(wid: str, target: Decimal) -> dict[str, Any]:
    """Demo helper: set the balance and record an ADJUST entry with the difference."""
    for _ in range(MAX_SET_ATTEMPTS):
        before = ensure_wallet(wallets_table, wid)["balance"]
        try:
            dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    balance_update(WALLETS_TABLE, wid, before, target),
                    txn_put(WALLET_TXNS_TABLE, wid, ADJUST, target - before, target, note=f"Demo balance set to {format_inr(target)}"),
                ]
            )
            break
        except dynamodb.meta.client.exceptions.TransactionCanceledException:
            continue  # a payment changed the balance in between: re-read and retry
    else:
        raise BadRequest("The wallet is busy, please try again")
    logger.info("Wallet balance set", walletId=wid, balance=target)
    return wallet_view(wid)
