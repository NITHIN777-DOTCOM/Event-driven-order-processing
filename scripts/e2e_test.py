"""End-to-end tests of every saga path against the LIVE deployment.

    python scripts/seed_inventory.py   # reset stock first
    python scripts/e2e_test.py

Scenarios (each uses its own product, so stock assertions can't interfere with each other):
  a) none              -> COMPLETED, stock decreased
  b) payment_declined  -> FAILED, stock restored, ReleaseInventory ran, execution FAILED at OrderFailed
  c) payment_flaky     -> COMPLETED after retries: paymentAttempts == 3, 2 x PAYMENT_RETRY
  d) out_of_stock      -> FAILED, stock unchanged, ReleaseInventory did NOT run
  e) same Idempotency-Key x3 -> exactly 1 order and 1 execution
  f) the same {orderId} sent to SQS twice more -> still exactly 1 execution
  g) poison            -> message lands in the DLQ (polled for up to 5 min), order stays PENDING
  h) low wallet balance -> a REAL decline (no simulate flag): no debit, stock released, order FAILED

DemoPay: the shared test wallet is reset to ₹10,00,000 first, and each scenario checks the ledger
(exactly one DEBIT for each paid order, none for failed ones).

The poison order is placed FIRST, so its ~3 minutes of SQS retries overlap the other scenarios.
The DLQ is only peeked (VisibilityTimeout=0) and is never purged, so it stays for screenshots.
Results are printed and written to docs/evidence/phase2-failure-tests.md. Exit code 1 if anything fails.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import boto3

from tf_outputs import load_outputs

OUT = load_outputs()
REGION = OUT["region"]
API = OUT["api_url"].rstrip("/")
EVIDENCE_FILE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "e2e-failure-tests.md"
DLQ_TIMEOUT_SECONDS = 300
WALLET_EMAIL = "e2e.tester@example.com"
LOW_BALANCE_EMAIL = "e2e.lowbalance@example.com"

ddb = boto3.resource("dynamodb", region_name=REGION)
orders_table = ddb.Table(OUT["orders_table"])
inventory_table = ddb.Table(OUT["inventory_table"])
sfn = boto3.client("stepfunctions", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)


# --------------------------------------------------------------------------------------------
# Result bookkeeping
# --------------------------------------------------------------------------------------------
@dataclass
class Scenario:
    key: str
    title: str
    order_id: str | None = None
    checks: list[tuple[bool, str]] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)

    def check(self, passed: bool, description: str) -> bool:
        self.checks.append((bool(passed), description))
        return bool(passed)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(ok for ok, _ in self.checks)

    @property
    def execution_arn(self) -> str | None:
        if not self.order_id:
            return None
        return f"{OUT['state_machine_arn'].replace(':stateMachine:', ':execution:')}:{self.order_id}"

    @property
    def console_link(self) -> str:
        return (
            f"https://{REGION}.console.aws.amazon.com/states/home?region={REGION}"
            f"#/v2/executions/details/{self.execution_arn}"
        )


# --------------------------------------------------------------------------------------------
# API / AWS helpers
# --------------------------------------------------------------------------------------------
def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def place_order(
    product_id: str, quantity: int, simulate: str, key: str | None = None, email: str = WALLET_EMAIL
) -> tuple[int, dict]:
    payload = {
        "customerName": "E2E Tester",
        "customerEmail": email,
        "items": [{"productId": product_id, "quantity": quantity}],
        "simulate": simulate,
    }
    return http_json("POST", f"{API}/orders", payload, {"Idempotency-Key": key or str(uuid.uuid4())})


def wallet(email: str = WALLET_EMAIL) -> dict:
    return http_json("GET", f"{API}/wallet?email={email}")[1]


def set_wallet(email: str, balance: float | None = None) -> dict:
    body = {"email": email} if balance is None else {"email": email, "balance": balance}
    return http_json("POST", f"{API}/wallet/reset", body)[1]


def debits_for(order_id: str, email: str = WALLET_EMAIL) -> int:
    return sum(1 for t in wallet(email)["transactions"] if t.get("orderId") == order_id and t["type"] == "DEBIT")


def get_order(order_id: str) -> dict:
    return http_json("GET", f"{API}/orders/{order_id}")[1]


def wait_for_terminal(order_id: str, timeout: int = 90) -> dict:
    deadline = time.monotonic() + timeout
    order: dict = {}
    while time.monotonic() < deadline:
        order = get_order(order_id)
        if order.get("status") in ("COMPLETED", "FAILED"):
            return order
        time.sleep(2)
    return order


def stock_of(product_id: str) -> tuple[int, int]:
    item = inventory_table.get_item(Key={"productId": product_id}, ConsistentRead=True)["Item"]
    return int(item["stock"]), int(item["reserved"])


def execution(scenario: Scenario) -> dict:
    return sfn.describe_execution(executionArn=scenario.execution_arn)


def states_entered(scenario: Scenario) -> list[str]:
    names = []
    for page in sfn.get_paginator("get_execution_history").paginate(executionArn=scenario.execution_arn):
        names += [e["stateEnteredEventDetails"]["name"] for e in page["events"] if "stateEnteredEventDetails" in e]
    return names


def executions_named(names: set[str]) -> int:
    count = 0
    for page in sfn.get_paginator("list_executions").paginate(stateMachineArn=OUT["state_machine_arn"]):
        count += sum(1 for e in page["executions"] if e["name"] in names)
    return count


def statuses(order: dict) -> list[str]:
    return [entry["status"] for entry in order.get("statusHistory", [])]


def count_log_lines(log_group: str, *terms: str, since_ms: int) -> int:
    pattern = " ".join(f'"{term}"' for term in terms)
    total = 0
    for page in logs.get_paginator("filter_log_events").paginate(
        logGroupName=log_group, filterPattern=pattern, startTime=since_ms
    ):
        total += len(page["events"])
    return total


# --------------------------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------------------------
def scenario_none() -> Scenario:
    s = Scenario("a", "simulate=none -> COMPLETED, stock decreased, wallet debited once")
    before = stock_of("MECH-KEYBOARD")
    balance_before = wallet()["balance"]
    code, body = place_order("MECH-KEYBOARD", 1, "none")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    expected = ["PENDING", "PROCESSING", "RESERVED", "PAYMENT_CAPTURED", "COMPLETED"]
    s.check(statuses(order) == expected, f"statusHistory {' -> '.join(statuses(order))}")
    after = stock_of("MECH-KEYBOARD")
    s.check(after == (before[0] - 1, before[1] + 1), f"MECH-KEYBOARD stock {before[0]} -> {after[0]} (expected -1)")
    s.check(execution(s)["status"] == "SUCCEEDED", f"execution {execution(s)['status']} (expected SUCCEEDED)")
    balance_after = wallet()["balance"]
    s.check(
        balance_before - balance_after == order.get("totalAmount"),
        f"DemoPay balance {balance_before} -> {balance_after} (expected -{order.get('totalAmount')})",
    )
    s.check(debits_for(s.order_id) == 1, f"DEBIT ledger entries for this order: {debits_for(s.order_id)} (expected 1)")
    return s


def scenario_payment_declined() -> Scenario:
    s = Scenario("b", "payment_declined -> FAILED, stock restored by compensation")
    before = stock_of("USBC-HUB")
    code, body = place_order("USBC-HUB", 2, "payment_declined")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "FAILED", f"order status {order.get('status')} (expected FAILED)")
    s.check(
        str(order.get("failureReason", "")).startswith("PaymentDeclined"),
        f"failureReason '{order.get('failureReason')}'",
    )
    s.check("INVENTORY_RELEASED" in statuses(order), f"statusHistory {' -> '.join(statuses(order))}")
    after = stock_of("USBC-HUB")
    s.check(after == before, f"USBC-HUB (stock, reserved) {before} -> {after} (expected unchanged after release)")
    info, entered = execution(s), states_entered(s)
    s.check(info["status"] == "FAILED", f"execution {info['status']} (expected FAILED)")
    s.check(info.get("error") == "OrderFailed", f"execution error '{info.get('error')}' (expected OrderFailed)")
    s.check("ReleaseInventory" in entered, "ReleaseInventory ran")
    s.check(entered[-1:] == ["OrderFailed"], f"last state {entered[-1:]} (expected OrderFailed)")
    s.check("RefundPayment" in entered, "RefundPayment ran (a no-op: nothing was charged)")
    s.check(debits_for(s.order_id) == 0, f"DEBIT ledger entries: {debits_for(s.order_id)} (expected 0, card declined before debit)")
    return s


def scenario_payment_flaky() -> Scenario:
    s = Scenario("c", "payment_flaky -> retried twice, then COMPLETED")
    before = stock_of("ANC-HEADPHONES")
    code, body = place_order("ANC-HEADPHONES", 1, "payment_flaky")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    s.check(order.get("paymentAttempts") == 3, f"paymentAttempts {order.get('paymentAttempts')} (expected 3)")
    retries = statuses(order).count("PAYMENT_RETRY")
    s.check(retries == 2, f"{retries} PAYMENT_RETRY entries (expected 2)")
    after = stock_of("ANC-HEADPHONES")
    s.check(after[0] == before[0] - 1, f"ANC-HEADPHONES stock {before[0]} -> {after[0]} (expected -1)")
    s.check(execution(s)["status"] == "SUCCEEDED", f"execution {execution(s)['status']} (expected SUCCEEDED)")
    s.check(debits_for(s.order_id) == 1, f"DEBIT ledger entries after 3 attempts: {debits_for(s.order_id)} (expected 1)")
    return s


def scenario_out_of_stock() -> Scenario:
    s = Scenario("d", "out_of_stock -> FAILED, nothing reserved, no compensation needed")
    before = stock_of("4K-MONITOR")
    code, body = place_order("4K-MONITOR", 1, "out_of_stock")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "FAILED", f"order status {order.get('status')} (expected FAILED)")
    s.check(
        str(order.get("failureReason", "")).startswith("OutOfStock"), f"failureReason '{order.get('failureReason')}'"
    )
    after = stock_of("4K-MONITOR")
    s.check(after == before, f"4K-MONITOR (stock, reserved) {before} -> {after} (expected unchanged)")
    info, entered = execution(s), states_entered(s)
    s.check(info["status"] == "FAILED", f"execution {info['status']} (expected FAILED)")
    s.check("ReleaseInventory" not in entered, f"ReleaseInventory NOT run (states: {' -> '.join(entered)})")
    s.check(debits_for(s.order_id) == 0, f"DEBIT ledger entries: {debits_for(s.order_id)} (expected 0)")
    return s


def scenario_duplicate_idempotency_key() -> Scenario:
    s = Scenario("e", "same Idempotency-Key sent 3x -> exactly 1 order, 1 execution")
    key = f"e2e-dup-{uuid.uuid4().hex[:8]}"
    before = stock_of("4K-MONITOR")
    responses = [place_order("4K-MONITOR", 1, "none", key) for _ in range(3)]
    codes = [code for code, _ in responses]
    ids = {body.get("orderId") for _, body in responses}
    s.order_id = responses[0][1].get("orderId")
    s.check(codes == [202, 200, 200], f"HTTP codes {codes} (expected [202, 200, 200])")
    s.check(len(ids) == 1, f"distinct orderIds returned: {len(ids)} (expected 1)")
    s.check([b.get("duplicate") for _, b in responses] == [False, True, True], "duplicate flags [False, True, True]")

    scan_kwargs = {"FilterExpression": "idempotencyKey = :k", "ExpressionAttributeValues": {":k": key}}
    matches = 0
    while True:
        page = orders_table.scan(**scan_kwargs)
        matches += page["Count"]
        if "LastEvaluatedKey" not in page:
            break
        scan_kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    s.check(matches == 1, f"orders with this key in DynamoDB: {matches} (expected 1)")

    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    s.check(executions_named(ids) == 1, f"executions: {executions_named(ids)} (expected 1)")
    after = stock_of("4K-MONITOR")
    s.check(after[0] == before[0] - 1, f"4K-MONITOR stock {before[0]} -> {after[0]} (expected -1, not -3)")
    s.check(debits_for(s.order_id) == 1, f"DEBIT ledger entries: {debits_for(s.order_id)} (expected 1, not 3)")
    return s


def scenario_duplicate_sqs_message() -> Scenario:
    s = Scenario("f", "same {orderId} delivered 3x via SQS -> exactly 1 execution")
    since_ms = int(time.time() * 1000)
    code, body = place_order("WIRELESS-MOUSE", 1, "none")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    message = json.dumps({"orderId": s.order_id})

    # Duplicate #1 races the original message; duplicate #2 arrives after the saga has finished.
    sqs.send_message(QueueUrl=OUT["queue_url"], MessageBody=message)
    order = wait_for_terminal(s.order_id)
    sqs.send_message(QueueUrl=OUT["queue_url"], MessageBody=message)
    time.sleep(15)  # let start_workflow consume the late duplicate

    order = get_order(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    s.check(executions_named({s.order_id}) == 1, f"executions: {executions_named({s.order_id})} (expected 1)")
    processing = statuses(order).count("PROCESSING")
    s.check(processing == 1, f"PROCESSING entries in statusHistory: {processing} (expected 1)")

    ignored = 0
    for _ in range(12):  # CloudWatch Logs ingestion can lag a few seconds
        ignored = count_log_lines(
            "/aws/lambda/order-saga-start-workflow", "Duplicate message ignored", s.order_id, since_ms=since_ms
        )
        if ignored >= 1:
            break
        time.sleep(5)
    s.check(ignored >= 1, f"'Duplicate message ignored' log lines for this order: {ignored} (expected >= 1)")
    s.check(debits_for(s.order_id) == 1, f"DEBIT ledger entries: {debits_for(s.order_id)} (expected 1)")
    return s


def scenario_low_balance() -> Scenario:
    s = Scenario("h", "wallet balance too low -> REAL decline, stock released, nothing debited")
    set_wallet(LOW_BALANCE_EMAIL, 1000)
    before = stock_of("USB-MIC")
    code, body = place_order("USB-MIC", 1, "none", email=LOW_BALANCE_EMAIL)  # ₹5,999 > ₹1,000, no simulate flag
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "FAILED", f"order status {order.get('status')} (expected FAILED)")
    reason = str(order.get("failureReason", ""))
    s.check(reason.startswith("PaymentDeclined: Insufficient wallet balance"), f"failureReason '{reason}'")
    s.check(stock_of("USB-MIC") == before, f"USB-MIC (stock, reserved) {before} -> {stock_of('USB-MIC')} (expected unchanged)")
    after = wallet(LOW_BALANCE_EMAIL)
    s.check(after["balance"] == 1000, f"DemoPay balance {after['balance']} (expected 1000, untouched)")
    s.check(debits_for(s.order_id, LOW_BALANCE_EMAIL) == 0, "no DEBIT ledger entry")
    s.check("ReleaseInventory" in states_entered(s), "ReleaseInventory ran (compensation)")
    set_wallet(LOW_BALANCE_EMAIL)  # leave the demo wallet back at ₹10,00,000
    return s


def start_poison() -> tuple[Scenario, float]:
    s = Scenario("g", "poison message -> DLQ after 3 receives, order stays PENDING")
    code, body = place_order("WIRELESS-MOUSE", 1, "poison")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    return s, time.monotonic()


def finish_poison(s: Scenario, started: float) -> Scenario:
    found_after = None
    while time.monotonic() - started < DLQ_TIMEOUT_SECONDS:
        # Peek only: VisibilityTimeout=0 leaves the message visible in the DLQ for the console demo.
        response = sqs.receive_message(
            QueueUrl=OUT["dlq_url"], MaxNumberOfMessages=10, VisibilityTimeout=0, WaitTimeSeconds=10
        )
        if any(json.loads(m["Body"]).get("orderId") == s.order_id for m in response.get("Messages", [])):
            found_after = time.monotonic() - started
            break
        time.sleep(5)
    s.check(
        found_after is not None,
        f"message found in order-saga-orders-dlq after {found_after:.0f}s" if found_after else "message NOT in DLQ within 5 min",
    )

    order = get_order(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "PENDING", f"order status {order.get('status')} (expected PENDING)")
    s.check(executions_named({s.order_id}) == 0, "no execution was started")
    errors = count_log_lines("/aws/lambda/order-saga-start-workflow", "PoisonMessage", s.order_id, since_ms=0)
    s.check(errors >= 3, f"start_workflow ERROR log lines with this orderId: {errors} (expected >= 3, one per receive)")
    return s


# --------------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------------
def write_evidence(results: list[Scenario], duration: float) -> None:
    passed = sum(r.passed for r in results)
    lines = [
        "# End-to-end tests: every saga path, including DemoPay wallet checks",
        "",
        f"Run: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC · Region: {REGION} · API: `{API}`",
        f"Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: {duration:.0f}s",
        "",
        f"**Result: {passed}/{len(results)} scenarios passed.**",
        "",
        "| # | Scenario | Result | orderId | Execution (console) |",
        "|---|----------|--------|---------|---------------------|",
    ]
    for r in results:
        link = f"[open]({r.console_link})" if r.key != "g" else "none started (by design)"
        lines.append(f"| {r.key} | {r.title} | {'PASS' if r.passed else 'FAIL'} | `{r.order_id}` | {link} |")
    for r in results:
        lines += ["", f"## {r.key}) {r.title} - {'PASS' if r.passed else 'FAIL'}", "", f"orderId: `{r.order_id}`"]
        if r.key != "g":
            lines.append(f"Execution ARN: `{r.execution_arn}`")
        lines += ["", "Checks:"]
        lines += [f"- {'PASS' if ok else 'FAIL'}: {text}" for ok, text in r.checks]
        if r.timeline:
            lines += ["", "statusHistory:", "```"]
            lines += [f"{e['timestamp']}  {e['status']:<19} {e['detail']}" for e in r.timeline]
            lines.append("```")
    EVIDENCE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    started = time.monotonic()
    set_wallet(WALLET_EMAIL)  # DemoPay: start every run from ₹10,00,000
    print("Placing poison order first (it needs ~3 min of SQS retries)...")
    poison, poison_started = start_poison()
    print(f"  poison order {poison.order_id}")

    results = []
    for run in (
        scenario_none,
        scenario_payment_declined,
        scenario_payment_flaky,
        scenario_out_of_stock,
        scenario_duplicate_idempotency_key,
        scenario_duplicate_sqs_message,
        scenario_low_balance,
    ):
        result = run()
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.key}) {result.title}  {result.order_id}")
        for ok, text in result.checks:
            if not ok:
                print(f"      FAIL: {text}")
        results.append(result)

    print("Waiting for the poison message to reach the DLQ (up to 5 min from placement)...")
    results.append(finish_poison(poison, poison_started))
    print(f"[{'PASS' if results[-1].passed else 'FAIL'}] g) {poison.title}  {poison.order_id}")

    results.sort(key=lambda r: r.key)
    duration = time.monotonic() - started
    print("\n" + "=" * 100)
    print(f"{'#':<3}{'Result':<8}{'orderId':<24}Scenario")
    for r in results:
        print(f"{r.key:<3}{'PASS' if r.passed else 'FAIL':<8}{r.order_id or '-':<24}{r.title}")
    print("=" * 100)
    for r in results:
        if r.key != "g":
            print(f"{r.key}) {r.console_link}")
    write_evidence(results, duration)
    print(f"\nEvidence written to {EVIDENCE_FILE}")
    passed = sum(r.passed for r in results)
    print(f"{passed}/{len(results)} scenarios passed in {duration:.0f}s")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
