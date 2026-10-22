"""DemoPay: a demo wallet per customer email, debited and refunded atomically with the order.

Data model: two tables.
  order-saga-wallets       PK walletId (lower-cased email)   -> balance, currency, createdAt, updatedAt
  order-saga-wallet-txns   PK walletId, SK txnId ("<ts>#<id>") -> type, amount, balanceAfter, orderId, note

Why a separate transactions table instead of a list on the wallet item: history grows without
limit, but a DynamoDB item caps at 400 KB. A Query on (walletId, newest first, Limit 20) is the
cheapest way to show recent activity. A TransactWriteItems still spans both tables (plus the
order), so a debit and its ledger entry can never get out of sync.

Concurrency: every balance change is conditional on the balance it read ("balance = :before").
That makes balanceAfter exact. If another write got there first, the caller re-reads and tries again.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from common.timeutil import utc_now_iso

INITIAL_BALANCE = Decimal("1000000")  # ₹10,00,000 for every new wallet
CURRENCY = "INR"
MAX_DEMO_BALANCE = Decimal("10000000")  # cap for the "set balance" demo helper
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEBIT, CREDIT, ADJUST = "DEBIT", "CREDIT", "ADJUST"


def wallet_id(email: str) -> str:
    """Wallets are keyed by the customer's email, case-insensitively."""
    return email.strip().lower()


def ensure_wallet(wallets_table: Any, wid: str) -> dict[str, Any]:
    """Return the wallet, creating it with ₹10,00,000 on first use (safe if two calls race)."""
    now = utc_now_iso()
    try:
        wallets_table.put_item(
            Item={"walletId": wid, "balance": INITIAL_BALANCE, "currency": CURRENCY, "createdAt": now, "updatedAt": now},
            ConditionExpression="attribute_not_exists(walletId)",
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
    return wallets_table.get_item(Key={"walletId": wid}, ConsistentRead=True)["Item"]


def balance_update(table_name: str, wid: str, before: Decimal, after: Decimal) -> dict[str, Any]:
    """TransactWriteItems 'Update' that sets the balance, only if it still equals `before`."""
    return {
        "Update": {
            "TableName": table_name,
            "Key": {"walletId": wid},
            "UpdateExpression": "SET balance = :after, updatedAt = :now",
            "ConditionExpression": "balance = :before",
            "ExpressionAttributeValues": {":before": before, ":after": after, ":now": utc_now_iso()},
        }
    }


def txn_put(
    table_name: str,
    wid: str,
    txn_type: str,
    amount: Decimal,
    balance_after: Decimal,
    order_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """TransactWriteItems 'Put' for one ledger entry. The txnId sorts by time."""
    ts = utc_now_iso()
    item = {
        "walletId": wid,
        "txnId": f"{ts}#{uuid.uuid4().hex[:8]}",
        "type": txn_type,
        "amount": amount,
        "balanceAfter": balance_after,
        "ts": ts,
        "note": note,
    }
    if order_id:
        item["orderId"] = order_id
    return {"Put": {"TableName": table_name, "Item": item, "ConditionExpression": "attribute_not_exists(txnId)"}}
