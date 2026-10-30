"""Legacy stock cleanup (step 2.4, the "migrate" left over from step 2.3): move the units of orders that COMPLETED on
the pre-2.3 definition from `reserved` to `sold`.

Before step 2.3 a completed order's units stayed in `reserved` for ever (there was no `sold` counter). Since 2.3 a
completed line moves reserved -> sold, so `reserved` should mean only "held by an order that is still in flight".
This script brings the old orders in line, so that is true again without re-seeding.

    python scripts/migrate_legacy_sold.py            # DRY RUN (default): what would move, per order and product
    python scripts/migrate_legacy_sold.py --apply    # do it
    python scripts/migrate_legacy_sold.py --check    # only the stock invariant check

Legacy order = status COMPLETED, has reservedItems, not released, and no line has a per-line fulfillment state
(fulfill_item never ran for it). Two kinds:
  - reserved AFTER the product's last seed (seededAt): its units really are in `reserved` -> move them to `sold`.
  - reserved BEFORE it: seed_inventory.py reset `reserved` to 0 since, so its units are no longer counted anywhere.
    Nothing to move (moving them would make `reserved` negative); the order is only marked.

Idempotent: each order is marked legacyStockMigratedAt (+ legacyUnitsMoved), and every write is conditional on that
mark being absent, in ONE transaction with the stock moves (reserved >= quantity), so a re-run or a concurrent run
moves nothing twice. Read-only unless --apply. Results are written to docs/evidence/upgrade-2.4/.

The check, before and after: I5 per product (seed stock = stock + held + reserved + sold + writtenOff) and an
attribution of `reserved`: units of orders still in flight + units of legacy orders not migrated yet. After --apply
the legacy part is 0 and nothing is unexplained.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from seed_inventory import PRODUCTS as SEED_PRODUCTS
from tf_outputs import load_outputs

OUT = load_outputs()
ddb = boto3.resource("dynamodb", region_name=OUT["region"])
orders_table = ddb.Table(OUT["orders_table"])
inventory_table = ddb.Table(OUT["inventory_table"])
EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "upgrade-2.4"
TERMINAL = {"COMPLETED", "FAILED", "PARTIALLY_FULFILLED", "CANCELLED"}
SEEDED = {p["productId"]: p["stock"] for p in SEED_PRODUCTS}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def scan(table, **kwargs) -> list[dict]:
    items: list[dict] = []
    while True:
        page = table.scan(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def reserved_at(order: dict) -> str:
    return next((h["timestamp"] for h in order.get("statusHistory", []) if h["status"] == "RESERVED"), "")


def is_legacy(order: dict) -> bool:
    return (
        order["status"] == "COMPLETED"
        and bool(order.get("reservedItems"))
        and not order.get("released")
        and not any(item.get("fulfillment") for item in order["items"])
    )


def load() -> tuple[dict[str, dict], list[dict]]:
    inventory = {i["productId"]: i for i in scan(inventory_table)}
    orders = scan(
        orders_table,
        ProjectionExpression="orderId, #s, statusHistory, reservedItems, released, #i, legacyStockMigratedAt",
        ExpressionAttributeNames={"#s": "status", "#i": "items"},
    )
    return inventory, orders


def plan(inventory: dict[str, dict], orders: list[dict]) -> list[dict]:
    """Every legacy order not migrated yet, with the units to move (those reserved since the product's last seed)."""
    planned = []
    for order in sorted(orders, key=lambda o: o["orderId"]):
        if not is_legacy(order) or order.get("legacyStockMigratedAt"):
            continue
        at = reserved_at(order)
        move = [(i["productId"], int(i["quantity"])) for i in order["reservedItems"] if at >= str(inventory[i["productId"]].get("seededAt", ""))]
        reset = [(i["productId"], int(i["quantity"])) for i in order["reservedItems"] if at < str(inventory[i["productId"]].get("seededAt", ""))]
        planned.append({"orderId": order["orderId"], "reservedAt": at, "move": move, "resetBySeed": reset})
    return planned


def check(inventory: dict[str, dict], orders: list[dict]) -> tuple[bool, list[str]]:
    """I5 and the attribution of `reserved`, per product. Returns (ok, report lines)."""
    in_flight: dict[str, int] = defaultdict(int)
    legacy: dict[str, int] = defaultdict(int)
    for order in orders:
        if not order.get("reservedItems") or order.get("released"):
            continue
        lines = {i["productId"]: i for i in order["items"]}
        at = reserved_at(order)
        for item in order["reservedItems"]:
            product = item["productId"]
            if at < str(inventory[product].get("seededAt", "")) or lines.get(product, {}).get("fulfillment"):
                continue  # counted before the seed reset it, or the line has left `reserved` (sold / written off)
            if is_legacy(order):
                if not order.get("legacyStockMigratedAt"):
                    legacy[product] += int(item["quantity"])
            elif order["status"] not in TERMINAL:
                in_flight[product] += int(item["quantity"])
    ok, report = True, ["| Product | stock | held | reserved | sold | writtenOff | I5 (sum = seed) | reserved = in flight + legacy |", "|---|---|---|---|---|---|---|---|"]
    for product in sorted(SEEDED):
        row = inventory[product]
        c = {k: int(row.get(k, 0)) for k in ("stock", "held", "reserved", "sold", "writtenOff")}
        i5 = sum(c.values()) == SEEDED[product]
        explained = c["reserved"] == in_flight[product] + legacy[product]
        ok = ok and i5 and explained
        report.append(
            f"| {product} | {c['stock']} | {c['held']} | {c['reserved']} | {c['sold']} | {c['writtenOff']} | "
            f"{sum(c.values())} = {SEEDED[product]} {'OK' if i5 else 'BROKEN'} | "
            f"{c['reserved']} = {in_flight[product]} + {legacy[product]} {'OK' if explained else 'UNEXPLAINED'} |"
        )
    return ok, report


def migrate(entry: dict) -> str:
    """One order, one transaction: the stock moves and the order's mark, all conditional."""
    now = utc_now()
    units = sum(q for _, q in entry["move"])
    note = "moved reserved -> sold" if units else "nothing to move: reserved before the last inventory seed, which reset the counters"
    items = [
        {
            "Update": {
                "TableName": OUT["inventory_table"],
                "Key": {"productId": product},
                "UpdateExpression": "SET reserved = reserved - :q, sold = if_not_exists(sold, :zero) + :q",
                "ConditionExpression": "reserved >= :q",
                "ExpressionAttributeValues": {":q": quantity, ":zero": 0},
            }
        }
        for product, quantity in entry["move"]
    ]
    items.append(
        {
            "Update": {
                "TableName": OUT["orders_table"],
                "Key": {"orderId": entry["orderId"]},
                "UpdateExpression": "SET legacyStockMigratedAt = :now, legacyUnitsMoved = :units, legacyStockMigration = :note",
                "ConditionExpression": "attribute_not_exists(legacyStockMigratedAt) AND #s = :completed",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": {":now": now, ":units": units, ":note": note, ":completed": "COMPLETED"},
            }
        }
    )
    try:
        ddb.meta.client.transact_write_items(TransactItems=items)
    except ClientError as err:
        if err.response["Error"]["Code"] == "TransactionCanceledException":
            return "skipped (already migrated, or the stock condition failed: nothing changed)"
        raise
    return f"migrated, {units} unit(s) moved"


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "check" if "--check" in sys.argv else "dry-run"
    inventory, orders = load()
    lines = [f"# Legacy stock cleanup: {mode} ({utc_now()})", ""]

    ok, report = check(inventory, orders)
    lines += ["## Stock check BEFORE", "", *report, "", f"Result: {'PASS' if ok else 'FAIL'}", ""]
    if mode != "check":
        planned = plan(inventory, orders)
        per_product: dict[str, int] = defaultdict(int)
        for entry in planned:
            for product, quantity in entry["move"]:
                per_product[product] += quantity
        moving = [e for e in planned if e["move"]]
        lines += [
            "## Plan",
            "",
            f"- Orders scanned: {len(orders)}; legacy COMPLETED orders not yet migrated: **{len(planned)}**",
            f"- With units still in `reserved` (reserved after the last seed): **{len(moving)}** orders, "
            f"**{sum(per_product.values())}** units",
            f"- Reserved before the last seed (counters already reset, only marked): {len(planned) - len(moving)} orders",
            "",
            "| Product | units reserved -> sold |",
            "|---|---|",
            *[f"| {product} | {units} |" for product, units in sorted(per_product.items())],
            *(["| (none) | 0 |"] if not per_product else []),
            "",
            "| orderId | RESERVED at | moves | reset by the seed |",
            "|---|---|---|---|",
            *[f"| {e['orderId']} | {e['reservedAt']} | {e['move'] or '-'} | {e['resetBySeed'] or '-'} |" for e in planned],
            "",
        ]
        if mode == "apply":
            results = [(e["orderId"], migrate(e)) for e in planned]
            done = sum(1 for _, r in results if r.startswith("migrated"))
            lines += ["## Applied", "", f"{done} of {len(results)} orders migrated.", ""]
            lines += [f"- {order_id}: {result}" for order_id, result in results if not result.startswith("migrated")]
            inventory, orders = load()
            ok, report = check(inventory, orders)
            leftover = plan(inventory, orders)
            ok = ok and not leftover
            lines += ["", "## Stock check AFTER", "", *report, "", f"Legacy orders left to migrate: {len(leftover)}", f"Result: {'PASS' if ok else 'FAIL'}", ""]
        else:
            lines += ["DRY RUN: nothing was written. Run with --apply to migrate.", ""]

    text = "\n".join(lines)
    print(text)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"legacy-migration-{mode}.md").write_text(text, encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
