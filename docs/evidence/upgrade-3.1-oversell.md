# Step 3.1: oversell race test (evidence)

Claim under test: when hundreds of buyers try to claim the last units at the same instant, exactly the available
units are claimed, every other attempt gets a clean out-of-stock answer (never a 500, never a charge), and all stock
comes back afterwards. Plus: the test itself can catch an oversell bug.

- Harness: `scripts/oversell_race.py` (LIVE, ap-south-1). Negative control: `tests/race/test_oversell_negative_control.py` (local, moto).
- Full per-attempt logs: `docs/evidence/upgrade-3.1/before-fix.md`, `after-fix-1.md`, `after-fix-2.md` (the final, passing run).

## Pre-flight (before racing)

| Limit | Value |
|---|---|
| Lambda account concurrency limit | **400** |
| Unreserved concurrency | **400** (no function has reserved concurrency) |
| API Gateway `order-saga-api` stage `$default` | burst **100**, rate **50 req/s** |
| Per-route throttling overrides | none |
| Buyers | 160 Cognito test users `race-001..160` (made like test users A/B; passwords only in SSM SecureStrings). race-001..010 place direct orders, race-011..160 one hold each (one ACTIVE hold per user is a product rule) |
| Tokens | access tokens fetched before the race; the 10 order buyers' wallets topped up |
| Race products | RACE-1 = 20, RACE-X = 10, RACE-Y = 10, `listed = false` (hidden from `GET /products`); seeding is conditional on held = reserved = sold = writtenOff = 0, so it can never break I5 |

The limit is not low (400), so the brief's 200 / 100 attempts were kept as written.

## The three live runs

| Run | Deploy | Result | What it showed |
|---|---|---|---|
| `before-fix` (07:55 UTC) | `8471de8` | **FAIL** | Never oversold (20/20, 10/10), but **112 phantom out-of-stock answers** (58 + 54 holds got 409 while 3-14 units were left) and 5 direct orders failed "Insufficient stock": `TransactionConflict` was read as out of stock |
| `after-fix-1` (08:17 UTC) | `bbc7bcd` (retry conflicts: 8 tries, 20-400 ms) | **FAIL** | 0 phantom out-of-stock; but 1 hold per round ran out of conflict retries -> **503** (counted as ERROR) |
| `after-fix-2` (11:38 UTC) | `365c6a5` (10 tries, 50 ms-1 s; consistent stock read before any 503) | **PASS** | every check below |

## Results, run `after-fix-2`

### Round 1: 200 simultaneous attempts on RACE-1 (20 units), all sent within 63 ms

| Path | Attempts | CLAIMED | OUT_OF_STOCK | THROTTLED (429, retried) | ERROR | Conflict retries (server) |
|---|---|---|---|---|---|---|
| checkout holds (`POST /holds`) | 150 | 20 | 130 | 0 | 0 | 3 holds, 1 retry each |
| direct orders (`POST /orders`) | 50 | 0 | 50 | 0 | 0 | 0 |
| **total** | **200** | **20** | **180** | **0** | **0** | **3** |

### Round 2: 100 simultaneous carts {RACE-X: 1, RACE-Y: 1}, item order alternating X,Y / Y,X, sent within 37 ms

| Path | Attempts | CLAIMED | OUT_OF_STOCK | THROTTLED | ERROR | Conflict retries (server) |
|---|---|---|---|---|---|---|
| checkout holds | 60 | 10 | 50 | 0 | 0 | 1 hold, 1 retry |
| direct orders | 40 | 0 | 40 | 0 | 0 | 0 |
| **total** | **100** | **10** | **90** | **0** | **0** | **1** |

Conflict retries come from CloudWatch Logs Insights on `/aws/lambda/order-saga-holds-api`
(`"Transaction committed after conflicts"`, field `conflictRetries`); the window had 0 ERROR log lines and 0 timeouts.

### Latency (ms, p50 / p95 / max)

| Measure | Round 1 | Round 2 |
|---|---|---|
| hold: request -> real stock answer (throttle retries included) | 1375 / 2004 / 3040 | 546 / 909 / 1571 |
| order: `POST /orders` -> 202 accepted | 1096 / 1291 / 1345 | 353 / 410 / 416 |
| order: accepted -> stock answer in the saga (RESERVED or FAILED out of stock) | 2019 / 2541 / 2600 | 797 / 1121 / 1210 |

Round 1 is slower because ~150 cold Lambda environments start at once (Round 2 reuses them) and 150 holds queue on one
DynamoDB item.

### Sampler (consistent reads every ~200 ms while each round ran)

| Product | Samples | Min `stock` ever seen | Max claimed ever seen | Seeded | I5 on every sample |
|---|---|---|---|---|---|
| RACE-1 | 50 | **0** | **20** | 20 | PASS |
| RACE-X | 29 | **0** | **10** | 10 | PASS |
| RACE-Y | 29 | **0** | **10** | 10 | PASS |

Claimed = held + reserved + sold + writtenOff. Never `stock < 0`, never claimed > seeded.

### Checks

| Check | Round 1 | Round 2 |
|---|---|---|
| exactly the available units claimed | PASS (20) | PASS (10 carts) |
| 0 ERROR (no 5xx) | PASS | PASS |
| every throttled request answered | PASS (none throttled) | PASS (none throttled) |
| no 409 while stock was still available (no phantom out-of-stock) | PASS (0) | PASS (0) |
| all-or-nothing: no cart got only one of its items | n/a | PASS (0) |
| losing direct orders: FAILED, out of stock, net ₹0, no DEBIT | PASS (50/50) | PASS (40/40) |
| I1-I4, I6-I9 for every race order | PASS: 90 orders, 0 failures | |
| I5 (stock conservation) for the race products and all 16 demo products | PASS | |

The direct orders lost every unit in this run: a hold answers in ~1.4 s, while an order reaches ReserveInventory only
after the outbox, SQS and Step Functions (~2-3 s), so the holds drain the stock first. The direct-order winning path
was exercised live in run `before-fix`, round 2: 4 direct orders RESERVED, then cancelled (HTTP 202, nothing charged),
with the cart still all-or-nothing (RACE-X and RACE-Y each held 6 + reserved 4).

## Throttling

0 requests were throttled in any of the three runs, although 200 requests arrived within 63 ms against a stage burst
of 100. The harness is ready for it: a 429 / `TooManyRequestsException` is classified THROTTLED, retried with
full-jitter backoff (0.2 s base, 4 s cap, 15 attempts) until a real stock answer arrives, and reported in its own
column; it is never counted as out of stock. Lambda peaked at **200** concurrent executions (CloudWatch `ConcurrentExecutions`, 1-minute maximum, 11:38 UTC), half the 400 account limit.

## Recovery

Winning holds were left to expire on their EventBridge Scheduler schedules (600 s); winning direct orders (none in this
run) are cancelled by the harness (`simulate=payment_manual`, so DemoPay never charges).

| Run | Full recovery after the last winning hold | Counters after (stock, held, reserved, sold, writtenOff) |
|---|---|---|
| before-fix | 652 s | RACE-1 (20,0,0,0,0), RACE-X (10,0,0,0,0), RACE-Y (10,0,0,0,0) |
| after-fix-1 | 646 s | same |
| after-fix-2 | **638 s** (hold length 600 s + ~38 s scheduler and poll delay) | same |

No ACTIVE holds left on race products; I5 PASS for all 16 products afterwards.

## Negative control (local only, never deployed)

`tests/race/test_oversell_negative_control.py` (marker `race`, in `pytest.ini` testpaths, so CI runs it; ~12 s). The
same thread race against moto, 50 threads on 5 units:

```
BrokenReserve: 50 buyers, 5 units -> claimed 50, stock -45, reserved 50
real reserve:  50 buyers, 5 units -> claimed 5, stock 0, reserved 5, out of stock 45
2 passed
```

`BrokenReserve` reads the stock, checks it, sleeps a few ms, then writes WITHOUT a condition: it oversells (the test
asserts claimed > 5; the count varies run to run, 40-50). The real `reserve_inventory` handler, whose transaction
decrements only `if stock >= :qty`, claims exactly 5. It lives under `tests/`, which is never packaged (each Lambda zip is
its own `handler.py` plus `src/common/*.py`, see `infra/main/lambda.tf`).

## Harness fix found while writing this up

The "Fired" timestamp was stamped before the threads pre-connected (~28 s for 200 TLS connections), not at the barrier
release. Latencies were unaffected (each thread times its own send). Now stamped in the barrier's `action`. The
`after-fix-2.md` file carries a note with the real release times from CloudWatch (11:38:30 and 11:38:48 UTC).

## Cost

Per run: ~300 API requests, ~700 Lambda invocations, 90 Standard executions (~1,000 state transitions = ~$0.025),
~3,000 DynamoDB request units, 30 Scheduler schedules, ~4,000 sampler reads, 160 Cognito MAU (inside the Essentials
free 10,000). **About $0.03-0.05 per run, ~$0.15 for all three runs.**
