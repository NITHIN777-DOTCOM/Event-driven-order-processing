"""Reconciliation job: audit invariants I1-I9 over every order, payment, ledger entry and stock counter (step 3.2).

Invoked hourly by EventBridge Scheduler (schedule order-saga-invariant-audit-hourly), every minute by
scripts/chaos_run.py during chaos experiments, or on demand (Lambda console "Test", or `aws lambda invoke`).
Read-only: it never repairs anything. A finding is a page for a human, with the runbook in the alarm description.

What it does:
  1. Audit (common/invariants.py: paginated, strongly consistent scans of 7 tables), wait CONFIRM_DELAY_SECONDS,
     audit again, and keep only the violations found BOTH times (a live change between scans can fool one audit).
  2. Label each STUCK order with its Step Functions execution status (FAILED = parked, redrive it).
  3. Log one JSON line per finding (orderId / productId, invariant, detail) and a summary line.
  4. Publish CloudWatch metrics in namespace OrderSaga/Audit: Violations, Stuck, Parked, and Violations per
     invariant (dimension Invariant = I1..I9, only when non-zero). Alarms order-saga-invariant-violation and
     order-saga-stuck-orders fire on > 0; the violation alarm is also the stop condition of every FIS experiment.
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.invariants import audit, confirm, load_snapshot
from common.logger import get_logger
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

TABLES = {
    "orders": os.environ["ORDERS_TABLE"],
    "payments": os.environ["PAYMENTS_TABLE"],
    "psp_transactions": os.environ["PSP_TABLE"],
    "wallet_txns": os.environ["WALLET_TXNS_TABLE"],
    "inventory": os.environ["INVENTORY_TABLE"],
    "write_offs": os.environ["WRITE_OFFS_TABLE"],
    "holds": os.environ["HOLDS_TABLE"],
}
NAMESPACE = "OrderSaga/Audit"
CONFIRM_DELAY_SECONDS = int(os.environ.get("CONFIRM_DELAY_SECONDS", "10"))
MAX_LOGGED_FINDINGS = 200  # per class; the counts are always complete

dynamodb = boto3.resource("dynamodb")
sfn = boto3.client("stepfunctions")
cloudwatch = boto3.client("cloudwatch")
logger = get_logger("invariant_auditor")


def describe_execution(arn: str) -> str:
    try:
        return sfn.describe_execution(executionArn=arn)["status"]
    except ClientError as err:
        return f"unknown ({err.response['Error']['Code']})"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    source = (event or {}).get("source", "manual")  # "schedule" | "chaos_run" | "manual"
    started = time.monotonic()
    first = audit(load_snapshot(dynamodb, TABLES))
    result = first
    if first.violations or first.stuck:
        # Look again: violations must show up twice to count (confirm()), and STUCK orders get their execution status.
        if first.violations:
            time.sleep(CONFIRM_DELAY_SECONDS)
        result = confirm(first, audit(load_snapshot(dynamodb, TABLES), describe_execution=describe_execution))

    log = logger.bind(auditSource=source)
    for kind, findings in (("violation", result.violations), ("stuck", result.stuck), ("parked", result.parked)):
        for finding in findings[:MAX_LOGGED_FINDINGS]:
            fields = {"orderId": finding.subject} if finding.subject.startswith(("ORD-", "OUTBOX-")) else {"subject": finding.subject}
            level = log.error if kind == "violation" else log.warning if kind == "stuck" else log.info
            level(f"Audit {kind}", auditFinding=kind, invariant=finding.invariant, detail=finding.detail, **fields)

    summary = result.summary()
    publish(summary)
    log.info("Audit finished", auditEvent="summary", durationMs=int((time.monotonic() - started) * 1000), **summary)
    return {
        **summary,
        "violationList": [f.__dict__ for f in result.violations[:MAX_LOGGED_FINDINGS]],
        "stuckList": [f.__dict__ for f in result.stuck[:MAX_LOGGED_FINDINGS]],
    }


def publish(summary: dict[str, Any]) -> None:
    """Violations, Stuck and Parked: one datapoint each per run, 0 included, so the alarms return to OK once fixed.

    Per-invariant counts (dimension Invariant = I1..I9) are published only when non-zero. A custom metric costs
    $0.30/month for every month (pro rata per hour) it receives data, so nine always-published zeros would cost
    ~$2.70/month to say nothing; the full breakdown is in every summary log line (perInvariant) anyway.
    """
    data = [
        {"MetricName": "Violations", "Value": summary["violations"], "Unit": "Count"},
        {"MetricName": "Stuck", "Value": summary["stuck"], "Unit": "Count"},
        {"MetricName": "Parked", "Value": summary["parked"], "Unit": "Count"},
    ]
    data += [
        {"MetricName": "Violations", "Dimensions": [{"Name": "Invariant", "Value": inv}], "Value": count, "Unit": "Count"}
        for inv, count in summary["perInvariant"].items()
        if count
    ]
    cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=data)
