"""Step 3.3 load test, part 3 of 3: measure the run from the data it left behind, then write the evidence.

    python scripts/loadtest_report.py --label after                            # after `k6 run ...` (loadtest/k6/orders.js)
    python scripts/loadtest_report.py --label before --dir build/loadtest-before   # re-check an earlier run's files

Inputs: build/loadtest/run.json (prep: run id, buyers, "before" facts) and build/loadtest/k6-summary.json (k6: API
latency, accepted / throttled / failed counts). Everything else is read from AWS directly, never through the API:
  * this run's orders: per buyer, gsi1 (USER#<sub>, newest after the run start), keeping customerName "Load <runId>",
    then the full items (BatchGetItem). Waits (DynamoDB reads every 30 s, at most 15 min) until every order is terminal;
  * completion time per order = its terminal statusHistory timestamp - createdAt; throughput per second from createdAt;
  * money (₹ lost): per order, ledger DEBITs - CREDITs (one query per buyer wallet since the run start) must equal the
    fulfilled line amounts (e2e_test.fulfilled_amount, the auditor's I6);
  * outcome per scenario: normal -> COMPLETED, partial -> PARTIALLY_FULFILLED, declined -> FAILED;
  * DLQ depths vs before, an auditor run (violations, stuck, how long it took), and CloudWatch: account Lambda
    concurrency peak and throttles, per-function errors, Step Functions executions started per minute, failed and
    throttled executions, API Gateway requests / 4xx / 5xx per minute.
  * declines outside the "declined" scenario (a PaymentDeclined failure on a normal or partial order) are listed:
    with DemoPay's wallet-conflict retry (step 3.3) there must be none.
Writes docs/evidence/upgrade-3.3-load-<label>.json. Exit code 1 if money, outcomes, auditor or DLQs fail.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

import e2e_test as e2e
from loadtest_prep import DLQS, dlq_depths, run_auditor

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"
OUT, REGION = e2e.OUT, e2e.REGION
TERMINAL = {"COMPLETED", "PARTIALLY_FULFILLED", "FAILED", "CANCELLED"}
EXPECTED = {"none": "COMPLETED", "item_unavailable": "PARTIALLY_FULFILLED", "payment_declined": "FAILED"}
KIND = {"none": "normal", "item_unavailable": "partial", "payment_declined": "declined"}

dynamodb = boto3.resource("dynamodb", region_name=REGION)
orders_table = dynamodb.Table(OUT["orders_table"])
ledger_table = dynamodb.Table(OUT["wallet_txns_table"])
cloudwatch = boto3.client("cloudwatch", region_name=REGION)


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile (no interpolation): the value p% of the orders are at or under."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(p / 100 * len(ordered) + 0.5) - 1))]


# ---------------------------------------------------------------------------------------------------------------
# This run's orders
# ---------------------------------------------------------------------------------------------------------------
def run_order_ids(run: dict, since: str) -> list[str]:
    ids = []
    for buyer in run["buyers"]:
        kwargs = {"IndexName": "gsi1", "KeyConditionExpression": Key("gsi1pk").eq(f"USER#{buyer['sub']}") & Key("gsi1sk").gt(since)}
        while True:
            page = orders_table.query(**kwargs)
            ids += [i["orderId"] for i in page["Items"]]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return ids


def load_orders(order_ids: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    client = dynamodb.meta.client
    for start in range(0, len(order_ids), 100):
        request = {OUT["orders_table"]: {"Keys": [{"orderId": o} for o in order_ids[start:start + 100]], "ConsistentRead": True}}
        while request:
            resp = client.batch_get_item(RequestItems=request)
            for item in resp["Responses"].get(OUT["orders_table"], []):
                found[item["orderId"]] = item
            request = resp.get("UnprocessedKeys") or None
            if request:
                time.sleep(0.2)
    return found


def wait_terminal(run: dict, since: str) -> dict[str, dict]:
    deadline = time.monotonic() + 900
    while True:
        orders = {o: i for o, i in load_orders(run_order_ids(run, since)).items() if i.get("customerName") == f"Load {run['runId']}"}
        pending = [o for o, i in orders.items() if i["status"] not in TERMINAL]
        print(f"  {len(orders)} orders, {len(pending)} not terminal yet")
        if not pending or time.monotonic() > deadline:
            return orders
        time.sleep(30)


def ledgers(run: dict, since: str) -> dict[str, list[dict]]:
    """orderId -> its ledger entries, from one paginated query per buyer wallet."""
    by_order: dict[str, list[dict]] = defaultdict(list)
    for buyer in run["buyers"]:
        kwargs = {"KeyConditionExpression": Key("walletId").eq(buyer["sub"]) & Key("txnId").gt(since), "ConsistentRead": True}
        while True:
            page = ledger_table.query(**kwargs)
            for entry in page["Items"]:
                if entry.get("orderId"):
                    by_order[entry["orderId"]].append(entry)
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return by_order


# ---------------------------------------------------------------------------------------------------------------
# CloudWatch
# ---------------------------------------------------------------------------------------------------------------
def series(namespace: str, metric: str, dims: list[dict], stat: str, start: datetime, end: datetime, period: int = 60) -> list[tuple[datetime, float]]:
    resp = cloudwatch.get_metric_statistics(Namespace=namespace, MetricName=metric, Dimensions=dims, StartTime=start,
                                            EndTime=end, Period=period, Statistics=[stat])
    return sorted((p["Timestamp"], p[stat]) for p in resp["Datapoints"])


def cloudwatch_facts(start: datetime, end: datetime) -> dict:
    sm = [{"Name": "StateMachineArn", "Value": OUT["state_machine_arn"]}]
    api = [{"Name": "ApiId", "Value": e2e.API.split("//")[1].split(".")[0]}]
    started = series("AWS/States", "ExecutionsStarted", sm, "Sum", start, end)
    facts = {
        "lambdaConcurrencyPeak": max((v for _, v in series("AWS/Lambda", "ConcurrentExecutions", [], "Maximum", start, end)), default=0),
        "lambdaThrottles": sum(v for _, v in series("AWS/Lambda", "Throttles", [], "Sum", start, end)),
        "lambdaErrorsAccount": sum(v for _, v in series("AWS/Lambda", "Errors", [], "Sum", start, end)),
        "sfnStartedPerMinutePeak": max((v for _, v in started), default=0),
        "sfnStartedPerMinute": [int(v) for _, v in started],
        "sfnFailed": sum(v for _, v in series("AWS/States", "ExecutionsFailed", sm, "Sum", start, end)),
        "sfnThrottled": sum(v for _, v in series("AWS/States", "ExecutionThrottled", sm, "Sum", start, end)),
        "apiRequestsPerMinute": [int(v) for _, v in series("AWS/ApiGateway", "Count", api, "Sum", start, end)],
        "api4xx": sum(v for _, v in series("AWS/ApiGateway", "4xx", api, "Sum", start, end)),
        "api5xx": sum(v for _, v in series("AWS/ApiGateway", "5xx", api, "Sum", start, end)),
    }
    errors = {}
    for name in ["create-order", "start-workflow", "reserve-inventory", "request-payment", "payment-provider", "payment-webhook",
                 "begin-fulfillment", "fulfill-item", "refund-payment", "release-inventory", "write-off-lines"]:
        fn = [{"Name": "FunctionName", "Value": f"order-saga-{name}"}]
        e = sum(v for _, v in series("AWS/Lambda", "Errors", fn, "Sum", start, end))
        t = sum(v for _, v in series("AWS/Lambda", "Throttles", fn, "Sum", start, end))
        if e or t:
            errors[name] = {"errors": int(e), "throttles": int(t)}
    facts["functionErrors"] = errors
    return facts


# ---------------------------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------------------------
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="after")
    parser.add_argument("--dir", type=Path, default=ROOT / "build" / "loadtest")
    args = parser.parse_args()
    run = json.loads((args.dir / "run.json").read_text(encoding="utf-8"))
    k6 = json.loads((args.dir / "k6-summary.json").read_text(encoding="utf-8"))["metrics"]
    since = run["preparedAt"]

    print("Waiting for every load order to finish (DynamoDB reads, not the API)...")
    orders = wait_terminal(run, since)
    entries = ledgers(run, since)

    created = sorted(ts(o["createdAt"]) for o in orders.values())
    start, end = created[0], created[-1]
    per_second = Counter(int((t - start).total_seconds()) for t in created)
    rates = [per_second.get(s, 0) for s in range(int((end - start).total_seconds()) + 1)]
    peak_10s = max(sum(rates[i:i + 10]) / 10 for i in range(max(len(rates) - 9, 1)))
    # "sustained": the best 3-minute average (the hold phase), the honest number to quote
    sustained = max(sum(rates[i:i + 180]) / 180 for i in range(max(len(rates) - 179, 1)))

    completion: dict[str, list[float]] = defaultdict(list)
    outcomes: Counter = Counter()
    off_path, money_bad, bad_declines = [], [], []
    lost = Decimal("0")
    debits_total = credits_total = fulfilled_total = Decimal("0")
    for oid, o in orders.items():
        kind = KIND.get(o.get("simulate", "none"), o.get("simulate"))
        outcomes[(kind, o["status"])] += 1
        if o["status"] != EXPECTED.get(o.get("simulate", "none")):
            off_path.append((oid, kind, o["status"], o.get("failureReason", "")[:120]))
            if kind != "declined" and "declin" in o.get("failureReason", "").lower():
                bad_declines.append((oid, kind, o.get("failureReason", "")[:160]))
        final = next((h for h in reversed(o["statusHistory"]) if h["status"] in TERMINAL), None)
        if final:
            seconds = (ts(final["timestamp"]) - ts(o["createdAt"])).total_seconds()
            completion[kind].append(seconds)
            completion["all"].append(seconds)
        debit = sum((e["amount"] for e in entries.get(oid, []) if e["type"] == "DEBIT"), Decimal("0"))
        credit = sum((e["amount"] for e in entries.get(oid, []) if e["type"] == "CREDIT"), Decimal("0"))
        expected = e2e.fulfilled_amount(o) if o["status"] in TERMINAL else debit - credit
        debits_total, credits_total, fulfilled_total = debits_total + debit, credits_total + credit, fulfilled_total + expected
        if debit - credit != expected:
            money_bad.append((oid, str(debit - credit), str(expected)))
            lost += abs(debit - credit - expected)

    print("Auditor + DLQs + CloudWatch...")
    time.sleep(60)  # let CloudWatch's last minute land
    after = {"dlq": dlq_depths(), "auditor": run_auditor()}
    cw = cloudwatch_facts(start - timedelta(minutes=2), datetime.now(timezone.utc))

    count = lambda m: int(k6.get(m, {}).get("count", 0))  # noqa: E731
    lat = k6.get("accept_latency", {})
    attempts = count("orders_accepted") + count("orders_throttled") + count("orders_failed")
    error_rate = count("orders_failed") / attempts if attempts else 0
    not_terminal = sum(1 for o in orders.values() if o["status"] not in TERMINAL)
    result = {
        "runId": run["runId"], "start": start.isoformat(), "end": end.isoformat(), "orders": len(orders),
        "k6": {"attempts": attempts, "accepted": count("orders_accepted"), "throttled429": count("orders_throttled"),
               "failed": count("orders_failed"), "acceptLatencyMs": {k: round(v, 1) for k, v in lat.items()}},
        "throughput": {"sustained3minPerS": round(sustained, 1), "peak10sPerS": round(peak_10s, 1)},
        "completionS": {k: {"p50": round(pct(v, 50), 1), "p95": round(pct(v, 95), 1), "max": round(max(v), 1), "n": len(v)} for k, v in completion.items()},
        "outcomes": {f"{k}->{s}": n for (k, s), n in sorted(outcomes.items())}, "offPath": off_path[:20], "offPathCount": len(off_path),
        "money": {"debits": str(debits_total), "credits": str(credits_total), "net": str(debits_total - credits_total),
                  "fulfilled": str(fulfilled_total), "lost": str(lost), "mismatches": money_bad[:20]},
        "failureReasons": dict(Counter(o.get("failureReason", "")[:60] for o in orders.values() if o["status"] == "FAILED").most_common(8)),
        "unexpectedDeclines": bad_declines[:20], "unexpectedDeclineCount": len(bad_declines),
        "notTerminal": not_terminal, "before": run["before"], "after": after, "cloudwatch": cw, "errorRate": error_rate,
    }
    (EVIDENCE / f"upgrade-3.3-load-{args.label}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("orders", "k6", "throughput", "completionS", "outcomes", "offPathCount", "failureReasons", "unexpectedDeclineCount", "money", "notTerminal", "before", "after")}, indent=1, default=str))
    ok = (lost == 0 and not money_bad and not bad_declines and not_terminal == 0 and after["auditor"]["violations"] == 0 and after["auditor"]["stuck"] == 0
          and all(after["dlq"][q] <= run["before"]["dlq"][q] for q in DLQS))
    print("PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
