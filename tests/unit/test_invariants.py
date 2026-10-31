"""The invariant auditor's checks (src/common/invariants.py), on hand-built snapshots.

Every invariant gets a negative control: a snapshot with exactly that bug must be reported, and the clean version of
the same snapshot must not. An auditor that never fires proves nothing (the same idea as the race test's control).
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from common.invariants import Snapshot, audit, confirm

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
OLD = "2026-11-01T10:00:00.000Z"  # 2 h before NOW: settled
SEEDED_AT = "2026-11-01T09:00:00.000Z"
WALLET = "user-1"


def ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def order(order_id="ORD-1", status="COMPLETED", lines=((("P1", 2, "100"), "FULFILLED"),), **extra) -> dict:
    items, reserved = [], []
    for index, ((product, qty, price), state) in enumerate(lines):
        item = {"productId": product, "quantity": Decimal(qty), "unitPrice": Decimal(price), "lineId": f"L{index + 1}"}
        if state:
            item["fulfillment"] = state
        items.append(item)
        reserved.append({"productId": product, "quantity": Decimal(qty)})
    history = [{"status": "PENDING", "timestamp": OLD}, {"status": "RESERVED", "timestamp": OLD}]
    if any(state == "FULFILLED" for _, state in lines):
        history += [{"status": "FULFILLING", "timestamp": OLD}, {"status": "ITEM_FULFILLED", "timestamp": OLD}]
    history.append({"status": status, "timestamp": OLD})
    total = sum(Decimal(q) * Decimal(p) for (_, q, p), _ in lines)
    return {
        "orderId": order_id, "status": status, "items": items, "reservedItems": reserved, "released": False,
        "totalAmount": total, "walletId": WALLET, "createdAt": OLD, "updatedAt": OLD, "statusHistory": history,
        "simulate": "none", **extra,
    }


def debit(order_id, amount, intent=True) -> dict:
    entry = {"walletId": WALLET, "txnId": f"{OLD}#d{order_id}", "type": "DEBIT", "amount": Decimal(amount), "orderId": order_id, "ts": OLD}
    if intent:
        entry["paymentIntentId"] = f"PI-{order_id}"
    return entry


def credit(order_id, amount, line=None) -> dict:
    entry = {"walletId": WALLET, "txnId": f"{OLD}#c{order_id}{line}", "type": "CREDIT", "amount": Decimal(amount), "orderId": order_id,
             "paymentIntentId": f"PI-{order_id}", "ts": OLD}
    if line:
        entry["lineId"] = line
    return entry


def charge(order_id, amount, outcome="SUCCEEDED", refunded=None) -> dict:
    record = {"pspTxnId": f"CHARGE#PI-{order_id}", "kind": "CHARGE", "paymentIntentId": f"PI-{order_id}", "orderId": order_id,
              "amount": Decimal(amount), "outcome": outcome, "createdAt": OLD}
    if refunded is not None:
        record["refundedAmount"] = Decimal(refunded)
    return record


def refund(order_id, amount, line=None) -> dict:
    key = f"REFUND#PI-{order_id}" + (f"#{line}" if line else "")
    record = {"pspTxnId": key, "kind": "REFUND", "paymentIntentId": f"PI-{order_id}", "orderId": order_id, "amount": Decimal(amount), "createdAt": OLD}
    if line:
        record["lineId"] = line
    return record


def intent(order_id, status="SUCCEEDED") -> dict:
    return {"paymentIntentId": f"PI-{order_id}", "orderId": order_id, "status": status}


def product(pid="P1", stock=98, sold=2, seeded=100, **extra) -> dict:
    return {"productId": pid, "stock": Decimal(stock), "held": Decimal(extra.pop("held", 0)), "reserved": Decimal(extra.pop("reserved", 0)),
            "sold": Decimal(sold), "writtenOff": Decimal(extra.pop("writtenOff", 0)), "seededStock": Decimal(seeded), "seededAt": SEEDED_AT, **extra}


def clean() -> Snapshot:
    """One COMPLETED order (2 x P1 at 100, fulfilled, paid once) and the matching stock books."""
    return Snapshot(
        inventory=[product()], holds=[], write_offs=[], orders=[order()], intents=[intent("ORD-1")],
        psp=[charge("ORD-1", "200")], ledger=[debit("ORD-1", "200")], started_at=NOW,
    )


def kinds(snap: Snapshot) -> set[str]:
    return {f.invariant for f in audit(snap).violations}


def test_a_clean_snapshot_has_no_findings():
    result = audit(clean())
    assert result.violations == [] and result.stuck == []
    assert result.stats["terminalChecked"] == 1 and result.stats["productsChecked"] == 1


def test_i1_completed_without_its_debit():
    snap = clean()
    snap.ledger, snap.psp = [], []
    assert {"I1", "I6"} <= kinds(snap)


def test_i2_failed_order_still_charged():
    snap = clean()
    snap.orders = [order(status="FAILED", lines=((("P1", 2, "100"), None),), released=True)]
    snap.inventory = [product(stock=100, sold=0)]
    assert kinds(snap) == {"I2", "I6"}
    snap.ledger.append(credit("ORD-1", "200"))
    snap.psp.append(refund("ORD-1", "200"))
    snap.psp[0]["refundedAmount"] = Decimal("200")
    assert kinds(snap) == set()


def test_i3_double_charge_and_double_refund():
    snap = clean()
    snap.ledger.append({**debit("ORD-1", "200"), "txnId": "x2"})
    assert "I3" in kinds(snap)
    snap = clean()
    snap.orders = [order(status="FAILED", lines=((("P1", 2, "100"), None),), released=True)]
    snap.inventory = [product(stock=100, sold=0)]
    snap.ledger += [credit("ORD-1", "200"), {**credit("ORD-1", "200"), "txnId": "c2"}]
    assert {"I3", "I7"} <= kinds(snap)


def test_i3_ledger_must_agree_with_demopay_records():
    snap = clean()
    snap.psp = []  # a DEBIT that DemoPay never recorded
    assert "I3" in kinds(snap)
    snap = clean()
    snap.ledger = [{**debit("ORD-1", "200"), "paymentIntentId": "PI-ORD-1"}]
    snap.psp.append(refund("ORD-1", "50"))  # a refund record with no CREDIT behind it
    snap.psp[0]["refundedAmount"] = Decimal("50")
    assert "I3" in kinds(snap)


def test_i4_terminal_order_with_an_unfinished_intent():
    snap = clean()
    snap.intents = [intent("ORD-1", "REQUESTED")]
    assert kinds(snap) == {"I4"}


def test_i5_counters_must_add_up_to_the_seed():
    snap = clean()
    snap.inventory = [product(stock=97)]  # one unit vanished
    assert kinds(snap) == {"I5"}
    snap.inventory = [product(stock=-1, sold=101)]
    assert "I5" in kinds(snap)


def test_i5_a_failed_order_that_never_released_its_stock():
    snap = clean()
    snap.orders = [order(status="FAILED", lines=((("P1", 2, "100"), None),))]  # released False
    snap.inventory = [product(stock=98, sold=0, reserved=2)]
    snap.ledger, snap.psp, snap.intents = [], [], []
    findings = [f for f in audit(snap).violations if f.invariant == "I5"]
    assert any(f.subject == "ORD-1" and "still holds reserved" in f.detail for f in findings)


def test_i5_counters_are_explained_by_holds_write_offs_and_orders():
    snap = clean()
    snap.inventory = [product(stock=97, held=1)]  # 1 held, but no ACTIVE hold exists
    assert kinds(snap) == {"I5"}
    snap.holds = [{"holdId": "HOLD-1", "status": "ACTIVE", "createdAt": OLD, "updatedAt": OLD, "items": [{"productId": "P1", "quantity": Decimal(1)}]}]
    assert kinds(snap) == set()
    snap.write_offs = [{"orderId": "ORD-9", "lineId": "L1", "productId": "P1", "quantity": Decimal(1), "writtenOffAt": OLD}]
    assert kinds(snap) == {"I5"}  # a write-off record without the counter


def test_reservations_from_before_the_last_seed_are_not_counted():
    snap = clean()
    snap.orders.append(order("ORD-OLD", status="FAILED", lines=((("P1", 5, "100"), None),)))
    snap.orders[-1]["statusHistory"][1]["timestamp"] = "2026-11-01T08:00:00.000Z"  # reserved before SEEDED_AT
    assert kinds(snap) == set()


def test_i6_partial_fulfillment_nets_the_delivered_lines():
    lines = ((("P1", 1, "100"), "FULFILLED"), (("P2", 1, "50"), "WRITTEN_OFF"))
    snap = Snapshot(
        inventory=[product(stock=99, sold=1), product("P2", stock=99, sold=0, writtenOff=1)],
        holds=[], orders=[order(status="PARTIALLY_FULFILLED", lines=lines)], intents=[intent("ORD-1")],
        write_offs=[{"orderId": "ORD-1", "lineId": "L2", "productId": "P2", "quantity": Decimal(1), "writtenOffAt": OLD}],
        psp=[charge("ORD-1", "150", refunded="50"), refund("ORD-1", "50", "L2")],
        ledger=[debit("ORD-1", "150"), credit("ORD-1", "50", "L2")], started_at=NOW,
    )
    assert kinds(snap) == set()
    snap.ledger.pop()  # the unavailable line was never refunded
    snap.psp = [charge("ORD-1", "150")]
    assert "I6" in kinds(snap)


def test_i7_refunds_above_the_charge():
    snap = clean()
    snap.psp[0]["refundedAmount"] = Decimal("250")
    assert "I7" in kinds(snap)


def test_i8_cancelled_order_must_be_refunded_and_released():
    snap = clean()
    cancelled = order(status="CANCELLED", lines=((("P1", 2, "100"), None),), cancelRequestedAt=OLD, released=True)
    cancelled["statusHistory"].insert(2, {"status": "INVENTORY_RELEASED", "timestamp": OLD})
    snap.orders, snap.inventory = [cancelled], [product(stock=100, sold=0)]
    assert kinds(snap) == {"I8", "I6"}  # charged, never refunded
    snap.ledger.append(credit("ORD-1", "200"))
    snap.psp += [refund("ORD-1", "200")]
    snap.psp[0]["refundedAmount"] = Decimal("200")
    assert kinds(snap) == set()


def test_i9_cancel_and_fulfillment_both_won():
    snap = clean()
    snap.orders[0]["cancelRequestedAt"] = OLD  # COMPLETED after FULFILLING, yet a cancel was committed
    assert "I9" in kinds(snap)


def test_legacy_shapes_are_understood():
    snap = clean()
    # pre-DemoPay: COMPLETED, no money ever moved
    snap.orders.append(order("ORD-LEGACY", lines=((("P9", 1, "10"), None),), createdAt="2026-10-22T11:00:00.000Z"))
    snap.orders[-1]["statusHistory"][1]["timestamp"] = "2026-10-22T11:00:00.000Z"
    # pre-2.3 refund: a whole-charge refund record but no refundedAmount on the charge
    snap.orders.append(order("ORD-OLDREF", status="FAILED", lines=((("P9", 1, "10"), None),), released=True, createdAt="2026-10-29T10:00:00.000Z"))
    snap.ledger += [debit("ORD-OLDREF", "10"), credit("ORD-OLDREF", "10")]
    snap.psp += [charge("ORD-OLDREF", "10"), {**refund("ORD-OLDREF", "10"), "createdAt": "2026-10-29T10:01:00.000Z"}]
    # pre-2.1: a direct debit without a payment intent
    snap.orders.append(order("ORD-PRE21", lines=((("P9", 1, "10"), None),), createdAt="2026-10-23T10:00:00.000Z"))
    snap.ledger.append(debit("ORD-PRE21", "10", intent=False))
    snap.inventory.append(product("P9", stock=10, sold=0, seeded=10, seededAt="2026-10-30T00:00:00.000Z"))
    assert audit(snap).violations == []


def test_stuck_parked_and_in_flight():
    snap = clean()
    snap.orders += [
        order("ORD-STUCK", status="FULFILLING", createdAt=ts(45), executionArn="arn:exec:ORD-STUCK"),
        order("ORD-YOUNG", status="PAYMENT_PENDING", createdAt=ts(5)),
        order("ORD-POISON", status="PENDING", createdAt=ts(600), simulate="poison", deadLettered=True),
    ]
    for o in snap.orders[1:]:
        o["reservedItems"] = []
    result = audit(snap, describe_execution=lambda arn: "FAILED")
    assert [(f.subject, "redrive" in f.detail) for f in result.stuck] == [("ORD-STUCK", True)]
    assert [f.subject for f in result.parked] == ["ORD-POISON"]
    assert result.stats["inFlight"] == 1


def test_recent_changes_are_settling_not_judged():
    snap = clean()
    snap.ledger = []  # would be I1 ... but the order changed seconds ago (a payment may be landing right now)
    snap.psp = []
    snap.orders[0]["updatedAt"] = ts(0.5)
    assert audit(snap).violations == []
    assert audit(snap).stats["settling"] == 1


def test_confirm_keeps_only_violations_seen_twice():
    broken = clean()
    broken.ledger, broken.psp = [], []
    first, second = audit(broken), audit(clean())
    assert confirm(first, second).violations == []
    assert {f.invariant for f in confirm(first, audit(copy.deepcopy(broken))).violations} == {"I1", "I6"}


@pytest.mark.parametrize("pages", [1, 3])
def test_scan_all_follows_every_page(pages):
    from common.invariants import scan_all

    class Table:
        def __init__(self):
            self.calls = []

        def scan(self, **kwargs):
            self.calls.append(kwargs)
            n = len(self.calls)
            page = {"Items": [{"n": n}]}
            if n < pages:
                page["LastEvaluatedKey"] = {"k": n}
            return page

    table = Table()
    assert [i["n"] for i in scan_all(table)] == list(range(1, pages + 1))
    assert all(call["ConsistentRead"] for call in table.calls)
