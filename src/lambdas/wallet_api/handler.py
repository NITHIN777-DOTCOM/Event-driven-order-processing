"""DemoPay wallet API: always the CALLER's own wallet.

  GET  /wallet                    -> balance + the 20 most recent transactions (newest first)
  POST /wallet/reset {balance?}   -> set the balance (default ₹10,00,000; demo helper)

The wallet is the signed-in user's (walletId = the JWT "sub", see common/auth.py). There is no email
or user parameter: an ?email= or a body "email" is ignored, so nobody can view or reset another
user's wallet. A wallet is created with ₹10,00,000 the first time it's seen.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from common.auth import Forbidden, Unauthorized, caller_from
from common.http import BadRequest, parse_json_body, response
from common.logger import get_logger
from common.money import format_inr
from common.tracing import instrument_aws_sdk
from common.wallet import (
    ADJUST,
    INITIAL_BALANCE,
    MAX_DEMO_BALANCE,
    balance_update,
    ensure_wallet,
    txn_put,
    wallet_id_for,
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
        wid = wallet_id_for(caller_from(event).user_id)
        if route == "GET /wallet":
            return response(200, wallet_view(wid))
        if route == "POST /wallet/reset":
            body = parse_json_body(event) if event.get("body") else {}
            return response(200, set_balance(wid, parse_balance(body.get("balance"))))
        return response(404, {"error": f"Unknown route {route}"})
    except Unauthorized as err:
        return response(401, {"error": str(err)})
    except Forbidden as err:
        return response(403, {"error": str(err)})
    except BadRequest as err:
        return response(400, {"error": str(err)})


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
