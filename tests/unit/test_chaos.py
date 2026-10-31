"""Step 3.2 chaos switches (src/common/chaos.py): E3 "crash after write".

Three properties, each on the real handlers (moto):
  1. Inert by default: with CHAOS_ENABLED unset/false an order carrying a chaos field behaves exactly as without it,
     and POST /orders refuses the field.
  2. When enabled, the handler performs its write and THEN raises ChaosCrashAfterWrite.
  3. The retry (what Step Functions / SQS / DemoPay does next) finds the write done, takes the idempotent path,
     returns normally, and moves nothing twice.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from common import chaos
from conftest import api_event, ledger, psp_request, seed_intent, seed_order, sqs_event, stock_of


@pytest.fixture
def chaos_on(monkeypatch):
    monkeypatch.setenv("CHAOS_ENABLED", "true")


def crash(point: str) -> dict:
    return {"chaos": f"crash_after:{point}"}


def test_switch_is_inert_unless_enabled(monkeypatch):
    item = crash("reserve")
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    chaos.crash_after_write(item, "reserve")  # no exception
    monkeypatch.setenv("CHAOS_ENABLED", "false")
    chaos.crash_after_write(item, "reserve")
    assert chaos.crash_point(item) is None
    monkeypatch.setenv("CHAOS_ENABLED", "true")
    chaos.crash_after_write(item, "fulfill")  # a different point: nothing
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        chaos.crash_after_write(item, "reserve")
    chaos.crash_after_write({"chaos": "crash_after:nonsense"}, "reserve")  # unknown points never fire


def test_create_order_refuses_the_chaos_field_while_disabled(aws, load_handler, monkeypatch):
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    body = {"customerName": "Asha", "items": [{"productId": "WIRELESS-MOUSE", "quantity": 1}], **crash("reserve")}
    result = load_handler("create_order").lambda_handler(api_event(body), None)
    assert result["statusCode"] == 400 and "chaos is disabled" in result["body"]


def test_create_order_stores_the_chaos_field_while_enabled(aws, load_handler, chaos_on):
    handler = load_handler("create_order")
    body = {"customerName": "Asha", "items": [{"productId": "WIRELESS-MOUSE", "quantity": 1}]}
    bad = handler.lambda_handler(api_event({**body, "chaos": "crash_after:everything"}), None)
    assert bad["statusCode"] == 400
    ok = handler.lambda_handler(api_event({**body, **crash("fulfill")}), None)
    order = aws.orders.get_item(Key={"orderId": json.loads(ok["body"])["orderId"]})["Item"]
    assert order["chaos"] == "crash_after:fulfill"


def test_reserve_crash_after_write_then_retry_reserves_once(aws, load_handler, chaos_on):
    handler = load_handler("reserve_inventory")
    order = seed_order(aws.orders, **crash("reserve"))
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        handler.lambda_handler({"orderId": order["orderId"]}, None)
    assert stock_of(aws, "WIRELESS-MOUSE") == (98, 2)  # the write happened
    handler.lambda_handler({"orderId": order["orderId"]}, None)  # the retry: idempotent, no crash
    assert stock_of(aws, "WIRELESS-MOUSE") == (98, 2)  # not reserved twice


def test_reserve_unchanged_when_disabled(aws, load_handler, monkeypatch):
    monkeypatch.setenv("CHAOS_ENABLED", "false")
    order = seed_order(aws.orders, **crash("reserve"))
    load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)
    assert stock_of(aws, "WIRELESS-MOUSE") == (98, 2)


def test_debit_crash_then_redelivery_never_debits_twice(aws, payments, chaos_on):
    order = seed_order(aws.orders)
    seed_intent(aws, order)
    request = psp_request(order, **crash("debit"))
    first = payments.provider.lambda_handler(sqs_event(request), None)
    assert first["batchItemFailures"]  # crashed after the debit: SQS will redeliver
    assert len(ledger(aws)) == 1 and payments.callbacks == []
    second = payments.provider.lambda_handler(sqs_event(request, receive_count=2), None)
    assert second == {"batchItemFailures": []}
    assert [t for t, _ in ledger(aws)] == ["DEBIT"]  # one debit
    assert len(payments.callbacks) == 1  # the callback goes out on the redelivery


def test_webhook_capture_crash_then_redelivered_callback_resumes_once(aws, payments, chaos_on):
    order = seed_order(aws.orders)
    seed_intent(aws, order, chaos="crash_after:webhook_capture")
    first = payments.provider.lambda_handler(sqs_event(psp_request(order)), None)
    # In-process the crash propagates through the fake HTTP hop (live: API Gateway answers 500); either way DemoPay
    # marks the request failed and SQS redelivers it.
    assert first["batchItemFailures"]
    assert aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]["status"] == "SUCCEEDED"
    assert payments.sfn.calls == []
    payments.provider.lambda_handler(sqs_event(psp_request(order), receive_count=2), None)
    assert [kind for kind, _ in payments.sfn.calls] == ["success"]  # resumed exactly once
    assert [t for t, _ in ledger(aws)] == ["DEBIT"]


def test_fulfill_crash_then_retry_moves_stock_once(aws, load_handler, chaos_on):
    order = seed_order(aws.orders, **crash("fulfill"))
    load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)
    fulfill = load_handler("fulfill_item")
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)
    assert fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)["status"] == "FULFILLED"
    item = aws.inventory.get_item(Key={"productId": "WIRELESS-MOUSE"})["Item"]
    assert (item["reserved"], item["sold"]) == (0, 2)


def test_write_off_crash_then_retry_writes_off_once(aws, load_handler, chaos_on):
    order = seed_order(aws.orders, **crash("write_off"))
    load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)
    handler = load_handler("write_off_lines")
    event = {"orderId": order["orderId"], "lines": [{"lineId": "L2", "reason": "damaged"}]}
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        handler.lambda_handler(event, None)
    assert handler.lambda_handler(event, None)["unitsWrittenOff"] == 0  # the retry finds it done
    item = aws.inventory.get_item(Key={"productId": "MECH-KEYBOARD"})["Item"]
    assert (item["reserved"], item["writtenOff"]) == (0, 1)


def test_release_crash_then_retry_releases_once(aws, load_handler, chaos_on):
    order = seed_order(aws.orders, **crash("release"))
    load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)
    release = load_handler("release_inventory")
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        release.lambda_handler({"orderId": order["orderId"]}, None)
    assert release.lambda_handler({"orderId": order["orderId"]}, None)["released"] is False
    assert stock_of(aws, "WIRELESS-MOUSE") == (100, 0)


@pytest.fixture
def refund_handler(load_handler, payments, monkeypatch):
    handler = load_handler("refund_payment")

    def call_provider(_client, _fn, intent_id, line=None, note=""):
        request = {"operation": "refund", "paymentIntentId": intent_id, **({"note": note} if note else {})}
        if line:
            request.update(lineId=line["lineId"], amount=str(line["amount"]), note=line.get("note", ""))
        return payments.provider.lambda_handler(request, None)

    monkeypatch.setattr(handler, "invoke_provider_refund", call_provider)
    return handler


def paid_order(aws, load_handler, payments, **extra):
    order = seed_order(aws.orders, **extra)
    load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)
    seed_intent(aws, order)
    payments.provider.lambda_handler(sqs_event(psp_request(order)), None)
    return order


def test_line_refund_crash_then_retry_credits_once(aws, load_handler, payments, refund_handler, chaos_on):
    order = paid_order(aws, load_handler, payments, **crash("line_refund"))
    event = {"orderId": order["orderId"], "lineIds": ["L2"]}
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        refund_handler.lambda_handler(event, None)
    refund_handler.lambda_handler(event, None)
    assert [t for t, _ in ledger(aws)] == ["DEBIT", "CREDIT"]
    assert ledger(aws)[1][1] == Decimal("3499.00")


def test_full_refund_crash_then_retry_credits_once(aws, load_handler, payments, refund_handler, chaos_on):
    order = paid_order(aws, load_handler, payments, **crash("full_refund"))
    with pytest.raises(chaos.ChaosCrashAfterWrite):
        refund_handler.lambda_handler({"orderId": order["orderId"]}, None)
    assert refund_handler.lambda_handler({"orderId": order["orderId"]}, None)["refunded"] is False  # already done
    assert [t for t, _ in ledger(aws)] == ["DEBIT", "CREDIT"]
