"""The state machine's per-item fulfillment wiring (step 2.3), tested on the REAL definition file.

The JSONata expressions are taken from statemachine/order_saga.asl.json and evaluated with jsonata-python, the same
way Step Functions binds them ($states.input), so the Map summary and the per-line error handling are tested as
deployed, not as a copy.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonata
import pytest

ASL = json.loads((Path(__file__).resolve().parents[2] / "statemachine" / "order_saga.asl.json").read_text(encoding="utf-8"))
STATES = ASL["States"]
ITERATION = STATES["FulfillItems"]["ItemProcessor"]["States"]


def evaluate(expression: str, state_input: dict):
    """Evaluate a "{% ... %}" JSONata expression with $states.input bound, as Step Functions does."""
    assert expression.startswith("{%") and expression.endswith("%}")
    compiled = jsonata.Jsonata(expression[2:-2].strip())
    compiled.assign("states", {"input": state_input})
    compiled.register_lambda("parse", json.loads)  # a Step Functions addition to JSONata: JSON string -> value
    return compiled.evaluate(None)


def lambda_error(error: str, message: str) -> dict:
    """A caught Lambda error, as a Catch with ResultPath $.error stores it (Cause is a JSON string)."""
    return {"Error": error, "Cause": json.dumps({"errorMessage": message, "errorType": error})}


def summarize(*results: tuple[str, str]) -> dict:
    lines = [{"lineId": line_id, "status": status, **({"reason": f"{line_id} damaged"} if status == "UNAVAILABLE" else {})} for line_id, status in results]
    return evaluate(STATES["SummarizeFulfillment"]["Output"], {"orderId": "ORD-1", "lineResults": lines})["fulfillment"]


def choose(fulfillment: dict) -> str:
    """The FulfillmentOutcome Choice, evaluated on a summary."""
    for rule in STATES["FulfillmentOutcome"]["Choices"]:
        field = rule["Variable"].removeprefix("$.fulfillment.")
        if fulfillment[field] == rule["NumericEquals"]:
            return rule["Next"]
    return STATES["FulfillmentOutcome"]["Default"]


# --- Map result aggregation -----------------------------------------------------------------------------
def test_all_lines_fulfilled_goes_to_the_existing_completed_path():
    summary = summarize(("L1", "FULFILLED"), ("L2", "FULFILLED"), ("L3", "FULFILLED"))

    assert summary == {"lineCount": 3, "fulfilledCount": 3, "unavailableCount": 0, "unavailableLineIds": [], "unavailableLines": []}
    assert choose(summary) == "MarkOrderCompleted"


def test_some_lines_unavailable_goes_to_the_partial_refund():
    summary = summarize(("L1", "FULFILLED"), ("L2", "UNAVAILABLE"), ("L3", "FULFILLED"))

    # A single unavailable line must still be an ARRAY (JSONata unwraps single matches unless wrapped in [ ]).
    assert summary["unavailableLineIds"] == ["L2"]
    assert summary["unavailableLines"] == [{"lineId": "L2", "reason": "L2 damaged"}]
    assert (summary["fulfilledCount"], summary["unavailableCount"]) == (2, 1)
    assert choose(summary) == "PartialRefund"


def test_no_line_fulfilled_refunds_and_writes_off_everything():
    summary = summarize(("L1", "UNAVAILABLE"), ("L2", "UNAVAILABLE"))

    assert summary["unavailableLineIds"] == ["L1", "L2"]
    assert choose(summary) == "RefundAllLines"


def test_a_single_line_order_that_is_fulfilled_completes_as_before():
    assert choose(summarize(("L1", "FULFILLED"))) == "MarkOrderCompleted"


def test_the_summary_keeps_the_rest_of_the_state():
    output = evaluate(STATES["SummarizeFulfillment"]["Output"], {"orderId": "ORD-1", "order": {"currency": "INR"}, "lineResults": []})

    assert output["orderId"] == "ORD-1" and output["order"] == {"currency": "INR"}


# --- One iteration's own error handling --------------------------------------------------------------------
def test_each_iteration_catches_every_error_itself():
    catch = ITERATION["FulfillItem"]["Catch"]

    assert catch == [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "LineUnavailable"}]
    assert ITERATION["LineUnavailable"]["End"] is True
    assert "Catch" not in STATES["FulfillItems"]  # nothing escapes an iteration, so the Map itself needs none


def test_an_unavailable_line_reports_the_lambda_error_message():
    state = {"orderId": "ORD-1", "lineId": "L2", "error": lambda_error("ItemUnavailable", "Desk Mat (line L2) was found damaged")}

    result = evaluate(ITERATION["LineUnavailable"]["Output"], state)

    assert result == {"lineId": "L2", "status": "UNAVAILABLE", "error": "ItemUnavailable", "reason": "Desk Mat (line L2) was found damaged"}


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        ({"Error": "States.Timeout", "Cause": "Task timed out"}, "Task timed out"),  # a Cause that is not JSON
        ({"Error": "States.TaskFailed"}, "States.TaskFailed"),  # no Cause at all
    ],
)
def test_an_unavailable_line_always_has_a_reason(error, reason):
    result = evaluate(ITERATION["LineUnavailable"]["Output"], {"lineId": "L1", "error": error})

    assert (result["status"], result["reason"]) == ("UNAVAILABLE", reason)


def test_only_transient_errors_are_retried_inside_an_iteration():
    retried = {error for rule in ITERATION["FulfillItem"]["Retry"] for error in rule["ErrorEquals"]}

    assert "FulfillmentTransientError" in retried
    assert "ItemUnavailable" not in retried and "States.ALL" not in retried


# --- Wiring -------------------------------------------------------------------------------------------
def test_fulfillment_runs_after_payment_over_the_reserved_lines():
    assert STATES["RequestPayment"]["Next"] == "FulfillItems"
    assert STATES["ReserveInventory"]["ResultSelector"]["lines.$"] == "$.Payload.lines"
    assert STATES["FulfillItems"]["ItemsPath"] == "$.order.lines"
    assert STATES["FulfillItems"]["ItemProcessor"]["ProcessorConfig"] == {"Mode": "INLINE"}
    assert 1 < STATES["FulfillItems"]["MaxConcurrency"] <= 10


def test_partial_and_full_paths():
    assert [STATES["PartialRefund"]["Next"], STATES["WriteOffLines"]["Next"], STATES["MarkOrderPartiallyFulfilled"]["Next"]] == [
        "WriteOffLines", "MarkOrderPartiallyFulfilled", "NotifyCustomerPartial",
    ]
    assert STATES["NotifyCustomerPartial"]["Next"] == "OrderPartiallyFulfilled"
    assert STATES["OrderPartiallyFulfilled"]["Type"] == "Succeed"
    assert [STATES["RefundAllLines"]["Next"], STATES["WriteOffAllLines"]["Next"], STATES["DescribeAllUnavailable"]["Next"]] == [
        "WriteOffAllLines", "DescribeAllUnavailable", "MarkOrderFailed",
    ]


@pytest.mark.parametrize("name", ["PartialRefund", "WriteOffLines", "RefundAllLines", "WriteOffAllLines"])
def test_money_and_stock_steps_retry_then_fail_loudly_instead_of_carrying_on(name):
    """No Catch: a refund that keeps failing stops the execution (alarm + redrive), never a silent COMPLETED."""
    assert "Catch" not in STATES[name]
    assert any("States.ALL" in rule["ErrorEquals"] for rule in STATES[name]["Retry"])


def test_line_refunds_send_only_line_ids_never_amounts():
    """The amount refunded comes from the order's stored lines (server-side prices), not from the state."""
    for name in ("PartialRefund", "RefundAllLines"):
        assert STATES[name]["Parameters"]["Payload"] == {"orderId.$": "$.orderId", "lineIds.$": "$.fulfillment.unavailableLineIds"}


def test_all_unavailable_fails_with_a_readable_reason():
    state = {"orderId": "ORD-1", "order": {"currency": "INR"}, "lineRefund": {"refundedAmount": "5097.00"}}

    output = evaluate(STATES["DescribeAllUnavailable"]["Output"], state)

    assert output["error"]["Error"] == "AllItemsUnavailable"
    assert output["failureReason"].startswith("AllItemsUnavailable: all items unavailable - INR 5097.00 refunded")
