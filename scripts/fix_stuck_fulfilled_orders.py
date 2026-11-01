"""One-off data correction after step 3.2's E3 "before" run: two orders parked in FULFILLING on the OLD definition.

What happened: E3 crashed fulfill_item right AFTER its pick committed (crash_after:fulfill). The pre-fix definition
caught that crash as LineUnavailable, so RefundAllLines was asked to refund a line that was already FULFILLED; it
refused (correctly), and the execution failed there. A redrive can't help: it re-runs the same state with the same
input, which still lists the fulfilled line as unavailable. In reality every line was picked and packed and the
customer paid the full amount once, so the true end state is COMPLETED. (The fix commit e02658d stops this from
happening again: only ItemUnavailable now marks a line unavailable.)

Guards, all checked before anything is written (otherwise: stop and show):
  * the order is still FULFILLING, and every line is FULFILLED with one ITEM_FULFILLED history entry per line (the
    entry is written in the same transaction that moves the line's units reserved -> sold, so the stock is in sold);
  * the order was never released (released != true) and has no refundedAmount;
  * the customer's ledger has exactly one DEBIT for the order total and no CREDIT;
  * the payment intent is SUCCEEDED (not REFUNDED); DemoPay has a CHARGE record with nothing refunded and no REFUND record.
The write itself is conditional on status = FULFILLING, so it can run once only. Money and stock are not touched.

    python scripts/fix_stuck_fulfilled_orders.py           # dry run (default)
    python scripts/fix_stuck_fulfilled_orders.py --apply   # do it
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key

from tf_outputs import load_outputs

ORDER_IDS = ["ORD-20261101-e10c6683", "ORD-20261101-11f6e7e1"]
DETAIL = (
    "Status corrected after the step 3.2 chaos run E3 (crash_after:fulfill on the pre-fix definition): every line "
    "was picked and paid in full, but the old definition took the crash for an unavailable item and its refund step "
    "refused a fulfilled line, so the execution stopped in FULFILLING. Money and stock unchanged."
)


def problems(order: dict, ledger: list[dict], intent: dict | None, charge: dict | None, refund: dict | None) -> list[str]:
    """Every guard that fails for this order (empty = safe to correct)."""
    found = []
    lines = order["items"]
    if order["status"] != "FULFILLING":
        found.append(f"status is {order['status']}, not FULFILLING")
    if any(line.get("fulfillment") != "FULFILLED" for line in lines):
        found.append(f"lines not all FULFILLED: {[(l.get('lineId'), l.get('fulfillment')) for l in lines]}")
    picks = sum(1 for h in order["statusHistory"] if h["status"] == "ITEM_FULFILLED")
    if picks != len(lines):
        found.append(f"{picks} ITEM_FULFILLED entries for {len(lines)} lines (stock may not be in sold)")
    if order.get("released") is True or order.get("refundedAmount"):
        found.append(f"released={order.get('released')} refundedAmount={order.get('refundedAmount')}")
    debits = [e["amount"] for e in ledger if e["type"] == "DEBIT"]
    credits = [e["amount"] for e in ledger if e["type"] == "CREDIT"]
    if debits != [Decimal(order["totalAmount"])] or credits:
        found.append(f"ledger DEBITs {debits} CREDITs {credits} (expected one DEBIT of {order['totalAmount']}, no CREDIT)")
    if not intent or intent.get("status") != "SUCCEEDED":
        found.append(f"payment intent status {(intent or {}).get('status')}, not SUCCEEDED")
    if charge is None or Decimal(charge.get("refundedAmount", 0)) != 0:
        found.append(f"DemoPay charge record {'missing' if charge is None else 'shows refundedAmount ' + str(charge.get('refundedAmount'))}")
    if refund is not None:
        found.append("DemoPay has a REFUND record for this intent")
    return found


def wallet_entries(table, wallet_id: str, order_id: str) -> list[dict]:
    """This order's ledger entries (all pages of the wallet's partition)."""
    kwargs = {"KeyConditionExpression": Key("walletId").eq(wallet_id), "FilterExpression": Attr("orderId").eq(order_id),
              "ConsistentRead": True}
    items: list[dict] = []
    while True:
        page = table.query(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = load_outputs()
    db = boto3.resource("dynamodb", region_name=out["region"])
    orders, ledger_t = db.Table(out["orders_table"]), db.Table(out["wallet_txns_table"])
    payments, psp = db.Table(out["payments_table"]), db.Table(out["psp_transactions_table"])

    ok = True
    for order_id in ORDER_IDS:
        order = orders.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
        ledger = wallet_entries(ledger_t, order["walletId"], order_id)
        intent_id = order["paymentIntentId"]
        intent = payments.get_item(Key={"paymentIntentId": intent_id}, ConsistentRead=True).get("Item")
        charge = psp.get_item(Key={"pspTxnId": f"CHARGE#{intent_id}"}, ConsistentRead=True).get("Item")
        refund = psp.get_item(Key={"pspTxnId": f"REFUND#{intent_id}"}, ConsistentRead=True).get("Item")
        found = problems(order, ledger, intent, charge, refund)
        print(f"{order_id}: {order['status']}, total {order['totalAmount']}, lines "
              f"{[(l['lineId'], l['productId'], l.get('fulfillment')) for l in order['items']]} -> {'OK' if not found else found}")
        ok = ok and not found
    if not ok:
        sys.exit("A guard failed: nothing changed.")
    print(f"Would set status COMPLETED on {ORDER_IDS} and append: {DETAIL}")
    if "--apply" not in sys.argv:
        print("Dry run. Re-run with --apply.")
        return

    for order_id in ORDER_IDS:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        orders.update_item(
            Key={"orderId": order_id},
            UpdateExpression="SET #s = :completed, updatedAt = :now, statusHistory = list_append(statusHistory, :entry)",
            ConditionExpression="#s = :fulfilling",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":completed": "COMPLETED", ":fulfilling": "FULFILLING", ":now": now,
                ":entry": [{"status": "COMPLETED", "timestamp": now, "detail": DETAIL}],
            },
        )
        print(f"{order_id}: corrected to COMPLETED.")


if __name__ == "__main__":
    main()
