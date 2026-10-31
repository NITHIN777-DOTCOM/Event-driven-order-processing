"""Step 3.2 chaos harness: run one experiment against the LIVE saga and check that nothing was lost.

Experiments (see infra/main/chaos.tf and src/common/chaos.py):
  E1  Fault injection: ~30% of the 9 saga Lambdas' invocations fail for 10 min.
  E2  Fault injection: half the DemoPay / webhook invocations start 25 s late, pushing payments past the 120 s timeout.
  E3  Code switches: each order crashes right AFTER one of its writes, once.
  E4  Duplicates: the same SQS message 3x, the webhook callback twice, two cancels at once.
  E5  Fault injection, refund outage (100% refund-payment errors, 6 min) -> orders that owe a refund park -> redrive.

E1/E2/E5 were designed for AWS FIS, which this account's AWS Free plan can't use (SubscriptionRequiredException).
The injector in src/common/chaos.py keeps FIS's contract (rate, duration, stop condition) and narrows the blast
radius: this script writes s3://<chaos_fault_bucket>/faults/active.json with a run id and an expiry of at most
15 minutes, and only orders it places (chaosRun = that run id) are affected. It deletes the configuration when the
run ends or when the order-saga-invariant-violation alarm fires (the stop condition). Every experiment except E4
needs CHAOS_ENABLED=true on the Lambdas (terraform apply -var chaos_enabled=true; back to false right after).

For each experiment: optional re-seed of the demo catalogue (the RACE-* products are not touched), ~N orders with
mixed scenarios placed while the fault is active, the invariant auditor Lambda invoked every minute, then a
per-order check: terminal (or STUCK and alarmed), one execution, no double DEBIT / CREDIT, net charge = what was
fulfilled (₹ lost = 0), plus SFN retry counts. Writes docs/evidence/upgrade-3.2/<experiment>.md and .json.

    python scripts/chaos_run.py E1 --orders 30 --seed
    python scripts/chaos_run.py E3                 # needs `terraform apply -var chaos_enabled=true` first
    python scripts/chaos_run.py E5                 # parks 3 orders, waits for the STUCK alarm
    python scripts/chaos_run.py E5 --redrive       # redrives the parked executions and re-checks

Never run during a demo.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import boto3

import e2e_test as e2e
from auth_tokens import auth_header

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "upgrade-3.2"
STATE_FILE = EVIDENCE_DIR / "e5-state.json"  # E5's parked orders, read back by --redrive
OUT = e2e.OUT
REGION = OUT["region"]
TERMINAL = {"COMPLETED", "PARTIALLY_FULFILLED", "FAILED", "CANCELLED"}
SAGA_FUNCTIONS = [
    "reserve_inventory", "request_payment", "payment_provider", "payment_webhook", "fulfill_item",
    "refund_payment", "release_inventory", "write_off_lines", "begin_fulfillment",
]
# The fault each injector experiment writes (the numbers the FIS templates had). Minutes must stay <= 15.
FAULTS = {
    "E1": {"functions": SAGA_FUNCTIONS, "action": "error", "percent": 30, "delayMs": 0, "minutes": 10},
    "E2": {"functions": ["payment_provider", "payment_webhook"], "action": "delay", "percent": 50, "delayMs": 25_000, "minutes": 10},
    "E5": {"functions": ["refund_payment"], "action": "error", "percent": 100, "delayMs": 0, "minutes": 6},
}
FAULT_KEY = "faults/active.json"  # src/common/chaos.py FAULT_KEY
STOP_ALARM = "order-saga-invariant-violation"

s3 = boto3.client("s3", region_name=REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
sfn = e2e.sfn
sqs = e2e.sqs


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------------------------
# One order placed by the harness, and what we found about it afterwards
# --------------------------------------------------------------------------------------------
@dataclass
class Placed:
    kind: str  # the scenario, e.g. "none", "partial", "cancel_after_payment", "crash_after:debit"
    order_id: str | None = None
    http: int = 0
    status: str = ""
    execution: str = ""  # SFN execution status
    executions: int = 0  # executions with this name (must be 1)
    debits: int = 0
    credit_keys: list[str] = field(default_factory=list)
    net: str = "0"  # ledger DEBIT - CREDIT
    expected_net: str = "0"  # what was fulfilled
    retries: dict[str, int] = field(default_factory=dict)  # state -> extra attempts
    problems: list[str] = field(default_factory=list)
    note: str = ""


RUN_ID: str | None = None  # this run's chaosRun marker (E1/E2/E5): the only orders the injected faults touch


def post_order(lines: list[tuple[str, int]], simulate: str = "none", chaos: str | None = None,
               simulate_line: int | None = None, hold_id: str | None = None) -> tuple[int, dict]:
    payload: dict = {
        "customerName": "Chaos Tester",
        "items": [{"productId": p, "quantity": q} for p, q in lines],
        "simulate": simulate,
    }
    if chaos:
        payload["chaos"] = chaos
    if RUN_ID:
        payload["chaosRun"] = RUN_ID
    if hold_id:
        payload["holdId"] = hold_id
    if simulate_line is not None:
        payload["simulateLine"] = simulate_line
    headers = {"Idempotency-Key": str(uuid.uuid4()), **auth_header(e2e.USER)}
    # The API answers 503 when a stock path stays busy (step 3.1); retry like the frontend does.
    for attempt in range(4):
        code, body = e2e.http_json("POST", f"{e2e.API}/orders", payload, headers)
        if code != 503:
            return code, body
        time.sleep(1 + attempt)
    return code, body


# --------------------------------------------------------------------------------------------
# Scenario drivers: each places one order (and does whatever the scenario needs next)
# --------------------------------------------------------------------------------------------
def drive_simple(kind: str, lines: list[tuple[str, int]], simulate: str, chaos: str | None = None,
                 simulate_line: int | None = None) -> Placed:
    placed = Placed(kind)
    placed.http, body = post_order(lines, simulate, chaos, simulate_line)
    placed.order_id = body.get("orderId")
    if not placed.order_id:
        placed.problems.append(f"POST /orders -> {placed.http} {body}")
    return placed


def drive_cancel_after_payment(kind: str = "cancel_after_payment", chaos: str | None = None, twice: bool = False) -> Placed:
    """fulfillment_slow gives a 10 s window after the capture; cancel inside it (twice at once for E4)."""
    placed = drive_simple(kind, [("4K-MONITOR", 1)], "fulfillment_slow", chaos)
    if not placed.order_id:
        return placed
    order = e2e.wait_for_status(placed.order_id, {"PAYMENT_CAPTURED"} | TERMINAL, timeout=240)
    if order.get("status") != "PAYMENT_CAPTURED":
        placed.note = f"never reached PAYMENT_CAPTURED (status {order.get('status')}); not cancelled"
        return placed
    if twice:
        with ThreadPoolExecutor(2) as pool:
            answers = list(pool.map(lambda _: e2e.cancel(placed.order_id, reason="chaos double cancel"), range(2)))
        placed.note = f"two concurrent cancels -> {[code for code, _ in answers]}"
    else:
        code, _ = e2e.cancel(placed.order_id, reason="chaos cancel")
        placed.note = f"cancel -> {code}"
    return placed


def drive_sqs_replay() -> Placed:
    """E4: the same orderId message sent to the orders queue 3 more times, one of them after the saga finished."""
    placed = drive_simple("sqs_replay", [("WIRELESS-MOUSE", 1)], "none")
    if not placed.order_id:
        return placed
    message = json.dumps({"orderId": placed.order_id})
    for _ in range(2):
        sqs.send_message(QueueUrl=OUT["queue_url"], MessageBody=message)
    e2e.wait_for_terminal(placed.order_id, timeout=120)
    sqs.send_message(QueueUrl=OUT["queue_url"], MessageBody=message)
    placed.note = "3 duplicate SQS messages (2 racing, 1 after the end)"
    return placed


def mixed_scenarios(n: int) -> list:
    """A repeatable mix of the saga's paths: happy, declined, flaky, out of stock, partial, cancel after payment."""
    base = [
        lambda: drive_simple("none", [("WIRELESS-MOUSE", 1)], "none"),
        lambda: drive_simple("none_multi", [("USBC-HUB", 1), ("DESK-MAT", 2)], "none"),
        lambda: drive_simple("payment_declined", [("LAPTOP-STAND", 1)], "payment_declined"),
        lambda: drive_simple("payment_flaky", [("LOWPRO-KEYBOARD", 1)], "payment_flaky"),
        lambda: drive_simple("out_of_stock", [("WEBCAM-1080P", 1)], "out_of_stock"),
        lambda: drive_simple("partial", [("WIRELESS-MOUSE", 1), ("ERGO-MOUSE", 1), ("DESK-MAT", 1)], "item_unavailable", simulate_line=2),
        lambda: drive_simple("none", [("MECH-KEYBOARD", 1)], "none"),
        lambda: drive_cancel_after_payment(),
        lambda: drive_simple("webhook_duplicate", [("ERGO-MOUSE", 1)], "webhook_duplicate"),
        lambda: drive_simple("none", [("WIRELESS-EARBUDS", 1)], "none"),
    ]
    return [base[i % len(base)] for i in range(n)]


def e3_scenarios() -> list:
    """One order per crash point, on a path that reaches that write; then the same mix with the switch on."""
    crash = "crash_after:"
    return [
        lambda: drive_simple(f"{crash}reserve", [("WIRELESS-MOUSE", 1)], "none", f"{crash}reserve"),
        lambda: drive_simple(f"{crash}debit", [("MECH-KEYBOARD", 1)], "none", f"{crash}debit"),
        lambda: drive_simple(f"{crash}webhook_capture", [("USBC-HUB", 1)], "none", f"{crash}webhook_capture"),
        lambda: drive_simple(f"{crash}fulfill", [("LAPTOP-STAND", 1)], "none", f"{crash}fulfill"),
        lambda: drive_simple(f"{crash}line_refund", [("WIRELESS-MOUSE", 1), ("ERGO-MOUSE", 1)], "item_unavailable", f"{crash}line_refund", 2),
        lambda: drive_simple(f"{crash}write_off", [("DESK-MAT", 1), ("LOWPRO-KEYBOARD", 1)], "item_unavailable", f"{crash}write_off", 2),
        lambda: drive_simple(f"{crash}release", [("WIRELESS-EARBUDS", 1)], "payment_declined", f"{crash}release"),
        lambda: drive_cancel_after_payment(f"{crash}full_refund", f"{crash}full_refund"),
        # the crash points again, so each fires on more than one order
        lambda: drive_simple(f"{crash}reserve", [("DESK-MAT", 2)], "none", f"{crash}reserve"),
        lambda: drive_simple(f"{crash}debit", [("ERGO-MOUSE", 1)], "payment_flaky", f"{crash}debit"),
        lambda: drive_simple(f"{crash}fulfill", [("USBC-HUB", 1), ("DESK-MAT", 1)], "none", f"{crash}fulfill"),
        lambda: drive_simple(f"{crash}release", [("LAPTOP-STAND", 1)], "payment_declined", f"{crash}release"),
    ]


def e4_scenarios(n: int) -> list:
    base = [
        drive_sqs_replay,
        lambda: drive_simple("webhook_duplicate", [("ERGO-MOUSE", 1)], "webhook_duplicate"),
        lambda: drive_cancel_after_payment("double_cancel", twice=True),
    ]
    return [base[i % len(base)] for i in range(n)]


def e5_scenarios() -> list:
    """Three orders that each need refund-payment: a damaged line, a cancel after payment, a decline after a hold."""
    def decline_after_hold() -> Placed:
        code, hold = e2e.post_hold([("LAPTOP-STAND", 1)])
        hold_id = hold.get("holdId") if code in (200, 201) else None
        placed = Placed("decline_after_hold")
        placed.http, body = post_order([("LAPTOP-STAND", 1)], "payment_declined", hold_id=hold_id)
        placed.order_id = body.get("orderId")
        placed.note = f"hold {hold_id}"
        return placed

    return [
        lambda: drive_simple("partial", [("WIRELESS-MOUSE", 1), ("ERGO-MOUSE", 1), ("DESK-MAT", 1)], "item_unavailable", simulate_line=2),
        lambda: drive_cancel_after_payment(),
        decline_after_hold,
    ]


# --------------------------------------------------------------------------------------------
# Background auditor: invoke order-saga-invariant-auditor every minute
# --------------------------------------------------------------------------------------------
class AuditLoop(threading.Thread):
    def __init__(self, every: int = 60):
        super().__init__(daemon=True)
        self.every = every
        self.results: list[dict] = []
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.results.append(invoke_auditor())
            self.stop_event.wait(self.every)

    def stop(self) -> None:
        self.stop_event.set()


def invoke_auditor() -> dict:
    resp = lambda_client.invoke(FunctionName=OUT["invariant_auditor_function_name"], Payload=b'{"source":"chaos_run"}')
    payload = json.loads(resp["Payload"].read() or b"{}")
    if resp.get("FunctionError"):
        return {"at": now_iso(), "error": str(payload)[:300]}
    return {
        "at": now_iso(), "violations": payload.get("violations"), "stuck": payload.get("stuck"),
        "parked": payload.get("parked"), "orders": payload.get("orders"),
        "violationList": payload.get("violationList", [])[:10], "stuckList": payload.get("stuckList", [])[:10],
    }


# --------------------------------------------------------------------------------------------
# Fault injection (our stand-in for AWS FIS; see the module docstring)
# --------------------------------------------------------------------------------------------
def alarm_state(name: str) -> str:
    alarms = cloudwatch.describe_alarms(AlarmNames=[name])["MetricAlarms"]
    return alarms[0]["StateValue"] if alarms else "MISSING"


class Fault(threading.Thread):
    """Writes the fault configuration; removes it at its expiry, or as soon as the stop-condition alarm fires."""

    def __init__(self, experiment: str, run_id: str):
        super().__init__(daemon=True)
        spec = FAULTS[experiment]
        assert spec["minutes"] <= 15, "the Lambdas ignore a fault configuration longer than 15 minutes"
        self.bucket = OUT["chaos_fault_bucket"]
        starts = datetime.now(timezone.utc)
        self.expires = starts + timedelta(minutes=spec["minutes"])
        self.config = {
            "run": run_id, "functions": spec["functions"], "action": spec["action"], "percent": spec["percent"],
            "delayMs": spec["delayMs"], "startsAt": starts.isoformat(timespec="seconds"),
            "expiresAt": self.expires.isoformat(timespec="seconds"),
        }
        self.record = {"run": run_id, "config": self.config, "status": "running", "reason": "", "stopAlarmChecks": 0}
        self.done = threading.Event()

    def begin(self) -> None:
        if alarm_state(STOP_ALARM) == "ALARM":
            raise SystemExit(f"{STOP_ALARM} is already in ALARM: fix that first")
        s3.put_object(Bucket=self.bucket, Key=FAULT_KEY, Body=json.dumps(self.config).encode(), ContentType="application/json")
        self.record["startedAt"] = now_iso()
        print(f"Fault {self.config['action']} {self.config['percent']}% on {self.config['functions']} "
              f"until {self.config['expiresAt']} (run {self.config['run']})")
        self.start()
        print("  waiting 35 s for warm containers to re-read it (30 s cache)")
        time.sleep(35)

    def run(self) -> None:
        while datetime.now(timezone.utc) < self.expires and not self.done.is_set():
            self.record["stopAlarmChecks"] += 1
            if alarm_state(STOP_ALARM) == "ALARM":
                self.finish("stopped", f"stop condition: {STOP_ALARM} in ALARM")
                return
            self.done.wait(15)
        self.finish("completed", "expired")

    def finish(self, status: str, reason: str) -> None:
        if self.record["status"] != "running":
            return
        s3.delete_object(Bucket=self.bucket, Key=FAULT_KEY)
        self.record.update(status=status, reason=reason, endedAt=now_iso())
        self.done.set()
        print(f"Fault configuration removed: {status} ({reason})")

    def wait(self) -> dict:
        self.done.wait()
        return self.record


# --------------------------------------------------------------------------------------------
# Per-order checks
# --------------------------------------------------------------------------------------------
def execution_arn(order_id: str) -> str:
    return f"{OUT['state_machine_arn'].replace(':stateMachine:', ':execution:')}:{order_id}"


def retry_counts(order_id: str) -> dict[str, int]:
    """Extra Lambda attempts per state (TaskScheduled events beyond the first, per state entry)."""
    extra: Counter = Counter()
    state, scheduled = None, 0
    try:
        for page in sfn.get_paginator("get_execution_history").paginate(executionArn=execution_arn(order_id)):
            for event in page["events"]:
                if "stateEnteredEventDetails" in event:
                    state, scheduled = event["stateEnteredEventDetails"]["name"], 0
                elif event["type"] in ("TaskScheduled", "LambdaFunctionScheduled"):
                    scheduled += 1
                    if scheduled > 1:
                        extra[state] += 1
    except sfn.exceptions.ExecutionDoesNotExist:
        pass
    return dict(extra)


def check(placed: Placed) -> Placed:
    if not placed.order_id:
        return placed
    order = e2e.orders_table.get_item(Key={"orderId": placed.order_id}, ConsistentRead=True).get("Item", {})
    placed.status = order.get("status", "?")
    try:
        placed.execution = sfn.describe_execution(executionArn=execution_arn(placed.order_id))["status"]
    except sfn.exceptions.ExecutionDoesNotExist:
        placed.execution = "-"
    placed.executions = e2e.executions_named({placed.order_id})
    entries = e2e.ledger_for(placed.order_id, e2e.USER)
    debits = [e["amount"] for e in entries if e["type"] == "DEBIT"]
    credits = [e for e in entries if e["type"] == "CREDIT"]
    placed.debits = len(debits)
    placed.credit_keys = [c.get("lineId", "*") for c in credits]
    net = sum(debits, Decimal("0")) - sum((c["amount"] for c in credits), Decimal("0"))
    placed.net = str(net)
    placed.retries = retry_counts(placed.order_id)

    if placed.status not in TERMINAL:
        placed.problems.append(f"not terminal: {placed.status} (execution {placed.execution})")
        return placed
    expected = e2e.fulfilled_amount(order)
    placed.expected_net = str(expected)
    if net != expected:
        placed.problems.append(f"net ₹{net} != fulfilled ₹{expected}")
    if placed.debits > 1:
        placed.problems.append(f"{placed.debits} DEBITs")
    if len(placed.credit_keys) != len(set(placed.credit_keys)):
        placed.problems.append(f"duplicate CREDITs {placed.credit_keys}")
    if placed.executions > 1:
        placed.problems.append(f"{placed.executions} executions")
    history = e2e.statuses(order)
    if history.count("PAYMENT_CAPTURED") > 1:
        placed.problems.append("PAYMENT_CAPTURED twice")
    return placed


def wait_all_terminal(placed: list[Placed], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    pending = [p for p in placed if p.order_id]
    while pending and time.monotonic() < deadline:
        pending = [p for p in pending if e2e.get_order(p.order_id).get("status") not in TERMINAL]
        if pending:
            print(f"  {len(pending)} orders not terminal yet")
            time.sleep(15)


def alarm_history(name: str, since: datetime) -> list[str]:
    items = cloudwatch.describe_alarm_history(AlarmName=f"{OUT.get('project_prefix', 'order-saga')}-{name}",
                                              HistoryItemType="StateUpdate", StartDate=since)["AlarmHistoryItems"]
    return [f"{i['Timestamp']:%H:%M:%S} {i['HistorySummary']}" for i in sorted(items, key=lambda i: i["Timestamp"])]


# --------------------------------------------------------------------------------------------
# Running an experiment
# --------------------------------------------------------------------------------------------
def place_all(drivers: list, spread_seconds: float, workers: int = 6) -> list[Placed]:
    """Run the drivers over `spread_seconds`, a few at a time (cancel drivers wait for their window)."""
    gap = spread_seconds / max(len(drivers), 1)
    futures = []
    with ThreadPoolExecutor(workers) as pool:
        for driver in drivers:
            futures.append(pool.submit(driver))
            time.sleep(gap)
        return [f.result() for f in futures]


def run_e2e() -> dict:
    print("Running the full e2e suite (scripts/e2e_test.py)...")
    started = time.monotonic()
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "e2e_test.py")], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = "\n".join(proc.stdout.strip().splitlines()[-6:])
    print(tail)
    return {"exit": proc.returncode, "seconds": round(time.monotonic() - started), "tail": tail}


def run(experiment: str, orders: int, seed: bool, e2e_after: bool) -> int:
    started = datetime.now(timezone.utc)
    if seed:
        print("Re-seeding the demo catalogue (RACE-* products untouched)...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_inventory.py")], check=True, capture_output=True)
    e2e.set_wallet(e2e.USER)
    chaos_flag = lambda_client.get_function_configuration(
        FunctionName=OUT["cancellation_function_names"]["payment_provider"])["Environment"]["Variables"].get("CHAOS_ENABLED")
    print(f"CHAOS_ENABLED on the Lambdas: {chaos_flag}")
    if experiment != "E4" and chaos_flag != "true":
        raise SystemExit(f"{experiment} needs CHAOS_ENABLED=true: terraform apply -var chaos_enabled=true (and back to false after)")
    global RUN_ID
    RUN_ID = f"{experiment}-{uuid.uuid4().hex[:8]}" if experiment in FAULTS else None

    baseline = invoke_auditor()
    print(f"Auditor before: {baseline.get('violations')} violations, {baseline.get('stuck')} stuck")
    auditor = AuditLoop()
    auditor.start()
    fault_record: dict = {}

    fault = None
    if experiment in FAULTS:
        fault = Fault(experiment, RUN_ID)
        fault.begin()

    try:
        if experiment in ("E1", "E2"):
            placed = place_all(mixed_scenarios(orders), spread_seconds=420)  # inside the 10 min fault window
        elif experiment == "E3":
            drivers = e3_scenarios()
            drivers += mixed_scenarios(max(orders - len(drivers), 0))
            placed = place_all(drivers, spread_seconds=180)
        elif experiment == "E4":
            placed = place_all(e4_scenarios(orders), spread_seconds=180)
        else:  # E5
            placed = place_all(e5_scenarios(), spread_seconds=10, workers=3)
    except BaseException:
        if fault:  # don't leave a fault behind (it would expire by itself within 15 min anyway)
            fault.finish("aborted", "the harness failed while placing orders")
        raise

    if fault:
        print("Waiting for the fault window to end...")
        fault_record = fault.wait()

    print("Waiting for every order to reach a terminal status...")
    wait_all_terminal(placed, timeout=900 if experiment != "E5" else 300)
    time.sleep(30)  # let the last writes settle before the final audit
    placed = [check(p) for p in placed]
    auditor.stop()
    final = invoke_auditor()
    record = {
        "experiment": experiment, "runId": RUN_ID, "startedAt": started.isoformat(timespec="seconds"), "endedAt": now_iso(),
        "fault": fault_record, "auditorBefore": baseline, "auditorFinal": final, "auditorRuns": auditor.results,
        "orders": [asdict(p) for p in placed],
        "alarms": {name: alarm_history(name, started) for name in ("invariant-violation", "stuck-orders", "refund-or-write-off-errors")},
    }

    if experiment == "E5":
        parked = [p.order_id for p in placed if p.order_id and p.execution == "FAILED"]
        STATE_FILE.write_text(json.dumps({"orders": record["orders"], "startedAt": record["startedAt"], "parked": parked,
                                          "fault": fault_record}, indent=2, default=str), encoding="utf-8")
        print(f"Parked (execution FAILED): {parked}. Saved {STATE_FILE}.")
        print("Wait ~30 min for the auditor to flag them STUCK (hourly schedule or --audit-now), then run --redrive.")
    elif e2e_after:
        record["e2e"] = run_e2e()

    return write_evidence(record)


def redrive() -> int:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    before = invoke_auditor()
    print(f"Auditor before the redrive: {before.get('violations')} violations, {before.get('stuck')} stuck")
    for item in before.get("stuckList", []):
        print(f"  STUCK {item.get('subject')}: {item.get('detail')}")
    redriven = []
    for order_id in state["parked"]:
        arn = execution_arn(order_id)
        print(f"aws stepfunctions redrive-execution --execution-arn {arn}")
        sfn.redrive_execution(executionArn=arn, clientToken=f"redrive-{order_id}"[:64])
        redriven.append(order_id)
    placed = [Placed(o["kind"], order_id=o["order_id"]) for o in state["orders"]]
    wait_all_terminal(placed, timeout=300)
    time.sleep(30)
    placed = [check(p) for p in placed]
    after = invoke_auditor()
    record = {
        "experiment": "E5-redrive", "startedAt": state["startedAt"], "endedAt": now_iso(), "fault": state.get("fault", {}),
        "redriven": redriven, "auditorBefore": before, "auditorFinal": after, "auditorRuns": [],
        "orders": [asdict(p) for p in placed],
        "alarms": {name: alarm_history(name, datetime.fromisoformat(state["startedAt"]))
                   for name in ("invariant-violation", "stuck-orders", "refund-or-write-off-errors")},
    }
    return write_evidence(record)


def write_evidence(record: dict) -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    name = record["experiment"].lower()
    (EVIDENCE_DIR / f"{name}.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    orders = record["orders"]
    problems = [o for o in orders if o["problems"]]
    lost = sum(abs(Decimal(o["net"]) - Decimal(o["expected_net"])) for o in orders if o["status"] in TERMINAL)
    retries = Counter()
    for o in orders:
        retries.update(o["retries"])
    final = record["auditorFinal"]
    runs = record["auditorRuns"]
    max_violations = max([r.get("violations") or 0 for r in runs] + [final.get("violations") or 0])
    lines = [
        f"# Step 3.2 chaos: {record['experiment']}",
        "",
        f"Run {record['startedAt']} to {record['endedAt']} (UTC). Generated by `scripts/chaos_run.py`.",
        "",
        f"- Fault window (injector, run {record['fault'].get('run', '-')}): {record['fault'].get('status', '-')} "
        f"({record['fault'].get('reason', '')}) · {json.dumps(record['fault'].get('config', {}))}",
        f"- Orders: {len(orders)} · statuses {dict(Counter(o['status'] for o in orders))}",
        f"- Executions: {dict(Counter(o['execution'] for o in orders))}",
        f"- Orders with a problem: {len(problems)}",
        f"- ₹ lost (sum of |net charge - fulfilled| over terminal orders): ₹{lost}",
        f"- Auditor: {len(runs)} runs during the experiment, max violations {max_violations}; final "
        f"{final.get('violations')} violations / {final.get('stuck')} stuck",
        f"- SFN extra Lambda attempts (retries) by state: {dict(retries) or 'none'}",
    ]
    if record.get("redriven"):
        lines.append(f"- Redriven executions: {', '.join(record['redriven'])}")
    if record.get("e2e"):
        lines.append(f"- e2e suite after: exit {record['e2e']['exit']} in {record['e2e']['seconds']} s")
    lines += ["", "## Alarms (state changes since the start)", ""]
    for name, history in record["alarms"].items():
        lines.append(f"- order-saga-{name}: " + ("; ".join(history) if history else "no change"))
    lines += ["", "## Orders", "", "| Scenario | orderId | HTTP | Status | Execution | DEBITs | CREDITs | Net ₹ | Expected ₹ | Retries | Note / problems |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for o in orders:
        notes = "; ".join(o["problems"]) or o["note"]
        lines.append(f"| {o['kind']} | {o['order_id']} | {o['http']} | {o['status']} | {o['execution']} | {o['debits']} | "
                     f"{','.join(o['credit_keys']) or '-'} | {o['net']} | {o['expected_net']} | {o['retries'] or '-'} | {notes} |")
    if final.get("violationList"):
        lines += ["", "## Auditor violations (final run)", ""] + [f"- {v}" for v in final["violationList"]]
    if final.get("stuckList"):
        lines += ["", "## Auditor stuck orders (final run)", ""] + [f"- {v}" for v in final["stuckList"]]
    text = "\n".join(lines) + "\n"
    (EVIDENCE_DIR / f"{name}.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    ok = not problems and lost == 0 and max_violations == 0
    print("PASS" if ok else "CHECK: see the problems above")
    return 0 if ok else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment", choices=["E1", "E2", "E3", "E4", "E5"])
    parser.add_argument("--orders", type=int, default=25)
    parser.add_argument("--seed", action="store_true", help="re-seed the demo catalogue first (nothing may be in flight)")
    parser.add_argument("--no-e2e", action="store_true", help="skip the e2e suite after the experiment")
    parser.add_argument("--redrive", action="store_true", help="E5 only: redrive the parked executions")
    args = parser.parse_args()
    random.seed(32)
    if args.redrive:
        return redrive()
    return run(args.experiment, args.orders, args.seed, not args.no_e2e)


if __name__ == "__main__":
    sys.exit(main())
