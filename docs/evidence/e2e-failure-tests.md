# End-to-end tests: every saga path, with DemoPay money and stock invariants (I1-I9)

Run: 2026-11-01 14:16:11 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 1086s

**Result: 35/35 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I9) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261101-a79002e1` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a79002e1) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261101-b323dcbd` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-b323dcbd) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261101-d7961340` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d7961340) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261101-fa63116c` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-fa63116c) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261101-11b02593` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-11b02593) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261101-25e4d6cd` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-25e4d6cd) |
| g | poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING | PASS | `ORD-20261101-bc5067b2` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261101-a336833a` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a336833a) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261101-6f764818` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6f764818) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261101-6f764818` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6f764818) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261101-a0b6d669` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a0b6d669) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261101-d45a4aec` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d45a4aec) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261101-4ac85e5c` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-4ac85e5c) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261101-8ed01d0a` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-8ed01d0a) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261101-0ddca27c` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-0ddca27c) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261101-96eeaa8b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-96eeaa8b) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261101-6904a2e7` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6904a2e7) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261101-24273afa` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-24273afa) |
| za | 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off | PASS | `ORD-20261101-e322a216` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹8495 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-e322a216) |
| zb | every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 | PASS | `ORD-20261101-31cacfc3` | REFUNDED · ledger 1 DEBIT / 2 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-31cacfc3) |
| zc | order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds | PASS | `ORD-20261101-eed0f42b` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-eed0f42b) |
| zd | cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent | PASS | `ORD-20261101-bc641919` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-bc641919) |
| ze | cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back | PASS | `ORD-20261101-5dbbb707` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-5dbbb707) |
| zf | cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry | PASS | `ORD-20261101-cadd1b31` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-cadd1b31) |
| zg | cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged | PASS | `ORD-20261101-a79002e1` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a79002e1) |
| zh | cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once | PASS | `ORD-20261101-0ea95f50` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-0ea95f50) |
| zi | RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) | PASS | `ORD-20261101-cec48d3b` | 8 x cancel won, late charge refunded by the webhook; 11 x cancel won, nothing charged; 1 x payment won, cancel refused (409) | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-cec48d3b) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261101-a79002e1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a79002e1`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> COMPLETED
- PASS: MECH-KEYBOARD (stock, reserved) (94, 0) -> (93, 0) (expected stock -1)
- PASS: MECH-KEYBOARD (sold, writtenOff) (6, 0) -> (7, 0) (expected sold +1)
- PASS: stored lines [('L1', Decimal('3499'))] (expected [('L1', 3499)])
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹3499: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹3499, credits []
- PASS: I6 COMPLETED -> net ₹3499 = fulfilled lines ₹3499
- PASS: I7 refunds ₹0 <= charged ₹3499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-a79002e1: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T13:58:11.852Z  PENDING             Order received via API
2026-11-01T13:58:12.086Z  PROCESSING          Saga workflow started
2026-11-01T13:58:12.192Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T13:58:12.359Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261101-a79002e1
2026-11-01T13:58:16.507Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-829efb5b3f93 (confirmed by webhook)
2026-11-01T13:58:16.634Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T13:58:16.740Z  ITEM_FULFILLED      Picked and packed 1 x Mechanical Keyboard, 60% Layout (line L1)
2026-11-01T13:58:16.772Z  COMPLETED           Order fulfilled - payment PAY-829efb5b3f93 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261101-b323dcbd`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-b323dcbd`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Card declined by issuer (simulated)'
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_DECLINED -> INVENTORY_RELEASED -> FAILED
- PASS: USBC-HUB (stock, reserved) (94, 0) -> (94, 0) (expected unchanged after release)
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
- PASS: I4 intent PI-ORD-20261101-b323dcbd: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T13:58:20.170Z  PENDING             Order received via API
2026-11-01T13:58:20.338Z  PROCESSING          Saga workflow started
2026-11-01T13:58:20.443Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T13:58:20.557Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261101-b323dcbd
2026-11-01T13:58:25.659Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-11-01T13:58:27.134Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T13:58:27.263Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261101-d7961340`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d7961340`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 86 -> 85 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹26990: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹26990, credits []
- PASS: I6 COMPLETED -> net ₹26990 = fulfilled lines ₹26990
- PASS: I7 refunds ₹0 <= charged ₹26990
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-d7961340: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T13:58:30.092Z  PENDING             Order received via API
2026-11-01T13:58:30.615Z  PROCESSING          Saga workflow started
2026-11-01T13:58:30.762Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T13:58:30.916Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-11-01T13:58:33.075Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-11-01T13:58:37.215Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261101-d7961340
2026-11-01T13:58:42.381Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-52c2e98be477 (confirmed by webhook)
2026-11-01T13:58:42.484Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T13:58:42.616Z  ITEM_FULFILLED      Picked and packed 1 x Noise-Cancelling Wireless Headphones (line L1)
2026-11-01T13:58:42.653Z  COMPLETED           Order fulfilled - payment PAY-52c2e98be477 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261101-fa63116c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-fa63116c`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (94, 0) -> (94, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> CheckCancelBeforeFailing -> CancelledWhileFailing -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261101-fa63116c: none (payment never requested) (expected None)

statusHistory:
```
2026-11-01T13:58:45.154Z  PENDING             Order received via API
2026-11-01T13:58:45.682Z  PROCESSING          Saga workflow started
2026-11-01T13:58:45.804Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-11-01T13:58:45.901Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261101-11b02593`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-11b02593`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this (user-scoped) key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1, not 3)
- PASS: 4K-MONITOR stock 94 -> 93 (expected -1, not -3)
- PASS: DEBIT ledger entries: 1 (expected 1, not 3)
- PASS: I1 COMPLETED -> one DEBIT of ₹24999: ledger 1 DEBIT / 0 CREDIT, net ₹24999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹24999, credits []
- PASS: I6 COMPLETED -> net ₹24999 = fulfilled lines ₹24999
- PASS: I7 refunds ₹0 <= charged ₹24999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-11b02593: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T13:58:48.472Z  PENDING             Order received via API
2026-11-01T13:58:48.685Z  PROCESSING          Saga workflow started
2026-11-01T13:58:48.780Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T13:58:48.895Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261101-11b02593
2026-11-01T13:58:54.065Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-65cebe1320f4 (confirmed by webhook)
2026-11-01T13:58:54.165Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T13:58:54.267Z  ITEM_FULFILLED      Picked and packed 1 x 27-inch 4K UHD IPS Monitor (line L1)
2026-11-01T13:58:54.311Z  COMPLETED           Order fulfilled - payment PAY-65cebe1320f4 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261101-25e4d6cd`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-25e4d6cd`

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
- PASS: I4 intent PI-ORD-20261101-25e4d6cd: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:06:21.202Z  PENDING             Order received via API
2026-11-01T14:06:21.859Z  PROCESSING          Saga workflow started
2026-11-01T14:06:22.795Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:06:23.746Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261101-25e4d6cd
2026-11-01T14:06:29.309Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-829db41bc562 (confirmed by webhook)
2026-11-01T14:06:30.074Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:06:30.922Z  ITEM_FULFILLED      Picked and packed 1 x Slim Wireless Mouse (line L1)
2026-11-01T14:06:30.967Z  COMPLETED           Order fulfilled - payment PAY-829db41bc562 captured
```

## g) poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING - PASS

orderId: `ORD-20261101-bc5067b2`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order-saga-orders-dlq count 46 -> 47: no new message within 5 min
- PASS: this order's message found in the DLQ (swept 31 of 47 messages, none deleted)
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 PENDING -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261101-bc5067b2: none (payment never requested) (expected None)

statusHistory:
```
2026-11-01T13:58:08.050Z  PENDING             Order received via API
2026-11-01T13:58:08.596Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-11-01T13:59:08.588Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-11-01T14:00:08.594Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261101-a336833a`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a336833a`

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
- PASS: I4 intent PI-ORD-20261101-a336833a: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T14:06:48.282Z  PENDING             Order received via API
2026-11-01T14:06:48.850Z  PROCESSING          Saga workflow started
2026-11-01T14:06:48.996Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:06:49.147Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261101-a336833a
2026-11-01T14:06:51.297Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-11-01T14:06:52.989Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T14:06:53.122Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261101-6f764818`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6f764818`

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
- PASS: I4 intent PI-ORD-20261101-6f764818: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:06:56.755Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-11-01T14:06:56.887Z  PROCESSING          Saga workflow started
2026-11-01T14:06:57.635Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:06:57.793Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261101-6f764818
2026-11-01T14:06:59.919Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-65de4b68f931 (confirmed by webhook)
2026-11-01T14:07:00.026Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:07:00.756Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-01T14:07:00.797Z  COMPLETED           Order fulfilled - payment PAY-65de4b68f931 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261101-6f764818`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6f764818`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-11-01T14:06:56.755Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-11-01T14:06:56.887Z  PROCESSING          Saga workflow started
2026-11-01T14:06:57.635Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:06:57.793Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261101-6f764818
2026-11-01T14:06:59.919Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-65de4b68f931 (confirmed by webhook)
2026-11-01T14:07:00.026Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:07:00.756Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-01T14:07:00.797Z  COMPLETED           Order fulfilled - payment PAY-65de4b68f931 captured
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

orderId: `ORD-20261101-a0b6d669`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a0b6d669`

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
2026-11-01T14:11:24.597Z  PENDING             Order received via API
2026-11-01T14:11:24.920Z  PROCESSING          Saga workflow started
2026-11-01T14:11:25.213Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:11:25.473Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261101-a0b6d669
2026-11-01T14:11:30.102Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-293ea845bda4 (confirmed by webhook)
2026-11-01T14:11:31.095Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:11:31.446Z  ITEM_FULFILLED      Picked and packed 1 x Felt and Leather Desk Mat (line L1)
2026-11-01T14:11:31.496Z  COMPLETED           Order fulfilled - payment PAY-293ea845bda4 captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261101-d45a4aec`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-d45a4aec`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261101-e0bfa025, B ORD-20261101-d45a4aec
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261101-e0bfa025 COMPLETED
- PASS: ORD-20261101-d45a4aec COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-d45a4aec: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:11:38.576Z  PENDING             Order received via API
2026-11-01T14:11:38.807Z  PROCESSING          Saga workflow started
2026-11-01T14:11:39.037Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:11:39.173Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261101-d45a4aec
2026-11-01T14:11:42.330Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-457b8fc7a492 (confirmed by webhook)
2026-11-01T14:11:42.433Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:11:42.528Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-01T14:11:42.561Z  COMPLETED           Order fulfilled - payment PAY-457b8fc7a492 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261101-e2ec613a)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261101-4ac85e5c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-4ac85e5c`

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
- PASS: I4 intent PI-ORD-20261101-4ac85e5c: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-11-01T13:58:08.290Z  PENDING             Order received via API
2026-11-01T13:58:08.634Z  PROCESSING          Saga workflow started
2026-11-01T13:58:08.775Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T13:58:08.898Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261101-4ac85e5c
2026-11-01T14:00:09.251Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T14:00:09.346Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261101-8ed01d0a`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-8ed01d0a`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261101-8ed01d0a REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹18999 <= charged ₹18999
- PASS: I4 intent PI-ORD-20261101-8ed01d0a: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-01T13:58:08.550Z  PENDING             Order received via API
2026-11-01T13:58:09.093Z  PROCESSING          Saga workflow started
2026-11-01T13:58:09.197Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T13:58:09.316Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261101-8ed01d0a
2026-11-01T14:00:09.542Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T14:00:09.636Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-11-01T14:00:40.369Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-5e7d4a43ec83, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261101-0ddca27c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-0ddca27c`

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
- PASS: I4 intent PI-ORD-20261101-0ddca27c: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:11:46.076Z  PENDING             Order received via API
2026-11-01T14:11:46.631Z  PROCESSING          Saga workflow started
2026-11-01T14:11:46.715Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:11:46.847Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261101-0ddca27c
2026-11-01T14:11:51.979Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-7cc682ba85f0 (confirmed by webhook)
2026-11-01T14:11:52.091Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:11:52.194Z  ITEM_FULFILLED      Picked and packed 1 x Ergonomic Wireless Mouse (line L1)
2026-11-01T14:11:52.230Z  COMPLETED           Order fulfilled - payment PAY-7cc682ba85f0 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261101-96eeaa8b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-96eeaa8b`

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
- PASS: I4 intent PI-ORD-20261101-96eeaa8b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:12:04.094Z  PENDING             Order received via API
2026-11-01T14:12:04.231Z  PROCESSING          Saga workflow started
2026-11-01T14:12:04.403Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:12:04.521Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261101-96eeaa8b
2026-11-01T14:12:09.681Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-ec5586918afd (confirmed by webhook)
2026-11-01T14:12:09.797Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:12:09.906Z  ITEM_FULFILLED      Picked and packed 1 x True Wireless Earbuds (line L1)
2026-11-01T14:12:09.939Z  COMPLETED           Order fulfilled - payment PAY-ec5586918afd captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 598 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (10, 0, 0) -> (8, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261101-9ba62edf54 exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (9, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261101-822c8d1658 -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (10, 0, 0) (expected (10, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-11-01T14:12:28.051Z  HOLD                HOLD-20261101-822c8d1658 and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261101-b3141acf92 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 33.8 s after expiresAt 2026-11-01T13:58:40.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved, sold, writtenOff) (90, 0, 0, 10, 0) -> (89, 0, 0, 11, 0): the 3 held units went back (held 0, pool 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-11-01T13:58:10.976Z  ACTIVE              HOLD-20261101-b3141acf92: 3 x DESK-MAT held for 30 s
2026-11-01T13:58:40.000Z  expiresAt           the schedule's at() time
2026-11-01T13:59:13.848Z  EXPIRED             by the schedule, 33.8 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261101-4f5896b325 (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261101-6904a2e7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-6904a2e7`

Checks:
- PASS: POST /holds -> 201 HOLD-20261101-3590365f83
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261101-3590365f83'
- PASS: hold CONSUMED by ORD-20261101-6904a2e7 (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (78, 0, 0) -> (77, 0, 0) (stock -1 once, at hold time; held -> reserved -> sold)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-6904a2e7: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:12:32.359Z  PENDING             Order received via API
2026-11-01T14:12:32.833Z  PROCESSING          Saga workflow started
2026-11-01T14:12:32.943Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261101-3590365f83
2026-11-01T14:12:33.195Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261101-6904a2e7
2026-11-01T14:12:35.329Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-ec7b58785bdd (confirmed by webhook)
2026-11-01T14:12:35.440Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:12:35.546Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-01T14:12:35.579Z  COMPLETED           Order fulfilled - payment PAY-ec7b58785bdd captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261101-24273afa`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-24273afa`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261101-497d29640f
- PASS: hold HOLD-20261101-497d29640f EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261101-497d29640f had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (10, 0, 0) -> (9, 0, 0) (a normal fresh reservation, then sold)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499, credits []
- PASS: I6 COMPLETED -> net ₹5499 = fulfilled lines ₹5499
- PASS: I7 refunds ₹0 <= charged ₹5499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-24273afa: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:15:25.175Z  PENDING             Order received via API
2026-11-01T14:15:25.779Z  PROCESSING          Saga workflow started
2026-11-01T14:15:26.071Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261101-497d29640f had ended, so reserved afresh)
2026-11-01T14:15:26.318Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261101-24273afa
2026-11-01T14:15:31.664Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-7911bf410550 (confirmed by webhook)
2026-11-01T14:15:31.841Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:15:32.068Z  ITEM_FULFILLED      Picked and packed 1 x Compact 65% Mechanical Keyboard (line L1)
2026-11-01T14:15:32.098Z  COMPLETED           Order fulfilled - payment PAY-7911bf410550 captured
```

## za) 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off - PASS

orderId: `ORD-20261101-e322a216`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-e322a216`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: line states ['FULFILLED', 'WRITTEN_OFF', 'FULFILLED']
- PASS: L2 refundedAmount 6499 = its lineAmount 6499
- PASS: ledger CREDITs [('L2', Decimal('6499'))] (expected exactly one, for L2)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> ITEM_FULFILLED -> LINE_REFUNDED -> ITEM_WRITTEN_OFF -> PARTIALLY_FULFILLED
- PASS: write-off audit record for L2: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
- PASS: L1 WIRELESS-MOUSE (stock, held, reserved, sold, writtenOff) (75, 0, 0, 25, 0) -> (73, 0, 0, 27, 0) (expected (73, 0, 0, 27, 0))
- PASS: L2 ERGO-MOUSE (stock, held, reserved, sold, writtenOff) (87, 0, 0, 6, 7) -> (86, 0, 0, 6, 8) (expected (86, 0, 0, 6, 8))
- PASS: L3 LOWPRO-KEYBOARD (stock, held, reserved, sold, writtenOff) (73, 0, 0, 26, 1) -> (70, 0, 0, 29, 1) (expected (70, 0, 0, 29, 1))
- PASS: execution SUCCEEDED (expected SUCCEEDED at OrderPartiallyFulfilled)
- PASS: the execution ended in OrderPartiallyFulfilled
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹8495, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹8495 = fulfilled lines ₹8495
- PASS: I7 refunds ₹6499 <= charged ₹14994
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261101-e322a216: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:12:38.054Z  PENDING             Order received via API
2026-11-01T14:12:38.564Z  PROCESSING          Saga workflow started
2026-11-01T14:12:38.672Z  RESERVED            Reserved stock for 3 product(s)
2026-11-01T14:12:38.815Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹14,994 · intent PI-ORD-20261101-e322a216
2026-11-01T14:12:41.975Z  PAYMENT_CAPTURED    ₹14,994 captured by DemoPay · PAY-79e998a7c65f (confirmed by webhook)
2026-11-01T14:12:42.089Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:12:42.180Z  ITEM_FULFILLED      Picked and packed 2 x Slim Wireless Mouse (line L1)
2026-11-01T14:12:42.207Z  ITEM_FULFILLED      Picked and packed 3 x Low-Profile Wireless Keyboard (line L3)
2026-11-01T14:12:43.122Z  LINE_REFUNDED       ₹6,499 refunded to DemoPay for 1 x Ergonomic Wireless Mouse (line L2)
2026-11-01T14:12:43.781Z  ITEM_WRITTEN_OFF    1 x Ergonomic Wireless Mouse (line L2) written off: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
2026-11-01T14:12:43.834Z  PARTIALLY_FULFILLED 2 of 3 items delivered - INR 6499.00 refunded for the unavailable items
```

## zb) every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 - PASS

orderId: `ORD-20261101-31cacfc3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-31cacfc3`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off'
- PASS: every line WRITTEN_OFF
- PASS: write-off audit records for L1 and L2
- PASS: L1 USBC-HUB (stock, held, reserved, sold, writtenOff) (94, 0, 0, 1, 5) -> (93, 0, 0, 1, 6) (expected (93, 0, 0, 1, 6))
- PASS: L2 WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (81, 0, 0, 9, 10) -> (79, 0, 0, 9, 12) (expected (79, 0, 0, 9, 12))
- PASS: RefundAllLines ran; ReleaseInventory did not (damaged units are written off, not released)
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 2 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 2 CREDIT, net ₹0, credits ['L1', 'L2']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹11997 <= charged ₹11997
- PASS: I9 one winner: cancel requested False, FULFILLING True, status FAILED
- PASS: I4 intent PI-ORD-20261101-31cacfc3: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-01T14:12:46.114Z  PENDING             Order received via API
2026-11-01T14:12:46.587Z  PROCESSING          Saga workflow started
2026-11-01T14:12:46.694Z  RESERVED            Reserved stock for 2 product(s)
2026-11-01T14:12:46.850Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹11,997 · intent PI-ORD-20261101-31cacfc3
2026-11-01T14:12:51.978Z  PAYMENT_CAPTURED    ₹11,997 captured by DemoPay · PAY-4d0395f9268d (confirmed by webhook)
2026-11-01T14:12:52.075Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:12:52.425Z  LINE_REFUNDED       ₹1,999 refunded to DemoPay for 1 x USB-C Hub, 6-in-1 (line L1)
2026-11-01T14:12:52.502Z  LINE_REFUNDED       ₹9,998 refunded to DemoPay for 2 x True Wireless Earbuds (line L2)
2026-11-01T14:12:52.597Z  ITEM_WRITTEN_OFF    1 x USB-C Hub, 6-in-1 (line L1) written off: USB-C Hub, 6-in-1 (line L1) was found damaged in the warehouse (simulated)
2026-11-01T14:12:52.614Z  ITEM_WRITTEN_OFF    2 x True Wireless Earbuds (line L2) written off: True Wireless Earbuds (line L2) was found damaged in the warehouse (simulated)
2026-11-01T14:12:52.719Z  FAILED              AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off
```

## zc) order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds - PASS

orderId: `ORD-20261101-eed0f42b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-eed0f42b`

Checks:
- PASS: POST /holds -> 201 HOLD-20261101-889c7241ff
- PASS: POST /orders with holdId -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: RESERVED detail: 'Reserved stock for 2 product(s) from checkout hold HOLD-20261101-889c7241ff'
- PASS: hold CONSUMED by ORD-20261101-eed0f42b
- PASS: L1 LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (77, 0, 0, 23, 0) -> (76, 0, 0, 24, 0) (expected (76, 0, 0, 24, 0))
- PASS: L2 ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (85, 0, 0, 7, 8) -> (83, 0, 0, 7, 10) (expected (83, 0, 0, 7, 10))
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹1799, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹53980 <= charged ₹55779
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261101-eed0f42b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:15:34.969Z  PENDING             Order received via API
2026-11-01T14:15:35.215Z  PROCESSING          Saga workflow started
2026-11-01T14:15:35.327Z  RESERVED            Reserved stock for 2 product(s) from checkout hold HOLD-20261101-889c7241ff
2026-11-01T14:15:35.545Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹55,779 · intent PI-ORD-20261101-eed0f42b
2026-11-01T14:15:39.680Z  PAYMENT_CAPTURED    ₹55,779 captured by DemoPay · PAY-1ffbb5e90868 (confirmed by webhook)
2026-11-01T14:15:39.772Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:15:39.957Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-11-01T14:15:40.203Z  LINE_REFUNDED       ₹53,980 refunded to DemoPay for 2 x Noise-Cancelling Wireless Headphones (line L2)
2026-11-01T14:15:40.370Z  ITEM_WRITTEN_OFF    2 x Noise-Cancelling Wireless Headphones (line L2) written off: Noise-Cancelling Wireless Headphones (line L2) was found damaged in the warehouse (simulated)
2026-11-01T14:15:40.420Z  PARTIALLY_FULFILLED 1 of 2 items delivered - INR 53980.00 refunded for the unavailable items
```

## zd) cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent - PASS

orderId: `ORD-20261101-bc641919`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-bc641919`

Checks:
- PASS: POST /orders -> 202
- PASS: waiting for DemoPay: PAYMENT_PENDING, canCancel True
- PASS: user B cancels A's order -> 404 (expected 404, exactly like a missing order)
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261101-bc641919', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-11-01T14:12:57.413Z'}
- PASS: repeated cancel -> 202, same request 2026-11-01T14:12:57.413Z
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (85, 0, 0, 7, 8) -> (85, 0, 0, 7, 8) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: CANCELLED detail 'Cancelled by the customer - nothing was charged'
- PASS: DemoPay CHARGE record VOIDED (expected VOIDED: never charged)
- PASS: cancel after the end -> 200 {'orderId': 'ORD-20261101-bc641919', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-11-01T14:12:57.413Z', 'refundedAmount': 0}
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-bc641919: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T14:12:55.674Z  PENDING             Order received via API
2026-11-01T14:12:55.837Z  PROCESSING          Saga workflow started
2026-11-01T14:12:55.947Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:12:56.083Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261101-bc641919
2026-11-01T14:12:57.413Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-01T14:12:58.329Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T14:12:58.370Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## ze) cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back - PASS

orderId: `ORD-20261101-5dbbb707`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-5dbbb707`

Checks:
- PASS: POST /orders -> 202
- PASS: paid, warehouse waiting: PAYMENT_CAPTURED, canCancel True
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261101-5dbbb707', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-11-01T14:13:32.410Z'}
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> CANCEL_REQUESTED -> PAYMENT_REFUNDED -> INVENTORY_RELEASED -> CANCELLED
- PASS: 4K-MONITOR (stock, held, reserved, sold, writtenOff) (93, 0, 0, 7, 0) -> (93, 0, 0, 7, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: refundedAmount 24999 (expected the total 24999)
- PASS: CANCELLED detail 'Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet'
- PASS: wallet CREDIT notes ['Refund for ORD-20261101-5dbbb707 (order cancelled)']
- PASS: cancel twice -> 200 {'orderId': 'ORD-20261101-5dbbb707', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-11-01T14:13:32.410Z', 'refundedAmount': 24999} (same answer, no second refund)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹24999 <= charged ₹24999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-5dbbb707: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-11-01T14:13:26.172Z  PENDING             Order received via API
2026-11-01T14:13:26.616Z  PROCESSING          Saga workflow started
2026-11-01T14:13:26.783Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:13:26.915Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261101-5dbbb707
2026-11-01T14:13:32.069Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-1677f951b6bb (confirmed by webhook)
2026-11-01T14:13:32.410Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-01T14:13:42.467Z  PAYMENT_REFUNDED    ₹24,999 refunded to DemoPay (order cancelled)
2026-11-01T14:13:42.568Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T14:13:42.605Z  CANCELLED           Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet
```

## zf) cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry - PASS

orderId: `ORD-20261101-cadd1b31`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-cadd1b31`

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
- PASS: I4 intent PI-ORD-20261101-cadd1b31: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-11-01T14:13:44.392Z  PENDING             Order received via API
2026-11-01T14:13:44.700Z  PROCESSING          Saga workflow started
2026-11-01T14:13:44.804Z  RESERVED            Reserved stock for 1 product(s)
2026-11-01T14:13:44.936Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261101-cadd1b31
2026-11-01T14:13:47.067Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-16e9f51d6313 (confirmed by webhook)
2026-11-01T14:13:57.196Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-11-01T14:13:57.994Z  CANCEL_REJECTED     Cancel request rejected: the order was already FULFILLING
2026-11-01T14:14:07.310Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-11-01T14:14:07.363Z  COMPLETED           Order fulfilled - payment PAY-16e9f51d6313 captured
```

## zg) cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged - PASS

orderId: `ORD-20261101-a79002e1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-a79002e1`

Checks:
- PASS: cancel -> 409 {'error': 'TOO_LATE_TO_CANCEL', 'status': 'COMPLETED'}
- PASS: status COMPLETED, canCancel False
- PASS: history only gained ['CANCEL_REJECTED'] (a CANCEL_REJECTED entry at most)

## zh) cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once - PASS

orderId: `ORD-20261101-0ea95f50`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-0ea95f50`

Checks:
- PASS: POST /holds -> 201 HOLD-20261101-e1531b0071
- PASS: POST /orders with holdId -> 202
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261101-e1531b0071'
- PASS: cancel -> 202
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (76, 0, 0, 24, 0) -> (76, 0, 0, 24, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: hold CONSUMED by ORD-20261101-0ea95f50 (expected CONSUMED by this order: never released a 2nd time)
- PASS: no current hold, no expiry schedule left
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-0ea95f50: FAILED (expected FAILED)

statusHistory:
```
2026-11-01T14:15:42.368Z  PENDING             Order received via API
2026-11-01T14:15:42.484Z  PROCESSING          Saga workflow started
2026-11-01T14:15:42.590Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261101-e1531b0071
2026-11-01T14:15:42.838Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261101-0ea95f50
2026-11-01T14:15:43.451Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-11-01T14:15:43.852Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-11-01T14:15:43.894Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## zi) RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) - PASS

orderId: `ORD-20261101-cec48d3b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261101-cec48d3b`

Checks:
- PASS: POST /orders x20 -> [202]
- PASS: ORD-20261101-cec48d3b CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-cec48d3b: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-08bfb9ec CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-08bfb9ec: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-b0d3b159 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-b0d3b159: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-926249af CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-926249af: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-5cf0b1d8 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-5cf0b1d8: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-00b73a24 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-00b73a24: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-4e5def56 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-4e5def56: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-69120f5b CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-69120f5b: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-d16aaf37 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-d16aaf37: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-4b99a39d CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-4b99a39d: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-0c4e5982 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-0c4e5982: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-1721d5ea CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-1721d5ea: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-327967fd CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-327967fd: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-9e94ab8c CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-9e94ab8c: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-df55e9e9 COMPLETED: cancel answered 409 (expected 409)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261101-df55e9e9: SUCCEEDED (expected SUCCEEDED)
- PASS: ORD-20261101-5625fc68 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-5625fc68: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-779fc4f1 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-779fc4f1: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-8042bb26 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-8042bb26: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-5e8ff7e3 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-5e8ff7e3: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261101-8b726d4e CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261101-8b726d4e: REFUNDED (expected FAILED or REFUNDED)
- PASS: WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (79, 0, 0, 9, 12) -> (78, 0, 0, 10, 12) (expected (78, 0, 0, 10, 12): only the 1 COMPLETED orders sold a unit)
