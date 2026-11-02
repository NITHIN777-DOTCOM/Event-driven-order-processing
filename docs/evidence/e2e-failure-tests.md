# End-to-end tests: every saga path, with DemoPay money and stock invariants (I1-I9)

Run: 2026-11-02 06:46:10 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 640s

**Result: 35/35 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I9) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261102-1c23639e` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-1c23639e) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261102-9e57b83d` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-9e57b83d) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261102-dead4cc0` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-dead4cc0) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261102-25e5fb2b` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-25e5fb2b) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261102-67aeca9e` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-67aeca9e) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261102-b29a3f89` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-b29a3f89) |
| g | poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING | PASS | `ORD-20261102-e8991ae1` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261102-21ceb684` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-21ceb684) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261102-abd4d5b8` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-abd4d5b8) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261102-abd4d5b8` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-abd4d5b8) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261102-31d0f1b7` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-31d0f1b7) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261102-c8e696ff` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-c8e696ff) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261102-cb86e83e` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-cb86e83e) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261102-695bd9b1` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-695bd9b1) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261102-eca7e792` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-eca7e792) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261102-1ca02a95` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-1ca02a95) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261102-9b75b256` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-9b75b256) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261102-8c32c4d9` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-8c32c4d9) |
| za | 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off | PASS | `ORD-20261102-0bc00ba3` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹8495 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-0bc00ba3) |
| zb | every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 | PASS | `ORD-20261102-8b04f458` | REFUNDED · ledger 1 DEBIT / 2 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-8b04f458) |
| zc | order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds | PASS | `ORD-20261102-f5a25ecc` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-f5a25ecc) |
| zd | cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent | PASS | `ORD-20261102-b22702e4` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-b22702e4) |
| ze | cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back | PASS | `ORD-20261102-5914a4f5` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-5914a4f5) |
| zf | cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry | PASS | `ORD-20261102-0da6298a` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-0da6298a) |
| zg | cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged | PASS | `ORD-20261102-1c23639e` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-1c23639e) |
| zh | cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once | PASS | `ORD-20261102-f9590f30` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-f9590f30) |
| zi | RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) | PASS | `ORD-20261102-3e63641f` | 18 x cancel won, nothing charged; 1 x paid first, then cancelled (saga refund); 1 x payment won, cancel refused (409) | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-3e63641f) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261102-1c23639e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-1c23639e`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> COMPLETED
- PASS: MECH-KEYBOARD (stock, reserved) (100, 0) -> (99, 0) (expected stock -1)
- PASS: MECH-KEYBOARD (sold, writtenOff) (0, 0) -> (1, 0) (expected sold +1)
- PASS: stored lines [('L1', Decimal('3499'))] (expected [('L1', 3499)])
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹3499: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹3499, credits []
- PASS: I6 COMPLETED -> net ₹3499 = fulfilled lines ₹3499
- PASS: I7 refunds ₹0 <= charged ₹3499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-1c23639e: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:36:12.892Z  PENDING             Order received via API
2026-11-02T06:36:13.309Z  PROCESSING          Saga workflow started
2026-11-02T06:36:13.442Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:36:13.605Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261102-1c23639e
2026-11-02T06:36:19.077Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-b4f22c23e495 (confirmed by webhook)
2026-11-02T06:36:20.014Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:36:21.035Z  ITEM_FULFILLED      Picked and packed 1 x Mechanical Keyboard, 60% Layout (line L1)
2026-11-02T06:36:21.091Z  COMPLETED           Order fulfilled - payment PAY-b4f22c23e495 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261102-9e57b83d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-9e57b83d`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Card declined by issuer (simulated)'
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_DECLINED -> INVENTORY_RELEASED -> FAILED
- PASS: USBC-HUB (stock, reserved) (100, 0) -> (100, 0) (expected unchanged after release)
- PASS: execution FAILED (expected FAILED)
- PASS: execution error 'OrderFailed' (expected OrderFailed)
- PASS: ReleaseInventory ran
- PASS: last state ['OrderFailed'] (expected OrderFailed)
- PASS: RefundPayment ran (a no-op: nothing was charged)
- PASS: DEBIT ledger entries: 0 (expected 0, card declined before debit)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261102-9e57b83d: FAILED (expected FAILED)

statusHistory:
```
2026-11-02T06:36:48.449Z  PENDING             Order received via API
2026-11-02T06:36:49.170Z  PROCESSING          Saga workflow started
2026-11-02T06:36:49.303Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:36:49.459Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261102-9e57b83d
2026-11-02T06:36:51.600Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-11-02T06:36:53.507Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:36:53.636Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261102-dead4cc0`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-dead4cc0`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹26990: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹26990, credits []
- PASS: I6 COMPLETED -> net ₹26990 = fulfilled lines ₹26990
- PASS: I7 refunds ₹0 <= charged ₹26990
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-dead4cc0: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:36:55.552Z  PENDING             Order received via API
2026-11-02T06:36:55.977Z  PROCESSING          Saga workflow started
2026-11-02T06:36:56.106Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:36:56.219Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-11-02T06:36:58.399Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-11-02T06:37:02.560Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261102-dead4cc0
2026-11-02T06:37:05.725Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-328d07dc7e3c (confirmed by webhook)
2026-11-02T06:37:05.858Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:37:05.974Z  ITEM_FULFILLED      Picked and packed 1 x Noise-Cancelling Wireless Headphones (line L1)
2026-11-02T06:37:06.018Z  COMPLETED           Order fulfilled - payment PAY-328d07dc7e3c captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261102-25e5fb2b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-25e5fb2b`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> CheckCancelBeforeFailing -> CancelledWhileFailing -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261102-25e5fb2b: none (payment never requested) (expected None)

statusHistory:
```
2026-11-02T06:37:09.449Z  PENDING             Order received via API
2026-11-02T06:37:09.974Z  PROCESSING          Saga workflow started
2026-11-02T06:37:10.093Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-11-02T06:37:10.212Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261102-67aeca9e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-67aeca9e`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this (user-scoped) key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1, not 3)
- PASS: 4K-MONITOR stock 100 -> 99 (expected -1, not -3)
- PASS: DEBIT ledger entries: 1 (expected 1, not 3)
- PASS: I1 COMPLETED -> one DEBIT of ₹24999: ledger 1 DEBIT / 0 CREDIT, net ₹24999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹24999, credits []
- PASS: I6 COMPLETED -> net ₹24999 = fulfilled lines ₹24999
- PASS: I7 refunds ₹0 <= charged ₹24999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-67aeca9e: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:37:14.110Z  PENDING             Order received via API
2026-11-02T06:37:14.489Z  PROCESSING          Saga workflow started
2026-11-02T06:37:14.634Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:37:14.759Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261102-67aeca9e
2026-11-02T06:37:19.925Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-85ee22e7462c (confirmed by webhook)
2026-11-02T06:37:20.035Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:37:20.168Z  ITEM_FULFILLED      Picked and packed 1 x 27-inch 4K UHD IPS Monitor (line L1)
2026-11-02T06:37:20.203Z  COMPLETED           Order fulfilled - payment PAY-85ee22e7462c captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261102-b29a3f89`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-b29a3f89`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹799: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹799, credits []
- PASS: I6 COMPLETED -> net ₹799 = fulfilled lines ₹799
- PASS: I7 refunds ₹0 <= charged ₹799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-b29a3f89: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:37:34.729Z  PENDING             Order received via API
2026-11-02T06:37:34.908Z  PROCESSING          Saga workflow started
2026-11-02T06:37:35.028Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:37:35.143Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261102-b29a3f89
2026-11-02T06:37:39.289Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-2722d29be711 (confirmed by webhook)
2026-11-02T06:37:39.397Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:37:39.497Z  ITEM_FULFILLED      Picked and packed 1 x Slim Wireless Mouse (line L1)
2026-11-02T06:37:39.536Z  COMPLETED           Order fulfilled - payment PAY-2722d29be711 captured
```

## g) poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING - PASS

orderId: `ORD-20261102-e8991ae1`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order-saga-orders-dlq count 0 -> 1: no new message within 5 min
- PASS: this order's message found in the DLQ and deleted after the checks (swept 1 of 1 messages; no other message deleted)
- PASS: order-saga-orders-dlq count back to 0 after the cleanup (now 0)
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 PENDING -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261102-e8991ae1: none (payment never requested) (expected None)

statusHistory:
```
2026-11-02T06:35:36.310Z  PENDING             Order received via API
2026-11-02T06:35:37.631Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-11-02T06:36:36.678Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-11-02T06:37:36.659Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261102-21ceb684`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-21ceb684`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed'
- PASS: USB-MIC (stock, reserved) (18, 0) -> (18, 0) (expected unchanged)
- PASS: DemoPay balance 1000 (expected 1000, untouched)
- PASS: no DEBIT ledger entry
- PASS: ReleaseInventory ran (compensation)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261102-21ceb684: FAILED (expected FAILED)

statusHistory:
```
2026-11-02T06:38:01.548Z  PENDING             Order received via API
2026-11-02T06:38:01.997Z  PROCESSING          Saga workflow started
2026-11-02T06:38:02.118Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:38:02.259Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261102-21ceb684
2026-11-02T06:38:04.799Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-11-02T06:38:05.037Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:38:05.166Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261102-abd4d5b8`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-abd4d5b8`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹2299: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹2299, credits []
- PASS: I6 COMPLETED -> net ₹2299 = fulfilled lines ₹2299
- PASS: I7 refunds ₹0 <= charged ₹2299
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-abd4d5b8: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:38:24.664Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-11-02T06:38:25.290Z  PROCESSING          Saga workflow started
2026-11-02T06:38:25.409Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:38:25.523Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261102-abd4d5b8
2026-11-02T06:38:27.663Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-847746ab4e6f (confirmed by webhook)
2026-11-02T06:38:27.770Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:38:27.880Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-02T06:38:27.913Z  COMPLETED           Order fulfilled - payment PAY-847746ab4e6f captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261102-abd4d5b8`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-abd4d5b8`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-11-02T06:38:24.664Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-11-02T06:38:25.290Z  PROCESSING          Saga workflow started
2026-11-02T06:38:25.409Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:38:25.523Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261102-abd4d5b8
2026-11-02T06:38:27.663Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-847746ab4e6f (confirmed by webhook)
2026-11-02T06:38:27.770Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:38:27.880Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-02T06:38:27.913Z  COMPLETED           Order fulfilled - payment PAY-847746ab4e6f captured
```

## k) auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public - PASS

orderId: `None`

Checks:
- PASS: GET /products without a token -> 200 (expected 200)
- PASS: POST /orders without a token -> 401 (expected 401)
- PASS: GET /orders without a token -> 401 (expected 401)
- PASS: GET /orders/ORD-20261028-00000000 without a token -> 401 (expected 401)
- PASS: GET /wallet without a token -> 401 (expected 401)
- PASS: POST /wallet/reset without a token -> 401 (expected 401)
- PASS: GET /wallet with a tampered signature -> 401 (expected 401)
- PASS: GET /wallet with a payload forged as user B -> 401 (expected 401)
- PASS: access token carries token_use=access, email (matches A: True), email_verified=True
- PASS: GET /wallet with the ACCESS token -> 200 (expected 200, A's wallet)
- PASS: GET /wallet with the ID token -> 401 (expected 401: ID tokens are not accepted: send the access token in the Authorization header)
- PASS: GET /orders with the ID token -> 401 (expected 401: ID tokens are not accepted: send the access token in the Authorization header)
- PASS: POST /orders with the ID token -> 401 (expected 401: ID tokens are not accepted: send the access token in the Authorization header)

## l) order isolation: A can't read B's order (404), each list shows only its owner's orders - PASS

orderId: `ORD-20261102-31d0f1b7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-31d0f1b7`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (50 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-11-02T06:39:04.348Z  PENDING             Order received via API
2026-11-02T06:39:04.575Z  PROCESSING          Saga workflow started
2026-11-02T06:39:04.698Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:39:04.839Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261102-31d0f1b7
2026-11-02T06:39:10.025Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-28aceea2c6ab (confirmed by webhook)
2026-11-02T06:39:10.159Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:39:10.271Z  ITEM_FULFILLED      Picked and packed 1 x Felt and Leather Desk Mat (line L1)
2026-11-02T06:39:10.322Z  COMPLETED           Order fulfilled - payment PAY-28aceea2c6ab captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261102-c8e696ff`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-c8e696ff`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261102-364b25d6, B ORD-20261102-c8e696ff
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261102-364b25d6 COMPLETED
- PASS: ORD-20261102-c8e696ff COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-c8e696ff: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:39:52.668Z  PENDING             Order received via API
2026-11-02T06:39:52.964Z  PROCESSING          Saga workflow started
2026-11-02T06:39:53.165Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:39:53.283Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261102-c8e696ff
2026-11-02T06:39:58.529Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-b120eb5a53b6 (confirmed by webhook)
2026-11-02T06:39:58.625Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:39:58.757Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-02T06:39:58.792Z  COMPLETED           Order fulfilled - payment PAY-b120eb5a53b6 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261102-e2eb520b)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261102-cb86e83e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-cb86e83e`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: the saga waited at PAYMENT_PENDING
- PASS: MarkPaymentTimedOut ran (States.Timeout caught after 120 s)
- PASS: compensation ran: RefundPayment, ReleaseInventory
- PASS: CURVED-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: RequestPayment waited 120.0 s before timing out (expected ~120)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261102-cb86e83e: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-11-02T06:35:36.850Z  PENDING             Order received via API
2026-11-02T06:35:37.913Z  PROCESSING          Saga workflow started
2026-11-02T06:35:38.944Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:35:39.972Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261102-cb86e83e
2026-11-02T06:37:39.987Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:37:40.085Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261102-695bd9b1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-695bd9b1`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261102-695bd9b1 REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹18999 <= charged ₹18999
- PASS: I4 intent PI-ORD-20261102-695bd9b1: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-02T06:35:37.410Z  PENDING             Order received via API
2026-11-02T06:35:38.502Z  PROCESSING          Saga workflow started
2026-11-02T06:35:39.315Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:35:40.240Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261102-695bd9b1
2026-11-02T06:37:40.622Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:37:40.713Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-11-02T06:38:10.669Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-444d8759e426, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261102-eca7e792`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-eca7e792`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: exactly one PAYMENT_CAPTURED in statusHistory
- PASS: webhook log lines with result 'duplicate' for this intent: 1 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹6499: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹6499, credits []
- PASS: I6 COMPLETED -> net ₹6499 = fulfilled lines ₹6499
- PASS: I7 refunds ₹0 <= charged ₹6499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-eca7e792: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:40:11.107Z  PENDING             Order received via API
2026-11-02T06:40:11.472Z  PROCESSING          Saga workflow started
2026-11-02T06:40:11.574Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:40:11.698Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261102-eca7e792
2026-11-02T06:40:16.831Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-5007e1c01ba5 (confirmed by webhook)
2026-11-02T06:40:16.925Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:40:17.038Z  ITEM_FULFILLED      Picked and packed 1 x Ergonomic Wireless Mouse (line L1)
2026-11-02T06:40:17.072Z  COMPLETED           Order fulfilled - payment PAY-5007e1c01ba5 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261102-1ca02a95`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-1ca02a95`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: 'webhook_signature_rejected' log lines since this order: 1 (expected >= 1)
- PASS: DemoPay logged the 401 for its forged callback, then sent the genuine one
- PASS: CloudWatch OrderSaga/WebhookSignatureFailures during this run: 6 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-1ca02a95: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:40:51.571Z  PENDING             Order received via API
2026-11-02T06:40:51.876Z  PROCESSING          Saga workflow started
2026-11-02T06:40:51.992Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:40:52.139Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261102-1ca02a95
2026-11-02T06:40:56.342Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-09efaf2375b8 (confirmed by webhook)
2026-11-02T06:40:56.533Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:40:56.661Z  ITEM_FULFILLED      Picked and packed 1 x True Wireless Earbuds (line L1)
2026-11-02T06:40:56.701Z  COMPLETED           Order fulfilled - payment PAY-09efaf2375b8 captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 599 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) -> (12, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261102-fc9a253f83 exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (13, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261102-425a9f4ad5 -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (14, 0, 0) (expected (14, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-11-02T06:41:21.518Z  HOLD                HOLD-20261102-425a9f4ad5 and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261102-c773317983 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 20.1 s after expiresAt 2026-11-02T06:36:11.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved, sold, writtenOff) (100, 0, 0, 0, 0) -> (99, 0, 0, 1, 0): the 3 held units went back (held 0, pool 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-11-02T06:35:41.052Z  ACTIVE              HOLD-20261102-c773317983: 3 x DESK-MAT held for 30 s
2026-11-02T06:36:11.000Z  expiresAt           the schedule's at() time
2026-11-02T06:36:31.146Z  EXPIRED             by the schedule, 20.1 s after expiresAt
```

## v) two users race for the last unit -> exactly one hold (201), the other 409 - PASS

orderId: `None`

Checks:
- PASS: HTTP codes [201, 409] (expected [201, 409])
- PASS: the loser's 409 names VERTICAL-MOUSE
- PASS: VERTICAL-MOUSE (stock, held) (0, 1) (expected (0, 1))
- PASS: VERTICAL-MOUSE restored to (9, 0, 0)

## w) hold ownership: B can't release or see A's hold (404) - PASS

orderId: `None`

Checks:
- PASS: B: DELETE /holds/HOLD-20261102-40e6d032a7 (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261102-9b75b256`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-9b75b256`

Checks:
- PASS: POST /holds -> 201 HOLD-20261102-55e4df5b91
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261102-55e4df5b91'
- PASS: hold CONSUMED by ORD-20261102-9b75b256 (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (98, 0, 0) -> (97, 0, 0) (stock -1 once, at hold time; held -> reserved -> sold)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-9b75b256: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:41:32.913Z  PENDING             Order received via API
2026-11-02T06:41:33.244Z  PROCESSING          Saga workflow started
2026-11-02T06:41:33.374Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261102-55e4df5b91
2026-11-02T06:41:33.578Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261102-9b75b256
2026-11-02T06:41:38.728Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-1890dade913c (confirmed by webhook)
2026-11-02T06:41:38.844Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:41:38.943Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-02T06:41:38.979Z  COMPLETED           Order fulfilled - payment PAY-1890dade913c captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261102-8c32c4d9`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-8c32c4d9`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261102-7848846468
- PASS: hold HOLD-20261102-7848846468 EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261102-7848846468 had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (14, 0, 0) -> (13, 0, 0) (a normal fresh reservation, then sold)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499, credits []
- PASS: I6 COMPLETED -> net ₹5499 = fulfilled lines ₹5499
- PASS: I7 refunds ₹0 <= charged ₹5499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-8c32c4d9: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:44:48.831Z  PENDING             Order received via API
2026-11-02T06:44:49.425Z  PROCESSING          Saga workflow started
2026-11-02T06:44:49.705Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261102-7848846468 had ended, so reserved afresh)
2026-11-02T06:44:49.958Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261102-8c32c4d9
2026-11-02T06:44:54.426Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-8fc7a1fe0752 (confirmed by webhook)
2026-11-02T06:44:54.598Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:44:54.900Z  ITEM_FULFILLED      Picked and packed 1 x Compact 65% Mechanical Keyboard (line L1)
2026-11-02T06:44:54.946Z  COMPLETED           Order fulfilled - payment PAY-8fc7a1fe0752 captured
```

## za) 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off - PASS

orderId: `ORD-20261102-0bc00ba3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-0bc00ba3`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: line states ['FULFILLED', 'WRITTEN_OFF', 'FULFILLED']
- PASS: L2 refundedAmount 6499 = its lineAmount 6499
- PASS: ledger CREDITs [('L2', Decimal('6499'))] (expected exactly one, for L2)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> ITEM_FULFILLED -> LINE_REFUNDED -> ITEM_WRITTEN_OFF -> PARTIALLY_FULFILLED
- PASS: write-off audit record for L2: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
- PASS: L1 WIRELESS-MOUSE (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 3, 0) (expected (97, 0, 0, 3, 0))
- PASS: L2 ERGO-MOUSE (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (98, 0, 0, 1, 1) (expected (98, 0, 0, 1, 1))
- PASS: L3 LOWPRO-KEYBOARD (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (96, 0, 0, 4, 0) (expected (96, 0, 0, 4, 0))
- PASS: execution SUCCEEDED (expected SUCCEEDED at OrderPartiallyFulfilled)
- PASS: the execution ended in OrderPartiallyFulfilled
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹8495, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹8495 = fulfilled lines ₹8495
- PASS: I7 refunds ₹6499 <= charged ₹14994
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261102-0bc00ba3: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:41:43.426Z  PENDING             Order received via API
2026-11-02T06:41:44.054Z  PROCESSING          Saga workflow started
2026-11-02T06:41:44.172Z  RESERVED            Reserved stock for 3 product(s)
2026-11-02T06:41:44.298Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹14,994 · intent PI-ORD-20261102-0bc00ba3
2026-11-02T06:41:48.441Z  PAYMENT_CAPTURED    ₹14,994 captured by DemoPay · PAY-01f869fc2ba6 (confirmed by webhook)
2026-11-02T06:41:48.549Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:41:48.652Z  ITEM_FULFILLED      Picked and packed 2 x Slim Wireless Mouse (line L1)
2026-11-02T06:41:48.691Z  ITEM_FULFILLED      Picked and packed 3 x Low-Profile Wireless Keyboard (line L3)
2026-11-02T06:41:49.046Z  LINE_REFUNDED       ₹6,499 refunded to DemoPay for 1 x Ergonomic Wireless Mouse (line L2)
2026-11-02T06:41:50.018Z  ITEM_WRITTEN_OFF    1 x Ergonomic Wireless Mouse (line L2) written off: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
2026-11-02T06:41:50.073Z  PARTIALLY_FULFILLED 2 of 3 items delivered - INR 6499.00 refunded for the unavailable items
```

## zb) every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 - PASS

orderId: `ORD-20261102-8b04f458`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-8b04f458`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off'
- PASS: every line WRITTEN_OFF
- PASS: write-off audit records for L1 and L2
- PASS: L1 USBC-HUB (stock, held, reserved, sold, writtenOff) (100, 0, 0, 0, 0) -> (99, 0, 0, 0, 1) (expected (99, 0, 0, 0, 1))
- PASS: L2 WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 1, 2) (expected (97, 0, 0, 1, 2))
- PASS: RefundAllLines ran; ReleaseInventory did not (damaged units are written off, not released)
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 2 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 2 CREDIT, net ₹0, credits ['L1', 'L2']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹11997 <= charged ₹11997
- PASS: I9 one winner: cancel requested False, FULFILLING True, status FAILED
- PASS: I4 intent PI-ORD-20261102-8b04f458: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-02T06:41:54.366Z  PENDING             Order received via API
2026-11-02T06:41:54.815Z  PROCESSING          Saga workflow started
2026-11-02T06:41:54.949Z  RESERVED            Reserved stock for 2 product(s)
2026-11-02T06:41:55.078Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹11,997 · intent PI-ORD-20261102-8b04f458
2026-11-02T06:41:57.206Z  PAYMENT_CAPTURED    ₹11,997 captured by DemoPay · PAY-4143d7ba8e87 (confirmed by webhook)
2026-11-02T06:41:57.313Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:41:57.705Z  LINE_REFUNDED       ₹1,999 refunded to DemoPay for 1 x USB-C Hub, 6-in-1 (line L1)
2026-11-02T06:41:57.785Z  LINE_REFUNDED       ₹9,998 refunded to DemoPay for 2 x True Wireless Earbuds (line L2)
2026-11-02T06:41:57.883Z  ITEM_WRITTEN_OFF    1 x USB-C Hub, 6-in-1 (line L1) written off: USB-C Hub, 6-in-1 (line L1) was found damaged in the warehouse (simulated)
2026-11-02T06:41:57.903Z  ITEM_WRITTEN_OFF    2 x True Wireless Earbuds (line L2) written off: True Wireless Earbuds (line L2) was found damaged in the warehouse (simulated)
2026-11-02T06:41:58.022Z  FAILED              AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off
```

## zc) order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds - PASS

orderId: `ORD-20261102-f5a25ecc`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-f5a25ecc`

Checks:
- PASS: POST /holds -> 201 HOLD-20261102-716c4a40a6
- PASS: POST /orders with holdId -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: RESERVED detail: 'Reserved stock for 2 product(s) from checkout hold HOLD-20261102-716c4a40a6'
- PASS: hold CONSUMED by ORD-20261102-f5a25ecc
- PASS: L1 LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (97, 0, 0, 3, 0) -> (96, 0, 0, 4, 0) (expected (96, 0, 0, 4, 0))
- PASS: L2 ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 1, 2) (expected (97, 0, 0, 1, 2))
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹1799, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹53980 <= charged ₹55779
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261102-f5a25ecc: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:44:58.964Z  PENDING             Order received via API
2026-11-02T06:44:59.376Z  PROCESSING          Saga workflow started
2026-11-02T06:44:59.488Z  RESERVED            Reserved stock for 2 product(s) from checkout hold HOLD-20261102-716c4a40a6
2026-11-02T06:44:59.738Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹55,779 · intent PI-ORD-20261102-f5a25ecc
2026-11-02T06:45:02.925Z  PAYMENT_CAPTURED    ₹55,779 captured by DemoPay · PAY-465f9f160a9c (confirmed by webhook)
2026-11-02T06:45:03.032Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:45:03.259Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-02T06:45:03.580Z  LINE_REFUNDED       ₹53,980 refunded to DemoPay for 2 x Noise-Cancelling Wireless Headphones (line L2)
2026-11-02T06:45:03.793Z  ITEM_WRITTEN_OFF    2 x Noise-Cancelling Wireless Headphones (line L2) written off: Noise-Cancelling Wireless Headphones (line L2) was found damaged in the warehouse (simulated)
2026-11-02T06:45:03.841Z  PARTIALLY_FULFILLED 1 of 2 items delivered - INR 53980.00 refunded for the unavailable items
```

## zd) cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent - PASS

orderId: `ORD-20261102-b22702e4`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-b22702e4`

Checks:
- PASS: POST /orders -> 202
- PASS: waiting for DemoPay: PAYMENT_PENDING, canCancel True
- PASS: user B cancels A's order -> 404 (expected 404, exactly like a missing order)
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261102-b22702e4', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-11-02T06:42:04.391Z'}
- PASS: repeated cancel -> 202, same request 2026-11-02T06:42:04.391Z
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (99, 0, 0, 1, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: CANCELLED detail 'Cancelled by the customer - nothing was charged'
- PASS: DemoPay CHARGE record VOIDED (expected VOIDED: never charged)
- PASS: cancel after the end -> 200 {'orderId': 'ORD-20261102-b22702e4', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-11-02T06:42:04.391Z', 'refundedAmount': 0}
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-b22702e4: FAILED (expected FAILED)

statusHistory:
```
2026-11-02T06:42:01.266Z  PENDING             Order received via API
2026-11-02T06:42:01.590Z  PROCESSING          Saga workflow started
2026-11-02T06:42:01.784Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:42:01.898Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261102-b22702e4
2026-11-02T06:42:04.391Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-02T06:42:04.893Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:42:04.935Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## ze) cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back - PASS

orderId: `ORD-20261102-5914a4f5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-5914a4f5`

Checks:
- PASS: POST /orders -> 202
- PASS: paid, warehouse waiting: PAYMENT_CAPTURED, canCancel True
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261102-5914a4f5', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-11-02T06:42:39.518Z'}
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> CANCEL_REQUESTED -> PAYMENT_REFUNDED -> INVENTORY_RELEASED -> CANCELLED
- PASS: 4K-MONITOR (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (99, 0, 0, 1, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: refundedAmount 24999 (expected the total 24999)
- PASS: CANCELLED detail 'Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet'
- PASS: wallet CREDIT notes ['Refund for ORD-20261102-5914a4f5 (order cancelled)']
- PASS: cancel twice -> 200 {'orderId': 'ORD-20261102-5914a4f5', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-11-02T06:42:39.518Z', 'refundedAmount': 24999} (same answer, no second refund)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹24999 <= charged ₹24999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-5914a4f5: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-02T06:42:32.547Z  PENDING             Order received via API
2026-11-02T06:42:33.132Z  PROCESSING          Saga workflow started
2026-11-02T06:42:33.258Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:42:33.398Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261102-5914a4f5
2026-11-02T06:42:38.545Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-61987d5640ce (confirmed by webhook)
2026-11-02T06:42:39.518Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-02T06:42:49.008Z  PAYMENT_REFUNDED    ₹24,999 refunded to DemoPay (order cancelled)
2026-11-02T06:42:49.106Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:42:49.137Z  CANCELLED           Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet
```

## zf) cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry - PASS

orderId: `ORD-20261102-0da6298a`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-0da6298a`

Checks:
- PASS: POST /orders -> 202
- PASS: packing: FULFILLING, canCancel False
- PASS: cancel -> 409 {'error': 'TOO_LATE_TO_CANCEL', 'status': 'FULFILLING'}
- PASS: cancel again -> 409 (expected 409)
- PASS: order status COMPLETED (expected COMPLETED: the refusal changed nothing)
- PASS: CANCEL_REJECTED entries: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹2299: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹2299, credits []
- PASS: I6 COMPLETED -> net ₹2299 = fulfilled lines ₹2299
- PASS: I7 refunds ₹0 <= charged ₹2299
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-0da6298a: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-02T06:42:50.946Z  PENDING             Order received via API
2026-11-02T06:42:51.154Z  PROCESSING          Saga workflow started
2026-11-02T06:42:51.309Z  RESERVED            Reserved stock for 1 product(s)
2026-11-02T06:42:51.438Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261102-0da6298a
2026-11-02T06:42:54.579Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-a2a893158053 (confirmed by webhook)
2026-11-02T06:43:04.758Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-02T06:43:05.899Z  CANCEL_REJECTED     Cancel request rejected: the order was already FULFILLING
2026-11-02T06:43:14.885Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-02T06:43:14.939Z  COMPLETED           Order fulfilled - payment PAY-a2a893158053 captured
```

## zg) cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged - PASS

orderId: `ORD-20261102-1c23639e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-1c23639e`

Checks:
- PASS: cancel -> 409 {'error': 'TOO_LATE_TO_CANCEL', 'status': 'COMPLETED'}
- PASS: status COMPLETED, canCancel False
- PASS: history only gained ['CANCEL_REJECTED'] (a CANCEL_REJECTED entry at most)

## zh) cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once - PASS

orderId: `ORD-20261102-f9590f30`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-f9590f30`

Checks:
- PASS: POST /holds -> 201 HOLD-20261102-5d5d81adba
- PASS: POST /orders with holdId -> 202
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261102-5d5d81adba'
- PASS: cancel -> 202
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (96, 0, 0, 4, 0) -> (96, 0, 0, 4, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: hold CONSUMED by ORD-20261102-f9590f30 (expected CONSUMED by this order: never released a 2nd time)
- PASS: no current hold, no expiry schedule left
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-f9590f30: FAILED (expected FAILED)

statusHistory:
```
2026-11-02T06:45:05.784Z  PENDING             Order received via API
2026-11-02T06:45:06.143Z  PROCESSING          Saga workflow started
2026-11-02T06:45:06.273Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261102-5d5d81adba
2026-11-02T06:45:06.498Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261102-f9590f30
2026-11-02T06:45:07.616Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-02T06:45:08.087Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-02T06:45:08.135Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## zi) RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) - PASS

orderId: `ORD-20261102-3e63641f`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261102-3e63641f`

Checks:
- PASS: POST /orders x20 -> [202]
- PASS: ORD-20261102-3e63641f CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-3e63641f: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-cbe4258f CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-cbe4258f: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-fcc3ca68 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-fcc3ca68: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-c9ab7f8f CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-c9ab7f8f: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-d792908b COMPLETED: cancel answered 409 (expected 409)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261102-d792908b: SUCCEEDED (expected SUCCEEDED)
- PASS: ORD-20261102-0513ba36 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-0513ba36: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-b2f8715e CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-b2f8715e: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-547bea92 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-547bea92: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-111bccde CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-111bccde: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-122ef5a7 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-122ef5a7: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-76044aa4 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-76044aa4: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-4e466502 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-4e466502: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-3bdab40a CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-3bdab40a: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-c3ab7c3f CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-c3ab7c3f: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-c73a5603 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-c73a5603: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-56da7329 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-56da7329: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-c3263e50 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-c3263e50: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-3222eafd CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-3222eafd: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-cc66f787 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-cc66f787: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261102-22e88f18 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261102-22e88f18: FAILED (expected FAILED or REFUNDED)
- PASS: WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (97, 0, 0, 1, 2) -> (96, 0, 0, 2, 2) (expected (96, 0, 0, 2, 2): only the 1 COMPLETED orders sold a unit)
