"""Per-item fulfillment building blocks (step 2.3): line prices on new orders, picking a line, writing a line off,
DemoPay line refunds (idempotent per line, capped at the charge: I7), and compensation after a line was sold.
Stock conservation is checked as I5: seeded = stock + held + reserved + sold + writtenOff."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from conftest import USER_A, api_event, ledger, psp_request, seed_intent, seed_order, sqs_event, wallet_of

SEEDED = {"WIRELESS-MOUSE": 100, "MECH-KEYBOARD": 2}
MOUSE_LINE, KEYBOARD_LINE = Decimal("1598.00"), Decimal("3499.00")  # 2 x 799, 1 x 3499
TOTAL = MOUSE_LINE + KEYBOARD_LINE


def counters(aws, product):
    item = aws.inventory.get_item(Key={"productId": product}, ConsistentRead=True)["Item"]
    return {key: int(item.get(key, 0)) for key in ("stock", "held", "reserved", "sold", "writtenOff")}


def assert_i5(aws):
    for product, seeded in SEEDED.items():
        c = counters(aws, product)
        assert sum(c.values()) == seeded, f"I5 broken for {product}: {c} vs {seeded}"


def reserve(aws, load_handler, **overrides):
    """A PENDING order (2 mice + 1 keyboard) with its stock reserved, as ReserveInventory leaves it."""
    order = seed_order(aws.orders, **overrides)
    load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)
    return aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]


def stored(aws, order):
    return aws.orders.get_item(Key={"orderId": order["orderId"]}, ConsistentRead=True)["Item"]


def history(aws, order):
    return [entry["status"] for entry in stored(aws, order)["statusHistory"]]


@pytest.fixture
def fulfill(load_handler):
    return load_handler("fulfill_item")


@pytest.fixture
def write_off(load_handler):
    return load_handler("write_off_lines")


@pytest.fixture
def paid(aws, payments):
    """An order with stock reserved and DemoPay's charge of the full amount (webhook: SUCCEEDED)."""

    def _paid(load_handler, **overrides):
        order = reserve(aws, load_handler, **overrides)
        seed_intent(aws, order)
        payments.provider.lambda_handler(sqs_event(psp_request(order)), None)
        return order

    return _paid


@pytest.fixture
def refund(load_handler, payments, monkeypatch):
    """refund_payment whose DemoPay calls (whole or per line) go straight to the provider handler."""
    handler = load_handler("refund_payment")

    def call_provider(_client, _fn, intent_id, line=None, note=""):
        request = {"operation": "refund", "paymentIntentId": intent_id, **({"note": note} if note else {})}
        if line:
            request.update(lineId=line["lineId"], amount=str(line["amount"]), note=line.get("note", ""))
        return payments.provider.lambda_handler(request, None)

    monkeypatch.setattr(handler, "invoke_provider_refund", call_provider)
    return handler


# --- Line prices on new orders ------------------------------------------------------------------------------
def test_new_orders_store_server_side_line_ids_and_amounts(aws, load_handler):
    body = {"customerName": "Asha", "items": [{"productId": "WIRELESS-MOUSE", "quantity": 3}, {"productId": "MECH-KEYBOARD", "quantity": 1}]}
    result = load_handler("create_order").lambda_handler(api_event(body), None)

    order = aws.orders.get_item(Key={"orderId": json.loads(result["body"])["orderId"]})["Item"]
    assert [(i["lineId"], i["lineAmount"]) for i in order["items"]] == [("L1", Decimal("2397.00")), ("L2", Decimal("3499.00"))]
    assert order["totalAmount"] == Decimal("5896.00")  # the sum of the lines


def test_old_orders_without_line_ids_get_the_same_derived_lines():
    from common.orders import order_lines

    lines = order_lines({"orderId": "ORD-1", "items": [{"productId": "A", "name": "A", "quantity": 2, "unitPrice": Decimal("799")}]})

    assert (lines[0]["lineId"], lines[0]["lineAmount"], lines[0]["index"]) == ("L1", Decimal("1598.00"), 0)


# --- fulfill_item --------------------------------------------------------------------------------------------
def test_fulfilling_a_line_moves_its_units_from_reserved_to_sold_once(aws, load_handler, fulfill):
    order = reserve(aws, load_handler)

    first = fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)
    again = fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)  # a retry

    assert first["status"] == again["status"] == "FULFILLED"
    assert counters(aws, "WIRELESS-MOUSE") == {"stock": 98, "held": 0, "reserved": 0, "sold": 2, "writtenOff": 0}
    assert stored(aws, order)["items"][0]["fulfillment"] == "FULFILLED"
    assert history(aws, order).count("ITEM_FULFILLED") == 1
    assert_i5(aws)


@pytest.mark.parametrize(
    ("simulate_line", "unavailable"),
    [(None, {"L2"}), (1, {"L1"}), ("all", {"L1", "L2"})],
    ids=["default-last-line", "line-1", "all-lines"],
)
def test_item_unavailable_targets_the_chosen_line(aws, load_handler, fulfill, simulate_line, unavailable):
    extra = {} if simulate_line is None else {"simulateLine": simulate_line}
    order = reserve(aws, load_handler, simulate="item_unavailable", **extra)

    failed = set()
    for line_id in ("L1", "L2"):
        try:
            fulfill.lambda_handler({"orderId": order["orderId"], "lineId": line_id}, None)
        except fulfill.ItemUnavailable as err:
            assert "damaged in the warehouse" in str(err)
            failed.add(line_id)

    assert failed == unavailable
    assert_i5(aws)  # an unavailable line keeps its units reserved until the write-off


def test_fulfill_refuses_to_sell_units_that_are_not_reserved(aws, fulfill):
    order = seed_order(aws.orders)  # never reserved

    with pytest.raises(RuntimeError, match="refusing to pick"):
        fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)
    assert "fulfillment" not in stored(aws, order)["items"][0]


# --- write_off_lines -----------------------------------------------------------------------------------------
def test_write_off_is_audited_and_idempotent_per_line(aws, load_handler, write_off):
    order = reserve(aws, load_handler)
    event = {"orderId": order["orderId"], "lines": [{"lineId": "L2", "reason": "found damaged"}]}

    first = write_off.lambda_handler(event, None)
    again = write_off.lambda_handler(event, None)

    assert first == {"orderId": order["orderId"], "writtenOffLineIds": ["L2"], "unitsWrittenOff": 1}
    assert again["unitsWrittenOff"] == 0  # nothing moved the second time
    assert counters(aws, "MECH-KEYBOARD") == {"stock": 1, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 1}
    records = aws.write_offs.query(KeyConditionExpression="orderId = :o", ExpressionAttributeValues={":o": order["orderId"]})["Items"]
    assert [(r["lineId"], r["productId"], r["quantity"], r["reason"]) for r in records] == [("L2", "MECH-KEYBOARD", 1, "found damaged")]
    assert stored(aws, order)["items"][1]["fulfillment"] == "WRITTEN_OFF"
    assert_i5(aws)


def test_a_fulfilled_line_is_never_written_off(aws, load_handler, fulfill, write_off):
    order = reserve(aws, load_handler)
    fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)

    with pytest.raises(RuntimeError, match="was fulfilled"):
        write_off.lambda_handler({"orderId": order["orderId"], "lines": [{"lineId": "L1", "reason": "x"}]}, None)
    assert counters(aws, "WIRELESS-MOUSE")["writtenOff"] == 0


# --- DemoPay line refunds (I7) ---------------------------------------------------------------------------------
def test_refunding_the_same_line_twice_credits_once(aws, load_handler, paid, refund):
    order = paid(load_handler)

    first = refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L1"]}, None)
    again = refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L1"]}, None)

    assert first["refundedAmount"] == again["refundedAmount"] == "1598.00"  # 2 x 799 (quantity > 1)
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", MOUSE_LINE)]
    line = stored(aws, order)["items"][0]
    assert line["refundedAmount"] == MOUSE_LINE and line["refundId"].startswith("RF-")
    assert stored(aws, order)["refundedAmount"] == MOUSE_LINE
    assert history(aws, order).count("LINE_REFUNDED") == 1
    intent = aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]
    assert intent["status"] == "SUCCEEDED" and intent["refundedAmount"] == MOUSE_LINE  # partly refunded
    assert "Wireless Mouse" in first["refundedItemsSummary"] and "Mechanical Keyboard" in first["keptItemsSummary"]


def test_refunding_every_line_refunds_the_charge_and_finishes_the_intent(aws, load_handler, paid, refund):
    order = paid(load_handler)

    result = refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L1", "L2"]}, None)

    assert result["refundedAmount"] == f"{TOTAL:.2f}" and result["keptCount"] == 0
    assert wallet_of(aws, USER_A)[0] == Decimal("1000000")  # net 0
    assert aws.payments.get_item(Key={"paymentIntentId": f"PI-{order['orderId']}"})["Item"]["status"] == "REFUNDED"


def test_line_refunds_can_never_exceed_the_charge(aws, load_handler, paid, payments):
    order = paid(load_handler)
    intent_id = f"PI-{order['orderId']}"
    provider = payments.provider
    provider.refund_line(intent_id, "L1", MOUSE_LINE)

    with pytest.raises(provider.RefundRejected, match="would exceed"):
        provider.refund_line(intent_id, "L9", TOTAL)  # only the keyboard's 3499 is left
    with pytest.raises(provider.RefundRejected):
        provider.refund_line(intent_id, "L8", Decimal("0"))
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", MOUSE_LINE)]


def test_the_full_refund_after_a_line_refund_returns_only_the_rest(aws, load_handler, paid, payments):
    order = paid(load_handler)
    intent_id = f"PI-{order['orderId']}"
    payments.provider.refund_line(intent_id, "L1", MOUSE_LINE)

    rest = payments.provider.refund(intent_id)
    again = payments.provider.refund(intent_id)

    assert rest["refunded"] is True and Decimal(rest["amount"]) == KEYBOARD_LINE
    assert again["alreadyRefunded"] is True
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", MOUSE_LINE), ("CREDIT", KEYBOARD_LINE)]
    assert wallet_of(aws, USER_A)[0] == Decimal("1000000")


def test_a_line_refund_after_the_full_refund_is_rejected(aws, load_handler, paid, payments):
    order = paid(load_handler)
    intent_id = f"PI-{order['orderId']}"
    payments.provider.refund(intent_id)

    with pytest.raises(payments.provider.RefundRejected):
        payments.provider.refund_line(intent_id, "L1", MOUSE_LINE)
    assert ledger(aws) == [("DEBIT", TOTAL), ("CREDIT", TOTAL)]


def test_line_refunds_need_a_successful_payment(aws, load_handler, refund):
    order = reserve(aws, load_handler)
    seed_intent(aws, order)  # still REQUESTED

    with pytest.raises(RuntimeError, match="REQUESTED"):
        refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L1"]}, None)


# --- Compensation after a line was sold ------------------------------------------------------------------------
def test_release_takes_back_sold_units_and_leaves_written_off_ones(aws, load_handler, fulfill, write_off):
    order = reserve(aws, load_handler)
    fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)
    write_off.lambda_handler({"orderId": order["orderId"], "lines": [{"lineId": "L2", "reason": "damaged"}]}, None)

    load_handler("release_inventory").lambda_handler({"orderId": order["orderId"]}, None)

    assert counters(aws, "WIRELESS-MOUSE") == {"stock": 100, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 0}
    assert counters(aws, "MECH-KEYBOARD") == {"stock": 1, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 1}
    assert_i5(aws)


def test_reserve_returns_the_lines_for_the_map(aws, load_handler):
    order = seed_order(aws.orders)

    result = load_handler("reserve_inventory").lambda_handler({"orderId": order["orderId"]}, None)

    assert result["lines"] == [
        {"lineId": "L1", "productId": "WIRELESS-MOUSE", "quantity": 2},
        {"lineId": "L2", "productId": "MECH-KEYBOARD", "quantity": 1},
    ]


def test_a_fulfilled_line_is_never_refunded(aws, load_handler, paid, refund):
    """If the Map ever reported a shipped line as unavailable, no money may move for it."""
    order = paid(load_handler)
    load_handler("fulfill_item").lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)

    with pytest.raises(RuntimeError, match="refusing to refund"):
        refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L1"]}, None)
    assert ledger(aws) == [("DEBIT", TOTAL)]


# --- The partial path, step by step (what the Map and the steps after it do) ------------------------------------
def test_partial_fulfillment_keeps_money_and_stock_consistent(aws, load_handler, paid, refund, fulfill, write_off):
    order = paid(load_handler, simulate="item_unavailable", simulateLine=2)
    fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L1"}, None)
    with pytest.raises(fulfill.ItemUnavailable):
        fulfill.lambda_handler({"orderId": order["orderId"], "lineId": "L2"}, None)

    refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L2"]}, None)
    write_off.lambda_handler({"orderId": order["orderId"], "lines": [{"lineId": "L2", "reason": "damaged"}]}, None)

    entries = ledger(aws)
    net = sum(a for t, a in entries if t == "DEBIT") - sum(a for t, a in entries if t == "CREDIT")
    assert net == MOUSE_LINE  # I6: exactly the fulfilled line
    assert [i.get("fulfillment") for i in stored(aws, order)["items"]] == ["FULFILLED", "WRITTEN_OFF"]
    assert counters(aws, "MECH-KEYBOARD") == {"stock": 1, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 1}
    assert_i5(aws)


# --- Line details in the order APIs (owner only) ----------------------------------------------------------------
def test_get_order_returns_each_line_with_its_outcome(aws, load_handler, paid, refund, write_off):
    order = paid(load_handler)
    refund.lambda_handler({"orderId": order["orderId"], "lineIds": ["L2"]}, None)
    write_off.lambda_handler({"orderId": order["orderId"], "lines": [{"lineId": "L2", "reason": "damaged"}]}, None)

    body = json.loads(load_handler("get_order").lambda_handler(api_event(path_parameters={"id": order["orderId"]}), None)["body"])

    l1, l2 = body["items"]
    assert (l1["lineId"], l1["lineAmount"], l1.get("fulfillment")) == ("L1", 1598, None)
    assert (l2["lineId"], l2["fulfillment"], l2["refundedAmount"], l2["writeOffReason"]) == ("L2", "WRITTEN_OFF", 3499, "damaged")
    assert "index" not in l1


def test_line_details_are_only_for_the_owner(aws, load_handler):
    from conftest import EMAIL_B, USER_B, jwt_claims

    order = seed_order(aws.orders, gsi1pk=f"USER#{USER_A}", gsi1sk=f"2026-10-22T10:00:00.000Z#ORD-20261022-abcdef12")
    as_b = api_event(path_parameters={"id": order["orderId"]}, claims=jwt_claims(USER_B, EMAIL_B))

    assert load_handler("get_order").lambda_handler(as_b, None)["statusCode"] == 404
    listed = json.loads(load_handler("list_orders").lambda_handler(api_event(claims=jwt_claims(USER_B, EMAIL_B)), None)["body"])
    assert listed["orders"] == []


def test_list_orders_includes_line_details(aws, load_handler):
    seed_order(aws.orders, gsi1pk=f"USER#{USER_A}", gsi1sk="2026-10-22T10:00:00.000Z#ORD-20261022-abcdef12", refundedAmount=Decimal("3499"))

    listed = json.loads(load_handler("list_orders").lambda_handler(api_event(), None)["body"])["orders"]

    assert [line["lineId"] for line in listed[0]["items"]] == ["L1", "L2"]
    assert listed[0]["refundedAmount"] == 3499
