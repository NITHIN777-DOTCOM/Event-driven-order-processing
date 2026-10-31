"""Invariant auditor, from a laptop: the same checks as Lambda order-saga-invariant-auditor (src/common/invariants.py).

    python scripts/audit_invariants.py                 # audit twice (confirmed violations only), print the report
    python scripts/audit_invariants.py --invoke        # run the DEPLOYED Lambda instead (publishes metrics -> alarms)
    python scripts/audit_invariants.py --out FILE.md   # also write the report as Markdown
    python scripts/audit_invariants.py --json          # machine-readable summary on stdout (used by chaos_run.py)

Read-only: scans the tables (paginated, strongly consistent) and describes executions; writes nothing to AWS.
Exit code: 0 = no violations, 1 = violations (STUCK alone does not fail the run; it is printed and alarmed).

Products without a stored `seededStock` (rows seeded before step 3.2) are compared against the catalogue in
seed_inventory.py / oversell_race.py with --catalogue-fallback, which `seed_inventory.py --stamp-seeded-stock` then
records on the row (only where the counters already add up to it).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common.invariants import AuditResult, audit, confirm, load_snapshot  # noqa: E402
from tf_outputs import load_outputs  # noqa: E402

CONFIRM_DELAY_SECONDS = 10


def catalogue_seed() -> dict[str, int]:
    """productId -> seeded units, from the seeding scripts (the source of truth before seededStock was stored)."""
    from seed_inventory import PRODUCTS

    seeds = {p["productId"]: int(p["stock"]) for p in PRODUCTS}
    seeds.update({"RACE-1": 20, "RACE-X": 10, "RACE-Y": 10})  # oversell_race.RACE_PRODUCTS (not imported: it logs in)
    return seeds


def run_local(out: dict, fallback: bool) -> AuditResult:
    ddb = boto3.resource("dynamodb", region_name=out["region"])
    sfn = boto3.client("stepfunctions", region_name=out["region"])
    tables = {
        "orders": out["orders_table"], "payments": out["payments_table"], "psp_transactions": out["psp_transactions_table"],
        "wallet_txns": out["wallet_txns_table"], "inventory": out["inventory_table"], "write_offs": out["write_offs_table"],
        "holds": out["holds_table"],
    }
    seeds = catalogue_seed() if fallback else {}

    def snapshot():
        snap = load_snapshot(ddb, tables)
        for product in snap.inventory:
            if "seededStock" not in product and product["productId"] in seeds:
                product["seededStock"] = seeds[product["productId"]]
        return snap

    def describe(arn: str) -> str:
        return sfn.describe_execution(executionArn=arn)["status"]

    first = audit(snapshot())
    if not (first.violations or first.stuck):
        return first
    if first.violations:
        time.sleep(CONFIRM_DELAY_SECONDS)
    return confirm(first, audit(snapshot(), describe_execution=describe))


def run_lambda(out: dict) -> dict:
    client = boto3.client("lambda", region_name=out["region"])
    resp = client.invoke(FunctionName=out["invariant_auditor_function_name"], Payload=json.dumps({"source": "manual"}).encode())
    payload = json.loads(resp["Payload"].read())
    if resp.get("FunctionError"):
        raise SystemExit(f"auditor failed: {payload}")
    return payload


def report(summary: dict, violations: list[dict], stuck: list[dict], parked: int) -> str:
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"## Invariant audit {when}",
        "",
        f"- Violations: **{summary['violations']}** · Stuck: **{summary['stuck']}** · Parked (dead-lettered by design): {parked}",
        f"- Per invariant: {', '.join(f'{k} {v}' for k, v in summary['perInvariant'].items())}",
        f"- Stats: {', '.join(f'{k} {v}' for k, v in sorted(summary['stats'].items()))}",
    ]
    if violations:
        lines += ["", "| Invariant | Subject | Detail |", "|---|---|---|"] + [f"| {v['invariant']} | `{v['subject']}` | {v['detail']} |" for v in violations]
    if stuck:
        lines += ["", "| Stuck order | Status | Detail |", "|---|---|---|"] + [f"| `{s['subject']}` | {s['invariant']} | {s['detail']} |" for s in stuck]
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--invoke", action="store_true", help="run the deployed auditor Lambda (publishes metrics)")
    parser.add_argument("--catalogue-fallback", action="store_true", help="use the seeding scripts' stock for rows without seededStock")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--out", type=Path, help="append the Markdown report to this file")
    args = parser.parse_args()
    out = load_outputs()

    if args.invoke:
        payload = run_lambda(out)
        summary = {k: payload[k] for k in ("violations", "stuck", "parked", "perInvariant", "stats")}
        violations, stuck = payload["violationList"], payload["stuckList"]
    else:
        result = run_local(out, args.catalogue_fallback)
        summary = result.summary()
        violations = [f.__dict__ for f in result.violations]
        stuck = [f.__dict__ for f in result.stuck]

    if args.json:
        print(json.dumps({**summary, "violationList": violations, "stuckList": stuck}, default=str))
    else:
        print(report(summary, violations, stuck, summary["parked"]))
    if args.out:
        with args.out.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(report(summary, violations, stuck, summary["parked"]) + "\n")
    return 1 if summary["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
