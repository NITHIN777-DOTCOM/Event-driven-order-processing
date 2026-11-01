# Step 3.3: load test (k6, live, ap-south-1)

Generated from `docs/evidence/upgrade-3.3-load-before.json` and `-after.json` (`scripts/loadtest_report.py`).

## Headline (run 2, after the fix)

| Number | Value |
|---|---|
| Sustained throughput (best 3-minute window, orders created per second) | **25.6 orders/s** (the designed limit, see below) |
| API latency, server side (API Gateway `Latency`, whole run) | **p50 51 ms, p95 82 ms, p99 99 ms** |
| Order completion time (created -> final status, from DynamoDB statusHistory) | **p50 4.7 s, p95 6.4 s** |
| Error rate | **0 API 5xx**; 1.5% of orders (192 of 12,704) timed out on payment and were refunded; **₹0 lost** |

## Profile

k6 `ramping-arrival-rate` (open model: slow answers never lower the offered rate), `loadtest/k6/orders.js`:
5 -> 50 orders/s over 5 min, hold 50/s for 3 min, spike offered at 100/s for 1 min. 160 test buyers (the step 3.1
race users, tokens fetched beforehand), 20 hidden products `LOAD-01..20` (`listed = false`). Mix: ~80% normal
(1-3 lines), ~10% partial fulfilment (one damaged line), ~10% payment declined. No status polling during the run.

## Results

| | Run 1 (before) `LT-b7d433c6` | Run 2 (after) `LT-fe9e8916` |
|---|---|---|
| DemoPay workers (SQS event source `maximum_concurrency`) | 2 | 20 |
| Requests sent / accepted / 429 / client network errors (status 0) | 22,160 / 18,492 / 3,570 / 98 | 20,851 / 12,634 / 7,503 / 714 |
| Orders created (DynamoDB) | 18,492 | 12,704 (70 more than k6 saw: answers lost on the laptop's link) |
| Accepted orders/s, best 3 min | 43.6 | 25.6 |
| Payments DemoPay could take | ~8/s (queue age reached 539 s) | kept up (queue stayed at 0) |
| Normal orders COMPLETED | 1,868 of 14,769 (13%) | 10,091 of 10,249 (98.5%) |
| Partial orders PARTIALLY_FULFILLED | 226 of 1,884 | 1,241 of 1,261 |
| Declined orders FAILED (expected) | 1,839 / 1,839 | 1,194 / 1,194 |
| Payment timeouts (refunded) | 16,146 | 192 |
| Completion p50 / p95 | 120.7 s / 121.0 s (the payment timeout) | 4.7 s / 6.4 s |
| API server-side p50 / p95 / p99 | 53 / 98 / 123 ms | 51 / 82 / 99 ms |
| API latency from the laptop p50 / p95 | 140 ms / 4.6 s | 154 ms / 6.6 s (home internet link; not the headline) |
| Ledger: debits / credits / net = fulfilled | ₹1,00,29,100 / ₹88,30,310 / ₹11,98,790 = ₹11,98,790 | ₹69,03,660 / ₹4,66,270 / ₹64,37,390 = ₹64,37,390 |
| ₹ lost | **0** (checked after DemoPay's queue drained) | **0** |
| Declines outside the "declined" scenario | 0 | 0 |
| DLQs (orders / outbox / PSP) before -> after | 43/0/3 -> 43/0/3 | 43/0/3 -> 43/0/3 |
| Lambda concurrency peak (account) / throttles | 37 / 0 | 61 / 0 |
| Step Functions executions started, peak per minute / throttled | 2,606 / 0 | 1,551 / 0 |
| API 4xx / 5xx | 3,939 / 9 | 12,833 / 0 |
| Lambda errors | fulfill-item 226 (simulated damaged lines), provider 9, webhook 9 | fulfill-item 1,241 (= the simulated damaged lines, one per partial order) |

## What the two runs show

- **Run 1 found a bottleneck.** DemoPay (the simulated payment provider) read its SQS queue with
  `maximum_concurrency = 2`, the SQS minimum. That was set when the account's concurrency pool was small (it is now
  400). DemoPay took ~8 payments/s while the API accepted 43/s, so payments arrived after the saga's 120 s wait.
  Those orders failed **safely**: once the queue drained (11:51:41Z), every late charge (16,146 orders) had been
  refunded through the webhook's late-payment path, and debits - refunds equalled the fulfilled lines exactly.
  That is the late-payment path proven at scale.
- **The fix** (one value + DemoPay retries): 20 workers; a wallet `TransactionConflict` is retried in-process
  (never a decline: 1 conflict seen, retried, 0 real declines); a throttled (429) webhook callback is retried with
  jittered backoff in the same invocation (~2,200 retries in run 2) instead of waiting for SQS redelivery.
- **Run 2 levels off at ~25 orders/s, the designed limit.** The API stage allows 50 req/s (cost/abuse guard, kept on
  purpose), and each order costs two requests: `POST /orders` and DemoPay's webhook callback. Above that, API
  Gateway answers 429 before any Lambda runs. The 192 timeouts are callbacks that were still throttled after 4 tries;
  SQS redelivered them after its visibility timeout, past the 120 s wait, and they were refunded.

## Auditor after run 2: Lambda timed out (problem, not fixed in this step)

The invariant auditor Lambda timed out at its 180 s limit after run 2 (39,221 orders; it full-scans 7 tables, and
scans again when the first pass has something to confirm). Its scan took 3.9 s before step 3.3, 51.5 s after run 1, 70.8 s before
run 2. The same audit run locally (`python scripts/audit_invariants.py`, read-only, one pass): **0 violations,
0 stuck** over 39,221 orders, 38,510 charges, 39 products, in 150 s. Until this is addressed the hourly audit times
out and publishes no datapoint.
