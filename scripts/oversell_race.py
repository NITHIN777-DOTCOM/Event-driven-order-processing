"""Oversell race test (step 3.1): hundreds of buyers try to claim the last units at the same instant, LIVE.

    python scripts/oversell_race.py                    # everything below, ~15 min (most of it waiting for expiry)
    python scripts/oversell_race.py --label after-fix  # names the evidence file docs/evidence/upgrade-3.1/<label>.md

Steps:
  0. Pre-flight: the account's Lambda concurrency and the API stage's throttling, printed before racing.
  1. Buyers: 160 Cognito test users (race-001 .. race-160), made exactly like test users A and B
     (create_test_users.ensure_user: example.com address, password only in an SSM SecureString). One ACTIVE hold per
     user is a product rule (anti-hoarding), so every hold attempt needs a buyer of its own: race-011 .. race-160 hold,
     race-001 .. race-010 place the direct orders. Tokens are fetched BEFORE the race, wallets topped up.
  2. Seed RACE-1 (20 units), RACE-X and RACE-Y (10 each), listed = false (never in the storefront). The put is
     conditional on nothing being held, reserved, sold or written off, so re-seeding can never break I5.
  3. Round 1: 200 attempts on RACE-1 x1 at once: 150 checkout holds (POST /holds) + 50 direct orders (POST /orders).
     Round 2: 100 attempts on the cart {RACE-X: 1, RACE-Y: 1}, item order alternating (X,Y / Y,X): 60 holds + 40 orders.
     Every request is built, signed (token) and connected (TCP + TLS) first; a barrier then releases all the threads
     together, so the requests leave within a few milliseconds of each other.
  4. Each answer is classified: CLAIMED | OUT_OF_STOCK | THROTTLED | ERROR. A 429 (API Gateway's rate limit) is
     retried with jittered exponential backoff until a real stock answer comes back, and is counted separately; a
     throttle is never an out-of-stock. A direct order's 202 only means "accepted": its stock answer comes from the
     saga (RESERVED, or FAILED with OUT_OF_STOCK), read from the orders table.
  5. A sampler reads the race products' counters (consistent reads) every ~200 ms throughout and records the lowest
     `stock` and the highest claimed (held + reserved + sold + writtenOff) it ever saw, and checks I5 on every sample.
  6. Winners give the stock back: direct orders use simulate=payment_manual (DemoPay waits for the harness, which
     never charges), so the winners sit in PAYMENT_PENDING and are cancelled (CANCELLED, nothing charged). The winning
     holds are left to expire on their EventBridge Scheduler schedules (10 minutes). Recovery = every race product back
     to its seeded stock with held = 0.
  7. Invariants: I1-I4, I6-I9 for every order created (e2e_test.check_money), I5 for the race products and for all
     16 demo products (e2e_test.scenario_stock_conservation).
Exit code 1 if any check fails. Results go to docs/evidence/upgrade-3.1/<label>.md.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import random
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config

import e2e_test as e2e  # live-system helpers and the money invariants (importing it only reads, never writes)
from auth_tokens import auth_header, test_user
from create_test_users import ensure_user

OUT, REGION, API = e2e.OUT, e2e.REGION, e2e.API
EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "upgrade-3.1"

RACE_PRODUCTS = {"RACE-1": 20, "RACE-X": 10, "RACE-Y": 10}  # productId -> seeded units
RACE_PRICE = Decimal("100")
ORDER_BUYERS = [f"race-{n:03d}" for n in range(1, 11)]  # place the direct orders (no per-user limit on orders)
HOLD_BUYERS = [f"race-{n:03d}" for n in range(11, 161)]  # one hold each (one ACTIVE hold per user)
ROUND1 = {"holds": 150, "orders": 50}
ROUND2 = {"holds": 60, "orders": 40}
SIMULATE = "payment_manual"  # the winners wait in PAYMENT_PENDING and are cancelled, so nobody is ever charged

MAX_ATTEMPTS = 15  # per request, counting throttled retries
BACKOFF_BASE_S, BACKOFF_CAP_S = 0.2, 4.0
SAMPLE_INTERVAL_S = 0.2
SETTLE_TIMEOUT_S = 90  # every direct order must have its stock answer by then (the payment timeout is 120 s)
RECOVERY_TIMEOUT_S = 20 * 60
HOLD_SECONDS = 600  # the storefront's hold length; recovery waits for these schedules on purpose

CLAIMED, OUT_OF_STOCK, THROTTLED, ERROR = "CLAIMED", "OUT_OF_STOCK", "THROTTLED", "ERROR"

ddb = boto3.resource("dynamodb", region_name=REGION)
ddb_client = ddb.meta.client
inventory_table, orders_table, holds_table = e2e.inventory_table, e2e.orders_table, e2e.holds_table
API_HOST = urlparse(API).hostname


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


# --------------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------------
@dataclass
class Attempt:
    """One buyer's attempt: a checkout hold or a direct order, for one cart."""

    index: int
    kind: str  # "hold" | "order"
    buyer: str
    cart: list[str]  # productIds in the order sent
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    outcome: str = ""  # CLAIMED | OUT_OF_STOCK | ERROR (THROTTLED is never final: it is retried)
    codes: list[int] = field(default_factory=list)  # every HTTP status, retries included
    throttles: int = 0
    sent_at: str = ""
    answered_at: str = ""
    first_send: float = 0.0
    final_ms: float = 0.0  # the attempt that got the real answer
    total_ms: float = 0.0  # first send -> real answer, throttled retries included
    body: dict = field(default_factory=dict)
    order_id: str | None = None
    hold_id: str | None = None
    detail: str = ""
    saga_ms: float | None = None  # direct orders: accepted -> stock answer in the saga

    def request(self) -> tuple[str, str, dict]:
        items = [{"productId": p, "quantity": 1} for p in self.cart]
        if self.kind == "hold":
            return "POST", "/holds", {"items": items}  # no durationSeconds: the storefront's 600 s
        return "POST", "/orders", {"customerName": f"Race buyer {self.buyer}", "items": items, "simulate": SIMULATE}


@dataclass
class Sampler:
    """Polls the race products' counters every ~200 ms while a round runs."""

    min_stock: dict[str, int] = field(default_factory=dict)
    max_claimed: dict[str, int] = field(default_factory=dict)
    samples: int = 0
    i5_breaks: list[str] = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)

    def run(self) -> None:
        keys = [{"productId": p} for p in RACE_PRODUCTS]
        while not self.stop.is_set():
            items = ddb_client.batch_get_item(RequestItems={OUT["inventory_table"]: {"Keys": keys, "ConsistentRead": True}})
            for item in items["Responses"][OUT["inventory_table"]]:
                product = item["productId"]
                stock, claimed = int(item["stock"]), sum(int(item.get(k, 0)) for k in ("held", "reserved", "sold", "writtenOff"))
                self.min_stock[product] = min(self.min_stock.get(product, stock), stock)
                self.max_claimed[product] = max(self.max_claimed.get(product, claimed), claimed)
                if stock + claimed != RACE_PRODUCTS[product] and len(self.i5_breaks) < 10:
                    self.i5_breaks.append(f"{now_iso()} {product}: stock {stock} + claimed {claimed} != {RACE_PRODUCTS[product]}")
            self.samples += 1
            self.stop.wait(SAMPLE_INTERVAL_S)


@dataclass
class Round:
    name: str
    title: str
    attempts: list[Attempt]
    sampler: Sampler = field(default_factory=Sampler)
    checks: list[tuple[bool, str]] = field(default_factory=list)
    counters_at_settle: dict[str, tuple[int, ...]] = field(default_factory=dict)
    fired_at: str = ""
    spread_ms: float = 0.0  # first send -> last send

    def check(self, ok: bool, text: str) -> bool:
        self.checks.append((bool(ok), text))
        print(f"  [{'PASS' if ok else 'FAIL'}] {text}")
        return bool(ok)

    @property
    def passed(self) -> bool:
        return all(ok for ok, _ in self.checks)


# --------------------------------------------------------------------------------------------
# Pre-flight, buyers, seed
# --------------------------------------------------------------------------------------------
def preflight() -> dict:
    settings = boto3.client("lambda", region_name=REGION).get_account_settings()["AccountLimit"]
    stage = boto3.client("apigatewayv2", region_name=REGION).get_stage(ApiId=API_HOST.split(".")[0], StageName="$default")
    route = stage.get("DefaultRouteSettings", {})
    facts = {
        "lambda_concurrency_limit": settings["ConcurrentExecutions"],
        "lambda_unreserved": settings["UnreservedConcurrentExecutions"],
        "api_burst": route.get("ThrottlingBurstLimit"),
        "api_rate": route.get("ThrottlingRateLimit"),
        "api_route_overrides": len(stage.get("RouteSettings") or {}),
    }
    print(
        f"Pre-flight: Lambda concurrency {facts['lambda_concurrency_limit']} (unreserved {facts['lambda_unreserved']}); "
        f"API stage burst {facts['api_burst']}, rate {facts['api_rate']}/s, per-route overrides {facts['api_route_overrides']}"
    )
    if facts["lambda_concurrency_limit"] <= 10:
        print("  NOTE: a very low account concurrency limit; throttling will dominate (kept at 200 attempts, as planned)")
    return facts


def prepare_buyers() -> None:
    """Create any missing race buyer (idempotent), fetch every token, and top up the order buyers' wallets."""
    session = boto3.session.Session(region_name=REGION)
    patient = Config(retries={"mode": "adaptive", "max_attempts": 10})  # SSM PutParameter allows only a few per second
    cognito, ssm = session.client("cognito-idp", config=patient), session.client("ssm", config=patient)
    labels = ORDER_BUYERS + HOLD_BUYERS
    created = [s for s in (ensure_user(cognito, ssm, OUT["user_pool_id"], label) for label in labels) if s != "exists"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(test_user, labels))  # sign-in now, so no token fetch happens during the race
    for label in ORDER_BUYERS:
        e2e.set_wallet(label)  # ₹10,00,000 each; nothing is charged anyway (payment_manual, cancelled)
    print(f"Buyers: {len(labels)} ready ({len(created)} created now), tokens fetched, {len(ORDER_BUYERS)} wallets topped up")


def seed_race_products() -> None:
    """Reset each race product to its seed, only if nothing of it is held, reserved, sold or written off."""
    seeded_at = now_iso()
    for product, units in RACE_PRODUCTS.items():
        try:
            inventory_table.put_item(
                Item={
                    "productId": product, "name": f"Race test product {product}", "category": "Test",
                    "price": RACE_PRICE, "mrp": RACE_PRICE, "stock": units, "held": 0, "reserved": 0, "sold": 0,
                    "writtenOff": 0, "listed": False, "seededAt": seeded_at,
                    "description": "Test-only product for scripts/oversell_race.py (step 3.1); never listed in the storefront.",
                },
                ConditionExpression="attribute_not_exists(productId) OR (held = :z AND reserved = :z AND sold = :z AND writtenOff = :z)",
                ExpressionAttributeValues={":z": 0},
            )
        except ddb_client.exceptions.ConditionalCheckFailedException:
            sys.exit(f"{product} still has units held/reserved from an earlier run; wait for its holds to expire, then re-run")
    print("Seeded " + ", ".join(f"{p} = {u}" for p, u in RACE_PRODUCTS.items()) + " (listed = false)")


# --------------------------------------------------------------------------------------------
# The race
# --------------------------------------------------------------------------------------------
def backoff(retry: int) -> float:
    """Full jitter: a random wait in [0, min(cap, base * 2^retry)], so throttled clients don't retry in lockstep."""
    return random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**retry))


def classify(attempt: Attempt, code: int, body: dict) -> str:
    text = json.dumps(body)
    if code == 429 or "TooManyRequests" in text or "Rate exceeded" in text:
        return THROTTLED
    if attempt.kind == "hold":
        if code == 201:
            attempt.hold_id = body.get("holdId")
            return CLAIMED
        if code == 409 and body.get("productId"):
            attempt.detail = f"409 {body.get('error')}"
            return OUT_OF_STOCK
        attempt.detail = f"{code} {text[:160]}"
        return ERROR
    if code in (200, 202) and body.get("orderId"):  # 200 = a retried request that had in fact been accepted
        attempt.order_id = body["orderId"]
        return "ACCEPTED"  # the stock answer comes from the saga (settle_orders)
    attempt.detail = f"{code} {text[:160]}"
    return ERROR


def send(attempt: Attempt, barrier: threading.Barrier) -> Attempt:
    """Connect first, wait at the barrier, then send; retry only throttles."""
    method, path, payload = attempt.request()
    headers = {"Content-Type": "application/json", **auth_header(attempt.buyer)}
    if attempt.kind == "order":
        headers["Idempotency-Key"] = attempt.idempotency_key  # the same key on every retry: never two orders
    data = json.dumps(payload)
    conn = http.client.HTTPSConnection(API_HOST, timeout=30)
    try:
        conn.connect()  # TCP + TLS before the barrier, so the request itself is all that's left
    except OSError as err:
        attempt.detail = f"could not pre-connect: {err!r}"  # still wait: the barrier needs every thread
    barrier.wait()
    attempt.first_send = time.perf_counter()
    attempt.sent_at = now_iso()
    for retry in range(MAX_ATTEMPTS):
        started = time.perf_counter()
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            code, raw = resp.status, resp.read()
        except (http.client.HTTPException, OSError) as err:
            attempt.outcome, attempt.detail = ERROR, f"transport error: {err!r}"
            break
        finally:
            conn.close()  # a fresh connection per try: a retry never reuses a socket the server may have dropped
        body = json.loads(raw or b"{}") if raw[:1] in (b"{", b"[") else {"raw": raw[:200].decode(errors="replace")}
        attempt.codes.append(code)
        result = classify(attempt, code, body)
        if result != THROTTLED:
            attempt.final_ms = (time.perf_counter() - started) * 1000
            attempt.outcome, attempt.body = result, body
            break
        attempt.throttles += 1
        time.sleep(backoff(retry))
        conn = http.client.HTTPSConnection(API_HOST, timeout=30)
    else:
        attempt.outcome, attempt.detail = ERROR, f"still throttled after {MAX_ATTEMPTS} tries"
    attempt.total_ms = (time.perf_counter() - attempt.first_send) * 1000
    attempt.answered_at = now_iso()
    return attempt


def fire(race: Round) -> None:
    """Release every attempt at the same instant, with the sampler running."""
    sampler_thread = threading.Thread(target=race.sampler.run, daemon=True)
    sampler_thread.start()
    # The action runs once, when the last thread arrives: that is the release, after every TCP + TLS pre-connect
    # (stamping before the pool starts would include ~10-30 s of connecting for 100-200 threads).
    barrier = threading.Barrier(len(race.attempts), action=lambda: setattr(race, "fired_at", now_iso()), timeout=120)
    with ThreadPoolExecutor(max_workers=len(race.attempts)) as pool:
        list(pool.map(lambda a: send(a, barrier), race.attempts))
    sends = [a.first_send for a in race.attempts]
    race.spread_ms = (max(sends) - min(sends)) * 1000
    settle_orders(race)
    race.sampler.stop.set()
    sampler_thread.join()


def stored_orders(order_ids: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for start in range(0, len(order_ids), 100):
        keys = [{"orderId": o} for o in order_ids[start:start + 100]]
        request = {OUT["orders_table"]: {"Keys": keys, "ConsistentRead": True}}
        while request:
            page = ddb_client.batch_get_item(RequestItems=request)
            for item in page["Responses"].get(OUT["orders_table"], []):
                found[item["orderId"]] = item
            request = page.get("UnprocessedKeys") or None
    return found


def settle_orders(race: Round) -> None:
    """Wait until every accepted direct order has its stock answer: reserved (and waiting for payment) or OUT_OF_STOCK."""
    pending = {a.order_id: a for a in race.attempts if a.outcome == "ACCEPTED"}
    deadline = time.monotonic() + SETTLE_TIMEOUT_S
    while pending and time.monotonic() < deadline:
        for order_id, order in stored_orders(list(pending)).items():
            history = {h["status"]: h for h in order.get("statusHistory", [])}
            attempt = pending[order_id]
            if "OUT_OF_STOCK" in history:  # written by ReserveInventory just before it fails the saga
                attempt.outcome, attempt.detail = OUT_OF_STOCK, history["OUT_OF_STOCK"].get("detail", "")
            elif order["status"] == "FAILED":
                attempt.outcome, attempt.detail = ERROR, f"FAILED without OUT_OF_STOCK: {order['statusHistory'][-1].get('detail', '')}"
                del pending[order_id]
                continue
            elif order["status"] == "PAYMENT_PENDING":
                attempt.outcome, attempt.detail = CLAIMED, history.get("RESERVED", {}).get("detail", "")
            else:
                continue
            answered = history.get("OUT_OF_STOCK") or history.get("RESERVED")
            attempt.saga_ms = (datetime.fromisoformat(answered["timestamp"].replace("Z", "+00:00"))
                               - datetime.fromisoformat(order["createdAt"].replace("Z", "+00:00"))).total_seconds() * 1000
            del pending[order_id]
        if pending:
            time.sleep(1)
    for attempt in pending.values():
        attempt.outcome, attempt.detail = ERROR, f"no stock answer within {SETTLE_TIMEOUT_S} s"
    race.counters_at_settle = {p: e2e.all_counters(p) for p in RACE_PRODUCTS}


# --------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------
def active_race_holds() -> dict[str, int]:
    """productId -> units in ACTIVE holds, from the holds table (not the counters)."""
    units: dict[str, int] = {}
    kwargs: dict = {"FilterExpression": "#s = :a", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":a": "ACTIVE"}}
    while True:
        page = holds_table.scan(**kwargs)
        for hold in page["Items"]:
            for item in hold["items"]:
                if item["productId"] in RACE_PRODUCTS:
                    units[item["productId"]] = units.get(item["productId"], 0) + int(item["quantity"])
        if "LastEvaluatedKey" not in page:
            return units
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def check_round(race: Round) -> None:
    cart = race.attempts[0].cart
    units = min(RACE_PRODUCTS[p] for p in cart)
    tally = {k: sum(a.outcome == k for a in race.attempts) for k in (CLAIMED, OUT_OF_STOCK, ERROR)}
    throttled = [a for a in race.attempts if a.throttles]
    print(f"  {len(race.attempts)} attempts sent within {race.spread_ms:.0f} ms: {tally}, throttled {len(throttled)} "
          f"({sum(a.throttles for a in race.attempts)} retries)")

    race.check(tally[CLAIMED] == units, f"exactly {units} carts claimed: {tally[CLAIMED]} (holds {sum(a.outcome == CLAIMED and a.kind == 'hold' for a in race.attempts)}, orders {sum(a.outcome == CLAIMED and a.kind == 'order' for a in race.attempts)})")
    errors = [f"\n      {a.kind} {a.buyer}: {a.detail}" for a in race.attempts if a.outcome == ERROR]
    race.check(tally[ERROR] == 0, f"0 ERROR answers: {tally[ERROR]}" + "".join(errors[:10]))
    race.check(all(a.outcome != THROTTLED for a in race.attempts), f"every throttled request was eventually answered ({len(throttled)} throttled at least once)")
    for product in cart:
        stock, held, reserved, sold, written_off = race.counters_at_settle[product]
        race.check(stock == 0 and held + reserved + sold + written_off == units,
                   f"{product} at settle: stock {stock}, held {held}, reserved {reserved} (claimed {held + reserved + sold + written_off} = {units})")
        race.check(race.sampler.min_stock.get(product, 0) >= 0 and race.sampler.max_claimed.get(product, 0) <= units,
                   f"{product} sampler ({race.sampler.samples} samples): min stock {race.sampler.min_stock.get(product)}, max claimed {race.sampler.max_claimed.get(product)} (<= {units})")
    race.check(not race.sampler.i5_breaks, f"I5 on every sample: stock + claimed = seeded" + "".join(f"\n      {b}" for b in race.sampler.i5_breaks))
    phantom = [a for a in race.attempts if a.outcome == OUT_OF_STOCK and a.kind == "hold" and int(a.body.get("available", 0)) > 0]
    race.check(not phantom, f"no out-of-stock answer while stock was left (409 with available > 0): {len(phantom)}")
    if len(cart) > 1:  # all-or-nothing: every claimed cart has every item, and the products moved together
        held_carts = [holds_table.get_item(Key={"holdId": a.hold_id}, ConsistentRead=True)["Item"] for a in race.attempts if a.outcome == CLAIMED and a.kind == "hold"]
        orders = stored_orders([a.order_id for a in race.attempts if a.outcome == CLAIMED and a.kind == "order"]).values()
        partial = [h["holdId"] for h in held_carts if {i["productId"] for i in h["items"]} != set(cart)]
        partial += [o["orderId"] for o in orders if {i["productId"] for i in o.get("reservedItems", [])} != set(cart)]
        claimed = {p: RACE_PRODUCTS[p] - race.counters_at_settle[p][0] for p in cart}
        race.check(not partial and len(set(claimed.values())) == 1, f"all-or-nothing: no cart with only one item ({len(partial)}), units claimed per product {claimed}")


def cancel_winners(race: Round) -> None:
    """Cancel every winning direct order (PAYMENT_PENDING; DemoPay never charges a payment_manual order)."""
    winners = [a for a in race.attempts if a.kind == "order" and a.outcome == CLAIMED]

    def cancel(attempt: Attempt) -> int:
        for retry in range(8):
            code, _ = e2e.cancel(attempt.order_id, user=attempt.buyer, reason="oversell race test: give the unit back")
            if code not in (429, 409):
                return code
            time.sleep(backoff(retry))
        return code

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(cancel, winners))
    race.check(all(c in (200, 202) for c in codes), f"cancelled the {len(winners)} winning orders: HTTP {sorted(set(codes))}")


def check_money(races: list[Round]) -> tuple[int, list[str]]:
    """I1-I4, I6-I9 for every order the race created (each attempt is checked as its own scenario)."""
    ids = [a for r in races for a in r.attempts if a.order_id]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:  # the cancelled winners finish their cancel branch first
        stored = stored_orders([a.order_id for a in ids])
        if all(o["status"] in ("FAILED", "CANCELLED", "COMPLETED") for o in stored.values()):
            break
        time.sleep(3)
    failures = []
    for attempt in ids:
        s = e2e.Scenario("race", attempt.order_id, order_id=attempt.order_id, user=attempt.buyer)
        e2e.check_money(s, attempt.order_id, {None} if attempt.outcome == OUT_OF_STOCK else {"FAILED", "REFUNDED"})
        status = stored_orders([attempt.order_id])[attempt.order_id]["status"]
        s.check(status == ("FAILED" if attempt.outcome == OUT_OF_STOCK else "CANCELLED"), f"final status {status}")
        attempt.detail += f" | final {status}, {s.money}"
        failures += [f"{attempt.order_id} ({attempt.buyer}): {text}" for ok, text in s.checks if not ok]
    return len(ids), failures


def wait_for_recovery(races: list[Round]) -> dict:
    """Wait for the winning holds' schedules to fire; then every race product is back to its seed with held = 0."""
    hold_ids = [a.hold_id for r in races for a in r.attempts if a.outcome == CLAIMED and a.kind == "hold"]
    started = time.monotonic()
    deadline = started + RECOVERY_TIMEOUT_S
    print(f"Waiting for {len(hold_ids)} winning holds to expire on their schedules (~{HOLD_SECONDS // 60} min)...")
    while time.monotonic() < deadline:
        counters = {p: e2e.all_counters(p) for p in RACE_PRODUCTS}
        if all(c[0] == RACE_PRODUCTS[p] and c[1] == 0 for p, c in counters.items()):
            break
        time.sleep(5)
    recovered_at = datetime.now(timezone.utc)
    holds = [holds_table.get_item(Key={"holdId": h}, ConsistentRead=True)["Item"] for h in hold_ids]
    last_created = max((datetime.fromisoformat(h["createdAt"].replace("Z", "+00:00")) for h in holds), default=recovered_at)
    lags = [int(h["expiryLagMs"]) / 1000 for h in holds if "expiryLagMs" in h]
    return {
        "counters": {p: e2e.all_counters(p) for p in RACE_PRODUCTS},
        "seconds_from_last_hold": (recovered_at - last_created).total_seconds(),
        "waited_seconds": time.monotonic() - started,
        "hold_statuses": {s: sum(h["status"] == s for h in holds) for s in sorted({h["status"] for h in holds})},
        "expired_by": {s: sum(h.get("expiredBy") == s for h in holds) for s in sorted({str(h.get("expiredBy")) for h in holds})},
        "lag_seconds": (min(lags), statistics.median(lags), max(lags)) if lags else None,
    }


# --------------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------------
def latency_row(values: list[float]) -> str:
    return f"{percentile(values, 50):.0f} / {percentile(values, 95):.0f} / {max(values, default=0):.0f}"


def round_markdown(race: Round) -> list[str]:
    lines = [f"## {race.title}", "", f"Fired {race.fired_at}; all {len(race.attempts)} requests left within **{race.spread_ms:.0f} ms**.", ""]
    lines += ["| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |", "|---|---|---|---|---|---|---|"]
    for kind in ("hold", "order", None):
        group = [a for a in race.attempts if kind is None or a.kind == kind]
        label = {"hold": "checkout holds", "order": "direct orders", None: "**total**"}[kind]
        lines.append(f"| {label} | {len(group)} | {sum(a.outcome == CLAIMED for a in group)} | {sum(a.outcome == OUT_OF_STOCK for a in group)} | "
                     f"{sum(a.outcome == ERROR for a in group)} | {sum(1 for a in group if a.throttles)} | {sum(a.throttles for a in group)} |")
    lines += ["", "Latency in ms, p50 / p95 / max:", "", "| Measure | p50 / p95 / max |", "|---|---|"]
    lines.append(f"| answering request, holds (the real stock answer) | {latency_row([a.final_ms for a in race.attempts if a.kind == 'hold'])} |")
    lines.append(f"| first send -> real answer, holds (throttled retries included) | {latency_row([a.total_ms for a in race.attempts if a.kind == 'hold'])} |")
    lines.append(f"| POST /orders accepted (202) | {latency_row([a.final_ms for a in race.attempts if a.kind == 'order'])} |")
    lines.append(f"| order accepted -> stock answer in the saga | {latency_row([a.saga_ms for a in race.attempts if a.saga_ms is not None])} |")
    lines += ["", "Sampler (consistent reads every ~200 ms during the round):", "", "| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |", "|---|---|---|---|---|"]
    for product in race.attempts[0].cart:
        lines.append(f"| {product} | {race.sampler.samples} | {race.sampler.min_stock.get(product)} | {race.sampler.max_claimed.get(product)} | {race.counters_at_settle[product]} |")
    lines += ["", "Checks:", ""] + [f"- {'PASS' if ok else '**FAIL**'}: {text}" for ok, text in race.checks]
    lines += ["", "<details><summary>Every attempt</summary>", "", "| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |", "|---|---|---|---|---|---|---|---|---|---|"]
    for a in race.attempts:
        lines.append(f"| {a.index} | {a.kind} | {a.buyer} | {','.join(a.cart)} | {' '.join(map(str, a.codes))} | {a.outcome} | {a.final_ms:.0f} | {a.total_ms:.0f} | "
                     f"{a.hold_id or a.order_id or '-'} | {a.detail.replace('|', '/')[:200]} |")
    return lines + ["", "</details>", ""]


def write_evidence(label: str, facts: dict, races: list[Round], money: tuple[int, list[str]], recovery: dict, i5: list[tuple[bool, str]], passed: bool, duration: float) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{label}.md"
    lines = [
        f"# Oversell race test, run `{label}`", "",
        f"Run: {races[0].fired_at} · Region: {REGION} · API: `{API}` · Command: `python scripts/oversell_race.py --label {label}` · Duration: {duration:.0f} s", "",
        f"**Result: {'PASS' if passed else 'FAIL'}**", "",
        "## Pre-flight", "",
        f"- Lambda account concurrency limit **{facts['lambda_concurrency_limit']}**, unreserved **{facts['lambda_unreserved']}** (no function has reserved concurrency).",
        f"- API Gateway stage `$default`: burst **{facts['api_burst']}**, rate **{facts['api_rate']}/s**, per-route overrides: {facts['api_route_overrides']}.",
        f"- Buyers: {len(ORDER_BUYERS)} order buyers + {len(HOLD_BUYERS)} hold buyers (one ACTIVE hold per user), tokens fetched before the race.", "",
    ]
    for race in races:
        lines += round_markdown(race)
    count, failures = money
    lines += ["## Money invariants (I1-I4, I6-I9)", "", f"Checked {count} orders: " + ("**all pass**" if not failures else f"**{len(failures)} failures**"), ""]
    lines += [f"- {f}" for f in failures[:30]]
    lines += ["", "## Recovery", "",
              f"- Counters after recovery (stock, held, reserved, sold, writtenOff): {recovery['counters']}",
              f"- Full recovery **{recovery['seconds_from_last_hold']:.0f} s after the last winning hold was created** (holds last {HOLD_SECONDS} s); waited {recovery['waited_seconds']:.0f} s.",
              f"- Winning holds: {recovery['hold_statuses']}, expired by {recovery['expired_by']}; schedule lag after expiresAt (min / median / max s): {recovery['lag_seconds']}", "",
              "## I5 stock conservation after recovery", ""]
    lines += [f"- {'PASS' if ok else '**FAIL**'}: {text}" for ok, text in i5]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------------------------------------
def build_round1() -> Round:
    holds = [Attempt(i, "hold", HOLD_BUYERS[i], ["RACE-1"]) for i in range(ROUND1["holds"])]
    orders = [Attempt(ROUND1["holds"] + i, "order", ORDER_BUYERS[i % len(ORDER_BUYERS)], ["RACE-1"]) for i in range(ROUND1["orders"])]
    attempts = holds + orders
    random.shuffle(attempts)  # holds and orders interleaved in the thread pool
    return Round("round1", f"Round 1: {len(attempts)} simultaneous attempts on RACE-1 ({RACE_PRODUCTS['RACE-1']} units)", attempts)


def build_round2(round1: Round) -> Round:
    """Hold buyers must not hold anything already: reuse round 1's losers (a 409 created no hold)."""
    free = [a.buyer for a in round1.attempts if a.kind == "hold" and a.outcome == OUT_OF_STOCK]
    if len(free) < ROUND2["holds"]:
        sys.exit(f"only {len(free)} round-1 hold buyers are free for round 2 (need {ROUND2['holds']})")
    carts = (["RACE-X", "RACE-Y"], ["RACE-Y", "RACE-X"])
    holds = [Attempt(i, "hold", free[i], list(carts[i % 2])) for i in range(ROUND2["holds"])]
    orders = [Attempt(ROUND2["holds"] + i, "order", ORDER_BUYERS[i % len(ORDER_BUYERS)], list(carts[i % 2])) for i in range(ROUND2["orders"])]
    attempts = holds + orders
    random.shuffle(attempts)
    return Round("round2", f"Round 2: {len(attempts)} simultaneous carts {{RACE-X: 1, RACE-Y: 1}} (10 + 10 units), item order X,Y / Y,X", attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--label", default=datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M"))
    label = parser.parse_args().label
    started = time.monotonic()
    facts = preflight()
    prepare_buyers()
    seed_race_products()

    round1 = build_round1()
    print(f"\n{round1.title}: firing...")
    fire(round1)
    check_round(round1)
    cancel_winners(round1)

    round2 = build_round2(round1)
    print(f"\n{round2.title}: firing...")
    fire(round2)
    check_round(round2)
    cancel_winners(round2)
    races = [round1, round2]

    print("\nChecking I1-I4, I6-I9 for every race order...")
    money = check_money(races)
    print(f"  {money[0]} orders checked, {len(money[1])} failures" + "".join(f"\n      {f}" for f in money[1][:10]))
    recovery = wait_for_recovery(races)
    print(f"Recovery: {recovery['counters']} after {recovery['waited_seconds']:.0f} s ({recovery['seconds_from_last_hold']:.0f} s after the last hold)")

    i5: list[tuple[bool, str]] = []
    for product, units in RACE_PRODUCTS.items():
        stock, held, reserved, sold, written_off = recovery["counters"][product]
        i5.append((stock == units and held == reserved == sold == written_off == 0, f"{product} back to its seed: stock {stock}/{units}, held {held}, reserved {reserved}"))
    active = active_race_holds()
    i5.append((not active, f"no ACTIVE holds left on race products: {active or 'none'}"))
    demo = e2e.scenario_stock_conservation()
    i5 += demo.checks
    for ok, text in i5:
        print(f"  [{'PASS' if ok else 'FAIL'}] {text}")

    passed = all(r.passed for r in races) and not money[1] and all(ok for ok, _ in i5)
    path = write_evidence(label, facts, races, money, recovery, i5, passed, time.monotonic() - started)
    print(f"\n{'PASS' if passed else 'FAIL'} in {time.monotonic() - started:.0f} s; evidence written to {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
