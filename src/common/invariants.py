"""Invariant auditor (step 3.2): reconcile orders, payments, the DemoPay ledger and the stock books, I1-I9.

The saga's own steps keep the invariants true one write at a time. This module checks them from the OUTSIDE, over
everything stored, the way a finance team reconciles the bank statement against the order book. It is used by
  - Lambda order-saga-invariant-auditor (hourly via EventBridge Scheduler, or on demand), which publishes metrics
    and alarms, and
  - scripts/audit_invariants.py (the same checks from a laptop, with a readable report).

Two result classes:
  VIOLATION  money or stock doesn't add up. Never expected, always a bug: alarm order-saga-invariant-violation.
  STUCK      an order still not terminal 30+ minutes after it was created (the saga normally ends in under 5), with
             its Step Functions execution status: a FAILED execution means it is parked and needs a redrive
             (docs/runbooks/redrive-stuck-order.md). Alarm order-saga-stuck-orders.
  (PARKED    poison orders dead-lettered on purpose by demos/tests and the labelled outbox DLQ probe: reported,
             counted, not alarmed here; the DLQ alarms already cover them.)

The invariants (per order unless noted):
  I1  COMPLETED -> exactly one DEBIT, of the order total, and no CREDIT
  I2  FAILED -> net charge 0
  I3  no double charge or double refund: at most one DEBIT; each refunded line (or the whole remainder) credited
      at most once; and the ledger agrees with DemoPay's own records (every SUCCEEDED charge has exactly one DEBIT
      of its amount, every refund record exactly one CREDIT of its amount, and nothing in the ledger lacks a record)
  I4  a terminal order's payment intent (if any) is final: SUCCEEDED, FAILED, TIMED_OUT or REFUNDED
  I5  stock conservation, per product: seededStock = stock + held + reserved + sold + writtenOff (no counter < 0);
      and each counter is explained: held = units in ACTIVE holds, reserved = units reserved by orders and not yet
      released / fulfilled / written off, sold = units of FULFILLED lines not released, writtenOff = the units in
      write-off audit records. Per order: a terminal order holds no reservation any more.
  I6  net charge = the sum of the FULFILLED line amounts (COMPLETED: the total; FAILED/CANCELLED: 0)
  I7  refunds never exceed the charge (ledger, and DemoPay's running refundedAmount = the sum of its refund records)
  I8  CANCELLED -> net 0, its stock released, no line fulfilled
  I9  cancel and fulfillment never both win: an order with a cancel request ended CANCELLED and never reached
      FULFILLING

Legacy shapes (the table holds every order since phase 1):
  - orders from before DemoPay existed (phase 4.1, DEMOPAY_STARTED_AT) never moved money: money checks are skipped
  - refunds from before step 2.3 have no running refundedAmount on the charge (REFUND_COUNTER_SINCE)
  - pre-2.1 orders were debited directly (ledger DEBIT without a paymentIntentId, no intent, no DemoPay record):
    the ledger checks apply, the provider cross-check does not
  - pre-2.3 COMPLETED orders have no per-line state (their lines count as delivered); the 233 migrated ones carry
    legacyStockMigratedAt. Their reservations predate the products' last seed, and a seed resets the counters, so
    every per-order stock check only counts reservations made AFTER the product's seededAt
  - RACE-* products (step 3.1) are ordinary products with listed = false; cancelled orders follow I8

Reading a live system: the scans are not one snapshot, so an order changing WHILE we read could look wrong for a
moment (e.g. a late refund lands between the orders scan and the ledger scan). Three guards:
  1. orders younger than STUCK_AFTER that are not terminal are in flight: skipped, not judged
  2. an order or ledger entry that changed in the last SETTLE_SECONDS is "settling": skipped this round
  3. the caller audits twice, a few seconds apart, and reports only violations found BOTH times (confirm())
The per-product sum (I5) is exact regardless: every stock move is one transaction on one item, so the sum of the
five counters of one item never changes, whenever it is read.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable

TERMINAL = frozenset({"COMPLETED", "FAILED", "PARTIALLY_FULFILLED", "CANCELLED"})
FINAL_INTENT = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "REFUNDED"})
INVARIANTS = ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9")

# The first DemoPay ledger entry ever written (phase 4.1, read from order-saga-wallet-txns). Orders created before it
# were "paid" by a simulated step that moved no money, so they have nothing to reconcile.
DEMOPAY_STARTED_AT = "2026-10-22T13:17:39.005Z"
# DemoPay's running `refundedAmount` on the CHARGE record (the I7 cap) arrived with step 2.3. Whole-charge refunds
# made before it have a refund record but no counter: the ledger check still covers them, the counter check can't.
REFUND_COUNTER_SINCE = "2026-10-30T00:00:00.000Z"
STUCK_AFTER = timedelta(minutes=30)
SETTLE_SECONDS = 120
ZERO = Decimal("0")


@dataclass
class Snapshot:
    """Everything the auditor reads, keyed for lookups. Built by load_snapshot() or by tests."""

    inventory: list[dict[str, Any]]
    holds: list[dict[str, Any]]
    write_offs: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    intents: list[dict[str, Any]]
    psp: list[dict[str, Any]]
    ledger: list[dict[str, Any]]
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Finding:
    kind: str  # VIOLATION | STUCK | PARKED
    invariant: str  # I1..I9, or the stuck reason
    subject: str  # orderId, productId or psp record id
    detail: str


@dataclass
class AuditResult:
    violations: list[Finding] = field(default_factory=list)
    stuck: list[Finding] = field(default_factory=list)
    parked: list[Finding] = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)

    def per_invariant(self) -> dict[str, int]:
        counts = Counter(f.invariant for f in self.violations)
        return {inv: counts.get(inv, 0) for inv in INVARIANTS}

    def summary(self) -> dict[str, Any]:
        return {
            "violations": len(self.violations),
            "stuck": len(self.stuck),
            "parked": len(self.parked),
            "perInvariant": self.per_invariant(),
            "stats": dict(self.stats),
        }


# --------------------------------------------------------------------------------------------------------------
# Loading (paginated scans, strongly consistent)
# --------------------------------------------------------------------------------------------------------------
def scan_all(table: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Every item of a table: Scan follows LastEvaluatedKey until the last page (1 MB per page)."""
    items: list[dict[str, Any]] = []
    kwargs.setdefault("ConsistentRead", True)
    while True:
        page = table.scan(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def load_snapshot(dynamodb: Any, tables: dict[str, str]) -> Snapshot:
    """Read every table. Order matters for counters checked against records written in the same transaction:
    inventory is read FIRST, so a record seen later can be newer than the counter but never older (see _sandwich)."""
    started = datetime.now(timezone.utc)
    read = lambda key: scan_all(dynamodb.Table(tables[key]))  # noqa: E731
    return Snapshot(
        inventory=read("inventory"),
        holds=read("holds"),
        write_offs=read("write_offs"),
        orders=read("orders"),
        intents=read("payments"),
        psp=read("psp_transactions"),
        ledger=read("wallet_txns"),
        started_at=started,
    )


# --------------------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------------------
def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def history(order: dict[str, Any]) -> list[str]:
    return [h.get("status", "") for h in order.get("statusHistory") or []]


def reserved_at(order: dict[str, Any]) -> str:
    """When the order's stock was reserved (its RESERVED history entry), or "" if it never was."""
    return next((h["timestamp"] for h in order.get("statusHistory") or [] if h.get("status") == "RESERVED"), "")


def line_amount(item: dict[str, Any]) -> Decimal:
    if item.get("lineAmount") is not None:
        return Decimal(str(item["lineAmount"]))
    return (Decimal(str(item["quantity"])) * Decimal(str(item["unitPrice"]))).quantize(Decimal("0.01"))


def fulfilled_amount(order: dict[str, Any]) -> Decimal:
    """I6: what the customer should have paid in the end."""
    if order["status"] == "COMPLETED":
        return Decimal(str(order["totalAmount"]))
    if order["status"] != "PARTIALLY_FULFILLED":
        return ZERO
    return sum((line_amount(i) for i in order.get("items") or [] if i.get("fulfillment") == "FULFILLED"), ZERO)


def is_parked_by_design(order: dict[str, Any]) -> bool:
    """Poison orders (demo/e2e) go to the orders DLQ on purpose; the OUTBOX-DLQ-TEST row is a labelled probe."""
    return order.get("simulate") == "poison" or bool(order.get("deadLettered")) or order["orderId"].startswith("OUTBOX-DLQ-TEST")


def open_units(order: dict[str, Any]) -> dict[str, int]:
    """productId -> units this order still holds in `reserved` (reserved, not released, line not handled yet)."""
    if not order.get("reservedItems") or order.get("released"):
        return {}
    handled = {i["productId"] for i in order.get("items") or [] if i.get("fulfillment") in ("FULFILLED", "WRITTEN_OFF")}
    legacy_done = order["status"] == "COMPLETED" and not any(i.get("fulfillment") for i in order.get("items") or [])
    if legacy_done:
        return {}  # pre-2.3 COMPLETED: delivered without per-line state (only exists before the last seed)
    units: dict[str, int] = defaultdict(int)
    for item in order["reservedItems"]:
        if item["productId"] not in handled:
            units[item["productId"]] += int(item["quantity"])
    return dict(units)


def sold_units(order: dict[str, Any]) -> dict[str, int]:
    """productId -> units of this order's FULFILLED lines still counted in `sold` (a release takes them back)."""
    if order.get("released"):
        return {}
    units: dict[str, int] = defaultdict(int)
    for item in order.get("items") or []:
        if item.get("fulfillment") == "FULFILLED":
            units[item["productId"]] += int(item["quantity"])
    return dict(units)


def _newest(*values: str | None) -> datetime | None:
    stamps = [t for t in (parse_ts(v) for v in values) if t]
    return max(stamps) if stamps else None


# --------------------------------------------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------------------------------------------
def audit(
    snap: Snapshot,
    now: datetime | None = None,
    stuck_after: timedelta = STUCK_AFTER,
    settle_seconds: int = SETTLE_SECONDS,
    describe_execution: Callable[[str], str] | None = None,
) -> AuditResult:
    """Check I1-I9 over the snapshot. `describe_execution(arn) -> status` labels STUCK orders (optional)."""
    now = now or snap.started_at
    settle = timedelta(seconds=settle_seconds)
    result = AuditResult()

    ledger_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in snap.ledger:
        if entry.get("orderId"):
            ledger_by_order[entry["orderId"]].append(entry)
    intents = {i["paymentIntentId"]: i for i in snap.intents}
    seeded_at = {p["productId"]: p.get("seededAt", "") for p in snap.inventory}

    for order in snap.orders:
        _audit_order(order, ledger_by_order.get(order["orderId"], []), intents, seeded_at, now, stuck_after, settle, result, describe_execution)
    _audit_provider(snap, now, settle, result)
    _audit_products(snap, now, settle, result)
    return result


def _audit_order(
    order: dict[str, Any],
    entries: list[dict[str, Any]],
    intents: dict[str, dict[str, Any]],
    seeded_at: dict[str, str],
    now: datetime,
    stuck_after: timedelta,
    settle: timedelta,
    result: AuditResult,
    describe_execution: Callable[[str], str] | None,
) -> None:
    order_id, status = order["orderId"], order.get("status", "")
    created = parse_ts(order.get("createdAt")) or now
    result.stats["orders"] += 1

    if status not in TERMINAL:
        if is_parked_by_design(order):
            result.parked.append(Finding("PARKED", "dead-lettered", order_id, f"{status}, simulate={order.get('simulate')} (in a DLQ on purpose)"))
        elif now - created >= stuck_after:
            execution = order.get("executionArn")
            exec_status = describe_execution(execution) if (execution and describe_execution) else ("no execution" if not execution else "unknown")
            minutes = int((now - created).total_seconds() // 60)
            action = "parked: redrive the execution" if exec_status == "FAILED" else "investigate"
            result.stuck.append(Finding("STUCK", status, order_id, f"{status} for {minutes} min, execution {exec_status} ({action})"))
        else:
            result.stats["inFlight"] += 1
        return

    # Settling: changed moments ago (e.g. a late refund may land between our scans). Judged next round.
    newest = _newest(order.get("updatedAt"), *(e.get("ts") for e in entries))
    if newest and now - newest < settle:
        result.stats["settling"] += 1
        return
    result.stats["terminalChecked"] += 1

    violations: list[tuple[str, str]] = []
    violations += _money_checks(order, entries, intents)
    violations += _stock_checks(order, seeded_at)
    for invariant, detail in violations:
        result.violations.append(Finding("VIOLATION", invariant, order_id, detail))


def _money_checks(order: dict[str, Any], entries: list[dict[str, Any]], intents: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    status = order["status"]
    if not entries and order.get("createdAt", "") < DEMOPAY_STARTED_AT:
        return []  # before DemoPay: no money ever moved for these orders
    out: list[tuple[str, str]] = []
    debits = [Decimal(str(e["amount"])) for e in entries if e["type"] == "DEBIT"]
    credits = [Decimal(str(e["amount"])) for e in entries if e["type"] == "CREDIT"]
    net = sum(debits, ZERO) - sum(credits, ZERO)
    ledger = f"{len(debits)} DEBIT / {len(credits)} CREDIT, net {net}"
    total = Decimal(str(order.get("totalAmount", "0")))

    if status == "COMPLETED" and not (debits == [total] and not credits):
        out.append(("I1", f"COMPLETED but ledger {ledger} (expected one DEBIT of {total})"))
    if status == "FAILED" and net != 0:
        out.append(("I2", f"{status} but net charge {net} ({ledger})"))
    credit_keys = [e.get("lineId", "*") for e in entries if e["type"] == "CREDIT"]
    if len(debits) > 1 or len(credit_keys) != len(set(credit_keys)):
        out.append(("I3", f"double charge or refund: {ledger}, credit keys {sorted(credit_keys)}"))
    expected = fulfilled_amount(order)
    if net != expected:
        out.append(("I6", f"{status}: net {net} != fulfilled lines {expected}"))
    if sum(credits, ZERO) > sum(debits, ZERO):
        out.append(("I7", f"refunded {sum(credits, ZERO)} > charged {sum(debits, ZERO)}"))
    hist = history(order)
    if status == "CANCELLED":
        released = bool(order.get("released")) or "INVENTORY_RELEASED" in hist or not order.get("reservedItems")
        if net != 0 or not released or "ITEM_FULFILLED" in hist:
            out.append(("I8", f"CANCELLED: net {net}, stock released {released}, a line fulfilled {'ITEM_FULFILLED' in hist}"))
    cancel = "cancelRequestedAt" in order
    if (cancel or "FULFILLING" in hist) and not (cancel != ("FULFILLING" in hist) and (not cancel or status == "CANCELLED")):
        out.append(("I9", f"cancel requested {cancel}, reached FULFILLING {'FULFILLING' in hist}, status {status}"))
    intent = intents.get(f"PI-{order['orderId']}")
    if intent and intent.get("status") not in FINAL_INTENT:
        out.append(("I4", f"terminal order {status} but intent {intent['paymentIntentId']} is {intent.get('status')}"))
    return out


def _stock_checks(order: dict[str, Any], seeded_at: dict[str, str]) -> list[tuple[str, str]]:
    """A terminal order holds no reservation (only reservations made after the product's last seed count)."""
    when = reserved_at(order)
    left = {p: q for p, q in open_units(order).items() if when and when >= seeded_at.get(p, "")}
    if left:
        return [("I5", f"{order['status']} order still holds reserved units {left} (never released, fulfilled or written off)")]
    return []


def _audit_provider(snap: Snapshot, now: datetime, settle: timedelta, result: AuditResult) -> None:
    """I3/I7 between DemoPay's records and the customers' ledger (both written in the same transactions)."""
    debits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    credits: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in snap.ledger:
        intent_id = entry.get("paymentIntentId")
        if not intent_id:
            continue  # pre-2.1 direct debits, ADJUST entries
        if entry["type"] == "DEBIT":
            debits[intent_id].append(entry)
        elif entry["type"] == "CREDIT":
            credits[(intent_id, entry.get("lineId", "*"))].append(entry)

    charges = {p["paymentIntentId"]: p for p in snap.psp if p.get("kind") == "CHARGE"}
    refunds: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in snap.psp:
        if record.get("kind") == "REFUND":
            refunds[record["paymentIntentId"]].append(record)

    def recent(item: dict[str, Any]) -> bool:
        stamp = parse_ts(item.get("createdAt") or item.get("ts"))
        return bool(stamp and now - stamp < settle)

    for intent_id, charge in charges.items():
        result.stats["chargesChecked"] += 1
        found = debits.pop(intent_id, [])
        if recent(charge):
            continue
        if charge.get("outcome") == "SUCCEEDED":
            if len(found) != 1 or Decimal(str(found[0]["amount"])) != Decimal(str(charge["amount"])):
                result.violations.append(Finding("VIOLATION", "I3", charge["pspTxnId"], f"SUCCEEDED charge {charge['amount']} has {len(found)} ledger DEBIT(s)"))
        elif found:
            result.violations.append(Finding("VIOLATION", "I3", charge["pspTxnId"], f"{charge.get('outcome')} charge but {len(found)} ledger DEBIT(s)"))
        refunded = sum((Decimal(str(r["amount"])) for r in refunds.get(intent_id, [])), ZERO)
        recorded = Decimal(str(charge.get("refundedAmount", "0")))
        legacy = "refundedAmount" not in charge and all(r.get("createdAt", "") < REFUND_COUNTER_SINCE for r in refunds.get(intent_id, []))
        if refunds.get(intent_id) and not legacy and not any(recent(r) for r in refunds[intent_id]):
            if refunded != recorded:
                result.violations.append(Finding("VIOLATION", "I7", charge["pspTxnId"], f"refund records sum {refunded} != charge refundedAmount {recorded}"))
        if recorded > Decimal(str(charge["amount"])):
            result.violations.append(Finding("VIOLATION", "I7", charge["pspTxnId"], f"refundedAmount {recorded} > charged {charge['amount']}"))

    for intent_id, records in refunds.items():
        for record in records:
            key = (intent_id, record.get("lineId", "*"))
            found = credits.pop(key, [])
            if recent(record):
                continue
            if len(found) != 1 or Decimal(str(found[0]["amount"])) != Decimal(str(record["amount"])):
                result.violations.append(Finding("VIOLATION", "I3", record["pspTxnId"], f"refund record {record['amount']} has {len(found)} ledger CREDIT(s)"))

    # Money moved in the ledger with no DemoPay record behind it.
    for intent_id, entries in debits.items():
        for entry in entries:
            if not recent(entry):
                result.violations.append(Finding("VIOLATION", "I3", intent_id, f"ledger DEBIT {entry['amount']} without a DemoPay charge record"))
    for (intent_id, line), entries in credits.items():
        for entry in entries:
            if not recent(entry):
                result.violations.append(Finding("VIOLATION", "I3", intent_id, f"ledger CREDIT {entry['amount']} (line {line}) without a DemoPay refund record"))


def _audit_products(snap: Snapshot, now: datetime, settle: timedelta, result: AuditResult) -> None:
    """I5 per product: the five counters add up to the seed, and each counter is explained by the records."""
    held: dict[str, int] = defaultdict(int)
    written: dict[str, int] = defaultdict(int)
    reserved: dict[str, int] = defaultdict(int)
    sold: dict[str, int] = defaultdict(int)
    seeded_at = {p["productId"]: p.get("seededAt", "") for p in snap.inventory}
    busy: set[str] = set()  # products touched by something in the last few minutes: cross-item checks wait

    def mark_busy(products: Iterable[str], stamp: str | None) -> None:
        when = parse_ts(stamp)
        if when and now - when < settle:
            busy.update(products)

    for hold in snap.holds:
        if not hold["holdId"].startswith("HOLD-"):
            continue  # USER#<sub> pointer items
        products = [i["productId"] for i in hold.get("items") or []]
        mark_busy(products, hold.get("updatedAt"))
        if hold.get("status") == "ACTIVE":
            for item in hold["items"]:
                if hold.get("createdAt", "") >= seeded_at.get(item["productId"], ""):
                    held[item["productId"]] += int(item["quantity"])
    for record in snap.write_offs:
        if record.get("writtenOffAt", "") >= seeded_at.get(record["productId"], ""):
            written[record["productId"]] += int(record["quantity"])
    for order in snap.orders:
        products = [i["productId"] for i in order.get("items") or []]
        mark_busy(products, order.get("updatedAt"))
        when = reserved_at(order)
        if not when:
            continue
        for product, units in open_units(order).items():
            if when >= seeded_at.get(product, ""):
                reserved[product] += units
        for product, units in sold_units(order).items():
            if when >= seeded_at.get(product, ""):
                sold[product] += units

    for product in snap.inventory:
        pid = product["productId"]
        result.stats["productsChecked"] += 1
        counters = {k: int(product.get(k, 0)) for k in ("stock", "held", "reserved", "sold", "writtenOff")}
        negative = [k for k, v in counters.items() if v < 0]
        if negative:
            result.violations.append(Finding("VIOLATION", "I5", pid, f"negative counter(s) {negative}: {counters}"))
        seeded = product.get("seededStock")
        if seeded is None:
            result.stats["productsWithoutSeededStock"] += 1
        elif sum(counters.values()) != int(seeded):
            result.violations.append(Finding("VIOLATION", "I5", pid, f"stock+held+reserved+sold+writtenOff = {sum(counters.values())} != seeded {int(seeded)} {counters}"))
        if pid in busy:
            result.stats["productsSettling"] += 1
            continue
        explained = {"held": held[pid], "reserved": reserved[pid], "sold": sold[pid], "writtenOff": written[pid]}
        wrong = {k: f"counter {counters[k]} vs records {v}" for k, v in explained.items() if counters[k] != v}
        if wrong:
            result.violations.append(Finding("VIOLATION", "I5", pid, f"counters not explained by the records: {wrong}"))


def confirm(first: AuditResult, second: AuditResult) -> AuditResult:
    """Keep only violations seen in BOTH audits (same invariant + subject): a live change between two scans can
    make one audit look wrong, but not two audits a few seconds apart. STUCK/PARKED come from the second run."""
    seen = {(f.invariant, f.subject) for f in first.violations}
    merged = AuditResult(stuck=second.stuck, parked=second.parked, stats=second.stats)
    merged.violations = [f for f in second.violations if (f.invariant, f.subject) in seen]
    merged.stats["unconfirmedViolations"] = len(second.violations) - len(merged.violations)
    return merged
