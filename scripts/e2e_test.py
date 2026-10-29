"""End-to-end tests of every saga path against the LIVE deployment.

    python scripts/seed_inventory.py   # reset stock first
    python scripts/e2e_test.py

Scenarios (each uses its own product, so stock assertions can't interfere with each other):
  a) none              -> COMPLETED, stock decreased
  b) payment_declined  -> FAILED, stock restored, ReleaseInventory ran, execution FAILED at OrderFailed
  c) payment_flaky     -> COMPLETED after retries: paymentAttempts == 3, 2 x PAYMENT_RETRY
  d) out_of_stock      -> FAILED, stock unchanged, ReleaseInventory did NOT run
  e) same Idempotency-Key x3 -> exactly 1 order, 1 stream INSERT and 1 execution
  f) the same {orderId} sent to SQS twice more -> still exactly 1 execution
  g) poison            -> message lands in the orders DLQ (polled for up to 5 min), order stays PENDING,
                          and NOT in the outbox DLQ (the pipe delivered it fine; start_workflow rejected it)
  h) low wallet balance -> a REAL decline (no simulate flag): no debit, stock released, order FAILED
  i) crash simulation  -> an order row written straight into DynamoDB (no API, no SQS send: exactly what a
                          crash right after the DynamoDB write leaves behind) still runs to COMPLETED via
                          the outbox (stream -> pipe -> queue)
  j) MODIFY            -> flipping an existing order's status back to PENDING (a MODIFY event) does NOT
                          re-enter the queue: the pipe only forwards INSERTs
  k) auth gate         -> no token / tampered / forged / ID token -> 401 from API Gateway; an access token
                          (email claims added by the pre-token trigger) -> 200; GET /products works signed out
  l) order isolation   -> A can't read B's order (404, same as a missing one); each list shows only its owner's
  m) wallet isolation  -> A resetting "B's" wallet (B's ids in the body) only changes A's wallet
  n) per-user idempotency -> B reusing A's Idempotency-Key gets B's OWN new order; A's replay still works
  o) payment webhook   -> POST /webhooks/payment (no JWT) rejects unsigned, forged, stale and future-dated requests
                          with 401; a correctly signed callback for an unknown intent is a 404 no-op
  p) payment_timeout   -> DemoPay never calls back: after 120 s the saga marks the intent TIMED_OUT, compensates,
                          and the order FAILS with "payment timeout"; nothing charged
  q) payment_late      -> DemoPay charges ~150 s in, after the timeout: the webhook finds TIMED_OUT and refunds at
                          once (intent REFUNDED, ledger DEBIT + CREDIT, net 0), the order stays FAILED
  r) webhook_duplicate -> the success callback arrives twice: COMPLETED, one DEBIT, the 2nd callback is a no-op
  s) webhook_bad_signature -> a forged callback (wrong secret) is rejected with 401 first, then the genuine one
                          completes the order; the rejection is logged and counted in a CloudWatch metric
  t) checkout hold     -> POST /holds moves stock to `held` and schedules its expiry; a 2nd hold releases the 1st
                          (one per user); over the per-item cap -> 400; out of stock -> 409 naming the product;
                          DELETE releases it (stock back, schedule gone)
  u) hold expiry       -> a 30 s hold (automation client) is expired by its EventBridge Scheduler schedule and the
                          stock comes back; records how many seconds after expiresAt the release happened
  v) last unit race    -> two users hold the last unit at the same moment: exactly one 201, one 409
  w) hold ownership    -> another user can't release (404) or see someone's hold
  x) I5                -> stock conservation for EVERY product at the end of the run: seeded stock =
                          stock + held + reserved, and held = the units in ACTIVE holds

Auth: every API call carries a Cognito access token for test user A (or B), from auth_tokens.py. The API
takes identity only from that token, so no request below sends an email or user id.

DemoPay: test user A's wallet is reset to ₹10,00,000 first. At the end, every order scenario is checked
against the money invariants, using the wallet ledger (order-saga-wallet-txns) and the payment intent
(order-saga-payments):
  I1  COMPLETED -> exactly one DEBIT of the order total, no CREDIT
  I2  FAILED (or never started) -> net charge 0 (no entries, or DEBIT + matching CREDIT)
  I3  never more than one DEBIT or one CREDIT per order (no double charge, no double refund)
  I4  the intent, if any, is in a final state (SUCCEEDED, FAILED, TIMED_OUT, REFUNDED), and the expected one

The poison, payment_timeout and payment_late orders and the 30 s hold are placed FIRST, so their minutes of waiting
(SQS retries, the 120 s payment timeout, the ~150 s late callback) overlap the other scenarios.
The DLQ is only peeked (VisibilityTimeout=0) and is never purged, so it stays for screenshots.
Results are printed and written to docs/evidence/e2e-failure-tests.md. Exit code 1 if anything fails.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
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

from auth_tokens import auth_header, test_user
from seed_inventory import PRODUCTS as SEED_PRODUCTS
from tf_outputs import load_outputs

OUT = load_outputs()
REGION = OUT["region"]
API = OUT["api_url"].rstrip("/")
EVIDENCE_FILE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "e2e-failure-tests.md"
DLQ_TIMEOUT_SECONDS = 300
USER = "a"  # the main test user (see create_test_users.py)
LOW_BALANCE_USER = "b"  # its wallet is set to ₹1,000 for the real-decline scenario

ddb = boto3.resource("dynamodb", region_name=REGION)
orders_table = ddb.Table(OUT["orders_table"])
streams = boto3.client("dynamodbstreams", region_name=REGION)
inventory_table = ddb.Table(OUT["inventory_table"])
sfn = boto3.client("stepfunctions", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
payments_table = ddb.Table(OUT["payments_table"])
wallet_txns_table = ddb.Table(OUT["wallet_txns_table"])
holds_table = ddb.Table(OUT["holds_table"])
scheduler = boto3.client("scheduler", region_name=REGION)
SEEDED_STOCK = {p["productId"]: p["stock"] for p in SEED_PRODUCTS}  # I5 baseline (run seed_inventory.py first)
SHORT_HOLD_SECONDS = 30
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
RUN_STARTED = datetime.now(timezone.utc)
SLOW_TIMEOUT_SECONDS = 300  # payment_timeout / payment_late: 120 s timeout, ~150 s late callback, plus slack


# --------------------------------------------------------------------------------------------
# Result bookkeeping
# --------------------------------------------------------------------------------------------
@dataclass
class Scenario:
    key: str
    title: str
    order_id: str | None = None
    user: str = USER  # whose order (and wallet) this is
    checks: list[tuple[bool, str]] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    money: str = ""  # intent status + ledger summary, filled by check_money
    hold_lag_seconds: float | None = None  # scenario u: how late the expiry schedule fired

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
    product_id: str, quantity: int, simulate: str, key: str | None = None, user: str = USER
) -> tuple[int, dict]:
    payload = {
        "customerName": "E2E Tester",
        "items": [{"productId": product_id, "quantity": quantity}],
        "simulate": simulate,
    }
    headers = {"Idempotency-Key": key or str(uuid.uuid4()), **auth_header(user)}
    return http_json("POST", f"{API}/orders", payload, headers)


def wallet(user: str = USER) -> dict:
    return http_json("GET", f"{API}/wallet", headers=auth_header(user))[1]


def set_wallet(user: str = USER, balance: float | None = None) -> dict:
    body = {} if balance is None else {"balance": balance}
    return http_json("POST", f"{API}/wallet/reset", body, auth_header(user))[1]


def debits_for(order_id: str, user: str = USER) -> int:
    return sum(1 for t in wallet(user)["transactions"] if t.get("orderId") == order_id and t["type"] == "DEBIT")


def get_order(order_id: str, user: str = USER) -> dict:
    return http_json("GET", f"{API}/orders/{order_id}", headers=auth_header(user))[1]


def wait_for_terminal(order_id: str, timeout: int = 90, user: str = USER) -> dict:
    deadline = time.monotonic() + timeout
    order: dict = {}
    while time.monotonic() < deadline:
        order = get_order(order_id, user)
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


EMPTY_READS_TO_STOP = 10


def stream_inserts(order_id: str) -> int:
    """Count INSERT records for this order in the orders table stream (it keeps 24 h of records).

    Reads every shard from TRIM_HORIZON. An OPEN shard can return empty pages before its end (DynamoDB Streams
    pages by time, not by record), so a shard counts as done only after EMPTY_READS_TO_STOP empty pages in a row.
    (With 2, a 4-shard stream gave up early and reported 0 INSERTs for an order that had 1: step 1.2 run.)
    """
    count = 0
    shards = streams.describe_stream(StreamArn=OUT["orders_stream_arn"])["StreamDescription"]["Shards"]
    for shard in shards:
        iterator = streams.get_shard_iterator(
            StreamArn=OUT["orders_stream_arn"], ShardId=shard["ShardId"], ShardIteratorType="TRIM_HORIZON"
        )["ShardIterator"]
        empty_reads = 0
        while iterator and empty_reads < EMPTY_READS_TO_STOP:
            page = streams.get_records(ShardIterator=iterator, Limit=1000)
            records = page["Records"]
            empty_reads = 0 if records else empty_reads + 1
            count += sum(
                1
                for r in records
                if r["eventName"] == "INSERT" and r["dynamodb"]["Keys"]["orderId"]["S"] == order_id
            )
            iterator = page.get("NextShardIterator")
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
    expected = ["PENDING", "PROCESSING", "RESERVED", "PAYMENT_PENDING", "PAYMENT_CAPTURED", "COMPLETED"]
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

    # create_order stores the key scoped to the caller ("<sub>#<key>", step 1.2), so look for that.
    scoped = f"{test_user(USER)['sub']}#{key}"
    scan_kwargs = {"FilterExpression": "idempotencyKey = :k", "ExpressionAttributeValues": {":k": scoped}}
    matches = 0
    while True:
        page = orders_table.scan(**scan_kwargs)
        matches += page["Count"]
        if "LastEvaluatedKey" not in page:
            break
        scan_kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    s.check(matches == 1, f"orders with this (user-scoped) key in DynamoDB: {matches} (expected 1)")

    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    s.check(executions_named(ids) == 1, f"executions: {executions_named(ids)} (expected 1)")
    inserts = stream_inserts(s.order_id)
    s.check(inserts == 1, f"INSERT records for this order in the orders stream: {inserts} (expected 1, not 3)")
    after = stock_of("4K-MONITOR")
    s.check(after[0] == before[0] - 1, f"4K-MONITOR stock {before[0]} -> {after[0]} (expected -1, not -3)")
    s.check(debits_for(s.order_id) == 1, f"DEBIT ledger entries: {debits_for(s.order_id)} (expected 1, not 3)")
    return s


def scenario_duplicate_sqs_message() -> Scenario:
    s = Scenario("f", "same {orderId} delivered 3x via SQS -> exactly 1 execution")
    since_ms = int(time.time() * 1000) - 120_000  # slack for local-clock skew; the orderId is unique anyway
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
    s = Scenario("h", "wallet balance too low -> REAL decline, stock released, nothing debited", user=LOW_BALANCE_USER)
    set_wallet(LOW_BALANCE_USER, 1000)
    before = stock_of("USB-MIC")
    code, body = place_order("USB-MIC", 1, "none", user=LOW_BALANCE_USER)  # ₹5,999 > ₹1,000, no simulate flag
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id, user=LOW_BALANCE_USER)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "FAILED", f"order status {order.get('status')} (expected FAILED)")
    reason = str(order.get("failureReason", ""))
    s.check(reason.startswith("PaymentDeclined: Insufficient wallet balance"), f"failureReason '{reason}'")
    s.check(stock_of("USB-MIC") == before, f"USB-MIC (stock, reserved) {before} -> {stock_of('USB-MIC')} (expected unchanged)")
    after = wallet(LOW_BALANCE_USER)
    s.check(after["balance"] == 1000, f"DemoPay balance {after['balance']} (expected 1000, untouched)")
    s.check(debits_for(s.order_id, LOW_BALANCE_USER) == 0, "no DEBIT ledger entry")
    s.check("ReleaseInventory" in states_entered(s), "ReleaseInventory ran (compensation)")
    set_wallet(LOW_BALANCE_USER)  # leave the demo wallet back at ₹10,00,000
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
    outbox_dlq = int(
        sqs.get_queue_attributes(QueueUrl=OUT["outbox_dlq_url"], AttributeNames=["ApproximateNumberOfMessages"])[
            "Attributes"
        ]["ApproximateNumberOfMessages"]
    )
    s.check(outbox_dlq == 0, f"order-saga-outbox-dlq messages: {outbox_dlq} (expected 0: the pipe delivered it)")
    return s


def scenario_crash_after_db_write() -> Scenario:
    s = Scenario("i", "crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox")
    product = inventory_table.get_item(Key={"productId": "LOWPRO-KEYBOARD"}, ConsistentRead=True)["Item"]
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    s.order_id = f"ORD-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
    # The same shape create_order writes (see build_order), but nothing is ever sent to SQS.
    owner = test_user(USER)
    orders_table.put_item(
        Item={
            "orderId": s.order_id,
            "idempotencyKey": f"{owner['sub']}#e2e-crash-{uuid.uuid4().hex[:8]}",
            "userId": owner["sub"],
            "walletId": owner["sub"],
            "customerName": "E2E Crash Simulation",
            "customerEmail": owner["email"],
            "items": [
                {"productId": "LOWPRO-KEYBOARD", "name": product["name"], "quantity": 1, "unitPrice": product["price"]}
            ],
            "totalAmount": product["price"],
            "currency": "INR",
            "status": "PENDING",
            "statusHistory": [
                {
                    "status": "PENDING",
                    "timestamp": now,
                    "detail": "Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)",
                }
            ],
            "simulate": "none",
            "createdAt": now,
            "updatedAt": now,
            "gsi1pk": f"USER#{owner['sub']}",
            "gsi1sk": f"{now}#{s.order_id}",
        },
        ConditionExpression="attribute_not_exists(orderId)",
    )
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    s.check(executions_named({s.order_id}) == 1, f"executions: {executions_named({s.order_id})} (expected 1)")
    s.check(debits_for(s.order_id) == 1, f"DEBIT ledger entries: {debits_for(s.order_id)} (expected 1)")
    inserts = stream_inserts(s.order_id)
    s.check(inserts == 1, f"INSERT records for this order in the orders stream: {inserts} (expected 1)")
    return s


def scenario_modify_does_not_restart(order_id: str) -> Scenario:
    """Flip a COMPLETED order back to PENDING (a MODIFY that passes the status filter but not the
    eventName filter), check nothing re-enters the queue, then put the status back."""
    s = Scenario("j", "MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution")
    s.order_id = order_id
    # Count this order's start_workflow log lines before and after, instead of using a time window:
    # the local clock can be off from CloudWatch's, which could hide a line and fake a pass.
    time.sleep(10)  # let the original delivery's log lines arrive in CloudWatch first
    baseline = count_log_lines("/aws/lambda/order-saga-start-workflow", order_id, since_ms=0)
    orders_table.update_item(
        Key={"orderId": order_id},
        UpdateExpression="SET #status = :pending, outboxModifyTestAt = :now",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":pending": "PENDING", ":now": datetime.now(timezone.utc).isoformat()},
    )
    time.sleep(45)  # far longer than a pipe delivery takes: if it were forwarded, start_workflow would have run
    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    s.check(order["status"] == "PENDING", f"status {order['status']} (expected PENDING: start_workflow never picked it up)")
    lines = count_log_lines("/aws/lambda/order-saga-start-workflow", order_id, since_ms=0) - baseline
    s.check(lines == 0, f"new start_workflow log lines for this order after the MODIFY: {lines} (expected 0)")
    s.check(executions_named({order_id}) == 1, f"executions: {executions_named({order_id})} (expected 1, unchanged)")
    orders_table.update_item(  # restore the real final status
        Key={"orderId": order_id},
        UpdateExpression="SET #status = :completed",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":completed": "COMPLETED"},
    )
    s.timeline = get_order(order_id).get("statusHistory", [])
    return s


# --------------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------------
def write_evidence(results: list[Scenario], duration: float) -> None:
    passed = sum(r.passed for r in results)
    lines = [
        "# End-to-end tests: every saga path, with DemoPay money invariants (I1-I4)",
        "",
        f"Run: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC · Region: {REGION} · API: `{API}`",
        f"Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: {duration:.0f}s",
        "",
        f"**Result: {passed}/{len(results)} scenarios passed.**",
        "",
        "| # | Scenario | Result | orderId | Intent · ledger (I1-I4) | Execution (console) |",
        "|---|----------|--------|---------|--------------------------|---------------------|",
    ]
    for r in results:
        link = f"[open]({r.console_link})" if r.order_id and r.key != "g" else "none started (by design)"
        lines.append(
            f"| {r.key} | {r.title} | {'PASS' if r.passed else 'FAIL'} | `{r.order_id}` | {r.money or '-'} | {link} |"
        )
    for r in results:
        lines += ["", f"## {r.key}) {r.title} - {'PASS' if r.passed else 'FAIL'}", "", f"orderId: `{r.order_id}`"]
        if r.order_id and r.key != "g":
            lines.append(f"Execution ARN: `{r.execution_arn}`")
        lines += ["", "Checks:"]
        lines += [f"- {'PASS' if ok else 'FAIL'}: {text}" for ok, text in r.checks]
        if r.timeline:
            lines += ["", "statusHistory:", "```"]
            lines += [f"{e['timestamp']}  {e['status']:<19} {e['detail']}" for e in r.timeline]
            lines.append("```")
    EVIDENCE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------------------------
# Step 1.2: authentication and row-level isolation
# --------------------------------------------------------------------------------------------
def tampered(token: str) -> str:
    """Same header and payload, one character of the signature changed."""
    head, payload, signature = token.split(".")
    flipped = ("A" if signature[10] != "A" else "B")
    return f"{head}.{payload}.{signature[:10]}{flipped}{signature[11:]}"


def forged_as(token: str, sub: str) -> str:
    """A's token with the payload's sub swapped for someone else's (signature left as it was)."""
    head, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["sub"] = sub
    new_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{head}.{new_payload}.{signature}"


def token_claims(token: str) -> dict:
    """A JWT's payload, decoded WITHOUT verifying it (only to look at the claims Cognito issued)."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def scenario_auth_gate() -> Scenario:
    s = Scenario("k", "auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public")
    code, body = http_json("GET", f"{API}/products")
    s.check(code == 200 and len(body.get("products", [])) > 0, f"GET /products without a token -> {code} (expected 200)")
    for method, path in (("POST", "/orders"), ("GET", "/orders"), ("GET", "/orders/ORD-20261028-00000000"),
                         ("GET", "/wallet"), ("POST", "/wallet/reset")):
        code, _ = http_json(method, f"{API}{path}", {} if method == "POST" else None)
        s.check(code == 401, f"{method} {path} without a token -> {code} (expected 401)")
    token = test_user(USER)["access_token"]
    for label, bad in (("tampered signature", tampered(token)), ("payload forged as user B", forged_as(token, test_user(LOW_BALANCE_USER)["sub"]))):
        code, _ = http_json("GET", f"{API}/wallet", headers={"Authorization": bad})
        s.check(code == 401, f"GET /wallet with a {label} -> {code} (expected 401)")
    # Step 2.0: the pre-token trigger puts the verified email in the ACCESS token, which the API now takes.
    claims = token_claims(token)
    s.check(
        claims.get("token_use") == "access" and claims.get("email") == test_user(USER)["email"] and claims.get("email_verified") is True,
        f"access token carries token_use={claims.get('token_use')}, email (matches A: {claims.get('email') == test_user(USER)['email']}), "
        f"email_verified={claims.get('email_verified')}",
    )
    code, body = http_json("GET", f"{API}/wallet", headers={"Authorization": token})
    s.check(code == 200 and body.get("walletId") == test_user(USER)["sub"], f"GET /wallet with the ACCESS token -> {code} (expected 200, A's wallet)")
    # A genuine, unexpired ID token passes the JWT authorizer (aud = our client) but is the wrong token for an API.
    for method, path in (("GET", "/wallet"), ("GET", "/orders"), ("POST", "/orders")):
        code, body = http_json(method, f"{API}{path}", {} if method == "POST" else None, {"Authorization": test_user(USER)["id_token"]})
        s.check(code == 401 and "ID tokens are not accepted" in body.get("error", ""),
                f"{method} {path} with the ID token -> {code} (expected 401: {body.get('error')})")
    return s


def scenario_order_isolation() -> Scenario:
    s = Scenario("l", "order isolation: A can't read B's order (404), each list shows only its owner's orders")
    code, body = place_order("DESK-MAT", 1, "none", user=LOW_BALANCE_USER)
    s.check(code == 202, f"B: POST /orders -> {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id, user=LOW_BALANCE_USER)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"B reads B's own order: {order.get('status')} (expected COMPLETED)")

    code_other, body_other = http_json("GET", f"{API}/orders/{s.order_id}", headers=auth_header(USER))
    missing = f"ORD-{datetime.now(timezone.utc):%Y%m%d}-00000000"
    code_missing, body_missing = http_json("GET", f"{API}/orders/{missing}", headers=auth_header(USER))
    s.check(code_other == 404, f"A: GET /orders/<B's order> -> {code_other} (expected 404, not 403)")
    s.check(
        code_missing == 404 and body_other.get("error", "").replace(s.order_id, "X") == body_missing.get("error", "").replace(missing, "X"),
        "the 404 for B's order is worded exactly like the 404 for an order that doesn't exist",
    )
    a_list = [o["orderId"] for o in http_json("GET", f"{API}/orders?limit=50", headers=auth_header(USER))[1]["orders"]]
    b_list = [o["orderId"] for o in http_json("GET", f"{API}/orders?limit=50", headers=auth_header(LOW_BALANCE_USER))[1]["orders"]]
    s.check(s.order_id not in a_list, f"A's GET /orders ({len(a_list)} orders) doesn't contain B's order")
    s.check(s.order_id in b_list, f"B's GET /orders ({len(b_list)} orders) contains B's order")
    s.check(not set(a_list) & set(b_list), "A's and B's order lists share no orderId")
    owners = {orders_table.get_item(Key={"orderId": oid})["Item"].get("userId") for oid in a_list}
    s.check(owners == {test_user(USER)["sub"]}, f"every order in A's list is owned by A's sub (owners seen: {len(owners)})")
    return s


def scenario_wallet_isolation() -> Scenario:
    s = Scenario("m", "wallet isolation: A's reset (with B's ids in the body) changes only A's wallet")
    b_before = wallet(LOW_BALANCE_USER)
    body = {"balance": 4321, "email": test_user(LOW_BALANCE_USER)["email"], "walletId": test_user(LOW_BALANCE_USER)["sub"]}
    code, result = http_json("POST", f"{API}/wallet/reset?email={test_user(LOW_BALANCE_USER)['email']}", body, auth_header(USER))
    s.check(code == 200 and result.get("walletId") == test_user(USER)["sub"], f"POST /wallet/reset as A -> {code}, walletId = A's sub")
    s.check(wallet(USER)["balance"] == 4321, f"A's balance is now {wallet(USER)['balance']} (expected 4321)")
    b_after = wallet(LOW_BALANCE_USER)
    s.check(
        b_after["balance"] == b_before["balance"] and len(b_after["transactions"]) == len(b_before["transactions"]),
        f"B's wallet unchanged: balance {b_before['balance']} -> {b_after['balance']}, "
        f"{len(b_before['transactions'])} -> {len(b_after['transactions'])} ledger entries",
    )
    set_wallet(USER)  # back to ₹10,00,000
    return s


def scenario_per_user_idempotency() -> Scenario:
    s = Scenario("n", "per-user idempotency: B reusing A's Idempotency-Key gets B's own order", user=LOW_BALANCE_USER)
    key = f"e2e-shared-{uuid.uuid4().hex[:8]}"
    code_a, body_a = place_order("LAPTOP-STAND", 1, "none", key=key, user=USER)
    code_b, body_b = place_order("LAPTOP-STAND", 1, "none", key=key, user=LOW_BALANCE_USER)
    code_a2, body_a2 = place_order("LAPTOP-STAND", 1, "none", key=key, user=USER)
    s.order_id = body_b.get("orderId")
    s.check(code_a == 202 and code_b == 202, f"A -> {code_a}, then B with the SAME key -> {code_b} (both 202 = new orders)")
    s.check(body_a.get("orderId") != body_b.get("orderId"), f"different orders: A {body_a.get('orderId')}, B {body_b.get('orderId')}")
    s.check(code_a2 == 200 and body_a2.get("duplicate") is True and body_a2.get("orderId") == body_a.get("orderId"),
            f"A again with the key -> {code_a2}, duplicate={body_a2.get('duplicate')}, the original order")
    owner = orders_table.get_item(Key={"orderId": s.order_id}, ConsistentRead=True)["Item"].get("userId")
    s.check(owner == test_user(LOW_BALANCE_USER)["sub"], "B's order is owned by B's sub")
    code, _ = http_json("GET", f"{API}/orders/{s.order_id}", headers=auth_header(USER))
    s.check(code == 404, f"A can't read the order B made with A's key -> {code} (expected 404)")
    for oid, user in ((body_a.get("orderId"), USER), (s.order_id, LOW_BALANCE_USER)):
        s.check(wait_for_terminal(oid, user=user).get("status") == "COMPLETED", f"{oid} COMPLETED")
    s.timeline = get_order(s.order_id, LOW_BALANCE_USER).get("statusHistory", [])
    return s


# --------------------------------------------------------------------------------------------
# Step 2.1: the payment webhook (server-to-server, HMAC-signed, no JWT)
# --------------------------------------------------------------------------------------------
def webhook_secret() -> str:
    """The shared HMAC secret, read with our AWS credentials. Held in memory only, never printed."""
    return ssm.get_parameter(Name=OUT["webhook_secret_parameter"], WithDecryption=True)["Parameter"]["Value"]


def post_webhook(body: dict, headers: dict) -> tuple[int, dict]:
    raw = json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
        OUT["webhook_url"], data=raw, method="POST", headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def signature_headers(secret: str, body: dict, at: float | None = None) -> dict:
    raw = json.dumps(body, separators=(",", ":")).encode()
    timestamp = str(int(time.time() if at is None else at))
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {"X-Timestamp": timestamp, "X-Signature": digest}


def scenario_webhook_security() -> Scenario:
    s = Scenario("o", "payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op")
    unknown = f"PI-ORD-{datetime.now(timezone.utc):%Y%m%d}-e2e{uuid.uuid4().hex[:5]}"
    body = {"eventId": "evt_e2e", "type": "payment.succeeded", "paymentIntentId": unknown,
            "orderId": unknown[3:], "paymentId": "PAY-e2e000000000", "amount": "1.00", "currency": "INR"}
    secret = webhook_secret()
    for label, headers in (
        ("no signature headers", {}),
        ("signed with a wrong secret", signature_headers("not-the-secret", body)),
        ("timestamp 10 min old (replay)", signature_headers(secret, body, time.time() - 600)),
        ("timestamp 10 min in the future", signature_headers(secret, body, time.time() + 600)),
    ):
        code, answer = post_webhook(body, headers)
        s.check(code == 401, f"POST /webhooks/payment {label} -> {code} (expected 401: {answer.get('error')})")
    code, answer = post_webhook(body, signature_headers(secret, body))
    s.check(code == 404, f"valid signature, unknown intent -> {code} (expected 404: {answer.get('error')})")
    s.check("Item" not in payments_table.get_item(Key={"paymentIntentId": unknown}), "no payment intent was created")
    code, _ = http_json("POST", f"{API}/webhooks/payment", body, auth_header(USER))
    s.check(code == 401, f"a user's JWT is no substitute for the signature -> {code} (expected 401)")
    return s


# --------------------------------------------------------------------------------------------
# Step 2.1: asynchronous payment scenarios
# --------------------------------------------------------------------------------------------
def intent_of(order_id: str) -> dict | None:
    return payments_table.get_item(Key={"paymentIntentId": f"PI-{order_id}"}, ConsistentRead=True).get("Item")


def start_slow(key: str, title: str, product: str, simulate: str) -> tuple[Scenario, tuple[int, int]]:
    """Place an order whose outcome takes minutes; finish_* checks it at the end of the run."""
    s = Scenario(key, title)
    before = stock_of(product)
    code, body = place_order(product, 1, simulate)
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    return s, before


def finish_timeout(s: Scenario, product: str, before: tuple[int, int]) -> Scenario:
    order = wait_for_terminal(s.order_id, timeout=SLOW_TIMEOUT_SECONDS)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "FAILED", f"order status {order.get('status')} (expected FAILED)")
    reason = str(order.get("failureReason", ""))
    s.check("payment timeout" in reason, f"failureReason '{reason}'")
    s.check("PAYMENT_PENDING" in statuses(order), "the saga waited at PAYMENT_PENDING")
    entered = states_entered(s)
    s.check("MarkPaymentTimedOut" in entered, "MarkPaymentTimedOut ran (States.Timeout caught after 120 s)")
    s.check({"RefundPayment", "ReleaseInventory"} <= set(entered), "compensation ran: RefundPayment, ReleaseInventory")
    s.check(stock_of(product) == before, f"{product} (stock, reserved) {before} -> {stock_of(product)} (expected unchanged)")
    waited = timeout_wait_seconds(s)
    s.check(waited is not None and 119 <= waited <= 135, f"RequestPayment waited {waited} s before timing out (expected ~120)")
    return s


def timeout_wait_seconds(s: Scenario) -> float | None:
    """Seconds between entering RequestPayment (last attempt) and the TaskTimedOut event."""
    entered_at = timed_out_at = None
    for page in sfn.get_paginator("get_execution_history").paginate(executionArn=s.execution_arn):
        for e in page["events"]:
            if e.get("stateEnteredEventDetails", {}).get("name") == "RequestPayment":
                entered_at = e["timestamp"]
            if e["type"] == "TaskTimedOut":
                timed_out_at = e["timestamp"]
    if entered_at and timed_out_at:
        return round((timed_out_at - entered_at).total_seconds(), 1)
    return None


def finish_late(s: Scenario, product: str, before: tuple[int, int]) -> Scenario:
    order = wait_for_terminal(s.order_id, timeout=SLOW_TIMEOUT_SECONDS)
    s.check(order.get("status") == "FAILED", f"order status {order.get('status')} (expected FAILED: timed out at 120 s)")
    s.check("payment timeout" in str(order.get("failureReason", "")), f"failureReason '{order.get('failureReason')}'")
    s.check(stock_of(product) == before, f"{product} (stock, reserved) {before} -> {stock_of(product)} (expected unchanged)")
    deadline = time.monotonic() + SLOW_TIMEOUT_SECONDS
    intent = intent_of(s.order_id) or {}
    while intent.get("status") != "REFUNDED" and time.monotonic() < deadline:
        time.sleep(5)  # DemoPay charges ~150 s after the request; the webhook then refunds at once
        intent = intent_of(s.order_id) or {}
    s.check(intent.get("status") == "REFUNDED", f"intent {intent.get('paymentIntentId')} {intent.get('status')} (expected REFUNDED)")
    order = get_order(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "FAILED", "order still FAILED after the late callback (it is never revived)")
    s.check(statuses(order).count("PAYMENT_REFUNDED") == 1, "exactly one PAYMENT_REFUNDED in statusHistory")
    return s


def scenario_webhook_duplicate() -> Scenario:
    s = Scenario("r", "webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once")
    code, body = place_order("ERGO-MOUSE", 1, "webhook_duplicate")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    s.check(statuses(order).count("PAYMENT_CAPTURED") == 1, "exactly one PAYMENT_CAPTURED in statusHistory")
    duplicates = poll_log_lines("/aws/lambda/order-saga-payment-webhook", f"PI-{s.order_id}", "duplicate")
    s.check(duplicates >= 1, f"webhook log lines with result 'duplicate' for this intent: {duplicates} (expected >= 1)")
    return s


def scenario_webhook_bad_signature() -> Scenario:
    s = Scenario("s", "webhook_bad_signature -> forged callback rejected (401), genuine one completes the order")
    since_ms = int(time.time() * 1000) - 120_000  # slack for local-clock skew
    code, body = place_order("WIRELESS-EARBUDS", 1, "webhook_bad_signature")
    s.check(code == 202, f"POST /orders returned {code} (expected 202)")
    s.order_id = body.get("orderId")
    order = wait_for_terminal(s.order_id)
    s.timeline = order.get("statusHistory", [])
    s.check(order.get("status") == "COMPLETED", f"order status {order.get('status')} (expected COMPLETED)")
    rejected = poll_log_lines("/aws/lambda/order-saga-payment-webhook", "webhook_signature_rejected", since_ms=since_ms)
    s.check(rejected >= 1, f"'webhook_signature_rejected' log lines since this order: {rejected} (expected >= 1)")
    rejected_by_provider = poll_log_lines("/aws/lambda/order-saga-payment-provider", f"PI-{s.order_id}", "WRONG secret")
    s.check(rejected_by_provider >= 1, "DemoPay logged the 401 for its forged callback, then sent the genuine one")
    return s


def check_signature_metric(s: Scenario) -> None:
    """The metric filter turns rejections into OrderSaga/WebhookSignatureFailures (alarm source). Checked at the
    end of the run because metric filters publish with a delay of a minute or two."""
    total = 0.0
    for _ in range(18):
        stats = cloudwatch.get_metric_statistics(
            Namespace="OrderSaga", MetricName="WebhookSignatureFailures", Statistics=["Sum"], Period=60,
            StartTime=RUN_STARTED.timestamp() - 300, EndTime=time.time() + 60,
        )
        total = sum(p["Sum"] for p in stats["Datapoints"])
        if total >= 1:
            break
        time.sleep(10)
    s.check(total >= 1, f"CloudWatch OrderSaga/WebhookSignatureFailures during this run: {total:.0f} (expected >= 1)")


def poll_log_lines(log_group: str, *terms: str, since_ms: int = 0, tries: int = 12) -> int:
    lines = 0
    for _ in range(tries):  # CloudWatch Logs ingestion can lag a few seconds
        lines = count_log_lines(log_group, *terms, since_ms=since_ms)
        if lines:
            break
        time.sleep(5)
    return lines


# Expected final payment intent status per scenario (None = payment never requested).
EXPECTED_INTENT = {
    "a": "SUCCEEDED", "b": "FAILED", "c": "SUCCEEDED", "d": None, "e": "SUCCEEDED", "f": "SUCCEEDED",
    "g": None, "h": "FAILED", "i": "SUCCEEDED", "n": "SUCCEEDED",
    "p": "TIMED_OUT", "q": "REFUNDED", "r": "SUCCEEDED", "s": "SUCCEEDED",
}
FINAL_INTENT_STATUSES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "REFUNDED"}


def ledger_for(order_id: str, user: str) -> list[dict]:
    """This order's entries in the user's DemoPay ledger, read straight from DynamoDB (not the API's last 20)."""
    since = (RUN_STARTED.timestamp() - 600)
    since_iso = datetime.fromtimestamp(since, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    kwargs = {
        "KeyConditionExpression": "walletId = :w AND txnId > :since",
        "FilterExpression": "orderId = :o",
        "ExpressionAttributeValues": {":w": test_user(user)["sub"], ":since": since_iso, ":o": order_id},
        "ConsistentRead": True,
    }
    items: list[dict] = []
    while True:
        page = wallet_txns_table.query(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def check_money(s: Scenario) -> None:
    """Money invariants I1-I4 for this scenario's order (see the module docstring)."""
    order = orders_table.get_item(Key={"orderId": s.order_id}, ConsistentRead=True)["Item"]
    entries = ledger_for(s.order_id, s.user)
    debits = [e["amount"] for e in entries if e["type"] == "DEBIT"]
    credits = [e["amount"] for e in entries if e["type"] == "CREDIT"]
    net = sum(debits) - sum(credits)
    ledger = f"ledger {len(debits)} DEBIT / {len(credits)} CREDIT, net ₹{net}"
    if order["status"] == "COMPLETED":
        s.check(debits == [order["totalAmount"]] and not credits, f"I1 COMPLETED -> one DEBIT of ₹{order['totalAmount']}: {ledger}")
    else:
        s.check(net == 0, f"I2 {order['status']} -> net charge 0: {ledger}")
    s.check(len(debits) <= 1 and len(credits) <= 1, f"I3 no double charge / double refund: {ledger}")
    intent = intent_of(s.order_id)
    status = intent["status"] if intent else None
    expected = EXPECTED_INTENT[s.key]
    s.check(
        (status is None or status in FINAL_INTENT_STATUSES) and status == expected,
        f"I4 intent PI-{s.order_id}: {status or 'none (payment never requested)'} (expected {expected or 'none'})",
    )
    s.money = f"{status or '-'} · {ledger}"


# --------------------------------------------------------------------------------------------
# Step 2.2: checkout holds
# --------------------------------------------------------------------------------------------
def post_hold(items: list[tuple[str, int]], user: str = USER, duration: int | None = None) -> tuple[int, dict]:
    body: dict = {"items": [{"productId": p, "quantity": q} for p, q in items]}
    if duration is not None:
        body["durationSeconds"] = duration
    return http_json("POST", f"{API}/holds", body, auth_header(user))


def current_hold(user: str = USER) -> dict | None:
    return http_json("GET", f"{API}/holds/current", headers=auth_header(user))[1].get("hold")


def delete_hold(hold_id: str, user: str = USER) -> tuple[int, dict]:
    request = urllib.request.Request(f"{API}/holds/{hold_id}", method="DELETE", headers=auth_header(user))
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def counters(product_id: str) -> tuple[int, int, int]:
    """(stock, held, reserved) for a product."""
    item = inventory_table.get_item(Key={"productId": product_id}, ConsistentRead=True)["Item"]
    return int(item["stock"]), int(item.get("held", 0)), int(item["reserved"])


def stored_hold(hold_id: str) -> dict:
    return holds_table.get_item(Key={"holdId": hold_id}, ConsistentRead=True).get("Item") or {}


def schedule_exists(hold_id: str) -> bool:
    try:
        scheduler.get_schedule(Name=hold_id, GroupName=OUT["holds_schedule_group"])
        return True
    except scheduler.exceptions.ResourceNotFoundException:
        return False


def scenario_hold_lifecycle() -> Scenario:
    s = Scenario("t", "checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases")
    product = "COMPACT-KEYBOARD"
    before = counters(product)
    code, first = post_hold([(product, 2)])
    s.check(code == 201 and first.get("status") == "ACTIVE", f"POST /holds -> {code} {first.get('status')} (expected 201 ACTIVE)")
    hold_id = first.get("holdId", "")
    s.check(first.get("durationSeconds") == 600 and 590 <= first.get("secondsLeft", 0) <= 600,
            f"no durationSeconds -> {first.get('durationSeconds')} s, secondsLeft {first.get('secondsLeft')} (expected 600)")
    s.check(counters(product) == (before[0] - 2, before[1] + 2, before[2]), f"{product} (stock, held, reserved) {before} -> {counters(product)} (2 units stock -> held)")
    s.check(schedule_exists(hold_id), f"one-time schedule {hold_id} exists in {OUT['holds_schedule_group']}")
    s.check((current_hold() or {}).get("holdId") == hold_id, "GET /holds/current returns it")

    code, second = post_hold([(product, 1)])
    s.check(code == 201, f"2nd POST /holds -> {code} (expected 201)")
    s.check(stored_hold(hold_id).get("status") == "RELEASED", f"1st hold {stored_hold(hold_id).get('status')} (expected RELEASED: one ACTIVE hold per user)")
    s.check(not schedule_exists(hold_id), "1st hold's schedule deleted")
    s.check(counters(product) == (before[0] - 1, before[1] + 1, before[2]), f"{product} now {counters(product)} (only the 2nd hold's 1 unit held)")

    code, body = post_hold([(product, 6)])
    s.check(code == 400, f"quantity 6 (cap 5) -> {code} (expected 400: {body.get('error')})")
    code, body = post_hold([("LAPTOP-STAND", 1)], duration=10)
    s.check(code == 400, f"durationSeconds 10 (min 30) -> {code} (expected 400)")
    code, body = post_hold([("WEBCAM-1080P", 1)])
    s.check(code == 409 and body.get("productId") == "WEBCAM-1080P", f"out of stock -> {code}, productId {body.get('productId')} (expected 409 WEBCAM-1080P)")

    code, _ = post_hold([(product, 1)])
    hold_id = (current_hold() or {}).get("holdId", "")
    code, body = delete_hold(hold_id)
    s.check(code == 200 and body.get("status") == "RELEASED", f"DELETE /holds/{hold_id} -> {code} {body.get('status')} (expected 200 RELEASED)")
    s.check(counters(product) == before, f"{product} back to {counters(product)} (expected {before})")
    s.check(current_hold() is None and not schedule_exists(hold_id), "no current hold, schedule deleted")
    s.order_id = None
    s.timeline = [{"timestamp": first.get("serverTime", ""), "status": "HOLD", "detail": f"{hold_id} and its predecessors"}]
    return s


def start_short_hold() -> tuple[Scenario, dict, tuple[int, int, int]]:
    s = Scenario("u", f"{SHORT_HOLD_SECONDS} s hold expired by its EventBridge Scheduler schedule, stock restored", user=LOW_BALANCE_USER)
    before = counters("DESK-MAT")
    code, hold = post_hold([("DESK-MAT", 3)], user=LOW_BALANCE_USER, duration=SHORT_HOLD_SECONDS)
    s.check(code == 201 and hold.get("durationSeconds") == SHORT_HOLD_SECONDS, f"POST /holds (automation client, {SHORT_HOLD_SECONDS} s) -> {code}")
    return s, hold, before


def finish_short_hold(s: Scenario, hold: dict, before: tuple[int, int, int]) -> Scenario:
    hold_id = hold.get("holdId", "")
    deadline = time.time() + SHORT_HOLD_SECONDS + 240
    item = stored_hold(hold_id)
    while item.get("status") == "ACTIVE" and time.time() < deadline:
        time.sleep(3)
        item = stored_hold(hold_id)
    s.check(item.get("status") == "EXPIRED", f"hold {hold_id} {item.get('status')} (expected EXPIRED)")
    s.check(item.get("expiredBy") == "schedule", f"expired by: {item.get('expiredBy')} (expected the schedule, not a lazy read)")
    lag = int(item.get("expiryLagMs", -1)) / 1000
    s.check(0 <= lag <= 120, f"released {lag:.1f} s after expiresAt {item.get('expiresAt')} (EventBridge Scheduler precision)")
    s.check(counters("DESK-MAT") == before, f"DESK-MAT (stock, held, reserved) back to {counters('DESK-MAT')} (expected {before})")
    s.check(not schedule_exists(hold_id), "schedule deleted itself after firing (ActionAfterCompletion DELETE)")
    s.timeline = [
        {"timestamp": item.get("createdAt", ""), "status": "ACTIVE", "detail": f"{hold_id}: 3 x DESK-MAT held for {SHORT_HOLD_SECONDS} s"},
        {"timestamp": item.get("expiresAt", ""), "status": "expiresAt", "detail": "the schedule's at() time"},
        {"timestamp": item.get("endedAt", ""), "status": "EXPIRED", "detail": f"by the schedule, {lag:.1f} s after expiresAt"},
    ]
    s.hold_lag_seconds = lag
    return s


def scenario_hold_ownership() -> Scenario:
    s = Scenario("w", "hold ownership: B can't release or see A's hold (404)")
    code, mine = post_hold([("LAPTOP-STAND", 1)])
    hold_id = mine.get("holdId", "")
    code, body = delete_hold(hold_id, user=LOW_BALANCE_USER)
    s.check(code == 404, f"B: DELETE /holds/{hold_id} (A's) -> {code} (expected 404, same as a missing hold)")
    s.check((current_hold(LOW_BALANCE_USER) or {}).get("holdId") != hold_id, "B's GET /holds/current never shows A's hold")
    s.check(stored_hold(hold_id).get("status") == "ACTIVE", "A's hold is still ACTIVE")
    s.check(delete_hold(hold_id)[0] == 200, "A can release it")
    return s


def scenario_last_unit_race() -> Scenario:
    """Make VERTICAL-MOUSE's last unit the only one, then let both users hold it at the same moment."""
    from concurrent.futures import ThreadPoolExecutor

    s = Scenario("v", "two users race for the last unit -> exactly one hold (201), the other 409")
    product, seeded = "VERTICAL-MOUSE", SEEDED_STOCK["VERTICAL-MOUSE"]
    try:  # test setup: park all but 1 unit (the conditional keeps it exact)
        inventory_table.update_item(
            Key={"productId": product}, UpdateExpression="SET stock = :one", ConditionExpression="stock = :seeded AND held = :zero",
            ExpressionAttributeValues={":one": 1, ":seeded": seeded, ":zero": 0},
        )
    except inventory_table.meta.client.exceptions.ConditionalCheckFailedException:
        s.check(False, f"setup: {product} is not at its seeded stock {seeded} with nothing held; run seed_inventory.py first")
        return s
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda user: (user, *post_hold([(product, 1)], user=user)), [USER, LOW_BALANCE_USER]))
        codes = sorted(code for _, code, _ in results)
        s.check(codes == [201, 409], f"HTTP codes {codes} (expected [201, 409])")
        winner = next((u, b) for u, c, b in results if c == 201)
        loser = next(b for _, c, b in results if c == 409)
        s.check(loser.get("productId") == product, f"the loser's 409 names {loser.get('productId')}")
        s.check(counters(product)[:2] == (0, 1), f"{product} (stock, held) {counters(product)[:2]} (expected (0, 1))")
        delete_hold(winner[1]["holdId"], user=winner[0])
    finally:
        inventory_table.update_item(  # put the parked units back
            Key={"productId": product}, UpdateExpression="SET stock = stock + :parked", ExpressionAttributeValues={":parked": seeded - 1},
        )
    s.check(counters(product) == (seeded, 0, 0), f"{product} restored to {counters(product)}")
    return s


def scenario_stock_conservation() -> Scenario:
    s = Scenario("x", "I5 stock conservation for every product: seeded = stock + held + reserved; held = ACTIVE holds")
    active: dict[str, int] = {}
    kwargs: dict = {"FilterExpression": "#s = :active", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":active": "ACTIVE"}}
    while True:
        page = holds_table.scan(**kwargs)
        for hold in page["Items"]:
            for item in hold["items"]:
                active[item["productId"]] = active.get(item["productId"], 0) + int(item["quantity"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    broken = []
    for product, seeded in SEEDED_STOCK.items():
        stock, held, reserved = counters(product)
        if stock + held + reserved != seeded or held != active.get(product, 0):
            broken.append(f"{product}: {stock}+{held}+{reserved} vs {seeded}, ACTIVE holds {active.get(product, 0)}")
    s.check(not broken, f"I5 holds for all {len(SEEDED_STOCK)} products" if not broken else f"I5 BROKEN: {broken}")
    return s


def main() -> int:
    started = time.monotonic()
    set_wallet(USER)  # DemoPay: start every run from ₹10,00,000
    print("Placing poison order first (it needs ~3 min of SQS retries)...")
    poison, poison_started = start_poison()
    print(f"  poison order {poison.order_id}")
    print("Placing payment_timeout and payment_late orders (they finish after 2-3 min)...")
    timeout_order, timeout_before = start_slow(
        "p", "payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged", "CURVED-MONITOR", "payment_timeout"
    )
    late_order, late_before = start_slow(
        "q", "payment_late -> charged after the timeout, refunded automatically, order stays FAILED", "PODCAST-MIC", "payment_late"
    )
    print(f"  payment_timeout {timeout_order.order_id} · payment_late {late_order.order_id}")
    short_hold, short_hold_body, short_hold_before = start_short_hold()
    print(f"  {SHORT_HOLD_SECONDS} s hold {short_hold_body.get('holdId')} (user B)")

    results = []
    for run in (
        scenario_none,
        scenario_payment_declined,
        scenario_payment_flaky,
        scenario_out_of_stock,
        scenario_duplicate_idempotency_key,
        scenario_duplicate_sqs_message,
        scenario_low_balance,
        scenario_crash_after_db_write,
        scenario_auth_gate,
        scenario_order_isolation,
        scenario_wallet_isolation,
        scenario_per_user_idempotency,
        scenario_webhook_duplicate,
        scenario_webhook_bad_signature,
        scenario_webhook_security,
        scenario_hold_lifecycle,
        scenario_hold_ownership,
    ):
        result = run()
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.key}) {result.title}  {result.order_id}")
        for ok, text in result.checks:
            if not ok:
                print(f"      FAIL: {text}")
        results.append(result)

    crash = next(r for r in results if r.key == "i")
    results.append(scenario_modify_does_not_restart(crash.order_id))
    print(f"[{'PASS' if results[-1].passed else 'FAIL'}] j) {results[-1].title}  {crash.order_id}")

    print("Waiting for the poison message to reach the DLQ (up to 5 min from placement)...")
    results.append(finish_poison(poison, poison_started))
    print(f"[{'PASS' if results[-1].passed else 'FAIL'}] g) {poison.title}  {poison.order_id}")

    print("Waiting for the payment timeout and the late callback's refund...")
    results.append(finish_timeout(timeout_order, "CURVED-MONITOR", timeout_before))
    results.append(finish_late(late_order, "PODCAST-MIC", late_before))
    check_signature_metric(next(r for r in results if r.key == "s"))
    results.append(finish_short_hold(short_hold, short_hold_body, short_hold_before))
    results.append(scenario_last_unit_race())
    results.append(scenario_stock_conservation())

    print("Checking the money invariants I1-I4 for every order...")
    for r in results:
        if r.key in EXPECTED_INTENT and r.order_id:
            check_money(r)

    results.sort(key=lambda r: r.key)
    duration = time.monotonic() - started
    print("\n" + "=" * 100)
    print(f"{'#':<3}{'Result':<8}{'orderId':<24}Scenario")
    for r in results:
        print(f"{r.key:<3}{'PASS' if r.passed else 'FAIL':<8}{r.order_id or '-':<24}{r.title}")
        for ok, text in r.checks:
            if not ok:
                print(f"      FAIL: {text}")
    print("=" * 100)
    for r in results:
        if r.order_id and r.key != "g":
            print(f"{r.key}) {r.console_link}")
    write_evidence(results, duration)
    print(f"\nEvidence written to {EVIDENCE_FILE}")
    passed = sum(r.passed for r in results)
    print(f"{passed}/{len(results)} scenarios passed in {duration:.0f}s")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
