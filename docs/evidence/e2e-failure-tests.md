# End-to-end tests: every saga path, with DemoPay money and stock invariants (I1-I9)

Run: 2026-11-01 04:18:41 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 404s

**Result: 35/35 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I9) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261101-d574ebc1` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d574ebc1) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261101-f6ac3e88` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-f6ac3e88) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261101-34d61939` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-34d61939) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261101-60fcd741` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-60fcd741) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261101-3191d322` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-3191d322) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261101-097e8882` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-097e8882) |
| g | poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING | PASS | `ORD-20261101-570f773f` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261101-bee61658` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-bee61658) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261101-ca0513a4` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-ca0513a4) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261101-ca0513a4` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-ca0513a4) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261101-c8b45515` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-c8b45515) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261101-2a483426` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-2a483426) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261101-ba28c24c` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-ba28c24c) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261101-2d40e430` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-2d40e430) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261101-3a27ab08` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-3a27ab08) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261101-fa1ee193` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-fa1ee193) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261101-7926d28c` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-7926d28c) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261101-0ba6c776` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-0ba6c776) |
| za | 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off | PASS | `ORD-20261101-7b2c398b` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹8495 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-7b2c398b) |
| zb | every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 | PASS | `ORD-20261101-73379a1b` | REFUNDED · ledger 1 DEBIT / 2 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-73379a1b) |
| zc | order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds | PASS | `ORD-20261101-000db153` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-000db153) |
| zd | cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent | PASS | `ORD-20261101-6ee8b70b` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6ee8b70b) |
| ze | cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back | PASS | `ORD-20261101-b5d54d8b` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-b5d54d8b) |
| zf | cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry | PASS | `ORD-20261101-9b29cd6b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-9b29cd6b) |
| zg | cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged | PASS | `ORD-20261101-d574ebc1` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d574ebc1) |
| zh | cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once | PASS | `ORD-20261101-08ca7c5a` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-08ca7c5a) |
| zi | RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) | PASS | `ORD-20261101-1b40c77f` | 3 x cancel won, late charge refunded by the webhook; 15 x cancel won, nothing charged; 2 x payment won, cancel refused (409) | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-1b40c77f) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261101-d574ebc1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d574ebc1`

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
- PASS: I4 intent PI-ORD-20261101-d574ebc1: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:12:04.009Z  PENDING             Order received via API
2026-11-01T04:12:04.257Z  PROCESSING          Saga workflow started
2026-11-01T04:12:04.374Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:04.493Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261101-d574ebc1
2026-11-01T04:12:06.627Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-becc3002b24d (confirmed by webhook)
2026-11-01T04:12:06.751Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:12:06.877Z  ITEM_FULFILLED      Picked and packed 1 x Mechanical Keyboard, 60% Layout (line L1)
2026-11-01T04:12:06.921Z  COMPLETED           Order fulfilled - payment PAY-becc3002b24d captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261101-f6ac3e88`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-f6ac3e88`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Card declined by issuer (simulated)'
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_DECLINED -> INVENTORY_RELEASED -> FAILED
- PASS: USBC-HUB (stock, reserved) (99, 0) -> (99, 0) (expected unchanged after release)
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
- PASS: I4 intent PI-ORD-20261101-f6ac3e88: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T04:12:10.257Z  PENDING             Order received via API
2026-11-01T04:12:10.762Z  PROCESSING          Saga workflow started
2026-11-01T04:12:10.876Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:11.006Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261101-f6ac3e88
2026-11-01T04:12:14.120Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-11-01T04:12:15.751Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:12:15.871Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261101-34d61939`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-34d61939`

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
- PASS: I4 intent PI-ORD-20261101-34d61939: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:12:18.191Z  PENDING             Order received via API
2026-11-01T04:12:18.785Z  PROCESSING          Saga workflow started
2026-11-01T04:12:18.890Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:19.035Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-11-01T04:12:21.170Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-11-01T04:12:25.344Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261101-34d61939
2026-11-01T04:12:27.476Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-25fd0ca65641 (confirmed by webhook)
2026-11-01T04:12:27.577Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:12:27.696Z  ITEM_FULFILLED      Picked and packed 1 x Noise-Cancelling Wireless Headphones (line L1)
2026-11-01T04:12:27.729Z  COMPLETED           Order fulfilled - payment PAY-25fd0ca65641 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261101-60fcd741`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-60fcd741`

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
- PASS: I4 intent PI-ORD-20261101-60fcd741: none (payment never requested) (expected None)

statusHistory:
```
2026-11-01T04:12:30.212Z  PENDING             Order received via API
2026-11-01T04:12:30.803Z  PROCESSING          Saga workflow started
2026-11-01T04:12:30.953Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-11-01T04:12:31.082Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261101-3191d322`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-3191d322`

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
- PASS: I4 intent PI-ORD-20261101-3191d322: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:12:33.532Z  PENDING             Order received via API
2026-11-01T04:12:34.048Z  PROCESSING          Saga workflow started
2026-11-01T04:12:34.177Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:34.314Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261101-3191d322
2026-11-01T04:12:36.451Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-01b928c80ab3 (confirmed by webhook)
2026-11-01T04:12:36.591Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:12:36.684Z  ITEM_FULFILLED      Picked and packed 1 x 27-inch 4K UHD IPS Monitor (line L1)
2026-11-01T04:12:36.721Z  COMPLETED           Order fulfilled - payment PAY-01b928c80ab3 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261101-097e8882`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-097e8882`

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
- PASS: I4 intent PI-ORD-20261101-097e8882: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:12:54.932Z  PENDING             Order received via API
2026-11-01T04:12:55.040Z  PROCESSING          Saga workflow started
2026-11-01T04:12:55.147Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:55.268Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261101-097e8882
2026-11-01T04:13:00.390Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-3d7b13970b0c (confirmed by webhook)
2026-11-01T04:13:00.485Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:13:00.577Z  ITEM_FULFILLED      Picked and packed 1 x Slim Wireless Mouse (line L1)
2026-11-01T04:13:00.613Z  COMPLETED           Order fulfilled - payment PAY-3d7b13970b0c captured
```

## g) poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING - PASS

orderId: `ORD-20261101-570f773f`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order-saga-orders-dlq count 40 -> 41: no new message within 5 min
- PASS: this order's message found in the DLQ (swept 18 of 41 messages, none deleted)
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 PENDING -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261101-570f773f: none (payment never requested) (expected None)

statusHistory:
```
2026-11-01T04:11:59.534Z  PENDING             Order received via API
2026-11-01T04:11:59.752Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-11-01T04:12:59.745Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-11-01T04:13:59.748Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261101-bee61658`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-bee61658`

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
- PASS: I4 intent PI-ORD-20261101-bee61658: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T04:13:22.072Z  PENDING             Order received via API
2026-11-01T04:13:22.402Z  PROCESSING          Saga workflow started
2026-11-01T04:13:22.514Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:13:22.629Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261101-bee61658
2026-11-01T04:13:24.770Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-11-01T04:13:25.017Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:13:25.140Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261101-ca0513a4`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-ca0513a4`

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
- PASS: I4 intent PI-ORD-20261101-ca0513a4: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:13:27.819Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-11-01T04:13:28.379Z  PROCESSING          Saga workflow started
2026-11-01T04:13:28.479Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:13:28.622Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261101-ca0513a4
2026-11-01T04:13:31.770Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-009a3e5e07d5 (confirmed by webhook)
2026-11-01T04:13:31.866Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:13:31.965Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-01T04:13:32Z  COMPLETED           Order fulfilled - payment PAY-009a3e5e07d5 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261101-ca0513a4`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-ca0513a4`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-11-01T04:13:27.819Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-11-01T04:13:28.379Z  PROCESSING          Saga workflow started
2026-11-01T04:13:28.479Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:13:28.622Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261101-ca0513a4
2026-11-01T04:13:31.770Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-009a3e5e07d5 (confirmed by webhook)
2026-11-01T04:13:31.866Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:13:31.965Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-01T04:13:32Z  COMPLETED           Order fulfilled - payment PAY-009a3e5e07d5 captured
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

orderId: `ORD-20261101-c8b45515`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-c8b45515`

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
2026-11-01T04:13:51.004Z  PENDING             Order received via API
2026-11-01T04:13:51.413Z  PROCESSING          Saga workflow started
2026-11-01T04:13:51.530Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:13:51.662Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261101-c8b45515
2026-11-01T04:13:56.790Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-cff24f23df1e (confirmed by webhook)
2026-11-01T04:13:56.883Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:13:56.962Z  ITEM_FULFILLED      Picked and packed 1 x Felt and Leather Desk Mat (line L1)
2026-11-01T04:13:56.994Z  COMPLETED           Order fulfilled - payment PAY-cff24f23df1e captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261101-2a483426`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-2a483426`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261101-8686cc25, B ORD-20261101-2a483426
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261101-8686cc25 COMPLETED
- PASS: ORD-20261101-2a483426 COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-2a483426: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:14:04.096Z  PENDING             Order received via API
2026-11-01T04:14:04.661Z  PROCESSING          Saga workflow started
2026-11-01T04:14:04.757Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:14:04.865Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261101-2a483426
2026-11-01T04:14:09.991Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-cfea9a40684d (confirmed by webhook)
2026-11-01T04:14:10.096Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:14:10.182Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-01T04:14:10.222Z  COMPLETED           Order fulfilled - payment PAY-cfea9a40684d captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261101-e2e07a0f)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261101-ba28c24c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-ba28c24c`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: the saga waited at PAYMENT_PENDING
- PASS: MarkPaymentTimedOut ran (States.Timeout caught after 120 s)
- PASS: compensation ran: RefundPayment, ReleaseInventory
- PASS: CURVED-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: RequestPayment waited 120.1 s before timing out (expected ~120)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261101-ba28c24c: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-11-01T04:11:59.794Z  PENDING             Order received via API
2026-11-01T04:12:00.008Z  PROCESSING          Saga workflow started
2026-11-01T04:12:00.127Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:00.274Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261101-ba28c24c
2026-11-01T04:14:00.477Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:14:00.565Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261101-2d40e430`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-2d40e430`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261101-2d40e430 REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹18999 <= charged ₹18999
- PASS: I4 intent PI-ORD-20261101-2d40e430: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-01T04:12:00.120Z  PENDING             Order received via API
2026-11-01T04:12:00.248Z  PROCESSING          Saga workflow started
2026-11-01T04:12:00.379Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:12:00.526Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261101-2d40e430
2026-11-01T04:14:00.726Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:14:00.830Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-11-01T04:14:31.497Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-1d4a9ca8496c, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261101-3a27ab08`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-3a27ab08`

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
- PASS: I4 intent PI-ORD-20261101-3a27ab08: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:14:12.012Z  PENDING             Order received via API
2026-11-01T04:14:12.434Z  PROCESSING          Saga workflow started
2026-11-01T04:14:12.532Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:14:12.682Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261101-3a27ab08
2026-11-01T04:14:15.808Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-e3e6d675ff70 (confirmed by webhook)
2026-11-01T04:14:15.898Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:14:16.002Z  ITEM_FULFILLED      Picked and packed 1 x Ergonomic Wireless Mouse (line L1)
2026-11-01T04:14:16.035Z  COMPLETED           Order fulfilled - payment PAY-e3e6d675ff70 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261101-fa1ee193`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-fa1ee193`

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
- PASS: I4 intent PI-ORD-20261101-fa1ee193: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:14:20.649Z  PENDING             Order received via API
2026-11-01T04:14:21.200Z  PROCESSING          Saga workflow started
2026-11-01T04:14:21.312Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:14:21.442Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261101-fa1ee193
2026-11-01T04:14:25.589Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-7dd33f9e4a67 (confirmed by webhook)
2026-11-01T04:14:25.687Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:14:25.787Z  ITEM_FULFILLED      Picked and packed 1 x True Wireless Earbuds (line L1)
2026-11-01T04:14:25.820Z  COMPLETED           Order fulfilled - payment PAY-7dd33f9e4a67 captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 599 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) -> (12, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261101-ff104963c4 exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (13, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261101-c8b68e5017 -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (14, 0, 0) (expected (14, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-11-01T04:14:43.947Z  HOLD                HOLD-20261101-c8b68e5017 and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261101-b8a6798665 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 41.7 s after expiresAt 2026-11-01T04:12:33.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved, sold, writtenOff) (95, 0, 0, 5, 0) -> (94, 0, 0, 6, 0): the 3 held units went back (held 0, pool 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-11-01T04:12:03.028Z  ACTIVE              HOLD-20261101-b8a6798665: 3 x DESK-MAT held for 30 s
2026-11-01T04:12:33.000Z  expiresAt           the schedule's at() time
2026-11-01T04:13:14.746Z  EXPIRED             by the schedule, 41.7 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261101-3c05cdcd90 (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261101-7926d28c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-7926d28c`

Checks:
- PASS: POST /holds -> 201 HOLD-20261101-f739f79cf6
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261101-f739f79cf6'
- PASS: hold CONSUMED by ORD-20261101-7926d28c (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (97, 0, 0) -> (96, 0, 0) (stock -1 once, at hold time; held -> reserved -> sold)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-7926d28c: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:14:48.692Z  PENDING             Order received via API
2026-11-01T04:14:49.226Z  PROCESSING          Saga workflow started
2026-11-01T04:14:49.352Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261101-f739f79cf6
2026-11-01T04:14:49.586Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261101-7926d28c
2026-11-01T04:14:53.728Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-cddda76e4110 (confirmed by webhook)
2026-11-01T04:14:53.815Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:14:53.923Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-01T04:14:53.959Z  COMPLETED           Order fulfilled - payment PAY-cddda76e4110 captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261101-0ba6c776`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-0ba6c776`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261101-886a14bcab
- PASS: hold HOLD-20261101-886a14bcab EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261101-886a14bcab had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (14, 0, 0) -> (13, 0, 0) (a normal fresh reservation, then sold)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499, credits []
- PASS: I6 COMPLETED -> net ₹5499 = fulfilled lines ₹5499
- PASS: I7 refunds ₹0 <= charged ₹5499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-0ba6c776: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:17:51.981Z  PENDING             Order received via API
2026-11-01T04:17:52.404Z  PROCESSING          Saga workflow started
2026-11-01T04:17:52.732Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261101-886a14bcab had ended, so reserved afresh)
2026-11-01T04:17:52.954Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261101-0ba6c776
2026-11-01T04:17:58.564Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-8d8332012ad1 (confirmed by webhook)
2026-11-01T04:17:58.795Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:17:59.004Z  ITEM_FULFILLED      Picked and packed 1 x Compact 65% Mechanical Keyboard (line L1)
2026-11-01T04:17:59.055Z  COMPLETED           Order fulfilled - payment PAY-8d8332012ad1 captured
```

## za) 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off - PASS

orderId: `ORD-20261101-7b2c398b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-7b2c398b`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: line states ['FULFILLED', 'WRITTEN_OFF', 'FULFILLED']
- PASS: L2 refundedAmount 6499 = its lineAmount 6499
- PASS: ledger CREDITs [('L2', Decimal('6499'))] (expected exactly one, for L2)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> ITEM_FULFILLED -> LINE_REFUNDED -> ITEM_WRITTEN_OFF -> PARTIALLY_FULFILLED
- PASS: write-off audit record for L2: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
- PASS: L1 WIRELESS-MOUSE (stock, held, reserved, sold, writtenOff) (95, 0, 0, 5, 0) -> (93, 0, 0, 7, 0) (expected (93, 0, 0, 7, 0))
- PASS: L2 ERGO-MOUSE (stock, held, reserved, sold, writtenOff) (97, 0, 0, 1, 2) -> (96, 0, 0, 1, 3) (expected (96, 0, 0, 1, 3))
- PASS: L3 LOWPRO-KEYBOARD (stock, held, reserved, sold, writtenOff) (98, 0, 0, 1, 1) -> (95, 0, 0, 4, 1) (expected (95, 0, 0, 4, 1))
- PASS: execution SUCCEEDED (expected SUCCEEDED at OrderPartiallyFulfilled)
- PASS: the execution ended in OrderPartiallyFulfilled
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹8495, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹8495 = fulfilled lines ₹8495
- PASS: I7 refunds ₹6499 <= charged ₹14994
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261101-7b2c398b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:14:56.787Z  PENDING             Order received via API
2026-11-01T04:14:57.273Z  PROCESSING          Saga workflow started
2026-11-01T04:14:57.370Z  RESERVED            Reserved stock for 3 product(s)
2026-11-01T04:14:57.479Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹14,994 · intent PI-ORD-20261101-7b2c398b
2026-11-01T04:15:02.604Z  PAYMENT_CAPTURED    ₹14,994 captured by DemoPay · PAY-e0f15e622994 (confirmed by webhook)
2026-11-01T04:15:02.705Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:15:02.822Z  ITEM_FULFILLED      Picked and packed 2 x Slim Wireless Mouse (line L1)
2026-11-01T04:15:02.866Z  ITEM_FULFILLED      Picked and packed 3 x Low-Profile Wireless Keyboard (line L3)
2026-11-01T04:15:03.087Z  LINE_REFUNDED       ₹6,499 refunded to DemoPay for 1 x Ergonomic Wireless Mouse (line L2)
2026-11-01T04:15:03.772Z  ITEM_WRITTEN_OFF    1 x Ergonomic Wireless Mouse (line L2) written off: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
2026-11-01T04:15:03.830Z  PARTIALLY_FULFILLED 2 of 3 items delivered - INR 6499.00 refunded for the unavailable items
```

## zb) every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 - PASS

orderId: `ORD-20261101-73379a1b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-73379a1b`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off'
- PASS: every line WRITTEN_OFF
- PASS: write-off audit records for L1 and L2
- PASS: L1 USBC-HUB (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (98, 0, 0, 1, 1) (expected (98, 0, 0, 1, 1))
- PASS: L2 WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 1, 2) (expected (97, 0, 0, 1, 2))
- PASS: RefundAllLines ran; ReleaseInventory did not (damaged units are written off, not released)
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 2 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 2 CREDIT, net ₹0, credits ['L1', 'L2']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹11997 <= charged ₹11997
- PASS: I9 one winner: cancel requested False, FULFILLING True, status FAILED
- PASS: I4 intent PI-ORD-20261101-73379a1b: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-01T04:15:07.407Z  PENDING             Order received via API
2026-11-01T04:15:07.787Z  PROCESSING          Saga workflow started
2026-11-01T04:15:07.884Z  RESERVED            Reserved stock for 2 product(s)
2026-11-01T04:15:08.019Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹11,997 · intent PI-ORD-20261101-73379a1b
2026-11-01T04:15:13.151Z  PAYMENT_CAPTURED    ₹11,997 captured by DemoPay · PAY-75c945026880 (confirmed by webhook)
2026-11-01T04:15:13.252Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:15:13.648Z  LINE_REFUNDED       ₹1,999 refunded to DemoPay for 1 x USB-C Hub, 6-in-1 (line L1)
2026-11-01T04:15:13.731Z  LINE_REFUNDED       ₹9,998 refunded to DemoPay for 2 x True Wireless Earbuds (line L2)
2026-11-01T04:15:13.818Z  ITEM_WRITTEN_OFF    1 x USB-C Hub, 6-in-1 (line L1) written off: USB-C Hub, 6-in-1 (line L1) was found damaged in the warehouse (simulated)
2026-11-01T04:15:13.839Z  ITEM_WRITTEN_OFF    2 x True Wireless Earbuds (line L2) written off: True Wireless Earbuds (line L2) was found damaged in the warehouse (simulated)
2026-11-01T04:15:13.949Z  FAILED              AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off
```

## zc) order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds - PASS

orderId: `ORD-20261101-000db153`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-000db153`

Checks:
- PASS: POST /holds -> 201 HOLD-20261101-774e4b0e7f
- PASS: POST /orders with holdId -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: RESERVED detail: 'Reserved stock for 2 product(s) from checkout hold HOLD-20261101-774e4b0e7f'
- PASS: hold CONSUMED by ORD-20261101-000db153
- PASS: L1 LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (96, 0, 0, 4, 0) -> (95, 0, 0, 5, 0) (expected (95, 0, 0, 5, 0))
- PASS: L2 ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 1, 2) (expected (97, 0, 0, 1, 2))
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹1799, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹53980 <= charged ₹55779
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261101-000db153: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:18:02.307Z  PENDING             Order received via API
2026-11-01T04:18:02.630Z  PROCESSING          Saga workflow started
2026-11-01T04:18:02.755Z  RESERVED            Reserved stock for 2 product(s) from checkout hold HOLD-20261101-774e4b0e7f
2026-11-01T04:18:02.994Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹55,779 · intent PI-ORD-20261101-000db153
2026-11-01T04:18:07.129Z  PAYMENT_CAPTURED    ₹55,779 captured by DemoPay · PAY-41d3362a2882 (confirmed by webhook)
2026-11-01T04:18:07.229Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:18:07.458Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-01T04:18:07.745Z  LINE_REFUNDED       ₹53,980 refunded to DemoPay for 2 x Noise-Cancelling Wireless Headphones (line L2)
2026-11-01T04:18:07.927Z  ITEM_WRITTEN_OFF    2 x Noise-Cancelling Wireless Headphones (line L2) written off: Noise-Cancelling Wireless Headphones (line L2) was found damaged in the warehouse (simulated)
2026-11-01T04:18:07.976Z  PARTIALLY_FULFILLED 1 of 2 items delivered - INR 53980.00 refunded for the unavailable items
```

## zd) cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent - PASS

orderId: `ORD-20261101-6ee8b70b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6ee8b70b`

Checks:
- PASS: POST /orders -> 202
- PASS: waiting for DemoPay: PAYMENT_PENDING, canCancel True
- PASS: user B cancels A's order -> 404 (expected 404, exactly like a missing order)
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261101-6ee8b70b', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-11-01T04:15:17.011Z'}
- PASS: repeated cancel -> 202, same request 2026-11-01T04:15:17.011Z
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (99, 0, 0, 1, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: CANCELLED detail 'Cancelled by the customer - nothing was charged'
- PASS: DemoPay CHARGE record VOIDED (expected VOIDED: never charged)
- PASS: cancel after the end -> 200 {'orderId': 'ORD-20261101-6ee8b70b', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-11-01T04:15:17.011Z', 'refundedAmount': 0}
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-6ee8b70b: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T04:15:15.067Z  PENDING             Order received via API
2026-11-01T04:15:15.372Z  PROCESSING          Saga workflow started
2026-11-01T04:15:15.461Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:15:15.584Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261101-6ee8b70b
2026-11-01T04:15:17.011Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-01T04:15:17.332Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:15:17.376Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## ze) cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back - PASS

orderId: `ORD-20261101-b5d54d8b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-b5d54d8b`

Checks:
- PASS: POST /orders -> 202
- PASS: paid, warehouse waiting: PAYMENT_CAPTURED, canCancel True
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261101-b5d54d8b', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-11-01T04:15:52.344Z'}
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> CANCEL_REQUESTED -> PAYMENT_REFUNDED -> INVENTORY_RELEASED -> CANCELLED
- PASS: 4K-MONITOR (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (99, 0, 0, 1, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: refundedAmount 24999 (expected the total 24999)
- PASS: CANCELLED detail 'Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet'
- PASS: wallet CREDIT notes ['Refund for ORD-20261101-b5d54d8b (order cancelled)']
- PASS: cancel twice -> 200 {'orderId': 'ORD-20261101-b5d54d8b', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-11-01T04:15:52.344Z', 'refundedAmount': 24999} (same answer, no second refund)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹24999 <= charged ₹24999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-b5d54d8b: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-01T04:15:45.650Z  PENDING             Order received via API
2026-11-01T04:15:46.000Z  PROCESSING          Saga workflow started
2026-11-01T04:15:46.192Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:15:46.319Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261101-b5d54d8b
2026-11-01T04:15:51.529Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-496f8bc788ee (confirmed by webhook)
2026-11-01T04:15:52.344Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-01T04:16:01.911Z  PAYMENT_REFUNDED    ₹24,999 refunded to DemoPay (order cancelled)
2026-11-01T04:16:01.991Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:16:02.030Z  CANCELLED           Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet
```

## zf) cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry - PASS

orderId: `ORD-20261101-9b29cd6b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-9b29cd6b`

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
- PASS: I4 intent PI-ORD-20261101-9b29cd6b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T04:16:04.310Z  PENDING             Order received via API
2026-11-01T04:16:04.760Z  PROCESSING          Saga workflow started
2026-11-01T04:16:04.907Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T04:16:05.017Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261101-9b29cd6b
2026-11-01T04:16:10.163Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-7b77833e6fe7 (confirmed by webhook)
2026-11-01T04:16:20.393Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T04:16:20.750Z  CANCEL_REJECTED     Cancel request rejected: the order was already FULFILLING
2026-11-01T04:16:30.519Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-01T04:16:30.558Z  COMPLETED           Order fulfilled - payment PAY-7b77833e6fe7 captured
```

## zg) cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged - PASS

orderId: `ORD-20261101-d574ebc1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d574ebc1`

Checks:
- PASS: cancel -> 409 {'error': 'TOO_LATE_TO_CANCEL', 'status': 'COMPLETED'}
- PASS: status COMPLETED, canCancel False
- PASS: history only gained ['CANCEL_REJECTED'] (a CANCEL_REJECTED entry at most)

## zh) cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once - PASS

orderId: `ORD-20261101-08ca7c5a`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-08ca7c5a`

Checks:
- PASS: POST /holds -> 201 HOLD-20261101-810465d70b
- PASS: POST /orders with holdId -> 202
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261101-810465d70b'
- PASS: cancel -> 202
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (95, 0, 0, 5, 0) -> (95, 0, 0, 5, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: hold CONSUMED by ORD-20261101-08ca7c5a (expected CONSUMED by this order: never released a 2nd time)
- PASS: no current hold, no expiry schedule left
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-08ca7c5a: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T04:18:10.464Z  PENDING             Order received via API
2026-11-01T04:18:10.894Z  PROCESSING          Saga workflow started
2026-11-01T04:18:11.072Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261101-810465d70b
2026-11-01T04:18:11.334Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261101-08ca7c5a
2026-11-01T04:18:11.675Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-01T04:18:12.158Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T04:18:12.212Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## zi) RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) - PASS

orderId: `ORD-20261101-1b40c77f`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-1b40c77f`

Checks:
- PASS: POST /orders x20 -> [202]
- PASS: ORD-20261101-1b40c77f CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-1b40c77f: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-4b51f28e CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-4b51f28e: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-ea35772b CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-ea35772b: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-5d05e6d7 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-5d05e6d7: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-378d99e5 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-378d99e5: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-9575fb77 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-9575fb77: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-9884291e CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-9884291e: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-25c7f82e CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-25c7f82e: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-aac57197 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-aac57197: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-3c9ee8e0 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-3c9ee8e0: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-1ff29564 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-1ff29564: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-0d0ce632 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-0d0ce632: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-18c71443 COMPLETED: cancel answered 409 (expected 409)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-18c71443: SUCCEEDED (expected SUCCEEDED)
- PASS: ORD-20261101-38b0a311 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-38b0a311: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-27f203e0 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-27f203e0: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-c5f741db CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-c5f741db: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-3f2e822a COMPLETED: cancel answered 409 (expected 409)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-3f2e822a: SUCCEEDED (expected SUCCEEDED)
- PASS: ORD-20261101-6a081fa0 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-6a081fa0: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-0f11f83d CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-0f11f83d: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-077ff218 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-077ff218: REFUNDED (expected FAILED or REFUNDED)
- PASS: WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (97, 0, 0, 1, 2) -> (95, 0, 0, 3, 2) (expected (95, 0, 0, 3, 2): only the 2 COMPLETED orders sold a unit)
