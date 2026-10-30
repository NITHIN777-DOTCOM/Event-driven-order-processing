"""Step 2.3 commit A check: the per-item fulfillment building blocks, LIVE, before they are wired into the saga.

    python scripts/seed_inventory.py        # optional: reset the counters first
    python scripts/fulfillment_check.py

Commit A deploys the new Lambdas (fulfill-item, write-off-lines), DemoPay's line refund and per-line prices on new
orders, but the state machine still runs the old definition. So this script drives the new pieces DIRECTLY
(synchronous Lambda invokes, exactly the payloads the Map and the steps after it will send in commit B):

  1. A 3-line order (one line with quantity 3) goes through the OLD saga to COMPLETED. Its stored lines carry
     lineId L1..L3 and lineAmount = quantity x the server's unit price; the total is their sum.
  2. fulfill-item on L1 and L3 AT THE SAME TIME (two lines of one order: the transaction-conflict path), then L1
     again: reserved -> sold once per line, the repeat is a no-op.
  3. write-off-lines on L2, twice: one audit record, reserved -> writtenOff once, L2 marked WRITTEN_OFF.
  4. refund-payment with lineIds [L2], twice: ONE ledger CREDIT of exactly L2's stored amount (I7: once per line),
     the line and the order record the refund, the intent stays SUCCEEDED with refundedAmount.
  5. I7 cap: a DemoPay line refund for the WHOLE charge amount (on top of L2's) is rejected: no money moves.
  6. Net charge = L1 + L3 (I6's rule for a partially fulfilled order), and I5 holds for the three products.

The order is a labelled test order ("Fulfillment Check"); its status stays COMPLETED because commit A has no
PARTIALLY_FULFILLED yet. Results are printed and written to docs/evidence/upgrade-2.3/fulfillment-check.md.
Exit code 1 if anything fails.

This is the commit A record only: from commit B on, the saga itself fulfils, refunds and writes off lines (e2e
scenarios za-zc), so an order no longer stays COMPLETED-with-reserved-units and step 1 here would fail.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import boto3

from auth_tokens import auth_header
from e2e_test import (
    API,
    OUT,
    REGION,
    USER,
    counters,
    fulfillment_counters,
    http_json,
    intent_of,
    ledger_for,
    orders_table,
    set_wallet,
    wait_for_terminal,
)

EVIDENCE_FILE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "upgrade-2.3" / "fulfillment-check.md"
# Products no e2e scenario asserts exact counters on. L2 is the "damaged" line.
LINES = [("WIRELESS-MOUSE", 3), ("ANC-HEADPHONES", 1), ("ERGO-MOUSE", 2)]
FUNCTIONS = OUT["fulfillment_function_names"]

lambda_client = boto3.client("lambda", region_name=REGION)
write_offs_table = boto3.resource("dynamodb", region_name=REGION).Table(OUT["write_offs_table"])
results: list[tuple[bool, str]] = []


def check(passed: bool, description: str) -> bool:
    results.append((bool(passed), description))
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")
    return bool(passed)


def invoke(function_key: str, payload: dict) -> tuple[dict, str | None]:
    """Synchronous invoke. Returns (payload, error type or None)."""
    response = lambda_client.invoke(FunctionName=FUNCTIONS[function_key], Payload=json.dumps(payload).encode())
    body = json.loads(response["Payload"].read() or b"{}")
    return body, (body.get("errorType") if response.get("FunctionError") else None)


def all_counters(product_id: str) -> tuple[int, int, int, int, int]:
    """(stock, held, reserved, sold, writtenOff)"""
    return (*counters(product_id), *fulfillment_counters(product_id))


def stored_order(order_id: str) -> dict:
    return orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]


def main() -> int:
    started = time.monotonic()
    set_wallet(USER)
    before = {product: all_counters(product) for product, _ in LINES}

    # 1. The order runs the OLD definition to COMPLETED and stores server-priced lines.
    code, body = http_json(
        "POST",
        f"{API}/orders",
        {"customerName": "Fulfillment Check", "items": [{"productId": p, "quantity": q} for p, q in LINES], "simulate": "none"},
        {"Idempotency-Key": str(uuid.uuid4()), **auth_header(USER)},
    )
    check(code == 202, f"POST /orders (3 lines) returned {code} (expected 202)")
    order_id = body["orderId"]
    print(f"  order {order_id}")
    order = wait_for_terminal(order_id)
    check(order.get("status") == "COMPLETED", f"old saga definition: order {order.get('status')} (expected COMPLETED)")
    stored = stored_order(order_id)
    lines = {item["lineId"]: item for item in stored["items"]}
    amounts_ok = all(
        item["lineAmount"] == (Decimal(item["quantity"]) * item["unitPrice"]).quantize(Decimal("0.01")) for item in stored["items"]
    )
    check(
        list(lines) == ["L1", "L2", "L3"] and amounts_ok and stored["totalAmount"] == sum(i["lineAmount"] for i in stored["items"]),
        "stored lines: " + ", ".join(f"{k} {i['quantity']} x {i['unitPrice']} = {i['lineAmount']}" for k, i in lines.items())
        + f"; total {stored['totalAmount']} = their sum",
    )
    after_saga = {product: all_counters(product) for product, _ in LINES}
    check(
        all(after_saga[p][3:] == before[p][3:] and after_saga[p][2] == before[p][2] + q for p, q in LINES),
        "old definition moved nothing to sold/writtenOff; units stay in reserved: "
        + "; ".join(f"{p} {before[p]} -> {after_saga[p]}" for p, _ in LINES),
    )

    # 2. fulfill-item: L1 and L3 concurrently, then L1 again.
    with ThreadPoolExecutor(max_workers=2) as pool:
        picked = list(pool.map(lambda lid: invoke("fulfill_item", {"orderId": order_id, "lineId": lid}), ["L1", "L3"]))
    check(all(err is None and out.get("status") == "FULFILLED" for out, err in picked), f"fulfill L1 + L3 concurrently: {picked}")
    repeat, err = invoke("fulfill_item", {"orderId": order_id, "lineId": "L1"})
    check(err is None and repeat.get("status") == "FULFILLED", f"fulfill L1 again (idempotent): {repeat}")
    for product, quantity in (LINES[0], LINES[2]):
        now = all_counters(product)
        expected = (after_saga[product][0], after_saga[product][1], after_saga[product][2] - quantity, after_saga[product][3] + quantity, after_saga[product][4])
        check(now == expected, f"{product} {after_saga[product]} -> {now} (expected {expected}: {quantity} reserved -> sold, once)")

    # 3. write-off-lines on L2, twice.
    write_off_input = {"orderId": order_id, "lines": [{"lineId": "L2", "reason": "found damaged in the warehouse (fulfillment check)"}]}
    first, err1 = invoke("write_off_lines", write_off_input)
    second, err2 = invoke("write_off_lines", write_off_input)
    check(err1 is None and err2 is None and first.get("unitsWrittenOff") == 1 and second.get("unitsWrittenOff") == 0,
          f"write off L2 twice: {first} then {second} (1 unit, then 0)")
    product, quantity = LINES[1]
    now = all_counters(product)
    expected = (after_saga[product][0], after_saga[product][1], after_saga[product][2] - quantity, after_saga[product][3], after_saga[product][4] + quantity)
    check(now == expected, f"{product} {after_saga[product]} -> {now} (expected {expected}: reserved -> writtenOff, not back on sale)")
    record = write_offs_table.get_item(Key={"orderId": order_id, "lineId": "L2"}, ConsistentRead=True).get("Item")
    check(bool(record) and record["productId"] == product and int(record["quantity"]) == quantity,
          f"write-off audit record: {record and {k: record[k] for k in ('productId', 'quantity', 'reason', 'writtenOffAt')}}")

    # 4. refund-payment for L2, twice.
    refund1, err1 = invoke("refund_payment", {"orderId": order_id, "lineIds": ["L2"]})
    refund2, err2 = invoke("refund_payment", {"orderId": order_id, "lineIds": ["L2"]})
    l2_amount = lines["L2"]["lineAmount"]
    check(err1 is None and err2 is None and Decimal(refund1.get("refundedAmount", "0")) == l2_amount,
          f"refund L2 twice: refundedAmount {refund1.get('refundedAmount')} / {refund2.get('refundedAmount')} (L2 = {l2_amount})")
    entries = ledger_for(order_id, USER)
    debits = [e["amount"] for e in entries if e["type"] == "DEBIT"]
    credits = [e["amount"] for e in entries if e["type"] == "CREDIT"]
    check(debits == [stored["totalAmount"]] and credits == [l2_amount],
          f"ledger: DEBIT {debits}, CREDIT {credits} (expected 1 DEBIT of {stored['totalAmount']}, 1 CREDIT of {l2_amount})")
    stored = stored_order(order_id)
    l2 = stored["items"][1]
    check(l2.get("refundedAmount") == l2_amount and stored.get("refundedAmount") == l2_amount,
          f"order: L2 refundedAmount {l2.get('refundedAmount')}, order refundedAmount {stored.get('refundedAmount')}")
    intent = intent_of(order_id) or {}
    check(intent.get("status") == "SUCCEEDED" and intent.get("refundedAmount") == l2_amount,
          f"intent PI-{order_id}: {intent.get('status')}, refundedAmount {intent.get('refundedAmount')} (expected SUCCEEDED, {l2_amount})")

    # 5. I7: DemoPay refuses a line refund that would take the total above the charge.
    over, err = invoke("payment_provider", {
        "operation": "refund", "paymentIntentId": f"PI-{order_id}", "lineId": "CAP-PROBE",
        "amount": str(stored["totalAmount"]), "note": "I7 probe (fulfillment check)",
    })
    check(err == "RefundRejected", f"I7 cap: refunding the whole {stored['totalAmount']} on top of L2 -> {err}: {over.get('errorMessage')}")
    credits_after = [e["amount"] for e in ledger_for(order_id, USER) if e["type"] == "CREDIT"]
    check(credits_after == [l2_amount], f"ledger after the rejected refund: CREDIT {credits_after} (unchanged)")

    # 6. I6 rule for partial fulfillment and I5 for the three products.
    net = sum(debits) - sum(credits_after)
    kept = lines["L1"]["lineAmount"] + lines["L3"]["lineAmount"]
    check(net == kept, f"I6: net charge {net} = L1 + L3 = {kept}")
    final = {product: all_counters(product) for product, _ in LINES}
    check(all(sum(final[p]) == sum(before[p]) for p, _ in LINES),
          "I5: stock + held + reserved + sold + writtenOff unchanged: " + "; ".join(f"{p} {sum(before[p])} -> {sum(final[p])}" for p, _ in LINES))

    write_evidence(order_id, time.monotonic() - started)
    passed = sum(ok for ok, _ in results)
    print(f"\n{passed}/{len(results)} checks passed. Evidence: {EVIDENCE_FILE}")
    return 0 if passed == len(results) else 1


def write_evidence(order_id: str, duration: float) -> None:
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step 2.3 commit A: fulfillment building blocks, tested live before the saga uses them",
        "",
        f"Generated by `scripts/fulfillment_check.py` in {duration:.0f} s. Order `{order_id}` "
        f"(user A, products {', '.join(p for p, _ in LINES)}).",
        "",
        "| Result | Check |",
        "|---|---|",
        *[f"| {'PASS' if ok else 'FAIL'} | {text.replace('|', '/')} |" for ok, text in results],
        "",
    ]
    EVIDENCE_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
