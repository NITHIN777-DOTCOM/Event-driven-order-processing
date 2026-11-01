# UPGRADE STEP 3.3 REPORT: load test

**Headline (run 2):** 25.6 orders/s sustained (designed limit) · API p95 82 ms server side · completion p50 4.7 s /
p95 6.4 s · 0 API 5xx, 1.5% payment timeouts refunded · ₹0 lost. Details: `docs/evidence/upgrade-3.3-load.md`.

## Results
- **Part 0:** ORD-20261101-e10c6683 and ORD-20261101-11f6e7e1 corrected to COMPLETED (`scripts/fix_stuck_fulfilled_orders.py`,
  dry run first, all guards passed); auditor 0 violations / 0 stuck.
- **Run 1 (before, `LT-b7d433c6`):** API accepted 43.6 orders/s, but DemoPay (2 workers) took ~8 payments/s:
  87% of normal orders timed out on payment. After the PSP queue drained, all 16,146 late charges were refunded:
  debits ₹1,00,29,100 - refunds ₹88,30,310 = fulfilled ₹11,98,790, ₹0 lost (the late-payment path at scale).
- **Fix (after "APPLY"):** `maximum_concurrency` 2 -> 20 on DemoPay's SQS event source; DemoPay retries a wallet
  `TransactionConflict` in-process (never a decline) and retries 429/5xx webhook callbacks with jittered backoff.
- **Run 2 (after, `LT-fe9e8916`):** 12,704 orders; 98.5% of normal orders COMPLETED; levels off at ~25 orders/s, the
  designed end-to-end limit (each order = `POST /orders` + one webhook callback through the 50 req/s stage). 0 real
  declines outside the declined scenario. DLQs unchanged (43/0/3). Lambda concurrency peak 61, no Lambda or
  Step Functions throttles, peak 1,551 executions started per minute.

## Problems
1. **Invariant auditor Lambda times out (180 s) at 39k orders.** Its scan took 3.9 s -> 51.5 s -> 70.8 s, then timed out
   after run 2. The local audit (read-only) reports 0 violations / 0 stuck in 150 s. The hourly audit publishes
   nothing until this is fixed. Not changed, as instructed.
2. **192 payment timeouts in run 2** (refunded): callbacks still throttled after 4 tries wait for SQS's visibility
   timeout, longer than the 120 s payment wait. Same known limitation as step 3.2.
3. **Client-side noise:** 714 status-0 network errors and a 6.6 s client p95 come from the laptop's home link (server
   p95 82 ms); 70 orders were created whose answers never reached k6. The headline uses API Gateway's latency.
4. Prep hung once: botocore's 60 s read timeout re-invoked the slow auditor; the prep client now waits 5 min, no retry.
5. **e2e after the deploy:** the first attempt crashed: `executions_named` listed all ~45k executions and Step
   Functions throttled `ListExecutions`. Fixed (one DescribeExecution per name; names are unique). The next attempt
   overlapped the crashed run's in-flight orders (32/35: g, p, q saw its poison message and reservations); on a quiet
   system: **35/35 PASS**.

## Cost
Two runs, ~31k orders: about $15 in total (Step Functions transitions dominate), approved.

## Commit / CI
- `7c1c4b7` step 3.3: CI 41308725952 green, Deploy 41308884378 green (0 added / 20 changed: same code, zips rebuilt on Linux).
- `776998a` follow-up (e2e harness fix + report): CI 41312081433 + Deploy 41312262943 green.
