### UPGRADE STEP 2.4 REPORT

1. **Summary.** Customers can cancel an order mid-saga: while it waits for payment (nothing charged, or a late
   charge refunded) or after payment but before fulfillment (full refund, stock released). Once the warehouse starts
   (FULFILLING) or the order is finished, the API answers `409 TOO_LATE_TO_CANCEL`. Every race (cancel vs the payment
   webhook vs BeginFulfillment vs the 120 s timeout) is decided by one conditional write on the order item, and the
   cancel reaches the paused saga with `SendTaskFailure("OrderCancelled")`, never `StopExecution`, so the saga runs
   its own clean-up and ends **CANCELLED**, a terminal status distinct from FAILED. New invariants I8 (CANCELLED =
   net ₹0 + stock back) and I9 (cancel and payment never both win) held for every e2e order, including a 20-order
   race. Rollout: commit A (switched off, proven unchanged 29/29), the legacy cleanup, then commit B (switched on;
   orders on the old definition proven to get 409 NOT_CANCELLABLE and finish on it).

2. **Resources created/changed (ap-south-1)**

| Service | Exact name | Purpose | Console |
|---|---|---|---|
| Lambda (new) | `order-saga-cancel-order` | `POST /orders/{id}/cancel`: owner check, the deciding conditional write, SendTaskFailure on the payment token | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-cancel-order |
| Lambda (new) | `order-saga-begin-fulfillment` | saga step: PAYMENT_CAPTURED → FULFILLING unless a cancel came first (the point of no return) | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-begin-fulfillment |
| API Gateway (changed) | route `POST /orders/{id}/cancel` on the HTTP API (JWT authorizer) | the cancel endpoint | https://ap-south-1.console.aws.amazon.com/apigateway/main/apis?region=ap-south-1 |
| Step Functions (changed) | `order-saga-workflow` | `cancellable` stamp, OrderCancelled Catch, WarehouseSpeed/WaitBeforeFulfillment, BeginFulfillment, CancelledBeforeFulfillment, CheckCancelBeforeFailing + CancelledWhileFailing, cancel branch RefundWhatIsLeft → CancelReleaseInventory → DescribeCancellation → MarkOrderCancelled → NotifyCustomerCancelled → OrderCancelled | https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/statemachines/view/arn:aws:states:ap-south-1:876889172858:stateMachine:order-saga-workflow |
| Lambda (changed) | `order-saga-payment-webhook` | capture/decline conditional on `attribute_not_exists(cancelRequestedAt)`; a losing webhook refunds and answers OrderCancelled | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-payment-webhook |
| Lambda (changed) | `order-saga-payment-provider` (DemoPay) | `void` operation; refund note on the wallet CREDIT; `payment_slow` / `payment_manual` | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-payment-provider |
| Lambda (changed) | `refund-payment`, `request-payment`, `reserve-inventory`, `create-order`, `get-order` | cancelled mode (void, refund what's left), conditional status writes, the stamp, demo scenarios, `canCancel` + feed rows | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions |
| CloudWatch | alarm `order-saga-cancellation-errors`; metric filters `order-saga-cancel-events-*` → `OrderSaga/CancelEvents` (dimension Event); dashboard row | cancellations must never fail silently | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#alarmsV2:alarm/order-saga-cancellation-errors |
| CloudWatch dashboard | `order-saga-dashboard` (cancellation row) | accepted / refunded / nothing charged / refused | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#dashboards/dashboard/order-saga-dashboard |
| IAM | roles of the 2 new Lambdas; SFN role (+ invoke begin-fulfillment, + `dynamodb:GetItem` orders for CheckForCancelBeforeFailing); payment-webhook (+ orders GetItem) | least privilege | https://console.aws.amazon.com/iam/home#/roles |
| Storefront | CloudFront `dg38gx94mao9n.cloudfront.net` | Cancel button + confirm, 409 messages, "Cancelled — refunded ₹X / nothing charged", Cancelled badge | https://dg38gx94mao9n.cloudfront.net |
| DynamoDB (data) | `order-saga-orders` | 233 legacy orders marked by the cleanup (`legacyStockMigratedAt`) | https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#table?name=order-saga-orders |

3. **Key configuration to show in the console**
   - `RequestPayment` Catch order: States.Timeout → MarkPaymentTimedOut; **OrderCancelled → RefundWhatIsLeft**;
     PaymentDeclined → RefundPayment; States.ALL → RefundPayment.
   - `BeginFulfillment` (Retry Lambda.* + States.ALL, 2 s ×4) → `CancelledBeforeFulfillment` Choice
     (`$.fulfillmentStart.outcome == CANCEL_REQUESTED` → cancel branch).
   - `CheckCancelBeforeFailing`: direct `dynamodb:getItem`, `ProjectionExpression cancelRequestedAt`,
     `ConsistentRead true`; Choice `IsPresent` → cancel branch, default MarkOrderFailed; Catch States.ALL →
     MarkOrderFailed (fallback).
   - Cancel branch: every step retries; MarkOrderCancelled sets `status CANCELLED`, `cancelledAt`, a history entry.
   - cancel_order's condition: `#status IN (RESERVED, PAYMENT_RETRY, PAYMENT_PENDING, PAYMENT_CAPTURED) AND
     attribute_not_exists(cancelRequestedAt) AND cancellable = true`, `ReturnValues UPDATED_OLD`.
   - Lambda `order-saga-cancel-order` env `CANCEL_ENABLED=true` (false in commit A → 503).
   - Demo: `"simulate": "payment_slow"` (DemoPay answers after 20 s), `"fulfillment_slow"` (10 s Waits before and
     after BeginFulfillment); the storefront offers both.

4. **Commands and key outputs**
   - Commit A Deploy 41044113358: `Apply complete! Resources: 16 added, 22 changed, 0 destroyed.`
   - `python scripts/e2e_test.py` on A: 28/29 (g, a test flaw) → **29/29**; `python scripts/capture_ui.py`: 9/9.
   - `python scripts/migrate_legacy_sold.py` (dry-run) → APPLY → `--apply`: "233 of 233 orders migrated", 0 units
     moved; `--check`: PASS (all 16 products) before and after; a re-run finds 0 left.
   - Commit B local plan: 0 to add, 25 to change, 0 to destroy (4 of them line-ending noise in query definitions);
     Deploy 41061113800: `Apply complete! Resources: 0 added, 21 changed, 0 destroyed.`
   - `python scripts/inflight_check.py` (during B's Deploy): PASS, 2 straddled, 13 × 409 NOT_CANCELLABLE.
   - `python scripts/e2e_test.py` on B: **35/35** in 361 s. `python scripts/capture_ui.py`: 10/10 (after the B fix).
   - Terraform outputs used: `cancellation_function_names` = {cancel_order: order-saga-cancel-order,
     begin_fulfillment: order-saga-begin-fulfillment, payment_provider: order-saga-payment-provider, hold_expiry:
     order-saga-hold-expiry}; `api_url` https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com;
     `frontend_url` https://dg38gx94mao9n.cloudfront.net.

5. **Tests and verification**
   - Unit: **327 passed, 93% coverage** (CI gate 85%). Race in both orders, repeated cancel, after FULFILLING,
     non-owner, old definition, used token, BeginFulfillment loses, refund-what's-left never over-refunds, the cancel
     Lambda dying after its write, payment_manual with no trigger, and the real definition walked from the payment
     timeout to OrderCancelled when `cancelRequestedAt` is set.
   - Live e2e B (all after a re-seed), I1–I9 on every order:
     zd `ORD-20261030-7726b40c` cancel while waiting → CANCELLED in 0.35 s, intent VOIDED at DemoPay, ledger empty;
     ze `ORD-20261030-4cd495b4` cancel after payment → one DEBIT + one CREDIT ("order cancelled");
     zf `ORD-20261030-94055573` cancel during fulfillment → 409 TOO_LATE_TO_CANCEL, COMPLETED;
     zg `ORD-20261030-b94dfc11` cancel a COMPLETED order → 409;
     zh `ORD-20261030-16044a76` cancel an order from a hold → stock back exactly once;
     zi race ×20 (first `ORD-20261030-eb4de5fb`): 14 cancel won / nothing charged, 4 cancel won / late charge
     refunded, 2 payment won / cancel 409, **0 both**.
   - In-flight (old definition): `ORD-20261030-37aca7af`, `ORD-20261030-8d3a3daf` straddled and finished on the
     old definition; the first new one `ORD-20261030-7dbed2c2` entered BeginFulfillment.
   - UI (after the B fix): "Cancel after payment" `ORD-20261030-806ae80a` → "Order cancelled", "Cancelled — refunded ₹1,299", one CREDIT.
   - Execution example: https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-4cd495b4

6. **Files added/changed**
   - A: `src/common/{orders,payments}.py`; `src/lambdas/{cancel_order,begin_fulfillment}/handler.py` (new);
     `src/lambdas/{payment_provider,payment_webhook,refund_payment,request_payment,reserve_inventory,create_order}/handler.py`;
     `infra/main/{lambda,api,iam,monitoring,outputs,tags}.tf`; `scripts/migrate_legacy_sold.py` (new);
     `tests/unit/test_cancellation.py` (new), `test_refund_payment.py`; `docs/interview-prep.md`, `docs/progress.md`.
   - B: `statemachine/order_saga.asl.json`; `infra/main/{iam,lambda,sfn,tags}.tf`; `src/common/{feed,payments}.py`;
     `src/lambdas/{get_order,payment_provider,payment_webhook,refund_payment}/handler.py`;
     `frontend/src/{api,format,tracker,types}.ts`, `components/ui.tsx`, `pages/Tracker.tsx`;
     `scripts/{e2e_test,inflight_check,capture_ui,smoke_test,place_order,generate_traffic}.py`;
     `tests/unit/{conftest,test_cancellation,test_feed,test_fulfillment,test_get_order,test_refund_payment,test_saga_definition}.py`;
     `docs/evidence/upgrade-2.4/*`, `e2e-failure-tests.md`, `ui/*`.
   - B fix: `src/lambdas/cancel_order/handler.py`, `src/common/feed.py`, `scripts/capture_ui.py`, tests.
   - Docs: `docs/evidence/upgrade-2.4-cancellation.md`, `upgrade-2.4-report.md`, `README.md`,
     `docs/interview-prep.md`, `docs/progress.md`, `scripts/e2e_test.py` (evidence header I1–I9).

7. **Problems hit and fixes**
   - Pre-APPLY review (A): the webhook's new condition is evaluated by TransactWriteItems' Update on the order item,
     authorised as `dynamodb:UpdateItem` (already allowed); the missing GetItem was added. A cancel Lambda dying after
     its write would have left the token unanswered: now the losing webhook answers OrderCancelled itself and a
     retried cancel re-answers it.
   - The cancel at the moment of the 120 s timeout would have ended FAILED: every failure path now checks
     `cancelRequestedAt` first (required by review; unit-tested; removed from Known gaps). Added a fallback Catch so
     a failing check can't leave the order unfinished.
   - e2e g failed on A: the DLQ (27 messages, never purged) peeked 10 at a time with nothing hidden. Now
     deterministic: count +1, then a full no-delete sweep (verified: found after 19 of 29; a missing one swept all 29).
   - Deploy ordering: the cancel Lambda flipped ~2 min before the state machine updated; the `cancellable` stamp held
     (13 × 409). Recorded as the debugging story.
   - First UI run on B crashed printing "₹" to a cp1252 console; the screenshots then showed the repeated default
     reason in the feed and a confirm step captured before the tracker's poll caught up. Fixed in `fd8709a`.
   - Local plans show query-definition and policy noise (CRLF heredocs, policy documents read during apply); CI's plan
     doesn't.
   - The legacy dry-run evidence file was overwritten by the post-apply re-run; renamed to
     `legacy-migration-dry-run-after-apply.md` (the BEFORE check and the plan are in `legacy-migration-apply.md`).

8. **Cost notes.** No always-on resource: two Lambdas, one route, one alarm (~$0.10/month), four metric filters
   (free). Per order, states entered: a one-line COMPLETED order 9 → 12 (+3: WarehouseSpeed, BeginFulfillment,
   CancelledBeforeFulfillment), a failed order +2 (the cancel check), a cancel while waiting 8, a cancel after payment
   12. At the Standard list price of $0.025 per 1,000 transitions (an estimate, not measured on the bill) that's about
   $0.0001 more per order. Today's test traffic: a few hundred orders, within the free tiers or cents.

9. **Manual steps.** None. The orders DLQ gained poison orders from the e2e and UI runs; leave them (never purged).
   Orders from `inflight_check.py` (payment_slow, "inflight_check: old-definition probe") and the race stay as history.

10. **Git.** A `eb9a4ab` (CI 41043851030, Deploy 41044113358), B `48e7d8e` (CI 41060910418, Deploy 41061113800),
    B fix `fd8709a` (CI 41064702078, Deploy 41065249876), all green and pushed. Docs commit DOCS_SHA
    (CI DOCS_CI, Deploy DOCS_DEPLOY), green; recorded by the follow-up commit that adds this line.
