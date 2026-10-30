"""Do executions that are RUNNING when the state machine is updated finish on the OLD definition? (step 2.3)

    python scripts/inflight_check.py      # start it right after pushing a commit that changes the definition

Step Functions keeps each Standard execution on the definition it started with. This script proves it live:
it places a payment_flaky order (the payment fails twice and is retried 2 s + 4 s later, so the execution runs for
~15 s) every few seconds, and watches the state machine's revisionId (it changes on every update). Once it changes,
it waits for every order to finish, reads the update time (updateDate of the definition the newest execution used,
from DescribeStateMachineForExecution), and sorts the executions:

  straddled  started BEFORE the update and still running after it. Expected: DescribeStateMachineForExecution
             returns exactly the definition captured when this script started (the old one), not the new one.
  after      started after the update: they use the new definition.
The FulfillItems / ITEM_FULFILLED columns show what each definition did (commit B: old = no per-line fulfillment).

Results are printed and written to docs/evidence/upgrade-2.3/inflight-definition.md. Exit code 1 if no execution
straddled the update (start it earlier) or if any straddling one used the new definition.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from e2e_test import OUT, USER, place_order, sfn, wait_for_terminal

EVIDENCE_FILE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "upgrade-2.3" / "inflight-definition.md"
PRODUCT = "MECH-KEYBOARD"  # one unit per order, ~6 orders a minute: seeded with 100 (run seed_inventory.py after)
INTERVAL_SECONDS = 10
MAX_WAIT_SECONDS = 20 * 60
STATE_MACHINE = OUT["state_machine_arn"]


def current() -> dict:
    return sfn.describe_state_machine(stateMachineArn=STATE_MACHINE)


def revision() -> str:
    return current()["revisionId"]


def execution_arn(order_id: str) -> str:
    return f"{STATE_MACHINE.replace(':stateMachine:', ':execution:')}:{order_id}"


def entered_states(arn: str) -> list[str]:
    names, kwargs = [], {"executionArn": arn, "maxResults": 1000}
    while True:
        page = sfn.get_execution_history(**kwargs)
        names += [e["stateEnteredEventDetails"]["name"] for e in page["events"] if "stateEnteredEventDetails" in e]
        if "nextToken" not in page:
            return names
        kwargs["nextToken"] = page["nextToken"]


def main() -> int:
    old_definition = current()
    baseline = old_definition["revisionId"]
    print(f"Definition revision {baseline}. Placing a payment_flaky order every {INTERVAL_SECONDS} s until it changes...")
    order_ids: list[str] = []
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    updated = baseline
    while updated == baseline and time.monotonic() < deadline:
        code, body = place_order(PRODUCT, 1, "payment_flaky", user=USER)
        if code == 202:
            order_ids.append(body["orderId"])
            print(f"  {datetime.now(timezone.utc):%H:%M:%S} placed {body['orderId']}")
        time.sleep(INTERVAL_SECONDS)
        updated = revision()
    if updated == baseline:
        print("The definition never changed; nothing to check.")
        return 1
    # One more order, certainly on the new definition: its DescribeStateMachineForExecution gives the update time.
    code, body = place_order(PRODUCT, 1, "payment_flaky", user=USER)
    if code == 202:
        order_ids.append(body["orderId"])
    wait_for_terminal(order_ids[-1], timeout=180)
    updated_at = sfn.describe_state_machine_for_execution(executionArn=execution_arn(order_ids[-1]))["updateDate"]
    print(f"Definition updated at {updated_at:%H:%M:%S}. Waiting for the orders to finish...")

    rows, straddled_ok, straddled = [], True, 0
    for order_id in order_ids:
        order = wait_for_terminal(order_id, timeout=180)
        arn = execution_arn(order_id)
        try:
            execution = sfn.describe_execution(executionArn=arn)
        except sfn.exceptions.ExecutionDoesNotExist:
            continue  # placed but never started before the deadline (shouldn't happen)
        started, stopped = execution["startDate"], execution.get("stopDate")
        used = sfn.describe_state_machine_for_execution(executionArn=arn)
        on_old = used["definition"] == old_definition["definition"]
        ran_map = "FulfillItems" in entered_states(arn)
        fulfilled = any(h["status"] == "ITEM_FULFILLED" for h in order.get("statusHistory", []))
        if started < updated_at and (stopped is None or stopped > updated_at):
            kind = "straddled"
            straddled += 1
            straddled_ok &= on_old
        else:
            kind = "before" if started < updated_at else "after"
        rows.append((order_id, kind, f"{started:%H:%M:%S.%f}"[:-3], f"{stopped:%H:%M:%S.%f}"[:-3] if stopped else "-",
                     order.get("status"), "old" if on_old else "new", ran_map, fulfilled))

    print(f"\n{'orderId':<24}{'window':<11}{'started':<14}{'stopped':<14}{'status':<11}{'definition':<12}{'Map ran':<9}ITEM_FULFILLED")
    for row in rows:
        print(f"{row[0]:<24}{row[1]:<11}{row[2]:<14}{row[3]:<14}{row[4]:<11}{row[5]:<12}{str(row[6]):<9}{row[7]}")
    passed = straddled > 0 and straddled_ok
    verdict = (
        f"PASS: {straddled} execution(s) straddled the update and all finished on the old definition"
        if passed else f"FAIL: straddled={straddled}, all on the old definition={straddled_ok}"
    )
    print("\n" + verdict)
    write_evidence(rows, updated_at, verdict)
    return 0 if passed else 1


def write_evidence(rows: list[tuple], updated: datetime, verdict: str) -> None:
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step 2.3 commit B: running executions keep the definition they started with",
        "",
        f"Generated by `scripts/inflight_check.py` while the Deploy job applied commit B. State machine updated at "
        f"**{updated:%Y-%m-%d %H:%M:%S} UTC**. Definition per execution from `DescribeStateMachineForExecution`.",
        "",
        "| orderId | Window | Started (UTC) | Stopped (UTC) | Status | Definition | FulfillItems entered | ITEM_FULFILLED |",
        "|---|---|---|---|---|---|---|---|",
        *[f"| {' | '.join(str(v) for v in row)} |" for row in rows],
        "",
        f"**{verdict}.**",
        "",
    ]
    EVIDENCE_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
