# End-to-end tests: every saga path, with DemoPay money and stock invariants (I1-I9)

Run: 2026-10-30 15:10:25 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 403s

**Result: 35/35 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I9) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261030-8e348721` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-8e348721) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261030-7a573102` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-7a573102) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261030-d0c4a966` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d0c4a966) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261030-52c1e380` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-52c1e380) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261030-5cc989cc` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5cc989cc) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261030-d206c163` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d206c163) |
| g | poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING | PASS | `ORD-20261030-974fb245` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261030-ac8c1769` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-ac8c1769) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261030-739f5f8d` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-739f5f8d) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261030-739f5f8d` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-739f5f8d) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261030-0e57e00e` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-0e57e00e) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261030-98d259b2` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-98d259b2) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261030-a3609c77` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-a3609c77) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261030-5176f0b8` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5176f0b8) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261030-339f10ce` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-339f10ce) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261030-4f50f0eb` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-4f50f0eb) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261030-9c89575f` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-9c89575f) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261030-1cd7c996` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1cd7c996) |
| za | 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off | PASS | `ORD-20261030-bbcf1a60` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹8495 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-bbcf1a60) |
| zb | every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 | PASS | `ORD-20261030-18a1f65b` | REFUNDED · ledger 1 DEBIT / 2 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-18a1f65b) |
| zc | order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds | PASS | `ORD-20261030-c779a9f3` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c779a9f3) |
| zd | cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent | PASS | `ORD-20261030-fba22f75` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-fba22f75) |
| ze | cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back | PASS | `ORD-20261030-31fe2d9a` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-31fe2d9a) |
| zf | cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry | PASS | `ORD-20261030-1b24ad87` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1b24ad87) |
| zg | cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged | PASS | `ORD-20261030-8e348721` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-8e348721) |
| zh | cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once | PASS | `ORD-20261030-6e917a60` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6e917a60) |
| zi | RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) | PASS | `ORD-20261030-3f608b8c` | 4 x cancel won, late charge refunded by the webhook; 15 x cancel won, nothing charged; 1 x payment won, cancel refused (409) | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-3f608b8c) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261030-8e348721`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-8e348721`

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
- PASS: I4 intent PI-ORD-20261030-8e348721: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:03:53.616Z  PENDING             Order received via API
2026-10-30T15:03:54.020Z  PROCESSING          Saga workflow started
2026-10-30T15:03:54.184Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:03:54.341Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261030-8e348721
2026-10-30T15:04:00.090Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-913d27e175b5 (confirmed by webhook)
2026-10-30T15:04:00.884Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:04:02.074Z  ITEM_FULFILLED      Picked and packed 1 x Mechanical Keyboard, 60% Layout (line L1)
2026-10-30T15:04:02.132Z  COMPLETED           Order fulfilled - payment PAY-913d27e175b5 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261030-7a573102`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-7a573102`

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
- PASS: I4 intent PI-ORD-20261030-7a573102: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T15:04:05.579Z  PENDING             Order received via API
2026-10-30T15:04:06.138Z  PROCESSING          Saga workflow started
2026-10-30T15:04:06.276Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:04:06.422Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261030-7a573102
2026-10-30T15:04:08.529Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-10-30T15:04:10.406Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:04:10.555Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261030-d0c4a966`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d0c4a966`

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
- PASS: I4 intent PI-ORD-20261030-d0c4a966: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:04:13.717Z  PENDING             Order received via API
2026-10-30T15:04:14.152Z  PROCESSING          Saga workflow started
2026-10-30T15:04:14.271Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:04:14.399Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-10-30T15:04:16.576Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-10-30T15:04:20.735Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261030-d0c4a966
2026-10-30T15:04:22.887Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-de55f17f53fa (confirmed by webhook)
2026-10-30T15:04:22.995Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:04:23.128Z  ITEM_FULFILLED      Picked and packed 1 x Noise-Cancelling Wireless Headphones (line L1)
2026-10-30T15:04:23.168Z  COMPLETED           Order fulfilled - payment PAY-de55f17f53fa captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261030-52c1e380`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-52c1e380`

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
- PASS: I4 intent PI-ORD-20261030-52c1e380: none (payment never requested) (expected None)

statusHistory:
```
2026-10-30T15:04:25.922Z  PENDING             Order received via API
2026-10-30T15:04:26.166Z  PROCESSING          Saga workflow started
2026-10-30T15:04:26.316Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-30T15:04:26.434Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261030-5cc989cc`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5cc989cc`

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
- PASS: I4 intent PI-ORD-20261030-5cc989cc: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:04:30.196Z  PENDING             Order received via API
2026-10-30T15:04:30.672Z  PROCESSING          Saga workflow started
2026-10-30T15:04:30.791Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:04:30.919Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261030-5cc989cc
2026-10-30T15:04:38.061Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-84eb13ed04b0 (confirmed by webhook)
2026-10-30T15:04:38.281Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:04:39.014Z  ITEM_FULFILLED      Picked and packed 1 x 27-inch 4K UHD IPS Monitor (line L1)
2026-10-30T15:04:39.059Z  COMPLETED           Order fulfilled - payment PAY-84eb13ed04b0 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261030-d206c163`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d206c163`

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
- PASS: I4 intent PI-ORD-20261030-d206c163: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:04:51.435Z  PENDING             Order received via API
2026-10-30T15:04:51.582Z  PROCESSING          Saga workflow started
2026-10-30T15:04:51.737Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:04:51.855Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261030-d206c163
2026-10-30T15:04:57.005Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-cc62e12b5088 (confirmed by webhook)
2026-10-30T15:04:57.740Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:04:57.946Z  ITEM_FULFILLED      Picked and packed 1 x Slim Wireless Mouse (line L1)
2026-10-30T15:04:57.999Z  COMPLETED           Order fulfilled - payment PAY-cc62e12b5088 captured
```

## g) poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING - PASS

orderId: `ORD-20261030-974fb245`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order-saga-orders-dlq count 33 -> 34: no new message within 5 min
- PASS: this order's message found in the DLQ (swept 34 of 34 messages, none deleted)
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 PENDING -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261030-974fb245: none (payment never requested) (expected None)

statusHistory:
```
2026-10-30T15:03:48.357Z  PENDING             Order received via API
2026-10-30T15:03:49.184Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-30T15:04:48.557Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-30T15:05:48.560Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261030-ac8c1769`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-ac8c1769`

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
- PASS: I4 intent PI-ORD-20261030-ac8c1769: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T15:05:17.994Z  PENDING             Order received via API
2026-10-30T15:05:18.469Z  PROCESSING          Saga workflow started
2026-10-30T15:05:18.581Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:05:18.715Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261030-ac8c1769
2026-10-30T15:05:20.851Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-30T15:05:21.087Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:05:21.204Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261030-739f5f8d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-739f5f8d`

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
- PASS: I4 intent PI-ORD-20261030-739f5f8d: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:05:23.737Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-30T15:05:23.956Z  PROCESSING          Saga workflow started
2026-10-30T15:05:24.058Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:05:24.194Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-739f5f8d
2026-10-30T15:05:26.329Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-c5162324fb6c (confirmed by webhook)
2026-10-30T15:05:26.456Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:05:26.561Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-30T15:05:26.595Z  COMPLETED           Order fulfilled - payment PAY-c5162324fb6c captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261030-739f5f8d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-739f5f8d`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-30T15:05:23.737Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-30T15:05:23.956Z  PROCESSING          Saga workflow started
2026-10-30T15:05:24.058Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:05:24.194Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-739f5f8d
2026-10-30T15:05:26.329Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-c5162324fb6c (confirmed by webhook)
2026-10-30T15:05:26.456Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:05:26.561Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-30T15:05:26.595Z  COMPLETED           Order fulfilled - payment PAY-c5162324fb6c captured
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

orderId: `ORD-20261030-0e57e00e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-0e57e00e`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (41 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-30T15:05:42.234Z  PENDING             Order received via API
2026-10-30T15:05:42.731Z  PROCESSING          Saga workflow started
2026-10-30T15:05:42.838Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:05:42.958Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261030-0e57e00e
2026-10-30T15:05:47.111Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-cb2fc6224a85 (confirmed by webhook)
2026-10-30T15:05:47.215Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:05:47.306Z  ITEM_FULFILLED      Picked and packed 1 x Felt and Leather Desk Mat (line L1)
2026-10-30T15:05:47.356Z  COMPLETED           Order fulfilled - payment PAY-cb2fc6224a85 captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261030-98d259b2`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-98d259b2`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261030-b8b34698, B ORD-20261030-98d259b2
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261030-b8b34698 COMPLETED
- PASS: ORD-20261030-98d259b2 COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261030-98d259b2: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:05:53.853Z  PENDING             Order received via API
2026-10-30T15:05:54.002Z  PROCESSING          Saga workflow started
2026-10-30T15:05:54.135Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:05:54.274Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-98d259b2
2026-10-30T15:05:58.425Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-c322ec4ea8c6 (confirmed by webhook)
2026-10-30T15:05:58.587Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:05:58.676Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-30T15:05:58.711Z  COMPLETED           Order fulfilled - payment PAY-c322ec4ea8c6 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261030-e2e4bcf8)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261030-a3609c77`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-a3609c77`

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
- PASS: I4 intent PI-ORD-20261030-a3609c77: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-10-30T15:03:48.716Z  PENDING             Order received via API
2026-10-30T15:03:49.743Z  PROCESSING          Saga workflow started
2026-10-30T15:03:50.779Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:03:51.656Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261030-a3609c77
2026-10-30T15:05:51.129Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:05:51.237Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261030-5176f0b8`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5176f0b8`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261030-5176f0b8 REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹18999 <= charged ₹18999
- PASS: I4 intent PI-ORD-20261030-5176f0b8: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-30T15:03:49.003Z  PENDING             Order received via API
2026-10-30T15:03:49.297Z  PROCESSING          Saga workflow started
2026-10-30T15:03:50.236Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:03:51.190Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261030-5176f0b8
2026-10-30T15:05:50.588Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:05:50.698Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-10-30T15:06:22.234Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-6705d9c1171e, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261030-339f10ce`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-339f10ce`

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
- PASS: I4 intent PI-ORD-20261030-339f10ce: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:06:01.713Z  PENDING             Order received via API
2026-10-30T15:06:02.288Z  PROCESSING          Saga workflow started
2026-10-30T15:06:02.389Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:06:02.534Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261030-339f10ce
2026-10-30T15:06:06.667Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-00674204f9cd (confirmed by webhook)
2026-10-30T15:06:06.757Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:06:06.835Z  ITEM_FULFILLED      Picked and packed 1 x Ergonomic Wireless Mouse (line L1)
2026-10-30T15:06:06.866Z  COMPLETED           Order fulfilled - payment PAY-00674204f9cd captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261030-4f50f0eb`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-4f50f0eb`

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
- PASS: I4 intent PI-ORD-20261030-4f50f0eb: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:06:11.513Z  PENDING             Order received via API
2026-10-30T15:06:11.811Z  PROCESSING          Saga workflow started
2026-10-30T15:06:11.912Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:06:12.020Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261030-4f50f0eb
2026-10-30T15:06:14.181Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-7e8461039907 (confirmed by webhook)
2026-10-30T15:06:14.292Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:06:14.397Z  ITEM_FULFILLED      Picked and packed 1 x True Wireless Earbuds (line L1)
2026-10-30T15:06:14.434Z  COMPLETED           Order fulfilled - payment PAY-7e8461039907 captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 599 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) -> (12, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261030-fe0e01da8d exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (13, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261030-1879a3e9f4 -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (14, 0, 0) (expected (14, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-10-30T15:06:32.573Z  HOLD                HOLD-20261030-1879a3e9f4 and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261030-1e13b4ba29 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 44.1 s after expiresAt 2026-10-30T15:04:22.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved, sold, writtenOff) (100, 0, 0, 0, 0) -> (99, 0, 0, 1, 0): the 3 held units went back (held 0, pool 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-10-30T15:03:52.620Z  ACTIVE              HOLD-20261030-1e13b4ba29: 3 x DESK-MAT held for 30 s
2026-10-30T15:04:22.000Z  expiresAt           the schedule's at() time
2026-10-30T15:05:06.139Z  EXPIRED             by the schedule, 44.1 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261030-493608d533 (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261030-9c89575f`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-9c89575f`

Checks:
- PASS: POST /holds -> 201 HOLD-20261030-74c3400aaf
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261030-74c3400aaf'
- PASS: hold CONSUMED by ORD-20261030-9c89575f (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (98, 0, 0) -> (97, 0, 0) (stock -1 once, at hold time; held -> reserved -> sold)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261030-9c89575f: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:06:38.233Z  PENDING             Order received via API
2026-10-30T15:06:38.564Z  PROCESSING          Saga workflow started
2026-10-30T15:06:38.715Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261030-74c3400aaf
2026-10-30T15:06:38.936Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-9c89575f
2026-10-30T15:06:41.091Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-ae8d3caec39d (confirmed by webhook)
2026-10-30T15:06:41.196Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:06:41.303Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-30T15:06:41.337Z  COMPLETED           Order fulfilled - payment PAY-ae8d3caec39d captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261030-1cd7c996`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1cd7c996`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261030-7495ad8da5
- PASS: hold HOLD-20261030-7495ad8da5 EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261030-7495ad8da5 had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (14, 0, 0) -> (13, 0, 0) (a normal fresh reservation, then sold)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499, credits []
- PASS: I6 COMPLETED -> net ₹5499 = fulfilled lines ₹5499
- PASS: I7 refunds ₹0 <= charged ₹5499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261030-1cd7c996: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:09:34.429Z  PENDING             Order received via API
2026-10-30T15:09:35.022Z  PROCESSING          Saga workflow started
2026-10-30T15:09:35.393Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261030-7495ad8da5 had ended, so reserved afresh)
2026-10-30T15:09:35.630Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261030-1cd7c996
2026-10-30T15:09:41.177Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-b68e63fd7862 (confirmed by webhook)
2026-10-30T15:09:41.621Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:09:41.770Z  ITEM_FULFILLED      Picked and packed 1 x Compact 65% Mechanical Keyboard (line L1)
2026-10-30T15:09:41.805Z  COMPLETED           Order fulfilled - payment PAY-b68e63fd7862 captured
```

## za) 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off - PASS

orderId: `ORD-20261030-bbcf1a60`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-bbcf1a60`

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
- PASS: I4 intent PI-ORD-20261030-bbcf1a60: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:06:44.673Z  PENDING             Order received via API
2026-10-30T15:06:45.039Z  PROCESSING          Saga workflow started
2026-10-30T15:06:45.120Z  RESERVED            Reserved stock for 3 product(s)
2026-10-30T15:06:45.254Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹14,994 · intent PI-ORD-20261030-bbcf1a60
2026-10-30T15:06:49.387Z  PAYMENT_CAPTURED    ₹14,994 captured by DemoPay · PAY-7d7b0c542212 (confirmed by webhook)
2026-10-30T15:06:49.505Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:06:49.585Z  ITEM_FULFILLED      Picked and packed 2 x Slim Wireless Mouse (line L1)
2026-10-30T15:06:49.660Z  ITEM_FULFILLED      Picked and packed 3 x Low-Profile Wireless Keyboard (line L3)
2026-10-30T15:06:49.852Z  LINE_REFUNDED       ₹6,499 refunded to DemoPay for 1 x Ergonomic Wireless Mouse (line L2)
2026-10-30T15:06:50.599Z  ITEM_WRITTEN_OFF    1 x Ergonomic Wireless Mouse (line L2) written off: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
2026-10-30T15:06:50.652Z  PARTIALLY_FULFILLED 2 of 3 items delivered - INR 6499.00 refunded for the unavailable items
```

## zb) every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 - PASS

orderId: `ORD-20261030-18a1f65b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-18a1f65b`

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
- PASS: I4 intent PI-ORD-20261030-18a1f65b: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-30T15:06:53.772Z  PENDING             Order received via API
2026-10-30T15:06:54.044Z  PROCESSING          Saga workflow started
2026-10-30T15:06:54.175Z  RESERVED            Reserved stock for 2 product(s)
2026-10-30T15:06:54.313Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹11,997 · intent PI-ORD-20261030-18a1f65b
2026-10-30T15:06:57.445Z  PAYMENT_CAPTURED    ₹11,997 captured by DemoPay · PAY-a99bc825ddf9 (confirmed by webhook)
2026-10-30T15:06:57.591Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:06:57.972Z  LINE_REFUNDED       ₹1,999 refunded to DemoPay for 1 x USB-C Hub, 6-in-1 (line L1)
2026-10-30T15:06:58.069Z  LINE_REFUNDED       ₹9,998 refunded to DemoPay for 2 x True Wireless Earbuds (line L2)
2026-10-30T15:06:58.165Z  ITEM_WRITTEN_OFF    1 x USB-C Hub, 6-in-1 (line L1) written off: USB-C Hub, 6-in-1 (line L1) was found damaged in the warehouse (simulated)
2026-10-30T15:06:58.186Z  ITEM_WRITTEN_OFF    2 x True Wireless Earbuds (line L2) written off: True Wireless Earbuds (line L2) was found damaged in the warehouse (simulated)
2026-10-30T15:06:58.258Z  FAILED              AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off
```

## zc) order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds - PASS

orderId: `ORD-20261030-c779a9f3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c779a9f3`

Checks:
- PASS: POST /holds -> 201 HOLD-20261030-df83d4f921
- PASS: POST /orders with holdId -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: RESERVED detail: 'Reserved stock for 2 product(s) from checkout hold HOLD-20261030-df83d4f921'
- PASS: hold CONSUMED by ORD-20261030-c779a9f3
- PASS: L1 LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (97, 0, 0, 3, 0) -> (96, 0, 0, 4, 0) (expected (96, 0, 0, 4, 0))
- PASS: L2 ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 1, 2) (expected (97, 0, 0, 1, 2))
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹1799, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹53980 <= charged ₹55779
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261030-c779a9f3: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:09:44.568Z  PENDING             Order received via API
2026-10-30T15:09:44.669Z  PROCESSING          Saga workflow started
2026-10-30T15:09:44.793Z  RESERVED            Reserved stock for 2 product(s) from checkout hold HOLD-20261030-df83d4f921
2026-10-30T15:09:45.090Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹55,779 · intent PI-ORD-20261030-c779a9f3
2026-10-30T15:09:47.252Z  PAYMENT_CAPTURED    ₹55,779 captured by DemoPay · PAY-9ad9b71f74e8 (confirmed by webhook)
2026-10-30T15:09:47.349Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:09:47.447Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-30T15:09:47.835Z  LINE_REFUNDED       ₹53,980 refunded to DemoPay for 2 x Noise-Cancelling Wireless Headphones (line L2)
2026-10-30T15:09:48.020Z  ITEM_WRITTEN_OFF    2 x Noise-Cancelling Wireless Headphones (line L2) written off: Noise-Cancelling Wireless Headphones (line L2) was found damaged in the warehouse (simulated)
2026-10-30T15:09:48.073Z  PARTIALLY_FULFILLED 1 of 2 items delivered - INR 53980.00 refunded for the unavailable items
```

## zd) cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent - PASS

orderId: `ORD-20261030-fba22f75`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-fba22f75`

Checks:
- PASS: POST /orders -> 202
- PASS: waiting for DemoPay: PAYMENT_PENDING, canCancel True
- PASS: user B cancels A's order -> 404 (expected 404, exactly like a missing order)
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261030-fba22f75', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-10-30T15:07:01.470Z'}
- PASS: repeated cancel -> 202, same request 2026-10-30T15:07:01.470Z
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (99, 0, 0, 1, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: CANCELLED detail 'Cancelled by the customer - nothing was charged'
- PASS: DemoPay CHARGE record VOIDED (expected VOIDED: never charged)
- PASS: cancel after the end -> 200 {'orderId': 'ORD-20261030-fba22f75', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-10-30T15:07:01.470Z', 'refundedAmount': 0}
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-fba22f75: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T15:06:59.172Z  PENDING             Order received via API
2026-10-30T15:06:59.287Z  PROCESSING          Saga workflow started
2026-10-30T15:06:59.403Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:06:59.553Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261030-fba22f75
2026-10-30T15:07:01.470Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-10-30T15:07:01.826Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:07:01.866Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## ze) cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back - PASS

orderId: `ORD-20261030-31fe2d9a`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-31fe2d9a`

Checks:
- PASS: POST /orders -> 202
- PASS: paid, warehouse waiting: PAYMENT_CAPTURED, canCancel True
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261030-31fe2d9a', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-10-30T15:07:36.360Z'}
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> CANCEL_REQUESTED -> PAYMENT_REFUNDED -> INVENTORY_RELEASED -> CANCELLED
- PASS: 4K-MONITOR (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (99, 0, 0, 1, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: refundedAmount 24999 (expected the total 24999)
- PASS: CANCELLED detail 'Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet'
- PASS: wallet CREDIT notes ['Refund for ORD-20261030-31fe2d9a (order cancelled)']
- PASS: cancel twice -> 200 {'orderId': 'ORD-20261030-31fe2d9a', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-10-30T15:07:36.360Z', 'refundedAmount': 24999} (same answer, no second refund)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹24999 <= charged ₹24999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-31fe2d9a: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-30T15:07:29.997Z  PENDING             Order received via API
2026-10-30T15:07:30.426Z  PROCESSING          Saga workflow started
2026-10-30T15:07:30.556Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:07:30.693Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261030-31fe2d9a
2026-10-30T15:07:35.843Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-46ec4ae25339 (confirmed by webhook)
2026-10-30T15:07:36.360Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-10-30T15:07:46.243Z  PAYMENT_REFUNDED    ₹24,999 refunded to DemoPay (order cancelled)
2026-10-30T15:07:46.346Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:07:46.382Z  CANCELLED           Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet
```

## zf) cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry - PASS

orderId: `ORD-20261030-1b24ad87`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1b24ad87`

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
- PASS: I4 intent PI-ORD-20261030-1b24ad87: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T15:07:48.475Z  PENDING             Order received via API
2026-10-30T15:07:48.926Z  PROCESSING          Saga workflow started
2026-10-30T15:07:49.035Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T15:07:49.177Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-1b24ad87
2026-10-30T15:07:53.647Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-94406d00ce27 (confirmed by webhook)
2026-10-30T15:08:03.788Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-30T15:08:04.125Z  CANCEL_REJECTED     Cancel request rejected: the order was already FULFILLING
2026-10-30T15:08:13.973Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-30T15:08:14.021Z  COMPLETED           Order fulfilled - payment PAY-94406d00ce27 captured
```

## zg) cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged - PASS

orderId: `ORD-20261030-8e348721`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-8e348721`

Checks:
- PASS: cancel -> 409 {'error': 'TOO_LATE_TO_CANCEL', 'status': 'COMPLETED'}
- PASS: status COMPLETED, canCancel False
- PASS: history only gained ['CANCEL_REJECTED'] (a CANCEL_REJECTED entry at most)

## zh) cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once - PASS

orderId: `ORD-20261030-6e917a60`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6e917a60`

Checks:
- PASS: POST /holds -> 201 HOLD-20261030-05c5a6bfa0
- PASS: POST /orders with holdId -> 202
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261030-05c5a6bfa0'
- PASS: cancel -> 202
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (96, 0, 0, 4, 0) -> (96, 0, 0, 4, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: hold CONSUMED by ORD-20261030-6e917a60 (expected CONSUMED by this order: never released a 2nd time)
- PASS: no current hold, no expiry schedule left
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-6e917a60: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T15:09:49.909Z  PENDING             Order received via API
2026-10-30T15:09:50.224Z  PROCESSING          Saga workflow started
2026-10-30T15:09:50.393Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261030-05c5a6bfa0
2026-10-30T15:09:50.555Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-6e917a60
2026-10-30T15:09:51.186Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-10-30T15:09:51.659Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T15:09:51.707Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## zi) RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) - PASS

orderId: `ORD-20261030-3f608b8c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-3f608b8c`

Checks:
- PASS: POST /orders x20 -> [202]
- PASS: ORD-20261030-3f608b8c CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-3f608b8c: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-d35af586 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-d35af586: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-e73232b6 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-e73232b6: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-16684076 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-16684076: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-1e20b59d CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-1e20b59d: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-3b4bd3db CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-3b4bd3db: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-de225025 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-de225025: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-6edb5365 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-6edb5365: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-e77db5bd CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-e77db5bd: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-cf0e9e09 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-cf0e9e09: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-1deb9071 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-1deb9071: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-72988180 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-72988180: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-06151ab7 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-06151ab7: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-dafcec3d CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-dafcec3d: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-0c1447a0 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-0c1447a0: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-06731de4 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-06731de4: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-f1bc3e5b CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-f1bc3e5b: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-69011131 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-69011131: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261030-d1bd08dc COMPLETED: cancel answered 409 (expected 409)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261030-d1bd08dc: SUCCEEDED (expected SUCCEEDED)
- PASS: ORD-20261030-a48c0fb5 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261030-a48c0fb5: FAILED (expected FAILED or REFUNDED)
- PASS: WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (97, 0, 0, 1, 2) -> (96, 0, 0, 2, 2) (expected (96, 0, 0, 2, 2): only the 1 COMPLETED orders sold a unit)
