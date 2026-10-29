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
  k) auth gate         -> no token / tampered token -> 401 from API Gateway; an access token (no email)
                          -> 403; GET /products works signed out
  l) order isolation   -> A can't read B's order (404, same as a missing one); each list shows only its owner's
  m) wallet isolation  -> A resetting "B's" wallet (B's ids in the body) only changes A's wallet
  n) per-user idempotency -> B reusing A's Idempotency-Key gets B's OWN new order; A's replay still works

Auth: every API call carries a Cognito ID token for test user A (or B), from auth_tokens.py. The API
takes identity only from that token, so no request below sends an email or user id.

DemoPay: test user A's wallet is reset to ₹10,00,000 first, and each scenario checks the ledger
(exactly one DEBIT for each paid order, none for failed ones).

The poison order is placed FIRST, so its ~3 minutes of SQS retries overlap the other scenarios.
The DLQ is only peeked (VisibilityTimeout=0) and is never purged, so it stays for screenshots.
Results are printed and written to docs/evidence/e2e-failure-tests.md. Exit code 1 if anything fails.
"""

from __future__ import annotations

import base64
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
    s = Scenario("h", "wallet balance too low -> REAL decline, stock released, nothing debited")
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
        link = f"[open]({r.console_link})" if r.order_id and r.key != "g" else "none started (by design)"
        lines.append(f"| {r.key} | {r.title} | {'PASS' if r.passed else 'FAIL'} | `{r.order_id}` | {link} |")
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
    s = Scenario("k", "auth gate: no/tampered/forged token -> 401, access token with email claims -> 200, /products public")
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
    code, body = http_json("GET", f"{API}/wallet", headers={"Authorization": test_user(USER)["id_token"]})
    s.check(code == 200, f"GET /wallet with the ID token -> {code} (expected 200 during the step 2.0 rollout)")
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
    s = Scenario("n", "per-user idempotency: B reusing A's Idempotency-Key gets B's own order")
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


def main() -> int:
    started = time.monotonic()
    set_wallet(USER)  # DemoPay: start every run from ₹10,00,000
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
        scenario_crash_after_db_write,
        scenario_auth_gate,
        scenario_order_isolation,
        scenario_wallet_isolation,
        scenario_per_user_idempotency,
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

    results.sort(key=lambda r: r.key)
    duration = time.monotonic() - started
    print("\n" + "=" * 100)
    print(f"{'#':<3}{'Result':<8}{'orderId':<24}Scenario")
    for r in results:
        print(f"{r.key:<3}{'PASS' if r.passed else 'FAIL':<8}{r.order_id or '-':<24}{r.title}")
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
