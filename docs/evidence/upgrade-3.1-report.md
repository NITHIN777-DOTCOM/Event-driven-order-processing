### UPGRADE STEP 3.1 REPORT

1. **Summary.** Built a live oversell race test (`scripts/oversell_race.py`): 160 Cognito test buyers, pre-signed and
   pre-connected requests released by a barrier, 200 attempts on 20 units (holds + direct orders) and 100 two-item
   carts on 10 + 10 units, with a 200 ms counter sampler, per-request classification (CLAIMED / OUT_OF_STOCK /
   THROTTLED / ERROR), money invariants per order and timed recovery. A local negative control proves the race catches
   a broken (unconditional) reserve. The first live run found a real bug, DynamoDB `TransactionConflict` answered as
   "out of stock" (112 false sold-out answers). Two fixes (separate commits) brought it to a clean PASS: exactly 20/20
   and 10/10 claimed, 0 errors, never stock < 0.

2. **Resources created/changed** (no Terraform or IAM change in this step).

| AWS service | Exact resource name | Purpose | Console link |
|---|---|---|---|
| Lambda (code changed, via Deploy) | `order-saga-holds-api`, `order-saga-reserve-inventory`, `order-saga-release-inventory` and every function packaging `common/transact.py` (19 updated) | retry TransactionConflict; 409 vs 503 decided by a consistent read | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-holds-api |
| DynamoDB items | `order-saga-inventory`: `RACE-1` (20), `RACE-X` (10), `RACE-Y` (10), `listed = false` | dedicated race products, hidden from GET /products | https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#item-explorer?table=order-saga-inventory |
| Cognito users | `order-saga-users`: race-001 .. race-160 (example.com) | one buyer per hold attempt | https://ap-south-1.console.aws.amazon.com/cognito/v2/idp/user-pools?region=ap-south-1 |
| SSM parameters | `/order-saga/test-users/race-*` (SecureString) | race buyers' passwords, never printed | https://ap-south-1.console.aws.amazon.com/systems-manager/parameters?region=ap-south-1 |
| CloudWatch Logs | `/aws/lambda/order-saga-holds-api` | `"Transaction committed after conflicts"` lines with `conflictRetries` | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#logsV2:log-groups |

3. **Key configuration values.**
   - Inventory claim: DynamoDB transaction with the condition `stock >= :qty` (all lines of a cart in one TransactWriteItems).
   - `common/transact.py`: retry while any cancellation reason is `TransactionConflict`: 10 tries, full-jitter backoff
     50 ms base, 1 s cap (worst case ~5.6 s). Only `ConditionalCheckFailed` = out of stock.
   - Holds API when conflicts never clear: consistent read; short -> 409, stock left -> 503 + `Retry-After`.
   - Limits: Lambda account concurrency 400 (unreserved 400); API stage `$default` burst 100, rate 50 rps; hold 600 s.
   - Harness: throttle retries full-jitter 0.2 s base, 4 s cap, 15 attempts; sampler every 200 ms.

4. **Commands run and key outputs.**
   - `python scripts/oversell_race.py --label before-fix` -> FAIL: 20/20, 10/10, but 112 x 409 with stock left.
   - `python scripts/oversell_race.py --label after-fix` (file `after-fix-1.md`) -> FAIL: 0 false out-of-stock, 1 x 503 per round.
   - `python scripts/oversell_race.py --label after-fix-2` -> **PASS in 847 s**:
     `200 attempts sent within 63 ms: CLAIMED 20, OUT_OF_STOCK 180, ERROR 0, throttled 0`;
     `100 attempts sent within 37 ms: CLAIMED 10, OUT_OF_STOCK 90, ERROR 0, throttled 0`;
     `90 orders checked, 0 failures`; `Recovery ... after 638 s`; `I5 holds for all 16 products`.
   - Logs Insights: 4 holds committed after 1 conflict retry (3 in round 1, 1 in round 2); 0 ERROR lines.
   - CloudWatch `ConcurrentExecutions` max 200 at 11:38 UTC.
   - Terraform outputs: unchanged (API `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`).

5. **Tests / verification.**

| Check | Result |
|---|---|
| Round 1: exactly 20 claimed (20 holds, 0 orders), 180 clean out-of-stock, 0 ERROR, 0 throttled | PASS |
| Round 1 sampler (50 samples): min stock 0, max claimed 20, I5 every sample | PASS |
| Round 2: exactly 10 carts, 0 half carts, X,Y and Y,X orders, 0 ERROR, no hang | PASS |
| Round 2 sampler (29 + 29 samples): min stock 0, max claimed 10 / 10 | PASS |
| No 409 while stock was left (phantom out-of-stock) | PASS (0; was 112 before the fix) |
| 90 losing direct orders FAILED out of stock, net ₹0, no DEBIT; I1-I4, I6-I9 | PASS |
| Recovery: RACE-1 20/20, RACE-X 10/10, RACE-Y 10/10, held 0, no ACTIVE holds; I5 for all 16 products | PASS (638 s) |
| Negative control (local, moto, 50 threads / 5 units): BrokenReserve claimed 50 (stock -45); real code exactly 5 | PASS |
| Unit + race tests (`pytest --cov=src`), local | PASS: 339 passed, coverage 93.54% |

   Example losing order: `ORD-20261031-52e1fd92` (run after-fix-1, FAILED, ledger 0 DEBIT / 0 CREDIT).
   Per-attempt tables with every orderId: `docs/evidence/upgrade-3.1/after-fix-2.md`.

6. **Files added/changed (step 3.1 overall).**
   - `scripts/oversell_race.py`, `tests/race/test_oversell_negative_control.py`, `pytest.ini`
   - `src/common/transact.py`, `src/common/holds.py`, `src/lambdas/holds_api/handler.py`,
     `src/lambdas/reserve_inventory/handler.py`, `src/lambdas/release_inventory/handler.py`,
     `src/lambdas/list_products/handler.py` (listed = false), `scripts/e2e_test.py`, `tests/unit/test_transact.py`,
     `tests/unit/test_list_handlers.py`
   - `docs/evidence/upgrade-3.1-oversell.md`, `docs/evidence/upgrade-3.1/{before-fix,after-fix-1,after-fix-2}.md`,
     `docs/evidence/upgrade-3.1-report.md`, `docs/interview-prep.md`, `docs/progress.md`, `README.md`

7. **Problems hit and fixes.**
   - **TransactionConflict read as out of stock** (run before-fix: 112 false 409s, 5 orders FAILED with stock left).
     Fix 1 `bbc7bcd`: retry conflicts on every stock path.
   - **Retry budget too small** (run after-fix-1: 1 hold per round answered 503). Fix 2 `365c6a5`: 10 tries up to 1 s,
     and a consistent read so a busy product is never called sold out (and a sold-out one never called busy).
   - **Harness "Fired" timestamp** was taken before ~28 s of TLS pre-connects; now stamped at the barrier release.
     Latencies were never affected; `after-fix-2.md` is annotated with the CloudWatch release times.
   - Local: the system `python` had no boto3; the harness runs with `.venv`.
   - Observation, not a bug: direct orders rarely win (holds answer in ~1.4 s, the saga reserves after ~2-3 s); the
     winning direct-order path ran live in before-fix round 2 (4 reserved, then cancelled, net ₹0).

8. **Cost.** ~$0.03-0.05 per live run (≈90 Standard executions, ~700 Lambda invocations, ~3,000 DynamoDB request
   units, 30 schedules, Logs Insights scans of a few MB); three runs ≈ **$0.15**. 160 Cognito MAU are inside the
   Essentials free tier. No standing cost added.

9. **Manual actions.** None. (The 160 race users and their SSM parameters stay for re-runs; nothing was deleted.)

10. **Git** (all pushed to origin main):
    - `8471de8` prep (unlisted test products): CI 41181937338, Deploy 41182050402 green.
    - `56ae364` harness + negative control + run before-fix: its CI 41183356083 was superseded (cancel-in-progress) by bbc7bcd's, same tree plus the fix.
    - `bbc7bcd` fix 1: CI 41183372836, Deploy 41183541011 green (0 added, 19 changed).
    - `365c6a5` fix 2: CI 41184787213, Deploy 41184914270 green.
    - `1b27b94` final run, evidence, docs: CI 41199119449, Deploy 41199290860 green (0 added, 0 changed, 0 destroyed).
    - This commit records the run IDs (docs only).
