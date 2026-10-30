### UPGRADE STEP 2.3 REPORT

1. **Summary.** Paid orders are now fulfilled one line at a time. If an item is found damaged after payment, only
   that line is refunded and written off; the rest ships and the order ends **PARTIALLY_FULFILLED**. If every line
   fails, everything is refunded and written off and the order FAILS ("all items unavailable"). Reservation stays
   all-or-nothing. The saga uses an inline Map whose iterations each catch their own errors, followed by a Choice.
   Refunds use the line prices stored on the order, are idempotent per (intent, line), and are capped at the charge
   (I7). Rollout was expand → migrate with nothing removed. Commit A was proven live in isolation (19/19) and the
   full old suite still passed (26/26) before the saga used it. Commit B passed 29/29 live. A running execution was
   shown to finish on its old definition.

2. **Resources created/changed (ap-south-1)**

| Service | Exact name | Purpose | Console |
|---|---|---|---|
| Lambda (new) | `order-saga-fulfill-item` | one Map iteration: picks one line, reserved → sold; `ItemUnavailable` | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-fulfill-item |
| Lambda (new) | `order-saga-write-off-lines` | reserved → writtenOff + audit record, idempotent per line | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-write-off-lines |
| DynamoDB (new) | `order-saga-write-offs` | write-off audit (orderId, lineId) | https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#table?name=order-saga-write-offs |
| Step Functions (changed) | `order-saga-workflow` | FulfillItems Map, SummarizeFulfillment, FulfillmentOutcome, partial and all-unavailable paths | https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/statemachines/view/arn:aws:states:ap-south-1:876889172858:stateMachine:order-saga-workflow |
| Lambda (changed) | `order-saga-payment-provider` (DemoPay), `order-saga-refund-payment` | line refunds with the I7 cap; `lineIds` mode | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions |
| Lambda (changed) | `create-order`, `reserve-inventory`, `release-inventory`, `get-order`, `list-orders` | per-line prices, `lines` for the Map, sold-aware release, line details in the API | (same) |
| CloudWatch | alarm `order-saga-refund-or-write-off-errors`; metric filters `order-saga-fulfillment-events-*`, written-off units, line-refund amount; dashboard row | refunds/write-offs must never fail silently | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#alarmsV2:alarm/order-saga-refund-or-write-off-errors |
| IAM | roles of the 2 new Lambdas; SFN role (+ invoke the 2); list-orders (+ BatchGetItem); payment-provider (+ UpdateItem on psp records) | least privilege | https://console.aws.amazon.com/iam/home#/roles |
| Storefront | CloudFront `dg38gx94mao9n.cloudfront.net` | tracker per-line status, "Partially fulfilled" badge, wallet refund notes | https://dg38gx94mao9n.cloudfront.net |

3. **Key configuration to show in the console**
   - `FulfillItems`: Map, `ProcessorConfig.Mode = INLINE`, `MaxConcurrency 5`, `ItemsPath $.order.lines`.
     Inside: `FulfillItem` with Retry on `FulfillmentTransientError` (1 s, ×3, backoff 2) and Catch `States.ALL` →
     `LineUnavailable` (JSONata Pass).
   - `FulfillmentOutcome` Choice: unavailableCount = 0 → MarkOrderCompleted; fulfilledCount = 0 → RefundAllLines;
     default → PartialRefund.
   - PartialRefund / WriteOffLines / RefundAllLines / WriteOffAllLines: Retry States.ALL (2 s, ×4, backoff 2), **no
     Catch** (they fail loudly and can be redriven).
   - DemoPay CHARGE record `refundedAmount` with the condition `refundedAmount <= charged − amount`; refund records
     `REFUND#<intent>#<lineId>`.
   - Inventory counters: stock, held, reserved, sold, writtenOff (I5).
   - Demo: `"simulate": "item_unavailable"`, `"simulateLine": 1..n | "all"` (default: the last line).

4. **Commands and key outputs**
   - Commit A `terraform apply` (Deploy 41029064222): 15 added, 22 changed, 0 destroyed.
   - Commit B (Deploy 41032444445): 0 added, 20 changed, 0 destroyed. B fix (Deploy 41035114664): 0 added, 1 changed, 0 destroyed.
   - `python scripts/fulfillment_check.py` → 19/19. `python scripts/e2e_test.py` → 26/26 (A), 28/29 then 29/29 (B).
     `python scripts/inflight_check.py` → PASS (during the B fix deploy). `python scripts/capture_ui.py` → 9/9.
   - New terraform outputs: `write_offs_table = order-saga-write-offs`; `fulfillment_function_names`
     (fulfill_item, write_off_lines, refund_payment, payment_provider).

5. **Tests and verification**
   - Unit: **266 passed, 93% coverage**, including 18 tests that evaluate the deployed ASL's JSONata with
     jsonata-python (all/some/none aggregation, one-item arrays, error reasons), line-refund idempotency, the I7 cap,
     amounts with quantity > 1, write-off idempotency and owner-only line details.
   - Commit A in isolation: order `ORD-20261030-399cf6c3`. L1 + L3 fulfilled concurrently; L2 written off and
     refunded twice → one CREDIT ₹26,990; I7 probe `RefundRejected`; net ₹15,395 = L1 + L3; I5 held.
   - Old path on A: full e2e **26/26**.
   - B: **29/29**. za `ORD-20261030-6289f422` (net ₹8,495 = lines 1 + 3; 1 CREDIT ₹6,499); zb
     `ORD-20261030-c689fb2c` (FAILED, 2 CREDITs, net 0, intent REFUNDED); zc `ORD-20261030-96692ac2` (hold consumed
     once); a `ORD-20261030-af2706e5` (COMPLETED as before, reserved → sold); x: I5 held for 16 products; I1–I7 held
     for every order.
   - Running execution: `ORD-20261030-62b512cd` started 09:41:17.873 UTC; the definition was updated at 09:41:22;
     it finished at 09:41:28.823 on the **old** definition (`DescribeStateMachineForExecution`).
   - UI: `ORD-20261030-e9c97701` "Order partially fulfilled"; wallet: one Refund +₹1,799 "line L2"; 0 console errors.
   - After the runs: alarm `order-saga-refund-or-write-off-errors` OK; refund-payment 0 errors, write-off-lines 0 errors.

6. **Files added/changed**
   - A: `infra/main/fulfillment.tf`, `iam.tf`, `lambda.tf`, `monitoring.tf`, `outputs.tf`, `tags.tf`;
     `src/common/orders.py`, `payments.py`; `src/lambdas/fulfill_item/`, `write_off_lines/`,
     `payment_provider/`, `refund_payment/`, `release_inventory/`, `reserve_inventory/`, `create_order/`;
     `scripts/fulfillment_check.py`, `e2e_test.py`, `seed_inventory.py`; `tests/unit/conftest.py`,
     `test_fulfillment.py`; `requirements-dev.txt`; `docs/interview-prep.md`, `docs/progress.md`.
   - B: `statemachine/order_saga.asl.json`; `infra/main/iam.tf`, `sfn.tf`, `tags.tf`; `src/common/feed.py`,
     `orders.py`; `src/lambdas/create_order/`, `get_order/`, `list_orders/`, `refund_payment/`;
     `frontend/src/types.ts`, `tracker.ts`, `format.ts`, `components/ui.tsx`, `pages/Tracker.tsx`;
     `scripts/e2e_test.py`, `capture_ui.py`, `inflight_check.py`; `tests/unit/test_saga_definition.py`,
     `test_fulfillment.py`, `test_create_order.py`, `test_feed.py`, `test_list_handlers.py`; docs.
   - B fix: `frontend/src/pages/WalletPage.tsx`, `scripts/capture_ui.py`, `e2e_test.py`, `inflight_check.py`, ASL comment.
   - Docs: `docs/evidence/upgrade-2.3-fulfillment.md`, `upgrade-2.3/*`, `upgrade-2.3-report.md`,
     `e2e-failure-tests.md`, `ui/*`, `README.md`, `docs/interview-prep.md`, `docs/progress.md`.

7. **Problems hit and fixes**
   - The Bash tool cut heredocs at some apostrophes (as in 2.2). Long edits went through scratchpad scripts.
   - jsonata-python lacks Step Functions' `$parse`; the tests register `json.loads` as `$parse`.
   - Changing the GSI projection to include line details would rebuild the index (the list would be down meanwhile).
     Instead, `list_orders` does one BatchGetItem for exactly the orders its Query returned.
   - B's first e2e: 28/29. u summed stock + reserved, but l's desk mat now ends in `sold`. Fixed the test (I5 passed).
   - The first UI run on B stopped at the wallet check: the CREDIT was right, but the page didn't show the note.
     Fixed by showing refund notes.
   - The in-flight check during B was inconclusive: the probe product had 18 units and ran out before the update.
     Re-run with a 100-unit product during the next real definition update: PASS.
   - The in-flight script printed local time (IST) labelled UTC. Fixed: it converts to UTC; the evidence is relabelled.
   - Known nit: the write-off feed row repeats the item name.

8. **Cost notes.** No always-on resource: one on-demand table, two Lambdas and one alarm (~$0.10/month; alarms are
   now past the 10-metric free tier, as in 2.2). Per order, measured states entered: 5 (old) → 9 for a one-line order,
   14 for a 3-line partial order. At the Standard list price of $0.025 per 1,000 transitions (an estimate, not measured
   on the bill) that's about $0.0001 more per order. Test traffic today: about 200 orders, all within the free tiers
   or cents.

9. **Manual steps.** None. The orders DLQ gained 2 poison orders (e2e) + 1 (UI); leave them. Test orders from
   `inflight_check.py` and `fulfillment_check.py` are labelled and stay as history.

10. **Git.** A `25a6b90` (CI 41028903864, Deploy 41029064222), B `89f355f` (CI 41032228377, Deploy 41032444445),
    B fix `e464e66` (CI 41034908817, Deploy 41035114664), all green and pushed. Docs commit `2a6ca16` (CI 41036078786, Deploy
    41036264119), green; recorded by the follow-up commit that adds this line.
