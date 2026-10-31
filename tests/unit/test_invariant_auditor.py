"""Lambda order-saga-invariant-auditor (moto): scans the real table shapes, confirms violations, publishes metrics."""

from __future__ import annotations

from decimal import Decimal

import boto3
import pytest

from conftest import seed_order


@pytest.fixture
def auditor(load_handler, monkeypatch):
    monkeypatch.setenv("CONFIRM_DELAY_SECONDS", "0")
    handler = load_handler("invariant_auditor")
    published: list[list[dict]] = []
    monkeypatch.setattr(handler.cloudwatch, "put_metric_data", lambda **kw: published.append(kw["MetricData"]))
    handler.published = published
    return handler


def metric(published, name, invariant=None):
    for datum in published[-1]:
        dims = {d["Name"]: d["Value"] for d in datum.get("Dimensions", [])}
        if datum["MetricName"] == name and dims.get("Invariant") == invariant:
            return datum["Value"]
    raise KeyError(name)


def stamp_seed(aws):
    """The moto inventory as seed_inventory.py would leave it (seededStock = what it holds now)."""
    for item in aws.inventory.scan()["Items"]:
        total = sum(int(item.get(k, 0)) for k in ("stock", "held", "reserved", "sold", "writtenOff"))
        aws.inventory.update_item(Key={"productId": item["productId"]}, UpdateExpression="SET seededStock = :s, seededAt = :t",
                                  ExpressionAttributeValues={":s": total, ":t": "2026-01-01T00:00:00.000Z"})


def test_clean_tables_publish_zero(aws, auditor):
    stamp_seed(aws)
    result = auditor.lambda_handler({"source": "manual"}, None)
    assert result["violations"] == 0 and result["stuck"] == 0
    assert metric(auditor.published, "Violations") == 0
    with pytest.raises(KeyError):  # per-invariant metrics only when non-zero (cost)
        metric(auditor.published, "Violations", "I5")


def test_a_lost_unit_is_reported_and_published(aws, auditor):
    stamp_seed(aws)
    aws.inventory.update_item(Key={"productId": "WIRELESS-MOUSE"}, UpdateExpression="SET stock = stock - :one", ExpressionAttributeValues={":one": 1})
    result = auditor.lambda_handler({}, None)
    assert result["violations"] >= 1
    assert any(v["invariant"] == "I5" and v["subject"] == "WIRELESS-MOUSE" for v in result["violationList"])
    assert metric(auditor.published, "Violations", "I5") >= 1


def test_a_stuck_order_is_labelled_with_its_execution_status(aws, auditor, monkeypatch):
    stamp_seed(aws)
    seed_order(aws.orders, status="FULFILLING", createdAt="2026-01-01T00:00:00.000Z", executionArn="arn:aws:states:x:execution:y:ORD-1")
    monkeypatch.setattr(auditor, "describe_execution", lambda arn: "FAILED")
    result = auditor.lambda_handler({}, None)
    assert result["stuck"] == 1 and "redrive" in result["stuckList"][0]["detail"]
    assert metric(auditor.published, "Stuck") == 1


def test_completed_order_without_payment_is_a_violation(aws, auditor):
    stamp_seed(aws)
    seed_order(aws.orders, status="COMPLETED", createdAt="2026-10-30T00:00:00.000Z", updatedAt="2026-10-30T00:00:00.000Z",
               totalAmount=Decimal("5097.00"))
    result = auditor.lambda_handler({}, None)
    assert {v["invariant"] for v in result["violationList"]} >= {"I1", "I6"}
