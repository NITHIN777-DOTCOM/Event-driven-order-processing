"""Do executions that are RUNNING when the state machine is updated finish on the OLD definition? (steps 2.3, 2.4)

    python scripts/inflight_check.py      # start it right after pushing a commit that changes the definition

Step Functions keeps each Standard execution on the definition it started with. This script proves it live:
it places a payment_slow order (DemoPay answers after 20 s, so the execution runs for ~25 s) every few seconds,
and watches the state machine's revisionId (it changes on every update). Once it changes, it waits for every order
to finish, reads the update time (updateDate of the definition the newest execution used, from
DescribeStateMachineForExecution), and sorts the executions:

  straddled  started BEFORE the update and still running after it. Expected: DescribeStateMachineForExecution
             returns exactly the definition captured when this script started (the old one), not the new one.
  after      started after the update: they use the new definition.

Step 2.4 (commit B switches cancellation on in the same apply): every 2 s the script also asks to cancel each
running order that has NO `cancellable` stamp, i.e. one whose execution runs the old definition (reserve_inventory
stamps only orders on the new one). Before the cancel Lambda is updated the answer is 503 CANCEL_DISABLED; after it,
it must be 409 NOT_CANCELLABLE: the old definition has no cancel branch, so such an order is never cancelled and
completes normally. Orders on the new definition are never asked (they would really be cancelled).

Results are printed and written to docs/evidence/upgrade-2.4/inflight-definition.md. Exit code 1 if no execution
straddled the update (start it earlier), if any straddling one used the new definition, if no old-definition order
was refused with 409 NOT_CANCELLABLE, or if any was cancelled.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from e2e_test import OUT, USER, cancel, orders_table, place_order, sfn, wait_for_terminal

EVIDENCE_FILE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "upgrade-2.4" / "inflight-definition.md"
PRODUCT = "MECH-KEYBOARD"  # one unit per order, ~6 orders a minute: seeded with 100 (run seed_inventory.py after)
SIMULATE = "payment_slow"
INTERVAL_SECONDS = 10
PROBE_SECONDS = 2
MAX_WAIT_SECONDS = 20 * 60
STATE_MACHINE = OUT["state_machine_arn"]
CANCEL_WINDOW = {"RESERVED", "PAYMENT_RETRY", "PAYMENT_PENDING", "PAYMENT_CAPTURED"}


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


def probe(order_ids: list[str], answers: dict[str, list[str]]) -> None:
    """Ask to cancel every running, UNSTAMPED order (old definition) that sits inside the cancel window."""
    for order_id in order_ids:
        item = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item") or {}
        if item.get("cancellable") is True or item.get("status") not in CANCEL_WINDOW:
            continue  # new definition (would really be cancelled), not reserved yet, or finished
        code, body = cancel(order_id, reason="inflight_check: old-definition probe")
        answer = f"{code} {body.get('error', body.get('status', ''))}"
        if not answers.setdefault(order_id, []) or answers[order_id][-1] != answer:
            answers[order_id].append(answer)
            print(f"  {datetime.now(timezone.utc):%H:%M:%S} cancel {order_id} ({item.get('status')}) -> {answer}")


def main() -> int:
    old_definition = current()
    baseline = old_definition["revisionId"]
    print(f"Definition revision {baseline}. Placing a {SIMULATE} order every {INTERVAL_SECONDS} s until it changes...")
    order_ids: list[str] = []
    answers: dict[str, list[str]] = {}
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    updated, next_order = baseline, 0.0
    while updated == baseline and time.monotonic() < deadline:
        if time.monotonic() >= next_order:
            code, body = place_order(PRODUCT, 1, SIMULATE, user=USER)
            if code == 202:
                order_ids.append(body["orderId"])
                print(f"  {datetime.now(timezone.utc):%H:%M:%S} placed {body['orderId']}")
            next_order = time.monotonic() + INTERVAL_SECONDS
        probe(order_ids, answers)
        time.sleep(PROBE_SECONDS)
        updated = revision()
    if updated == baseline:
        print("The definition never changed; nothing to check.")
        return 1
    # One more order, certainly on the new definition: its DescribeStateMachineForExecution gives the update time.
    code, body = place_order(PRODUCT, 1, SIMULATE, user=USER)
    newest = body.get("orderId") if code == 202 else None
    # Keep probing the old-definition orders until they leave the cancel window (the Lambda may update after the SFN).
    probe_until = time.monotonic() + 40
    while time.monotonic() < probe_until:
        probe(order_ids, answers)
        time.sleep(PROBE_SECONDS)
    if newest:
        order_ids.append(newest)
        wait_for_terminal(newest, timeout=180)
    updated_at = sfn.describe_state_machine_for_execution(executionArn=execution_arn(order_ids[-1]))["updateDate"].astimezone(timezone.utc)
    print(f"Definition updated at {updated_at:%H:%M:%S}. Waiting for the orders to finish...")

    rows, straddled_ok, straddled, refused, cancelled = [], True, 0, 0, 0
    for order_id in order_ids:
        order = wait_for_terminal(order_id, timeout=180)
        arn = execution_arn(order_id)
        try:
            execution = sfn.describe_execution(executionArn=arn)
        except sfn.exceptions.ExecutionDoesNotExist:
            continue  # placed but never started before the deadline (shouldn't happen)
        # boto3 returns local-time datetimes; everything here is compared and printed in UTC.
        started = execution["startDate"].astimezone(timezone.utc)
        stopped = execution["stopDate"].astimezone(timezone.utc) if execution.get("stopDate") else None
        used = sfn.describe_state_machine_for_execution(executionArn=arn)
        on_old = used["definition"] == old_definition["definition"]
        began = "BeginFulfillment" in entered_states(arn)
        asked = answers.get(order_id, [])
        refused += any(a.startswith("409 NOT_CANCELLABLE") for a in asked)
        cancelled += order.get("status") == "CANCELLED" and not order.get("cancellable")
        if started < updated_at and (stopped is None or stopped > updated_at):
            kind = "straddled"
            straddled += 1
            straddled_ok &= on_old
        else:
            kind = "before" if started < updated_at else "after"
        rows.append((order_id, kind, f"{started:%H:%M:%S.%f}"[:-3], f"{stopped:%H:%M:%S.%f}"[:-3] if stopped else "-",
                     order.get("status"), "old" if on_old else "new", began, " then ".join(asked) or "-"))

    print(f"\n{'orderId':<24}{'window':<11}{'started':<14}{'stopped':<14}{'status':<11}{'definition':<12}{'Begin':<7}cancel answers")
    for row in rows:
        print(f"{row[0]:<24}{row[1]:<11}{row[2]:<14}{row[3]:<14}{row[4]:<11}{row[5]:<12}{str(row[6]):<7}{row[7]}")
    passed = straddled > 0 and straddled_ok and refused > 0 and cancelled == 0
    verdict = (
        f"PASS: {straddled} execution(s) straddled the update and all finished on the old definition; "
        f"{refused} old-definition order(s) refused with 409 NOT_CANCELLABLE, none cancelled"
        if passed else
        f"FAIL: straddled={straddled}, all on the old definition={straddled_ok}, 409 NOT_CANCELLABLE={refused}, cancelled={cancelled}"
    )
    print("\n" + verdict)
    write_evidence(rows, updated_at, verdict)
    return 0 if passed else 1


def write_evidence(rows: list[tuple], updated: datetime, verdict: str) -> None:
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Running executions keep the state machine definition they started with (step 2.4 commit B)",
        "",
        f"Generated by `scripts/inflight_check.py` during the Deploy that switched cancellation on. State machine updated "
        f"at **{updated:%Y-%m-%d %H:%M:%S} UTC**. Definition per execution from `DescribeStateMachineForExecution`. "
        f"`{SIMULATE}` orders; the cancel API was asked to cancel every running order that has no `cancellable` stamp "
        "(old definition): 503 = the cancel Lambda not updated yet, 409 NOT_CANCELLABLE = refused, as it must be.",
        "",
        "| orderId | Window | Started (UTC) | Stopped (UTC) | Status | Definition | BeginFulfillment entered | Cancel answers |",
        "|---|---|---|---|---|---|---|---|",
        *[f"| {' | '.join(str(v) for v in row)} |" for row in rows],
        "",
        f"**{verdict}.**",
        "",
    ]
    EVIDENCE_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
