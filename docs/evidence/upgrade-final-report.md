# UPGRADE FINAL REPORT (step 3.4, 2026-11-01)

**Upgrade complete.** Steps 1.0-3.4 done. The system is live, chaos-tested and load-tested (25.6 orders/s, ₹0 lost),
documented for a 10-minute read (README, [interview cheat sheet](../INTERVIEW-CHEATSHEET.md)), with a
[teardown procedure](../teardown.md) (not run).

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
| Live e2e after this deploy | **35/35 in 1086 s (2026-11-01 14:16 UTC, after Deploy 41313535866)** | [e2e-failure-tests.md](e2e-failure-tests.md) |
| Cancel race x20 (same run) | exactly one winner in 20/20: 11 cancel won (nothing charged), 8 cancel won (late charge refunded), 1 payment won (cancel 409); never both | [e2e-failure-tests.md](e2e-failure-tests.md) |
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
- Chaos E3 "5 -> 9 orders on their normal path" (interview-prep) can't be recomputed from the E3 files (crash
  scenarios have no single "normal" outcome); the README/cheat sheet use the files' own fields: violations 2 -> 0.

## Live state at the end
- CHAOS_ENABLED = false on all 10 Lambdas that carry it; fault bucket `order-saga-fis-config-876889172858` empty.
- Alarms: `order-saga-dlq-not-empty` and `order-saga-psp-dlq-not-empty` stay in ALARM by design (parked messages).
  `order-saga-webhook-signature-failures` went to ALARM at 14:13 UTC from the e2e forged-signature scenarios (o, s),
  as on every e2e run; 5-min period, missing = not breaching, so it returns to OK by itself. All others OK.
- DLQs: orders 47 (poison-message test orders, one per e2e run; 43 at the end of 3.3) / outbox 0 / PSP 3
  (unchanged since 3.2). Clearing them means deleting messages: not done (needs "DESTROY").

## Observations (not changed in this step)
- **`order-saga-refund-or-write-off-errors` -> ALARM at 14:16 UTC during the e2e cancel race (zi).** Two
  `order-saga-refund-payment` invocations at 14:15 UTC failed with `DemoPay refund failed: ... TransactionCanceledException
  [TransactionConflict, ...]`: 20 cancels refunding on the same test wallet at once. Step Functions retried them
  (refund retries since 3.2) and every race order passed I1-I9 in the e2e run, so money is correct. The alarm counts
  raw Lambda errors, retried or not. DemoPay retries TransactionConflict in-process on the DEBIT path (3.3) but not
  on the REFUND path; adding the same retry would keep this alarm quiet. The alarm returns to OK by itself
  (missing data = not breaching).

## Cost
- Idle (measured, Cost Explorer usage before credits, quiet days 2026-10-24..27): **$0.117/day, ~$3.5/month**.
- New since the load test: the hourly full-scan audit, ~60.6k RRU per run x 720 runs ≈ 44M RRU/month,
  **est. ~$6/month** (on-demand reads), plus <$1 Lambda. Estimated total **~$10/month at today's data size**:
  above the $5 budget alert, covered by credits (expire ~2026-11-27). Not changed (owner's call): run the audit every
  6 h, or use eventually consistent scans (half the RRU).
- This step: 1 audit + 1 e2e run + 2 Cost Explorer calls: well under $1.

## Commits / CI
- `55bd0fe` part 0 (auditor): CI 41313374590 green, Deploy 41313535866 green (1 added, 1 changed).
- `3669bae` docs (README, cheat sheet, teardown, this report): CI 41315408578 green, Deploy 41315632333 green (no infra changes; smoke test passed).
- Repo description + topics: set with `gh repo edit` after the owner approves the text (see the step 3.4 chat).
