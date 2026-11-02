# UPGRADE FINAL REPORT (step 3.4, 2026-11-01)

**Upgrade complete.** Steps 1.0-3.4 done. The system is live, chaos-tested and load-tested (25.6 orders/s, ₹0 lost),
documented for a 10-minute read (README), with a teardown procedure (in the README; not run).

## Step 3.4 Part 0: auditor fix (config only, no IAM change)
- `order-saga-invariant-auditor`: timeout 180 -> **900 s**, memory 512 -> **1769 MB** (1 full vCPU).
- Heartbeat `OrderSaga/Audit AuditCompleted = 1`, sent only after a full audit; new alarm
  **`order-saga-auditor-missed`**: Sum < 1 over 7200 s, missing data = breaching -> `order-saga-ops-alerts`.
  CloudWatch slides the 2 h window with the clock (state reason: "datapoint [1.0 (11:58:00)]"), so the hourly runs at
  :49 never fall into an empty bucket.
- Scripts that invoke the auditor (`chaos_run.py`, `audit_invariants.py --invoke`, `loadtest_prep.py`): read timeout
  960 s, 1 attempt (no client-side retry that would start a second audit).
- **Live verification (2026-11-01 13:56 UTC, `aws lambda invoke`):**

| Check | Result |
|---|---|
| Config | Timeout 900, MemorySize 1769, LastUpdateStatus Successful |
| Audit | **39,322 orders**, 38,602 charges, 39 products: **0 violations, 0 stuck**, 46 parked (poison orders, by design) |
| Scan time | **37.4 s** (REPORT Duration 37397 ms; max memory used 680 MB). Before: timed out at 180 s |
| Read units, one audit | orders 42,853 · payments 10,450 · psp 3,702 · wallet-txns 3,290 · others 325 = **~60.6k RRU** |
| Heartbeat | `AuditCompleted` datapoint 1.0 at 13:57 UTC |
| Alarms | `order-saga-auditor-missed` INSUFFICIENT_DATA -> ALARM (created before the first datapoint, 13:56:53) -> **OK** (13:58:53); `invariant-violation` OK; `stuck-orders` OK |

## Test numbers (as used in README + cheat sheet)

| Test | Result | Evidence |
|---|---|---|
| Unit + race tests (local, 2026-11-01) | **417 passed, 94% coverage** (2,757 statements, 169 missed) | this file |
| Live e2e, final (after the refund retry, Deploy 41318185369) | **35/35 in 640 s (2026-11-02 06:46 UTC)** | [e2e-failure-tests.md](e2e-failure-tests.md), [console log](e2e-console-2026-11-02.md) |
| Live e2e after the auditor deploy | 35/35 in 1086 s (2026-11-01 14:16 UTC, after Deploy 41313535866) | superseded by the run above |
| Cancel race x20 (2026-11-01 run) | exactly one winner in 20/20: 11 cancel won (nothing charged), 8 cancel won (late charge refunded), 1 payment won (cancel 409); never both | [e2e-failure-tests.md](e2e-failure-tests.md) |
| UI suite | 11/11 scenarios, 0 console errors | [ui/README.md](ui/README.md) |
| Oversell race | 20 / 180 / 0 errors; 10 carts / 0 half carts | [upgrade-3.1-oversell.md](upgrade-3.1-oversell.md) |
| Chaos E1 / E3 | normal path 10 -> 19 of 30 / violations 2 -> 0; ₹0 lost | [upgrade-3.2/](upgrade-3.2/) |
| Load test | 13% -> 98.5% completed; 25.6 orders/s; p95 82 ms; ₹0 lost | [upgrade-3.3-load.md](upgrade-3.3-load.md) |

**Where evidence files disagreed (later one used):**
- UI suite: the old README and the 2.4 report say 10/10; `ui/README.md` (2026-10-31, later) lists **11** scenarios
  (adds "Busy 503 -> retried" from step 3.1), all passing.
- Cancel race x20: 14/4/2 (`upgrade-2.4-cancellation.md`) and 15/4/1 (2.4 report re-run) are older; the latest
  e2e run is used. The invariant is the same in all runs: exactly one winner per order, never both.
- Unit tests: 327 (old README) / 339 (3.1 report) -> **417** now (3.2 + 3.3 added tests).
- Chaos E3 "5 -> 9 orders on their normal path": **claim removed** (commit `e2d1689`). It can't be rebuilt from
  `e3-before-placed.json` / `e3-placed.json` (a recheck gives non-FAILED 5 -> 7, SUCCEEDED executions 3 -> 7; two
  before-orders were corrected in 3.3). Only the files' own field is quoted: violations 2 -> 0.

## Live state at the end (checked 2026-11-02 after the final e2e)
- CHAOS_ENABLED = false on all 10 Lambdas that carry it; fault bucket `order-saga-fis-config-876889172858` empty.
- **DLQs: all 0** (orders, outbox, PSP; main queues 0 too). The parked messages were archived to JSON with
  `scripts/archive_dlq.py` (body + attributes), then exactly those message ids were deleted, on the owner's instruction:
  - [dlq-archive-2026-11-01.json](dlq-archive-2026-11-01.json): orders DLQ 47 + PSP DLQ 3 (poison test orders, one per
    e2e run; 3 PSP messages from 3.2).
  - [dlq-archive-2026-11-01-b.json](dlq-archive-2026-11-01-b.json), [-c.json](dlq-archive-2026-11-01-c.json): 1 + 1
    poison messages left by an e2e run that crashed and one that was stopped (scenario g now deletes its own message
    after asserting it, so these were the last ones).
  - Runbook rule from now on: a DLQ should be empty; anything in it is a real incident.
- **Alarms:** after the final e2e every alarm is OK except two that the e2e trips by design and that clear by
  themselves (missing data = not breaching): `order-saga-dlq-not-empty` (scenario g's poison message passes through
  the DLQ before the test deletes it; 60 s period) and `order-saga-webhook-signature-failures` (forged signatures in
  scenarios o and s; 300 s period). `order-saga-refund-or-write-off-errors` stayed **OK** through the cancel race.
  **Recheck 06:57 UTC: all 16 alarms OK** (`order-saga-webhook-signature-failures` returned to OK at 06:57:41 UTC).

## Observation, then fixed: refund TransactionConflict
- **`order-saga-refund-or-write-off-errors` -> ALARM at 14:16 UTC (2026-11-01) during the e2e cancel race (zi).** Two
  `order-saga-refund-payment` invocations failed with `DemoPay refund failed: ... TransactionCanceledException
  [TransactionConflict, ...]`: 20 cancels refunding on the same test wallet at once. Step Functions retried them and
  every race order passed I1-I9, so money was correct, but the alarm counts raw Lambda errors.
- **Fix (`e2d1689`, Deploy 41318185369):** the DemoPay refund path (`refund` / `refund_line` via `move_refund`) now
  retries TransactionConflict in-process with growing jittered backoff, like the debit path (unit tests added).
  The final e2e (same 20-way cancel race) left this alarm OK.

## Cost
- Idle (measured, Cost Explorer usage before credits, quiet days 2026-10-24..27): **$0.117/day, ~$3.5/month**.
- New since the load test: the hourly full-scan audit, ~60.6k RRU per run x 720 runs ≈ 44M RRU/month,
  **est. ~$6/month** (on-demand reads), plus <$1 Lambda. Estimated total **~$10/month at today's data size**:
  above the $5 budget alert, covered by credits (expire ~2026-11-27). Not changed (owner's call): run the audit every
  6 h, or use eventually consistent scans (half the RRU).
- This step: 1 audit + 4 e2e runs (2 completed, 1 crashed, 1 stopped) + 2 Cost Explorer calls: well under $1.

## Commits / CI
- `55bd0fe` part 0 (auditor): CI 41313374590 green, Deploy 41313535866 green (1 added, 1 changed).
- `3669bae` docs (README, cheat sheet, teardown, this report): CI 41315408578 green, Deploy 41315632333 green (no infra changes; smoke test passed).
- `ed35771` docs (run IDs, refund-conflict observation).
- `e2d1689` refund conflict retry, DLQ archive script, self-cleaning e2e poison, E3 claim removed: Deploy 41318185369 green.
- Final commit (e2e evidence, notes made private, this report): FINAL_RUN_IDS
- Personal notes (progress log, interview prep, cheat sheet, resume, teardown) are no longer in this repo: gitignored
  and kept in a private notes repo. Teardown steps are in the README.
- Repo description (owner-approved, set with `gh repo edit` 2026-11-02):
  > Serverless e-commerce order saga on AWS: Step Functions with compensation, async payment callbacks (waitForTaskToken + HMAC webhook), mid-saga cancellation, per-item partial refunds, Cognito auth, transactional outbox (DynamoDB Streams -> Pipes -> SQS). Chaos-tested, load-tested (25.6 orders/s, ₹0 lost). Terraform + OIDC CI/CD.
- Topics added: cognito, transactional-outbox, chaos-engineering, idempotency, k6, load-testing, eventbridge,
  distributed-systems (20 topics in total, GitHub's maximum).
