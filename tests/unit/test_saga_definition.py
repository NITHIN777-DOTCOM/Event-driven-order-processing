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
    # Step 2.4: payment -> (demo Wait) -> BeginFulfillment (the point of no return) -> FulfillItems.
    assert STATES["RequestPayment"]["Next"] == "WarehouseSpeed"
    assert STATES["WarehouseSpeed"]["Default"] == "BeginFulfillment"
    assert STATES["BeginFulfillment"]["Next"] == "CancelledBeforeFulfillment"
    assert STATES["CancelledBeforeFulfillment"]["Default"] == "FulfillItems"
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
        "WriteOffAllLines", "DescribeAllUnavailable", "CheckCancelBeforeFailing",
    ]
    assert STATES["CancelledWhileFailing"]["Default"] == "MarkOrderFailed"  # FAILED unless a cancel was requested


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


# --- step 2.4: customer cancellation -----------------------------------------------------------------------
def _get(data: dict, path: str):
    """A plain "$.a.b" JSONPath read; None when any part is missing."""
    for part in path.removeprefix("$.").split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def _matches(rule: dict, data: dict) -> bool:
    """The Choice operators the saga uses."""
    if "And" in rule:
        return all(_matches(r, data) for r in rule["And"])
    if "Or" in rule:
        return any(_matches(r, data) for r in rule["Or"])
    if "Not" in rule:
        return not _matches(rule["Not"], data)
    value = _get(data, rule["Variable"])
    if "IsPresent" in rule:
        return (value is not None) is rule["IsPresent"]
    if "StringEquals" in rule:
        return value == rule["StringEquals"]
    if "NumericEquals" in rule:
        return value == rule["NumericEquals"]
    raise AssertionError(f"operator not handled by this walker: {rule}")


def _set(data: dict, path: str, value) -> dict:
    keys = path.removeprefix("$.").split(".")
    target = data
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value
    return data


def walk(start: str, state_input: dict, task_results: dict[str, dict]) -> tuple[list[str], dict]:
    """Follow the REAL definition from `start` to a Succeed/Fail state.

    Choices are evaluated, JSONata Pass states are run, and each Task's result is taken from `task_results`
    (stored at its ResultPath), so a test states only what the AWS calls would return.
    """
    path, data, name = [], json.loads(json.dumps(state_input)), start
    while True:
        path.append(name)
        state = STATES[name]
        if state["Type"] in ("Succeed", "Fail"):
            return path, data
        if state["Type"] == "Choice":
            name = next((r["Next"] for r in state["Choices"] if _matches(r, data)), state.get("Default"))
            continue
        if state["Type"] == "Pass" and "Output" in state:
            data = evaluate(state["Output"], data)
        elif state["Type"] == "Task" and state.get("ResultPath"):
            data = _set(data, state["ResultPath"], task_results.get(name, {}))
        name = state["Next"]


TIMED_OUT = {
    "orderId": "ORD-1",
    "order": {"customerName": "Asha", "currency": "INR", "totalAmount": 5097, "itemsSummary": "1 x Desk Mat"},
    "error": {"Error": "States.Timeout", "Cause": "payment timeout"},
}


def _timeout_catcher() -> str:
    return next(c["Next"] for c in STATES["RequestPayment"]["Catch"] if c["ErrorEquals"] == ["States.Timeout"])


def test_payment_timeout_on_a_cancelled_order_ends_cancelled_not_failed():
    """The 120 s timeout fires after the customer cancelled (e.g. the cancel API died before SendTaskFailure)."""
    path, data = walk(
        _timeout_catcher(),
        TIMED_OUT,
        {
            "CheckCancelBeforeFailing": {"Item": {"cancelRequestedAt": {"S": "2026-10-30T10:00:00.000Z"}}},
            "RefundWhatIsLeft": {"refunded": False, "refundedAmount": "0.00"},
        },
    )

    assert path[-1] == "OrderCancelled"
    assert "MarkOrderFailed" not in path
    # Void/refund what is left, then the stock goes back, then the order is marked CANCELLED and the customer told.
    cancel_steps = [s for s in path if s in ("RefundWhatIsLeft", "CancelReleaseInventory", "MarkOrderCancelled", "NotifyCustomerCancelled")]
    assert cancel_steps == ["RefundWhatIsLeft", "CancelReleaseInventory", "MarkOrderCancelled", "NotifyCustomerCancelled"]
    assert data["cancellation"]["detail"] == "Cancelled by the customer - nothing was charged"


def test_payment_timeout_without_a_cancel_still_fails_as_before():
    path, _ = walk(_timeout_catcher(), TIMED_OUT, {"CheckCancelBeforeFailing": {}})  # GetItem: no cancelRequestedAt

    assert "MarkOrderFailed" in path and "RefundWhatIsLeft" not in path


def test_order_cancelled_from_the_payment_wait_goes_straight_to_the_cancel_branch():
    catcher = next(c for c in STATES["RequestPayment"]["Catch"] if c["ErrorEquals"] == ["OrderCancelled"])
    catchers = [c["ErrorEquals"] for c in STATES["RequestPayment"]["Catch"]]

    assert catcher["Next"] == "RefundWhatIsLeft"
    assert catchers.index(["OrderCancelled"]) < catchers.index(["States.ALL"])  # never swallowed by States.ALL


def test_cancel_seen_by_begin_fulfillment_takes_the_cancel_branch():
    path, data = walk(
        "CancelledBeforeFulfillment",
        {**TIMED_OUT, "fulfillmentStart": {"outcome": "CANCEL_REQUESTED"}},
        {"RefundWhatIsLeft": {"refunded": True, "refundedAmount": "5097.00"}},
    )

    assert path[-1] == "OrderCancelled" and "FulfillItems" not in path
    assert data["cancellation"]["detail"] == "Cancelled by the customer - INR 5097.00 refunded to the DemoPay wallet"
    assert data["cancellation"]["emailLine"] == "We refunded INR 5097.00 to your DemoPay wallet."


def test_reservation_stamps_new_orders_as_cancellable():
    assert STATES["ReserveInventory"]["Parameters"]["Payload"]["cancellable"] is True


@pytest.mark.parametrize("name", ["BeginFulfillment", "CheckCancelBeforeFailing", "RefundWhatIsLeft", "CancelReleaseInventory", "MarkOrderCancelled", "NotifyCustomerCancelled"])
def test_every_cancel_step_retries(name):
    assert any("States.ALL" in r["ErrorEquals"] for r in STATES[name]["Retry"])


def test_if_the_cancel_check_itself_fails_the_order_still_ends_failed():
    catch = STATES["CheckCancelBeforeFailing"]["Catch"]

    assert catch == [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.cancelCheckError", "Next": "MarkOrderFailed"}]
