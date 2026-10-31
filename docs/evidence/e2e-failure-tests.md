# End-to-end tests: every saga path, with DemoPay money and stock invariants (I1-I9)

Run: 2026-10-31 16:30:15 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 389s

**Result: 35/35 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I9) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261031-97d0c30b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-97d0c30b) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261031-8b5ef9f7` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-8b5ef9f7) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261031-7b73bc83` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-7b73bc83) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261031-7671b963` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-7671b963) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261031-7661eb31` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-7661eb31) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261031-605ff552` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-605ff552) |
| g | poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING | PASS | `ORD-20261031-7b77f4c5` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261031-071bce39` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-071bce39) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261031-766323a3` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-766323a3) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261031-766323a3` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-766323a3) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261031-1e6ee4af` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-1e6ee4af) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261031-95776018` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-95776018) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261031-4ec77b10` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-4ec77b10) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261031-07387738` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-07387738) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261031-b445a302` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-b445a302) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261031-c6acfd44` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-c6acfd44) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261031-8c16c90d` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-8c16c90d) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261031-f17dacd3` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-f17dacd3) |
| za | 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off | PASS | `ORD-20261031-076f5d4b` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹8495 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-076f5d4b) |
| zb | every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 | PASS | `ORD-20261031-faaa19a7` | REFUNDED · ledger 1 DEBIT / 2 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-faaa19a7) |
| zc | order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds | PASS | `ORD-20261031-94d6a532` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-94d6a532) |
| zd | cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent | PASS | `ORD-20261031-a789af83` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-a789af83) |
| ze | cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back | PASS | `ORD-20261031-308906f5` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-308906f5) |
| zf | cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry | PASS | `ORD-20261031-31c21e19` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-31c21e19) |
| zg | cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged | PASS | `ORD-20261031-97d0c30b` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-97d0c30b) |
| zh | cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once | PASS | `ORD-20261031-1119c5b3` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-1119c5b3) |
| zi | RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) | PASS | `ORD-20261031-2864ec95` | 3 x cancel won, late charge refunded by the webhook; 17 x cancel won, nothing charged | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-2864ec95) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261031-97d0c30b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-97d0c30b`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> COMPLETED
- PASS: MECH-KEYBOARD (stock, reserved) (98, 0) -> (97, 0) (expected stock -1)
- PASS: MECH-KEYBOARD (sold, writtenOff) (2, 0) -> (3, 0) (expected sold +1)
- PASS: stored lines [('L1', Decimal('3499'))] (expected [('L1', 3499)])
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹3499: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹3499, credits []
- PASS: I6 COMPLETED -> net ₹3499 = fulfilled lines ₹3499
- PASS: I7 refunds ₹0 <= charged ₹3499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261031-97d0c30b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:23:55.800Z  PENDING             Order received via API
2026-10-31T16:23:55.909Z  PROCESSING          Saga workflow started
2026-10-31T16:23:56.062Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:23:56.191Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261031-97d0c30b
2026-10-31T16:24:03.281Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-73d15908959b (confirmed by webhook)
2026-10-31T16:24:04.265Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:24:05.423Z  ITEM_FULFILLED      Picked and packed 1 x Mechanical Keyboard, 60% Layout (line L1)
2026-10-31T16:24:05.476Z  COMPLETED           Order fulfilled - payment PAY-73d15908959b captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261031-8b5ef9f7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-8b5ef9f7`

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
- PASS: I4 intent PI-ORD-20261031-8b5ef9f7: FAILED (expected FAILED)

statusHistory:
```
2026-10-31T16:24:07.620Z  PENDING             Order received via API
2026-10-31T16:24:07.743Z  PROCESSING          Saga workflow started
2026-10-31T16:24:07.898Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:24:08.046Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261031-8b5ef9f7
2026-10-31T16:24:11.159Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-10-31T16:24:13.246Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:24:13.362Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261031-7b73bc83`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-7b73bc83`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 97 -> 96 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹26990: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹26990, credits []
- PASS: I6 COMPLETED -> net ₹26990 = fulfilled lines ₹26990
- PASS: I7 refunds ₹0 <= charged ₹26990
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261031-7b73bc83: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:24:15.600Z  PENDING             Order received via API
2026-10-31T16:24:15.769Z  PROCESSING          Saga workflow started
2026-10-31T16:24:15.906Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:24:16.048Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-10-31T16:24:18.250Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-10-31T16:24:22.406Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261031-7b73bc83
2026-10-31T16:24:25.590Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-d58d11e8e6c4 (confirmed by webhook)
2026-10-31T16:24:25.733Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:24:25.846Z  ITEM_FULFILLED      Picked and packed 1 x Noise-Cancelling Wireless Headphones (line L1)
2026-10-31T16:24:25.883Z  COMPLETED           Order fulfilled - payment PAY-d58d11e8e6c4 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261031-7671b963`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-7671b963`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (99, 0) -> (99, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> CheckCancelBeforeFailing -> CancelledWhileFailing -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261031-7671b963: none (payment never requested) (expected None)

statusHistory:
```
2026-10-31T16:24:27.886Z  PENDING             Order received via API
2026-10-31T16:24:28.019Z  PROCESSING          Saga workflow started
2026-10-31T16:24:28.120Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-31T16:24:28.215Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261031-7661eb31`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-7661eb31`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this (user-scoped) key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1, not 3)
- PASS: 4K-MONITOR stock 99 -> 98 (expected -1, not -3)
- PASS: DEBIT ledger entries: 1 (expected 1, not 3)
- PASS: I1 COMPLETED -> one DEBIT of ₹24999: ledger 1 DEBIT / 0 CREDIT, net ₹24999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹24999, credits []
- PASS: I6 COMPLETED -> net ₹24999 = fulfilled lines ₹24999
- PASS: I7 refunds ₹0 <= charged ₹24999
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261031-7661eb31: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:24:31.320Z  PENDING             Order received via API
2026-10-31T16:24:31.542Z  PROCESSING          Saga workflow started
2026-10-31T16:24:31.649Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:24:31.769Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261031-7661eb31
2026-10-31T16:24:33.913Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-2ffed09ccf79 (confirmed by webhook)
2026-10-31T16:24:34.022Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:24:34.106Z  ITEM_FULFILLED      Picked and packed 1 x 27-inch 4K UHD IPS Monitor (line L1)
2026-10-31T16:24:34.158Z  COMPLETED           Order fulfilled - payment PAY-2ffed09ccf79 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261031-605ff552`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-605ff552`

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
- PASS: I4 intent PI-ORD-20261031-605ff552: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:24:47.980Z  PENDING             Order received via API
2026-10-31T16:24:48.096Z  PROCESSING          Saga workflow started
2026-10-31T16:24:48.206Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:24:48.305Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261031-605ff552
2026-10-31T16:24:50.501Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-e3efd3d63213 (confirmed by webhook)
2026-10-31T16:24:50.591Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:24:50.694Z  ITEM_FULFILLED      Picked and packed 1 x Slim Wireless Mouse (line L1)
2026-10-31T16:24:50.734Z  COMPLETED           Order fulfilled - payment PAY-e3efd3d63213 captured
```

## g) poison message -> DLQ after 3 receives (DLQ count +1, message found), order stays PENDING - PASS

orderId: `ORD-20261031-7b77f4c5`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order-saga-orders-dlq count 34 -> 35: no new message within 5 min
- PASS: this order's message found in the DLQ (swept 35 of 35 messages, none deleted)
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 PENDING -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261031-7b77f4c5: none (payment never requested) (expected None)

statusHistory:
```
2026-10-31T16:23:52.142Z  PENDING             Order received via API
2026-10-31T16:23:53.071Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-31T16:24:52.420Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-31T16:25:52.425Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261031-071bce39`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-071bce39`

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
- PASS: I4 intent PI-ORD-20261031-071bce39: FAILED (expected FAILED)

statusHistory:
```
2026-10-31T16:25:11.541Z  PENDING             Order received via API
2026-10-31T16:25:12.074Z  PROCESSING          Saga workflow started
2026-10-31T16:25:12.219Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:25:12.404Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261031-071bce39
2026-10-31T16:25:15.659Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-31T16:25:15.885Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:25:15.991Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261031-766323a3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-766323a3`

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
- PASS: I4 intent PI-ORD-20261031-766323a3: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:25:16.605Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-31T16:25:17.820Z  PROCESSING          Saga workflow started
2026-10-31T16:25:17.919Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:25:18.025Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261031-766323a3
2026-10-31T16:25:22.187Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-b4947dd318c4 (confirmed by webhook)
2026-10-31T16:25:22.297Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:25:22.444Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-31T16:25:22.501Z  COMPLETED           Order fulfilled - payment PAY-b4947dd318c4 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261031-766323a3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-766323a3`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-31T16:25:16.605Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-31T16:25:17.820Z  PROCESSING          Saga workflow started
2026-10-31T16:25:17.919Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:25:18.025Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261031-766323a3
2026-10-31T16:25:22.187Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-b4947dd318c4 (confirmed by webhook)
2026-10-31T16:25:22.297Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:25:22.444Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-31T16:25:22.501Z  COMPLETED           Order fulfilled - payment PAY-b4947dd318c4 captured
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

orderId: `ORD-20261031-1e6ee4af`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-1e6ee4af`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (44 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-31T16:25:40.342Z  PENDING             Order received via API
2026-10-31T16:25:40.592Z  PROCESSING          Saga workflow started
2026-10-31T16:25:40.699Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:25:40.804Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261031-1e6ee4af
2026-10-31T16:25:42.969Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-00bf421c02b1 (confirmed by webhook)
2026-10-31T16:25:43.082Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:25:43.184Z  ITEM_FULFILLED      Picked and packed 1 x Felt and Leather Desk Mat (line L1)
2026-10-31T16:25:43.219Z  COMPLETED           Order fulfilled - payment PAY-00bf421c02b1 captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261031-95776018`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-95776018`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261031-f3aec2ed, B ORD-20261031-95776018
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261031-f3aec2ed COMPLETED
- PASS: ORD-20261031-95776018 COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261031-95776018: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:25:50.278Z  PENDING             Order received via API
2026-10-31T16:25:50.706Z  PROCESSING          Saga workflow started
2026-10-31T16:25:50.879Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:25:50.986Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261031-95776018
2026-10-31T16:25:54.126Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-a2b362258f71 (confirmed by webhook)
2026-10-31T16:25:54.239Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:25:54.338Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-31T16:25:54.390Z  COMPLETED           Order fulfilled - payment PAY-a2b362258f71 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261031-e2e80671)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261031-4ec77b10`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-4ec77b10`

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
- PASS: I4 intent PI-ORD-20261031-4ec77b10: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-10-31T16:23:52.462Z  PENDING             Order received via API
2026-10-31T16:23:53.364Z  PROCESSING          Saga workflow started
2026-10-31T16:23:54.579Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:23:55.546Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261031-4ec77b10
2026-10-31T16:25:54.940Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:25:55.040Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261031-07387738`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-07387738`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261031-07387738 REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹18999 <= charged ₹18999
- PASS: I4 intent PI-ORD-20261031-07387738: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-31T16:23:52.722Z  PENDING             Order received via API
2026-10-31T16:23:53.171Z  PROCESSING          Saga workflow started
2026-10-31T16:23:54.209Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:23:55.192Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261031-07387738
2026-10-31T16:25:54.644Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:25:54.747Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-10-31T16:26:25.879Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-59591e4f175c, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261031-b445a302`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-b445a302`

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
- PASS: I4 intent PI-ORD-20261031-b445a302: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:25:55.978Z  PENDING             Order received via API
2026-10-31T16:25:56.110Z  PROCESSING          Saga workflow started
2026-10-31T16:25:56.220Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:25:56.362Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261031-b445a302
2026-10-31T16:25:58.485Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-43f65cad3cb0 (confirmed by webhook)
2026-10-31T16:25:58.581Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:25:58.661Z  ITEM_FULFILLED      Picked and packed 1 x Ergonomic Wireless Mouse (line L1)
2026-10-31T16:25:58.696Z  COMPLETED           Order fulfilled - payment PAY-43f65cad3cb0 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261031-c6acfd44`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-c6acfd44`

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
- PASS: I4 intent PI-ORD-20261031-c6acfd44: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:26:10.121Z  PENDING             Order received via API
2026-10-31T16:26:10.452Z  PROCESSING          Saga workflow started
2026-10-31T16:26:10.559Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:26:10.662Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261031-c6acfd44
2026-10-31T16:26:12.846Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-d212c86c8a0a (confirmed by webhook)
2026-10-31T16:26:12.923Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:26:13.047Z  ITEM_FULFILLED      Picked and packed 1 x True Wireless Earbuds (line L1)
2026-10-31T16:26:13.100Z  COMPLETED           Order fulfilled - payment PAY-d212c86c8a0a captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 599 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (13, 0, 0) -> (11, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261031-b2a70ffb71 exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (12, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261031-62fd17d067 -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (13, 0, 0) (expected (13, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-10-31T16:26:30.418Z  HOLD                HOLD-20261031-62fd17d067 and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261031-e903fc40ce EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 12.1 s after expiresAt 2026-10-31T16:24:24.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (98, 0, 0, 2, 0): the 3 held units went back (held 0, pool 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-10-31T16:23:54.953Z  ACTIVE              HOLD-20261031-e903fc40ce: 3 x DESK-MAT held for 30 s
2026-10-31T16:24:24.000Z  expiresAt           the schedule's at() time
2026-10-31T16:24:36.081Z  EXPIRED             by the schedule, 12.1 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261031-a6adcb6a62 (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261031-8c16c90d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-8c16c90d`

Checks:
- PASS: POST /holds -> 201 HOLD-20261031-d023677bdd
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261031-d023677bdd'
- PASS: hold CONSUMED by ORD-20261031-8c16c90d (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (94, 0, 0) -> (93, 0, 0) (stock -1 once, at hold time; held -> reserved -> sold)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261031-8c16c90d: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:26:35.079Z  PENDING             Order received via API
2026-10-31T16:26:35.254Z  PROCESSING          Saga workflow started
2026-10-31T16:26:35.379Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261031-d023677bdd
2026-10-31T16:26:35.602Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261031-8c16c90d
2026-10-31T16:26:37.768Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-0f00b94787b0 (confirmed by webhook)
2026-10-31T16:26:37.878Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:26:37.966Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-31T16:26:38.022Z  COMPLETED           Order fulfilled - payment PAY-0f00b94787b0 captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261031-f17dacd3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-f17dacd3`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261031-c60427ea7e
- PASS: hold HOLD-20261031-c60427ea7e EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261031-c60427ea7e had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (13, 0, 0) -> (12, 0, 0) (a normal fresh reservation, then sold)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499, credits []
- PASS: I6 COMPLETED -> net ₹5499 = fulfilled lines ₹5499
- PASS: I7 refunds ₹0 <= charged ₹5499
- PASS: I9 one winner: cancel requested False, FULFILLING True, status COMPLETED
- PASS: I4 intent PI-ORD-20261031-f17dacd3: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:29:27.452Z  PENDING             Order received via API
2026-10-31T16:29:27.710Z  PROCESSING          Saga workflow started
2026-10-31T16:29:28.028Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261031-c60427ea7e had ended, so reserved afresh)
2026-10-31T16:29:28.276Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261031-f17dacd3
2026-10-31T16:29:32.964Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-b406e13de5a0 (confirmed by webhook)
2026-10-31T16:29:33.138Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:29:33.354Z  ITEM_FULFILLED      Picked and packed 1 x Compact 65% Mechanical Keyboard (line L1)
2026-10-31T16:29:33.414Z  COMPLETED           Order fulfilled - payment PAY-b406e13de5a0 captured
```

## za) 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off - PASS

orderId: `ORD-20261031-076f5d4b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-076f5d4b`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: line states ['FULFILLED', 'WRITTEN_OFF', 'FULFILLED']
- PASS: L2 refundedAmount 6499 = its lineAmount 6499
- PASS: ledger CREDITs [('L2', Decimal('6499'))] (expected exactly one, for L2)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> FULFILLING -> ITEM_FULFILLED -> ITEM_FULFILLED -> LINE_REFUNDED -> ITEM_WRITTEN_OFF -> PARTIALLY_FULFILLED
- PASS: write-off audit record for L2: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
- PASS: L1 WIRELESS-MOUSE (stock, held, reserved, sold, writtenOff) (88, 0, 0, 12, 0) -> (86, 0, 0, 14, 0) (expected (86, 0, 0, 14, 0))
- PASS: L2 ERGO-MOUSE (stock, held, reserved, sold, writtenOff) (96, 0, 0, 2, 2) -> (95, 0, 0, 2, 3) (expected (95, 0, 0, 2, 3))
- PASS: L3 LOWPRO-KEYBOARD (stock, held, reserved, sold, writtenOff) (91, 0, 0, 9, 0) -> (88, 0, 0, 12, 0) (expected (88, 0, 0, 12, 0))
- PASS: execution SUCCEEDED (expected SUCCEEDED at OrderPartiallyFulfilled)
- PASS: the execution ended in OrderPartiallyFulfilled
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹8495, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹8495 = fulfilled lines ₹8495
- PASS: I7 refunds ₹6499 <= charged ₹14994
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261031-076f5d4b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:26:41.056Z  PENDING             Order received via API
2026-10-31T16:26:41.514Z  PROCESSING          Saga workflow started
2026-10-31T16:26:41.619Z  RESERVED            Reserved stock for 3 product(s)
2026-10-31T16:26:41.742Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹14,994 · intent PI-ORD-20261031-076f5d4b
2026-10-31T16:26:44.887Z  PAYMENT_CAPTURED    ₹14,994 captured by DemoPay · PAY-43d424197774 (confirmed by webhook)
2026-10-31T16:26:44.991Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:26:45.086Z  ITEM_FULFILLED      Picked and packed 3 x Low-Profile Wireless Keyboard (line L3)
2026-10-31T16:26:45.126Z  ITEM_FULFILLED      Picked and packed 2 x Slim Wireless Mouse (line L1)
2026-10-31T16:26:46.090Z  LINE_REFUNDED       ₹6,499 refunded to DemoPay for 1 x Ergonomic Wireless Mouse (line L2)
2026-10-31T16:26:47.266Z  ITEM_WRITTEN_OFF    1 x Ergonomic Wireless Mouse (line L2) written off: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
2026-10-31T16:26:47.331Z  PARTIALLY_FULFILLED 2 of 3 items delivered - INR 6499.00 refunded for the unavailable items
```

## zb) every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 - PASS

orderId: `ORD-20261031-faaa19a7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-faaa19a7`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off'
- PASS: every line WRITTEN_OFF
- PASS: write-off audit records for L1 and L2
- PASS: L1 USBC-HUB (stock, held, reserved, sold, writtenOff) (99, 0, 0, 0, 1) -> (98, 0, 0, 0, 2) (expected (98, 0, 0, 0, 2))
- PASS: L2 WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (95, 0, 0, 3, 2) -> (93, 0, 0, 3, 4) (expected (93, 0, 0, 3, 4))
- PASS: RefundAllLines ran; ReleaseInventory did not (damaged units are written off, not released)
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 2 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 2 CREDIT, net ₹0, credits ['L1', 'L2']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹11997 <= charged ₹11997
- PASS: I9 one winner: cancel requested False, FULFILLING True, status FAILED
- PASS: I4 intent PI-ORD-20261031-faaa19a7: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-31T16:26:49.599Z  PENDING             Order received via API
2026-10-31T16:26:50.022Z  PROCESSING          Saga workflow started
2026-10-31T16:26:50.139Z  RESERVED            Reserved stock for 2 product(s)
2026-10-31T16:26:50.262Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹11,997 · intent PI-ORD-20261031-faaa19a7
2026-10-31T16:26:55.406Z  PAYMENT_CAPTURED    ₹11,997 captured by DemoPay · PAY-c4d2f00f8580 (confirmed by webhook)
2026-10-31T16:26:55.514Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:26:55.810Z  LINE_REFUNDED       ₹1,999 refunded to DemoPay for 1 x USB-C Hub, 6-in-1 (line L1)
2026-10-31T16:26:55.910Z  LINE_REFUNDED       ₹9,998 refunded to DemoPay for 2 x True Wireless Earbuds (line L2)
2026-10-31T16:26:55.994Z  ITEM_WRITTEN_OFF    1 x USB-C Hub, 6-in-1 (line L1) written off: USB-C Hub, 6-in-1 (line L1) was found damaged in the warehouse (simulated)
2026-10-31T16:26:56.013Z  ITEM_WRITTEN_OFF    2 x True Wireless Earbuds (line L2) written off: True Wireless Earbuds (line L2) was found damaged in the warehouse (simulated)
2026-10-31T16:26:56.110Z  FAILED              AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off
```

## zc) order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds - PASS

orderId: `ORD-20261031-94d6a532`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-94d6a532`

Checks:
- PASS: POST /holds -> 201 HOLD-20261031-90f478414f
- PASS: POST /orders with holdId -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: RESERVED detail: 'Reserved stock for 2 product(s) from checkout hold HOLD-20261031-90f478414f'
- PASS: hold CONSUMED by ORD-20261031-94d6a532
- PASS: L1 LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (93, 0, 0, 7, 0) -> (92, 0, 0, 8, 0) (expected (92, 0, 0, 8, 0))
- PASS: L2 ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (96, 0, 0, 2, 2) -> (94, 0, 0, 2, 4) (expected (94, 0, 0, 2, 4))
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹1799, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹53980 <= charged ₹55779
- PASS: I9 one winner: cancel requested False, FULFILLING True, status PARTIALLY_FULFILLED
- PASS: I4 intent PI-ORD-20261031-94d6a532: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:29:35.292Z  PENDING             Order received via API
2026-10-31T16:29:35.384Z  PROCESSING          Saga workflow started
2026-10-31T16:29:35.522Z  RESERVED            Reserved stock for 2 product(s) from checkout hold HOLD-20261031-90f478414f
2026-10-31T16:29:35.776Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹55,779 · intent PI-ORD-20261031-94d6a532
2026-10-31T16:29:40.929Z  PAYMENT_CAPTURED    ₹55,779 captured by DemoPay · PAY-438a397b4dcf (confirmed by webhook)
2026-10-31T16:29:41.027Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:29:41.119Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-31T16:29:41.529Z  LINE_REFUNDED       ₹53,980 refunded to DemoPay for 2 x Noise-Cancelling Wireless Headphones (line L2)
2026-10-31T16:29:41.737Z  ITEM_WRITTEN_OFF    2 x Noise-Cancelling Wireless Headphones (line L2) written off: Noise-Cancelling Wireless Headphones (line L2) was found damaged in the warehouse (simulated)
2026-10-31T16:29:41.791Z  PARTIALLY_FULFILLED 1 of 2 items delivered - INR 53980.00 refunded for the unavailable items
```

## zd) cancel while waiting for payment -> CANCELLED, nothing charged, DemoPay's late charge voided; B 404; repeats idempotent - PASS

orderId: `ORD-20261031-a789af83`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-a789af83`

Checks:
- PASS: POST /orders -> 202
- PASS: waiting for DemoPay: PAYMENT_PENDING, canCancel True
- PASS: user B cancels A's order -> 404 (expected 404, exactly like a missing order)
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261031-a789af83', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-10-31T16:26:59.371Z'}
- PASS: repeated cancel -> 202, same request 2026-10-31T16:26:59.371Z
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (96, 0, 0, 2, 2) -> (96, 0, 0, 2, 2) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: CANCELLED detail 'Cancelled by the customer - nothing was charged'
- PASS: DemoPay CHARGE record VOIDED (expected VOIDED: never charged)
- PASS: cancel after the end -> 200 {'orderId': 'ORD-20261031-a789af83', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-10-31T16:26:59.371Z', 'refundedAmount': 0}
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-a789af83: FAILED (expected FAILED)

statusHistory:
```
2026-10-31T16:26:57.256Z  PENDING             Order received via API
2026-10-31T16:26:57.524Z  PROCESSING          Saga workflow started
2026-10-31T16:26:57.640Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:26:57.765Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261031-a789af83
2026-10-31T16:26:59.371Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-10-31T16:26:59.722Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:26:59.759Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## ze) cancel after payment, before fulfillment -> CANCELLED, full refund (one CREDIT), stock back - PASS

orderId: `ORD-20261031-308906f5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-308906f5`

Checks:
- PASS: POST /orders -> 202
- PASS: paid, warehouse waiting: PAYMENT_CAPTURED, canCancel True
- PASS: POST /orders/{id}/cancel -> 202 {'orderId': 'ORD-20261031-308906f5', 'status': 'CANCEL_REQUESTED', 'cancelRequestedAt': '2026-10-31T16:27:33.157Z'}
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> CANCEL_REQUESTED -> PAYMENT_REFUNDED -> INVENTORY_RELEASED -> CANCELLED
- PASS: 4K-MONITOR (stock, held, reserved, sold, writtenOff) (98, 0, 0, 2, 0) -> (98, 0, 0, 2, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: refundedAmount 24999 (expected the total 24999)
- PASS: CANCELLED detail 'Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet'
- PASS: wallet CREDIT notes ['Refund for ORD-20261031-308906f5 (order cancelled)']
- PASS: cancel twice -> 200 {'orderId': 'ORD-20261031-308906f5', 'status': 'CANCELLED', 'cancelRequestedAt': '2026-10-31T16:27:33.157Z', 'refundedAmount': 24999} (same answer, no second refund)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹24999 <= charged ₹24999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-308906f5: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-31T16:27:27.796Z  PENDING             Order received via API
2026-10-31T16:27:28.405Z  PROCESSING          Saga workflow started
2026-10-31T16:27:28.485Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:27:28.600Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261031-308906f5
2026-10-31T16:27:32.816Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-c938e07cc323 (confirmed by webhook)
2026-10-31T16:27:33.157Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-10-31T16:27:43.236Z  PAYMENT_REFUNDED    ₹24,999 refunded to DemoPay (order cancelled)
2026-10-31T16:27:43.305Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:27:43.337Z  CANCELLED           Cancelled by the customer - INR 24999.00 refunded to the DemoPay wallet
```

## zf) cancel during fulfillment -> 409 TOO_LATE_TO_CANCEL, the order still COMPLETES, one CANCEL_REJECTED entry - PASS

orderId: `ORD-20261031-31c21e19`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-31c21e19`

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
- PASS: I4 intent PI-ORD-20261031-31c21e19: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-31T16:27:45.294Z  PENDING             Order received via API
2026-10-31T16:27:45.436Z  PROCESSING          Saga workflow started
2026-10-31T16:27:45.560Z  RESERVED            Reserved stock for 1 product(s)
2026-10-31T16:27:45.700Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261031-31c21e19
2026-10-31T16:27:47.875Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-183f8fc08317 (confirmed by webhook)
2026-10-31T16:27:58.002Z  FULFILLING          Fulfillment started: the warehouse is picking the items, so the order can no longer be cancelled
2026-10-31T16:27:58.573Z  CANCEL_REJECTED     Cancel request rejected: the order was already FULFILLING
2026-10-31T16:28:08.138Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-31T16:28:08.193Z  COMPLETED           Order fulfilled - payment PAY-183f8fc08317 captured
```

## zg) cancel a COMPLETED order -> 409 TOO_LATE_TO_CANCEL, order unchanged - PASS

orderId: `ORD-20261031-97d0c30b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-97d0c30b`

Checks:
- PASS: cancel -> 409 {'error': 'TOO_LATE_TO_CANCEL', 'status': 'COMPLETED'}
- PASS: status COMPLETED, canCancel False
- PASS: history only gained ['CANCEL_REJECTED'] (a CANCEL_REJECTED entry at most)

## zh) cancel an order placed from a checkout hold -> CANCELLED, hold consumed, stock back exactly once - PASS

orderId: `ORD-20261031-1119c5b3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-1119c5b3`

Checks:
- PASS: POST /holds -> 201 HOLD-20261031-fdd13de9cc
- PASS: POST /orders with holdId -> 202
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261031-fdd13de9cc'
- PASS: cancel -> 202
- PASS: order status CANCELLED (expected CANCELLED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> CANCEL_REQUESTED -> INVENTORY_RELEASED -> CANCELLED
- PASS: LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (92, 0, 0, 8, 0) -> (92, 0, 0, 8, 0) (expected unchanged)
- PASS: execution SUCCEEDED, last state ['OrderCancelled'] (expected OrderCancelled)
- PASS: cancel branch ran: RefundWhatIsLeft -> CancelReleaseInventory -> MarkOrderCancelled -> NotifyCustomerCancelled
- PASS: hold CONSUMED by ORD-20261031-1119c5b3 (expected CONSUMED by this order: never released a 2nd time)
- PASS: no current hold, no expiry schedule left
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-1119c5b3: FAILED (expected FAILED)

statusHistory:
```
2026-10-31T16:29:42.955Z  PENDING             Order received via API
2026-10-31T16:29:43.400Z  PROCESSING          Saga workflow started
2026-10-31T16:29:43.522Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261031-fdd13de9cc
2026-10-31T16:29:43.756Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261031-1119c5b3
2026-10-31T16:29:44.171Z  CANCEL_REQUESTED    Cancellation requested by the customer: changed my mind (e2e)
2026-10-31T16:29:44.618Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-31T16:29:44.664Z  CANCELLED           Cancelled by the customer - nothing was charged
```

## zi) RACE x20: cancel API vs DemoPay charge at the same moment -> exactly one winner per order (I8, I9) - PASS

orderId: `ORD-20261031-2864ec95`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261031-2864ec95`

Checks:
- PASS: POST /orders x20 -> [202]
- PASS: ORD-20261031-2864ec95 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-2864ec95: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-609dc0c2 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-609dc0c2: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-bd147ac5 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-bd147ac5: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-41a6bc2d CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-41a6bc2d: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-456bbdcd CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-456bbdcd: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-64ab1050 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-64ab1050: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-e051db3a CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-e051db3a: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-09be010f CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-09be010f: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-b1ff7778 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-b1ff7778: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-1cc13dc4 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-1cc13dc4: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-a2f5a60c CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-a2f5a60c: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-7e02cf82 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-7e02cf82: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-7491739b CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-7491739b: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-8d7dc522 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-8d7dc522: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-76f0bd96 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-76f0bd96: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-4e7082b5 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-4e7082b5: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-ac2dbdfe CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-ac2dbdfe: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-1468d9b8 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹4999 <= charged ₹4999
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-1468d9b8: REFUNDED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-54b0095c CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-54b0095c: FAILED (expected FAILED or REFUNDED)
- PASS: ORD-20261031-40c57305 CANCELLED: cancel answered 202 (expected 202)
- PASS: I2 CANCELLED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 CANCELLED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I8 CANCELLED -> net ₹0, stock released: True, no line fulfilled: True
- PASS: I9 one winner: cancel requested True, FULFILLING False, status CANCELLED
- PASS: I4 intent PI-ORD-20261031-40c57305: FAILED (expected FAILED or REFUNDED)
- PASS: WIRELESS-EARBUDS (stock, held, reserved, sold, writtenOff) (93, 0, 0, 3, 4) -> (93, 0, 0, 3, 4) (expected (93, 0, 0, 3, 4): only the 0 COMPLETED orders sold a unit)
