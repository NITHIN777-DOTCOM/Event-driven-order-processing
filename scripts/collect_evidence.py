"""Collect monitoring evidence from the live account into docs/evidence/.

    python scripts/collect_evidence.py --order-id ORD-20261022-13c33683

Writes docs/evidence/phase3-monitoring.md plus PNGs of the dashboard graphs (rendered by CloudWatch
with GetMetricWidgetImage) under docs/evidence/phase3/. It records:
  - every order-saga alarm, its state and its reason; and the SNS actions the DLQ alarm executed
  - order KPIs for the time window (started / succeeded / failed / success rate)
  - the X-Ray service map edges
  - the output of the saved "Trace one order" Logs Insights query for --order-id
Read-only: it never changes any AWS resource.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

from tf_outputs import load_outputs

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence"
IMAGE_DIR = EVIDENCE_DIR / "phase3"

OUT = load_outputs()
REGION = OUT["region"]
PREFIX = "order-saga"

cloudwatch = boto3.client("cloudwatch", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)
xray = boto3.client("xray", region_name=REGION)


def alarms() -> list[dict]:
    return cloudwatch.describe_alarms(AlarmNamePrefix=f"{PREFIX}-")["MetricAlarms"]


def alarm_actions(alarm_name: str) -> list[str]:
    items = cloudwatch.describe_alarm_history(AlarmName=alarm_name, HistoryItemType="Action", MaxRecords=10)
    return [f"{i['Timestamp']:%Y-%m-%d %H:%M:%S} UTC - {i['HistorySummary']}" for i in items["AlarmHistoryItems"]]


def order_kpis(minutes: int) -> dict[str, float]:
    end = datetime.now(timezone.utc)
    queries = [
        {
            "Id": name.lower(),
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/States",
                    "MetricName": f"Executions{name}",
                    "Dimensions": [{"Name": "StateMachineArn", "Value": OUT["state_machine_arn"]}],
                },
                "Period": minutes * 60,
                "Stat": "Sum",
            },
        }
        for name in ("Started", "Succeeded", "Failed")
    ]
    result = cloudwatch.get_metric_data(MetricDataQueries=queries, StartTime=end - timedelta(minutes=minutes), EndTime=end)
    return {r["Id"]: sum(r["Values"]) for r in result["MetricDataResults"]}


def render_dashboard_images(minutes: int) -> list[tuple[str, Path]]:
    """Render each time-series widget of the live dashboard to a PNG."""
    body = json.loads(cloudwatch.get_dashboard(DashboardName=f"{PREFIX}-dashboard")["DashboardBody"])
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    rendered = []
    for index, widget in enumerate(body["widgets"]):
        props = widget.get("properties", {})
        if widget["type"] != "metric" or props.get("view") != "timeSeries":
            continue
        spec = {**props, "start": f"-PT{minutes}M", "end": "P0D", "width": 900, "height": 360}
        png = cloudwatch.get_metric_widget_image(MetricWidget=json.dumps(spec))["MetricWidgetImage"]
        path = IMAGE_DIR / f"{index:02d}-{_slug(props['title'])}.png"
        path.write_bytes(png)
        rendered.append((props["title"], path))
    return rendered


def _slug(text: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in text).split())[:50]


def service_map_edges(minutes: int) -> list[str]:
    now = time.time()
    graph = xray.get_service_graph(StartTime=now - minutes * 60, EndTime=now)["Services"]
    names = {s["ReferenceId"]: f"{s['Name'].rsplit('/', 1)[-1]} ({s['Type']})" for s in graph}
    edges = {f"{names[s['ReferenceId']]} -> {names[e['ReferenceId']]}" for s in graph for e in s.get("Edges", [])}
    return sorted(edges)


def trace_order(order_id: str) -> list[dict]:
    """Run the saved 'Trace one order' query for one orderId."""
    definition = next(
        q for q in logs.describe_query_definitions(queryDefinitionNamePrefix=f"{PREFIX}/Trace one order")["queryDefinitions"]
    )
    query = definition["queryString"].replace("ORD-PASTE-ORDER-ID-HERE", order_id)
    end = int(time.time())
    query_id = logs.start_query(
        logGroupNames=definition["logGroupNames"], startTime=end - 6 * 3600, endTime=end, queryString=query
    )["queryId"]
    while True:
        result = logs.get_query_results(queryId=query_id)
        if result["status"] in ("Complete", "Failed", "Cancelled", "Timeout"):
            break
        time.sleep(1)
    return [{field["field"]: field["value"] for field in row} for row in result["results"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--order-id", required=True, help="orderId to run the 'Trace one order' query for")
    parser.add_argument("--minutes", type=int, default=60, help="time window for metrics, images and service map")
    args = parser.parse_args()

    alarm_list = alarms()
    kpis = order_kpis(args.minutes)
    images = render_dashboard_images(args.minutes)
    edges = service_map_edges(args.minutes)
    trace = trace_order(args.order_id)
    dlq_actions = alarm_actions(f"{PREFIX}-dlq-not-empty")

    links = OUT["console_links"]
    rate = 100 * kpis["succeeded"] / kpis["started"] if kpis.get("started") else 0
    lines = [
        "# Phase 3 evidence: monitoring, alarms, tracing",
        "",
        f"Collected: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC · Region: {REGION} · Window: last {args.minutes} min",
        f"Command: `python scripts/collect_evidence.py --order-id {args.order_id}`",
        "",
        f"- Dashboard: {links['dashboard']}",
        f"- Alarms: {links['alarms']}",
        f"- X-Ray service map: {links['xray_map']}",
        "",
        "## Orders in the window (Step Functions metrics)",
        "",
        "| Started | Succeeded | Failed | Success rate |",
        "|---|---|---|---|",
        f"| {kpis.get('started', 0):.0f} | {kpis.get('succeeded', 0):.0f} | {kpis.get('failed', 0):.0f} | {rate:.1f}% |",
        "",
        "## Alarms",
        "",
        "| Alarm | State | Reason |",
        "|---|---|---|",
    ]
    for alarm in sorted(alarm_list, key=lambda a: a["AlarmName"]):
        reason = alarm["StateReason"].replace("|", "/")[:160]
        lines.append(f"| `{alarm['AlarmName']}` | **{alarm['StateValue']}** | {reason} |")
    lines += ["", "SNS actions executed by `order-saga-dlq-not-empty` (this sends the ops-alert email):", ""]
    lines += [f"- {a}" for a in dlq_actions] or ["- (none yet)"]

    lines += ["", "## Dashboard graphs (rendered by CloudWatch GetMetricWidgetImage)", ""]
    for title, path in images:
        lines += [f"### {title}", "", f"![{title}]({path.relative_to(EVIDENCE_DIR).as_posix()})", ""]

    lines += ["## X-Ray service map edges", "", "```"] + edges + ["```", ""]
    lines += [
        "Notes on tracing:",
        "- API Gateway **HTTP APIs** don't support X-Ray (only REST APIs do), so the map starts at the",
        "  `create_order` Lambda and shows the caller as `client`.",
        "- With botocore patched (`src/common/tracing.py`), the trace continues create_order -> SQS -> start_workflow",
        "  -> StepFunctions -> reserve / payment / release Lambdas -> DynamoDB tables, as ONE trace ID.",
        "- The state machine's own segment (AWS::StepFunctions::StateMachine) doesn't show up, even though tracing",
        "  is enabled, its role has the 4 X-Ray permissions, and AssumeRole succeeds (checked in CloudTrail). Step",
        "  Functions does pass the trace header on, because the Lambdas it invokes appear in the same trace. So its",
        "  direct DynamoDB and SNS integrations are visible in the execution graph and in its logs, not on the map.",
        "",
    ]

    lines += [
        f"## Logs Insights: saved query 'order-saga/Trace one order' for `{args.order_id}`",
        "",
        "| Time | Log group | Source | Level | Event (message / state / error) |",
        "|---|---|---|---|---|",
    ]
    for row in trace:
        group = row.get("@log", "").split(":")[-1]
        text = row.get("event", "").replace("|", "/").replace("\n", " ")
        text = text if len(text) <= 140 else text[:137] + "..."
        lines.append(
            f"| {row.get('@timestamp', '')} | `{group}` | {row.get('source', '')} | {row.get('level', '')} | {text} |"
        )

    out = EVIDENCE_DIR / "phase3-monitoring.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out} ({len(images)} graph images, {len(trace)} trace rows, {len(edges)} service-map edges)")


if __name__ == "__main__":
    main()
