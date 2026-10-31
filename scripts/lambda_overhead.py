"""Latency and cold start of the FIS-target Lambdas in a time window, from their REPORT log lines (step 3.2).

Used to measure what the AWS FIS extension layer costs when NO experiment is running: run it over a window before
the layer was added and over a window after, with comparable traffic (the e2e suite), and compare.

    python scripts/lambda_overhead.py --since 2026-10-30T00:00:00Z --until 2026-10-31T13:00:00Z --label before
    python scripts/lambda_overhead.py --since <deploy time> --label after

Read-only (CloudWatch Logs Insights). Prints a Markdown table; --out appends it to a file.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from tf_outputs import load_outputs

FUNCTIONS = [
    "reserve-inventory", "request-payment", "payment-provider", "payment-webhook", "fulfill-item",
    "refund-payment", "release-inventory", "write-off-lines", "begin-fulfillment",
]
QUERY = """filter @type = "REPORT"
| stats count(*) as invocations,
        pct(@duration, 50) as p50, pct(@duration, 95) as p95,
        sum(ispresent(@initDuration)) as coldStarts,
        pct(@initDuration, 50) as initP50, pct(@initDuration, 95) as initP95"""


def parse_time(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def query(logs, group: str, start: int, end: int) -> dict:
    qid = logs.start_query(logGroupName=group, startTime=start, endTime=end, queryString=QUERY)["queryId"]
    while True:
        result = logs.get_query_results(queryId=qid)
        if result["status"] in ("Complete", "Failed", "Cancelled"):
            break
        time.sleep(1)
    rows = result.get("results") or [[]]
    return {f["field"]: f["value"] for f in rows[0]} if rows and rows[0] else {}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", default=None)
    parser.add_argument("--label", default="window")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = load_outputs()
    logs = boto3.client("logs", region_name=out["region"])
    start = parse_time(args.since)
    end = parse_time(args.until) if args.until else int(time.time())

    def num(row: dict, key: str) -> str:
        return f"{float(row[key]):.0f}" if row.get(key) not in (None, "") else "-"

    lines = [
        f"### {args.label}: {datetime.fromtimestamp(start, timezone.utc):%Y-%m-%d %H:%M} to {datetime.fromtimestamp(end, timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        "| Function | Invocations | p50 ms | p95 ms | Cold starts | Init p50 ms | Init p95 ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for fn in FUNCTIONS:
        row = query(logs, f"/aws/lambda/order-saga-{fn}", start, end)
        lines.append(
            f"| {fn} | {row.get('invocations', '0')} | {num(row, 'p50')} | {num(row, 'p95')} | {num(row, 'coldStarts')} | "
            f"{num(row, 'initP50')} | {num(row, 'initP95')} |"
        )
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with args.out.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
