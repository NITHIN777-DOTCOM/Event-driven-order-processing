# End-to-end tests: every saga path, with DemoPay money invariants (I1-I4)

Run: 2026-10-30 09:33:42 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 313s

**Result: 29/29 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I4) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261030-af2706e5` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-af2706e5) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261030-198ebc51` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-198ebc51) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261030-0f9ea06b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-0f9ea06b) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261030-4fa335d6` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-4fa335d6) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261030-5083df56` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5083df56) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261030-411885db` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-411885db) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261030-99b904c9` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261030-0dba2570` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-0dba2570) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261030-1f4e6799` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1f4e6799) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261030-1f4e6799` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1f4e6799) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261030-6d52ed95` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6d52ed95) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261030-30f5b79b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-30f5b79b) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261030-6d7ada4b` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6d7ada4b) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261030-6dbb9b7d` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6dbb9b7d) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261030-309a10a9` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-309a10a9) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261030-30d5bb9f` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-30d5bb9f) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261030-adc9740b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-adc9740b) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261030-5909bedd` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5909bedd) |
| za | 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off | PASS | `ORD-20261030-6289f422` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹8495 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6289f422) |
| zb | every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 | PASS | `ORD-20261030-c689fb2c` | REFUNDED · ledger 1 DEBIT / 2 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c689fb2c) |
| zc | order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds | PASS | `ORD-20261030-96692ac2` | SUCCEEDED · ledger 1 DEBIT / 1 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-96692ac2) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261030-af2706e5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-af2706e5`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> ITEM_FULFILLED -> COMPLETED
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
- PASS: I4 intent PI-ORD-20261030-af2706e5: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:28:33.168Z  PENDING             Order received via API
2026-10-30T09:28:33.309Z  PROCESSING          Saga workflow started
2026-10-30T09:28:33.420Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:28:33.569Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261030-af2706e5
2026-10-30T09:28:36.916Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-da0cf30c3c8c (confirmed by webhook)
2026-10-30T09:28:37.091Z  ITEM_FULFILLED      Picked and packed 1 x Mechanical Keyboard, 60% Layout (line L1)
2026-10-30T09:28:37.129Z  COMPLETED           Order fulfilled - payment PAY-da0cf30c3c8c captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261030-198ebc51`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-198ebc51`

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
- PASS: I4 intent PI-ORD-20261030-198ebc51: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T09:28:38.871Z  PENDING             Order received via API
2026-10-30T09:28:39.054Z  PROCESSING          Saga workflow started
2026-10-30T09:28:39.153Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:28:39.289Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261030-198ebc51
2026-10-30T09:28:42.395Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-10-30T09:28:42.778Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:28:42.833Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261030-0f9ea06b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-0f9ea06b`

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
- PASS: I4 intent PI-ORD-20261030-0f9ea06b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:28:44.071Z  PENDING             Order received via API
2026-10-30T09:28:44.572Z  PROCESSING          Saga workflow started
2026-10-30T09:28:44.680Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:28:44.809Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-10-30T09:28:46.955Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-10-30T09:28:51.109Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261030-0f9ea06b
2026-10-30T09:28:53.296Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-85aa4324d946 (confirmed by webhook)
2026-10-30T09:28:53.431Z  ITEM_FULFILLED      Picked and packed 1 x Noise-Cancelling Wireless Headphones (line L1)
2026-10-30T09:28:53.469Z  COMPLETED           Order fulfilled - payment PAY-85aa4324d946 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261030-4fa335d6`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-4fa335d6`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261030-4fa335d6: none (payment never requested) (expected none)

statusHistory:
```
2026-10-30T09:28:55.689Z  PENDING             Order received via API
2026-10-30T09:28:55.856Z  PROCESSING          Saga workflow started
2026-10-30T09:28:55.993Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-30T09:28:56.018Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261030-5083df56`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5083df56`

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
- PASS: I4 intent PI-ORD-20261030-5083df56: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:28:58.688Z  PENDING             Order received via API
2026-10-30T09:28:58.848Z  PROCESSING          Saga workflow started
2026-10-30T09:28:58.962Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:28:59.094Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261030-5083df56
2026-10-30T09:29:03.255Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-68a0e7ee97d0 (confirmed by webhook)
2026-10-30T09:29:03.384Z  ITEM_FULFILLED      Picked and packed 1 x 27-inch 4K UHD IPS Monitor (line L1)
2026-10-30T09:29:03.419Z  COMPLETED           Order fulfilled - payment PAY-68a0e7ee97d0 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261030-411885db`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-411885db`

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
- PASS: I4 intent PI-ORD-20261030-411885db: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:29:12.289Z  PENDING             Order received via API
2026-10-30T09:29:12.724Z  PROCESSING          Saga workflow started
2026-10-30T09:29:12.820Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:29:12.949Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261030-411885db
2026-10-30T09:29:18.094Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-b45829b71dc7 (confirmed by webhook)
2026-10-30T09:29:18.222Z  ITEM_FULFILLED      Picked and packed 1 x Slim Wireless Mouse (line L1)
2026-10-30T09:29:18.286Z  COMPLETED           Order fulfilled - payment PAY-b45829b71dc7 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261030-99b904c9`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 291s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0, credits []
- PASS: I6 PENDING -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹0 <= charged ₹0
- PASS: I4 intent PI-ORD-20261030-99b904c9: none (payment never requested) (expected none)

statusHistory:
```
2026-10-30T09:28:30.432Z  PENDING             Order received via API
2026-10-30T09:28:30.824Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-30T09:29:30.803Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-30T09:30:30.812Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261030-0dba2570`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-0dba2570`

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
- PASS: I4 intent PI-ORD-20261030-0dba2570: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T09:29:36.513Z  PENDING             Order received via API
2026-10-30T09:29:36.647Z  PROCESSING          Saga workflow started
2026-10-30T09:29:36.782Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:29:36.895Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261030-0dba2570
2026-10-30T09:29:39.051Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-30T09:29:39.287Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:29:39.335Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261030-1f4e6799`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1f4e6799`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹2299: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹2299, credits []
- PASS: I6 COMPLETED -> net ₹2299 = fulfilled lines ₹2299
- PASS: I7 refunds ₹0 <= charged ₹2299
- PASS: I4 intent PI-ORD-20261030-1f4e6799: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:29:41.733Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-30T09:29:41.910Z  PROCESSING          Saga workflow started
2026-10-30T09:29:42.026Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:29:42.169Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-1f4e6799
2026-10-30T09:29:46.313Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-334afd5230d4 (confirmed by webhook)
2026-10-30T09:29:46.442Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-30T09:29:46.481Z  COMPLETED           Order fulfilled - payment PAY-334afd5230d4 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261030-1f4e6799`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-1f4e6799`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-30T09:29:41.733Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-30T09:29:41.910Z  PROCESSING          Saga workflow started
2026-10-30T09:29:42.026Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:29:42.169Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-1f4e6799
2026-10-30T09:29:46.313Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-334afd5230d4 (confirmed by webhook)
2026-10-30T09:29:46.442Z  ITEM_FULFILLED      Picked and packed 1 x Low-Profile Wireless Keyboard (line L1)
2026-10-30T09:29:46.481Z  COMPLETED           Order fulfilled - payment PAY-334afd5230d4 captured
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

orderId: `ORD-20261030-6d52ed95`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6d52ed95`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (29 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-30T09:29:56.611Z  PENDING             Order received via API
2026-10-30T09:29:57.157Z  PROCESSING          Saga workflow started
2026-10-30T09:29:57.279Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:29:57.409Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261030-6d52ed95
2026-10-30T09:29:59.554Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-259fc568859c (confirmed by webhook)
2026-10-30T09:29:59.711Z  ITEM_FULFILLED      Picked and packed 1 x Felt and Leather Desk Mat (line L1)
2026-10-30T09:29:59.757Z  COMPLETED           Order fulfilled - payment PAY-259fc568859c captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261030-30f5b79b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-30f5b79b`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261030-49f36af7, B ORD-20261030-30f5b79b
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261030-49f36af7 COMPLETED
- PASS: ORD-20261030-30f5b79b COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I4 intent PI-ORD-20261030-30f5b79b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:30:04.615Z  PENDING             Order received via API
2026-10-30T09:30:05.212Z  PROCESSING          Saga workflow started
2026-10-30T09:30:05.355Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:30:05.489Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-30f5b79b
2026-10-30T09:30:07.653Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-0ad1123edd06 (confirmed by webhook)
2026-10-30T09:30:07.785Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-30T09:30:07.827Z  COMPLETED           Order fulfilled - payment PAY-0ad1123edd06 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261030-e2ebc713)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261030-6d7ada4b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6d7ada4b`

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
- PASS: I4 intent PI-ORD-20261030-6d7ada4b: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-10-30T09:28:30.648Z  PENDING             Order received via API
2026-10-30T09:28:31.286Z  PROCESSING          Saga workflow started
2026-10-30T09:28:31.534Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:28:31.652Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261030-6d7ada4b
2026-10-30T09:30:31.894Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:30:31.931Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261030-6dbb9b7d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6dbb9b7d`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261030-6dbb9b7d REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0, credits ['*']
- PASS: I6 FAILED -> net ₹0 = fulfilled lines ₹0
- PASS: I7 refunds ₹18999 <= charged ₹18999
- PASS: I4 intent PI-ORD-20261030-6dbb9b7d: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-30T09:28:30.849Z  PENDING             Order received via API
2026-10-30T09:28:31.051Z  PROCESSING          Saga workflow started
2026-10-30T09:28:31.182Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:28:31.349Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261030-6dbb9b7d
2026-10-30T09:30:31.566Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:30:31.602Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-10-30T09:31:01.692Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-78aaa8136ae4, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261030-309a10a9`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-309a10a9`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: exactly one PAYMENT_CAPTURED in statusHistory
- PASS: webhook log lines with result 'duplicate' for this intent: 1 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹6499: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹6499, credits []
- PASS: I6 COMPLETED -> net ₹6499 = fulfilled lines ₹6499
- PASS: I7 refunds ₹0 <= charged ₹6499
- PASS: I4 intent PI-ORD-20261030-309a10a9: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:30:09.831Z  PENDING             Order received via API
2026-10-30T09:30:10.192Z  PROCESSING          Saga workflow started
2026-10-30T09:30:10.294Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:30:10.409Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261030-309a10a9
2026-10-30T09:30:15.554Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-e9651fa200a5 (confirmed by webhook)
2026-10-30T09:30:15.685Z  ITEM_FULFILLED      Picked and packed 1 x Ergonomic Wireless Mouse (line L1)
2026-10-30T09:30:15.724Z  COMPLETED           Order fulfilled - payment PAY-e9651fa200a5 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261030-30d5bb9f`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-30d5bb9f`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: 'webhook_signature_rejected' log lines since this order: 1 (expected >= 1)
- PASS: DemoPay logged the 401 for its forged callback, then sent the genuine one
- PASS: CloudWatch OrderSaga/WebhookSignatureFailures during this run: 12 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999, credits []
- PASS: I6 COMPLETED -> net ₹4999 = fulfilled lines ₹4999
- PASS: I7 refunds ₹0 <= charged ₹4999
- PASS: I4 intent PI-ORD-20261030-30d5bb9f: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:30:23.371Z  PENDING             Order received via API
2026-10-30T09:30:23.943Z  PROCESSING          Saga workflow started
2026-10-30T09:30:24.041Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:30:24.249Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261030-30d5bb9f
2026-10-30T09:30:28.437Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-134b1d95df3a (confirmed by webhook)
2026-10-30T09:30:28.585Z  ITEM_FULFILLED      Picked and packed 1 x True Wireless Earbuds (line L1)
2026-10-30T09:30:28.618Z  COMPLETED           Order fulfilled - payment PAY-134b1d95df3a captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 599 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) -> (12, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261030-bae63f7674 exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (13, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261030-e6b3377bdb -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (14, 0, 0) (expected (14, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-10-30T09:30:43.562Z  HOLD                HOLD-20261030-e6b3377bdb and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261030-f4a3136830 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 49.1 s after expiresAt 2026-10-30T09:29:02.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved, sold, writtenOff) (100, 0, 0, 0, 0) -> (99, 0, 0, 1, 0): the 3 held units went back (held 0, pool 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-10-30T09:28:32.472Z  ACTIVE              HOLD-20261030-f4a3136830: 3 x DESK-MAT held for 30 s
2026-10-30T09:29:02.000Z  expiresAt           the schedule's at() time
2026-10-30T09:29:51.075Z  EXPIRED             by the schedule, 49.1 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261030-ce16f8f93f (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261030-adc9740b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-adc9740b`

Checks:
- PASS: POST /holds -> 201 HOLD-20261030-670563f20d
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261030-670563f20d'
- PASS: hold CONSUMED by ORD-20261030-adc9740b (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (98, 0, 0) -> (97, 0, 0) (stock -1 once, at hold time; held -> reserved -> sold)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799, credits []
- PASS: I6 COMPLETED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹0 <= charged ₹1799
- PASS: I4 intent PI-ORD-20261030-adc9740b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:30:46.754Z  PENDING             Order received via API
2026-10-30T09:30:47.009Z  PROCESSING          Saga workflow started
2026-10-30T09:30:47.162Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261030-670563f20d
2026-10-30T09:30:47.449Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-adc9740b
2026-10-30T09:30:49.633Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-68229a44bb71 (confirmed by webhook)
2026-10-30T09:30:49.751Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-30T09:30:49.791Z  COMPLETED           Order fulfilled - payment PAY-68229a44bb71 captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261030-5909bedd`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-5909bedd`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261030-b4df5d8703
- PASS: hold HOLD-20261030-b4df5d8703 EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261030-b4df5d8703 had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (14, 0, 0) -> (13, 0, 0) (a normal fresh reservation, then sold)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499, credits []
- PASS: I6 COMPLETED -> net ₹5499 = fulfilled lines ₹5499
- PASS: I7 refunds ₹0 <= charged ₹5499
- PASS: I4 intent PI-ORD-20261030-5909bedd: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:33:28.980Z  PENDING             Order received via API
2026-10-30T09:33:29.697Z  PROCESSING          Saga workflow started
2026-10-30T09:33:30.046Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261030-b4df5d8703 had ended, so reserved afresh)
2026-10-30T09:33:30.309Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261030-5909bedd
2026-10-30T09:33:32.768Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-4f42acb18c04 (confirmed by webhook)
2026-10-30T09:33:33.045Z  ITEM_FULFILLED      Picked and packed 1 x Compact 65% Mechanical Keyboard (line L1)
2026-10-30T09:33:33.091Z  COMPLETED           Order fulfilled - payment PAY-4f42acb18c04 captured
```

## za) 3 lines, line 2 damaged after payment -> PARTIALLY_FULFILLED, only line 2 refunded and written off - PASS

orderId: `ORD-20261030-6289f422`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-6289f422`

Checks:
- PASS: POST /orders -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: line states ['FULFILLED', 'WRITTEN_OFF', 'FULFILLED']
- PASS: L2 refundedAmount 6499 = its lineAmount 6499
- PASS: ledger CREDITs [('L2', Decimal('6499'))] (expected exactly one, for L2)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> ITEM_FULFILLED -> ITEM_FULFILLED -> LINE_REFUNDED -> ITEM_WRITTEN_OFF -> PARTIALLY_FULFILLED
- PASS: write-off audit record for L2: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
- PASS: L1 WIRELESS-MOUSE (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 3, 0) (expected (97, 0, 0, 3, 0))
- PASS: L2 ERGO-MOUSE (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (98, 0, 0, 1, 1) (expected (98, 0, 0, 1, 1))
- PASS: L3 LOWPRO-KEYBOARD (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (96, 0, 0, 4, 0) (expected (96, 0, 0, 4, 0))
- PASS: execution SUCCEEDED (expected SUCCEEDED at OrderPartiallyFulfilled)
- PASS: the execution ended in OrderPartiallyFulfilled
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹8495, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹8495 = fulfilled lines ₹8495
- PASS: I7 refunds ₹6499 <= charged ₹14994
- PASS: I4 intent PI-ORD-20261030-6289f422: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:30:52.094Z  PENDING             Order received via API
2026-10-30T09:30:52.238Z  PROCESSING          Saga workflow started
2026-10-30T09:30:52.339Z  RESERVED            Reserved stock for 3 product(s)
2026-10-30T09:30:52.469Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹14,994 · intent PI-ORD-20261030-6289f422
2026-10-30T09:30:57.628Z  PAYMENT_CAPTURED    ₹14,994 captured by DemoPay · PAY-969e3377b6bc (confirmed by webhook)
2026-10-30T09:30:57.750Z  ITEM_FULFILLED      Picked and packed 3 x Low-Profile Wireless Keyboard (line L3)
2026-10-30T09:30:57.884Z  ITEM_FULFILLED      Picked and packed 2 x Slim Wireless Mouse (line L1)
2026-10-30T09:30:58.134Z  LINE_REFUNDED       ₹6,499 refunded to DemoPay for 1 x Ergonomic Wireless Mouse (line L2)
2026-10-30T09:30:58.337Z  ITEM_WRITTEN_OFF    1 x Ergonomic Wireless Mouse (line L2) written off: Ergonomic Wireless Mouse (line L2) was found damaged in the warehouse (simulated)
2026-10-30T09:30:58.381Z  PARTIALLY_FULFILLED 2 of 3 items delivered - INR 6499.00 refunded for the unavailable items
```

## zb) every line damaged -> FAILED 'all items unavailable', full refund, everything written off, net 0 - PASS

orderId: `ORD-20261030-c689fb2c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c689fb2c`

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
- PASS: I4 intent PI-ORD-20261030-c689fb2c: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-30T09:30:59.757Z  PENDING             Order received via API
2026-10-30T09:31:00.253Z  PROCESSING          Saga workflow started
2026-10-30T09:31:00.368Z  RESERVED            Reserved stock for 2 product(s)
2026-10-30T09:31:00.509Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹11,997 · intent PI-ORD-20261030-c689fb2c
2026-10-30T09:31:04.672Z  PAYMENT_CAPTURED    ₹11,997 captured by DemoPay · PAY-098e90893046 (confirmed by webhook)
2026-10-30T09:31:04.994Z  LINE_REFUNDED       ₹1,999 refunded to DemoPay for 1 x USB-C Hub, 6-in-1 (line L1)
2026-10-30T09:31:05.114Z  LINE_REFUNDED       ₹9,998 refunded to DemoPay for 2 x True Wireless Earbuds (line L2)
2026-10-30T09:31:05.215Z  ITEM_WRITTEN_OFF    1 x USB-C Hub, 6-in-1 (line L1) written off: USB-C Hub, 6-in-1 (line L1) was found damaged in the warehouse (simulated)
2026-10-30T09:31:05.235Z  ITEM_WRITTEN_OFF    2 x True Wireless Earbuds (line L2) written off: True Wireless Earbuds (line L2) was found damaged in the warehouse (simulated)
2026-10-30T09:31:05.276Z  FAILED              AllItemsUnavailable: all items unavailable - INR 11997.00 refunded to your DemoPay wallet and every line written off
```

## zc) order with a checkout hold, last line damaged -> hold consumed once, PARTIALLY_FULFILLED, I5 holds - PASS

orderId: `ORD-20261030-96692ac2`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-96692ac2`

Checks:
- PASS: POST /holds -> 201 HOLD-20261030-89656bba52
- PASS: POST /orders with holdId -> 202 (expected 202)
- PASS: order status PARTIALLY_FULFILLED (expected PARTIALLY_FULFILLED)
- PASS: RESERVED detail: 'Reserved stock for 2 product(s) from checkout hold HOLD-20261030-89656bba52'
- PASS: hold CONSUMED by ORD-20261030-96692ac2
- PASS: L1 LAPTOP-STAND (stock, held, reserved, sold, writtenOff) (97, 0, 0, 3, 0) -> (96, 0, 0, 4, 0) (expected (96, 0, 0, 4, 0))
- PASS: L2 ANC-HEADPHONES (stock, held, reserved, sold, writtenOff) (99, 0, 0, 1, 0) -> (97, 0, 0, 1, 2) (expected (97, 0, 0, 1, 2))
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹1799, credits ['L2']
- PASS: I6 PARTIALLY_FULFILLED -> net ₹1799 = fulfilled lines ₹1799
- PASS: I7 refunds ₹53980 <= charged ₹55779
- PASS: I4 intent PI-ORD-20261030-96692ac2: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:33:34.240Z  PENDING             Order received via API
2026-10-30T09:33:34.828Z  PROCESSING          Saga workflow started
2026-10-30T09:33:34.965Z  RESERVED            Reserved stock for 2 product(s) from checkout hold HOLD-20261030-89656bba52
2026-10-30T09:33:35.255Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹55,779 · intent PI-ORD-20261030-96692ac2
2026-10-30T09:33:37.599Z  PAYMENT_CAPTURED    ₹55,779 captured by DemoPay · PAY-0a16c6f13b07 (confirmed by webhook)
2026-10-30T09:33:37.728Z  ITEM_FULFILLED      Picked and packed 1 x Aluminium Laptop Stand (line L1)
2026-10-30T09:33:38.031Z  LINE_REFUNDED       ₹53,980 refunded to DemoPay for 2 x Noise-Cancelling Wireless Headphones (line L2)
2026-10-30T09:33:38.211Z  ITEM_WRITTEN_OFF    2 x Noise-Cancelling Wireless Headphones (line L2) written off: Noise-Cancelling Wireless Headphones (line L2) was found damaged in the warehouse (simulated)
2026-10-30T09:33:38.257Z  PARTIALLY_FULFILLED 1 of 2 items delivered - INR 53980.00 refunded for the unavailable items
```
