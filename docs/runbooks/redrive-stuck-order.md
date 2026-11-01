# Runbook: redrive a stuck order

> **DLQs:** a dead-letter queue should be empty. Each poison message is inspected, archived
> (`python scripts/archive_dlq.py --out docs/evidence/dlq-archive-<date>.json`), then removed
> (`--delete-archived <that file>`).

**When:** alarm `order-saga-stuck-orders` fires (SNS `order-saga-ops-alerts`), or the auditor lists an order as
STUCK: not terminal 30+ minutes after it was created. Often it also follows `order-saga-refund-or-write-off-errors`.

**Why it happens:** a Task state with no Catch, such as `RefundPayment`, `ReleaseInventory`, `PartialRefund`,
`RefundAllLines`, `RefundWhatIsLeft`, `WriteOffLines` or `CancelReleaseInventory`, used up its retries (or a
`FulfillItem` line kept failing with an error other than ItemUnavailable, which fails the `FulfillItems` Map). The saga does not move money forward without that
step, so the execution FAILS there on purpose and the order keeps its last status (e.g. FULFILLING,
CANCEL_REQUESTED). The order still owes the customer something, usually a refund. Nothing is lost: the execution is
*parked* until a person fixes the cause and resumes it.

## 1. Confirm it is a parked execution

```powershell
python scripts/audit_invariants.py --invoke        # STUCK list: orderId, status, "execution FAILED ... redrive"
aws stepfunctions describe-execution --execution-arn arn:aws:states:ap-south-1:<account>:execution:order-saga-workflow:<orderId> `
  --query "{status:status,error:error,cause:cause,redriveStatus:redriveStatus,redriveCount:redriveCount}"
```

You want `status = FAILED` and `redriveStatus = REDRIVABLE`. Find the state that failed (the last `TaskFailed` /
`LambdaFunctionFailed` event):

```powershell
aws stepfunctions get-execution-history --execution-arn <arn> --reverse-order --max-items 15 `
  --query "events[].[timestamp,type,stateEnteredEventDetails.name]" --output table
```

The step's own logs, by orderId (Logs Insights over `/aws/lambda/order-saga-refund-payment` etc.):

```
fields @timestamp, level, message, error, reason | filter orderId = "<orderId>" | sort @timestamp asc
```

**Do not redrive** an execution that ended at the `OrderFailed` Fail state. DescribeExecution still says
`REDRIVABLE`, but the redrive resumes AT the Fail state: no step re-runs. Seen live in step 3.2 on
ORD-20261031-88258147 (a declined order, nothing owed): `ExecutionRedriven` was followed directly by `ExecutionFailed`.
That is why, since step 3.2, `RefundPayment` and `ReleaseInventory` have no Catch: a refund that keeps failing parks
the execution on its own task (redrivable) instead of reaching `OrderFailed`. An order that is FAILED and terminal but still owes money is a VIOLATION (I2), not STUCK,
and it needs a bug fix, not a redrive.

## 2. Fix the cause first

A redrive re-runs the failed step with the **same input** and the **same state machine definition**. If the cause is
still there, it fails again. Typical causes:
- DemoPay or refund-payment is unavailable (outage, throttling, a fault injection still active). Check the function's
  Errors metric and wait for 0.
- A code bug in the step. Deploy the fix first: the redrive runs the Lambda's current code.
- A definition bug in the state machine: a redrive can't pick up a new definition. Fix the data or start a new
  execution only through a reviewed change. Never start a second execution by hand: the orderId is the execution
  name, and start_workflow treats `ExecutionAlreadyExists` as "already running".

## 3. Redrive

```powershell
aws stepfunctions redrive-execution --execution-arn <arn> --client-token redrive-<orderId>
```

- It resumes at the failed state. Steps that already succeeded are not re-run, and the failed Task's Retry counters
  start again from 0. In a Map, only the failed iterations are re-run.
- Safe to repeat: every saga step is idempotent (a refund replays its REFUND record, a release checks `released`).
  `--client-token` makes the redrive request itself idempotent.
- Limits: Standard workflows only, within 14 days of the execution closing, and fewer than 24,999 history events.
- Needs `states:RedriveExecution` on the execution ARN (the local admin profile; the CI deploy role has `states:*` on
  order-saga-* but must never redrive).

## 4. Verify

```powershell
aws stepfunctions describe-execution --execution-arn <arn> --query "{status:status,redriveCount:redriveCount}"
python scripts/audit_invariants.py --invoke        # expect: Violations 0, Stuck 0
```

Then check the order: a terminal status (PARTIALLY_FULFILLED / CANCELLED / FAILED), and in the wallet ledger exactly
one CREDIT per refunded line, or one full refund. `order-saga-stuck-orders` returns to OK after the next audit (hourly,
or run the auditor on demand as above).

## Drill

To rehearse without waiting 30 minutes, run the auditor with a drill-only threshold (it can only lower it, 1-30 min):

```powershell
aws lambda invoke --function-name order-saga-invariant-auditor --cli-binary-format raw-in-base64-out `
  --payload '{"source":"drill","stuckAfterMinutes":2}' out.json
```

Rehearsed in step 3.2, experiment E5 (refund outage, `scripts/chaos_run.py E5` then `--redrive`). The evidence,
with the real order and execution IDs, is in `docs/evidence/upgrade-3.2/e5-redrive.md`.
