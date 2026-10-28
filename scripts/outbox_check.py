"""Rollout checks for the transactional outbox (upgrade step 1.1), against the LIVE deployment.

    python scripts/outbox_check.py timing --label before --dual   # commit A: direct send + pipe both active
    python scripts/outbox_check.py timing --label after           # commit B: pipe only
    python scripts/outbox_check.py cost --minutes 60              # measured stream reads -> monthly cost

timing  Places N orders one at a time (simulate=none) and, for each, measures:
          - client:   POST /orders -> GET shows COMPLETED (polled every 0.25 s)
          - delivery: PENDING -> PROCESSING from statusHistory (write -> start_workflow picked it up)
          - saga:     PENDING -> COMPLETED from statusHistory
        and checks exactly 1 execution and exactly 1 DEBIT per order. With --dual it also checks that the
        order was delivered TWICE (one "Saga execution started" + at least one "Duplicate message ignored"
        in start_workflow's logs): the idempotent consumer at work.
cost    Reads the CloudWatch metric SuccessfulRequestLatency (Operation=GetRecords) SampleCount for the
        orders stream = the number of billed GetRecords calls the pipe made, and projects a 30-day month.

Results are printed and written to docs/evidence/upgrade-1.1/<label>.md (or cost.md).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

from e2e_test import (
    OUT,
    REGION,
    USER,
    count_log_lines,
    debits_for,
    executions_named,
    get_order,
    place_order,
    set_wallet,
)

EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "upgrade-1.1"
PRODUCT = "DESK-MAT"  # cheap, plenty of stock, not used by e2e_test.py
START_WORKFLOW_LOGS = "/aws/lambda/order-saga-start-workflow"

# DynamoDB Streams: price per 100,000 read request units from the AWS pricing page example, and the
# monthly free tier (2.5M stream read requests per Region per payer account).
STREAM_READ_PRICE_PER_100K = 0.02
STREAM_READ_FREE_TIER = 2_500_000
SECONDS_PER_MONTH = 30 * 24 * 3600


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ms_between(order: dict, start_status: str, end_status: str) -> float | None:
    """Milliseconds between the FIRST start_status and the LAST end_status entries in statusHistory."""
    history = order.get("statusHistory", [])
    starts = [parse_ts(e["timestamp"]) for e in history if e["status"] == start_status]
    ends = [parse_ts(e["timestamp"]) for e in history if e["status"] == end_status]
    if not starts or not ends:
        return None
    return (ends[-1] - starts[0]).total_seconds() * 1000


def wait_completed(order_id: str, timeout: float = 90) -> tuple[dict, float]:
    """Poll GET /orders/{id} every 0.25 s; return (order, seconds until a terminal status was seen)."""
    started = time.monotonic()
    order: dict = {}
    while time.monotonic() - started < timeout:
        order = get_order(order_id)
        if order.get("status") in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.25)
    return order, time.monotonic() - started


def summary(values: list[float]) -> str:
    values = sorted(values)
    p95 = values[min(len(values) - 1, round(0.95 * (len(values) - 1)))]
    return f"min {values[0]:.0f} · median {statistics.median(values):.0f} · p95 {p95:.0f} · max {values[-1]:.0f}"


def run_timing(label: str, count: int, dual: bool) -> int:
    set_wallet(USER)  # DemoPay: start from ₹10,00,000
    # 2 min of slack: the local clock can run ahead of CloudWatch; orderIds are unique, so nothing else matches.
    since_ms = int(time.time() * 1000) - 120_000
    rows, failures = [], []

    for index in range(count):
        posted = time.monotonic()
        code, body = place_order(PRODUCT, 1, "none")
        order_id = body.get("orderId")
        if code != 202 or not order_id:
            failures.append(f"order {index + 1}: POST /orders returned {code} {body}")
            continue
        order, _ = wait_completed(order_id)
        client_ms = (time.monotonic() - posted) * 1000
        rows.append(
            {
                "orderId": order_id,
                "status": order.get("status"),
                "client_ms": client_ms,
                "delivery_ms": ms_between(order, "PENDING", "PROCESSING"),
                "saga_ms": ms_between(order, "PENDING", "COMPLETED"),
            }
        )
        print(f"  {order_id}  {order.get('status'):<10} client {client_ms:6.0f} ms  delivery {rows[-1]['delivery_ms']} ms")
        time.sleep(1)

    # Correctness per order: one execution, one debit, and (dual mode) two deliveries.
    for row in rows:
        oid = row["orderId"]
        row["executions"] = executions_named({oid})
        row["debits"] = debits_for(oid)
        if row["status"] != "COMPLETED":
            failures.append(f"{oid}: status {row['status']} (expected COMPLETED)")
        if row["executions"] != 1:
            failures.append(f"{oid}: {row['executions']} executions (expected 1)")
        if row["debits"] != 1:
            failures.append(f"{oid}: {row['debits']} DEBIT entries (expected 1)")
        if dual:
            # Two deliveries = two log lines in total. Usually 1 start + 1 duplicate; if both arrive while the
            # execution is still starting, Step Functions treats the identical StartExecution as idempotent
            # and both log a start. Either way the execution count above must still be exactly 1.
            for _ in range(12):
                row["started_logs"] = count_log_lines(START_WORKFLOW_LOGS, "Saga execution started", oid, since_ms=since_ms)
                row["duplicate_logs"] = count_log_lines(START_WORKFLOW_LOGS, "Duplicate message ignored", oid, since_ms=since_ms)
                if row["started_logs"] + row["duplicate_logs"] >= 2:
                    break
                time.sleep(5)
            if row["started_logs"] + row["duplicate_logs"] < 2:
                failures.append(
                    f"{oid}: start_workflow logged {row['started_logs']} starts / {row['duplicate_logs']} duplicates "
                    "(expected 2 deliveries: one from create_order, one from the pipe)"
                )

    lines = [
        f"# Outbox timing: {label}",
        "",
        f"Run: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC · `python scripts/outbox_check.py timing --label {label}"
        f"{' --dual' if dual else ''}` · {len(rows)} orders, one at a time, product {PRODUCT}, simulate=none",
        "",
        "| orderId | status | executions | DEBITs |" + (" starts / duplicates logged |" if dual else "")
        + " client POST→COMPLETED (ms) | PENDING→PROCESSING (ms) | PENDING→COMPLETED (ms) |",
        "|---|---|---|---|" + ("---|" if dual else "") + "---|---|---|",
    ]
    for r in rows:
        dual_cell = f" {r['started_logs']} / {r['duplicate_logs']} |" if dual else ""
        lines.append(
            f"| `{r['orderId']}` | {r['status']} | {r['executions']} | {r['debits']} |{dual_cell}"
            f" {r['client_ms']:.0f} | {r['delivery_ms']:.0f} | {r['saga_ms']:.0f} |"
        )
    if rows:
        lines += [
            "",
            f"- client POST→COMPLETED (ms): {summary([r['client_ms'] for r in rows])}",
            f"- PENDING→PROCESSING (ms): {summary([r['delivery_ms'] for r in rows])}",
            f"- PENDING→COMPLETED (ms): {summary([r['saga_ms'] for r in rows])}",
        ]
    lines += ["", f"**Result: {'PASS' if not failures else 'FAIL'}**"] + [f"- FAIL: {f}" for f in failures]

    write(f"{label}.md", lines)
    return 0 if not failures else 1


def run_cost(minutes: int) -> int:
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(minutes=minutes)
    table = OUT["orders_table"]
    result = cloudwatch.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "getrecords",
                "Expression": (
                    "SEARCH('{AWS/DynamoDB,Operation,StreamLabel,TableName} MetricName=\"SuccessfulRequestLatency\" "
                    f"Operation=\"GetRecords\" TableName=\"{table}\"', 'SampleCount', 300)"
                ),
            }
        ],
        StartTime=start,
        EndTime=end,
    )
    calls = sum(sum(series["Values"]) for series in result["MetricDataResults"])
    per_second = calls / (minutes * 60)
    per_month = per_second * SECONDS_PER_MONTH
    billable = max(0.0, per_month - STREAM_READ_FREE_TIER)
    cost = billable / 100_000 * STREAM_READ_PRICE_PER_100K

    lines = [
        "# Outbox cost: measured DynamoDB stream reads by the pipe",
        "",
        f"Window: {start:%Y-%m-%d %H:%M} -> {end:%H:%M} UTC ({minutes} min) · `python scripts/outbox_check.py cost --minutes {minutes}`",
        "",
        f"- GetRecords calls on the `{table}` stream (CloudWatch SuccessfulRequestLatency SampleCount): **{calls:,.0f}**",
        f"- Rate: **{per_second:.2f} calls/s** (AWS documents a base polling rate of 4/s per shard)",
        f"- Projected 30-day month: **{per_month:,.0f}** stream read requests",
        f"- Minus the {STREAM_READ_FREE_TIER:,} free-tier reads: {billable:,.0f} billable",
        f"- At ${STREAM_READ_PRICE_PER_100K} per 100,000: **≈ ${cost:.2f}/month** at idle "
        "(pipe requests themselves are $0.40/million AFTER filtering, ≈ $0 at demo volume)",
    ]
    write("cost.md", lines)
    return 0


def write(name: str, lines: list[str]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print(f"\nWritten to {path}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # the evidence uses arrows; the Windows console default is cp1252
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    timing = sub.add_parser("timing")
    timing.add_argument("--label", required=True)
    timing.add_argument("--count", type=int, default=10)
    timing.add_argument("--dual", action="store_true", help="commit A: expect two deliveries per order")
    cost = sub.add_parser("cost")
    cost.add_argument("--minutes", type=int, default=60)
    args = parser.parse_args()
    if args.command == "timing":
        return run_timing(args.label, args.count, args.dual)
    return run_cost(args.minutes)


if __name__ == "__main__":
    sys.exit(main())
