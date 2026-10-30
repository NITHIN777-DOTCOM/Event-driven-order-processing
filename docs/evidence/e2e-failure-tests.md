# End-to-end tests: every saga path, with DemoPay money invariants (I1-I4)

Run: 2026-10-30 09:03:49 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 276s

**Result: 26/26 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I4) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261030-7a05ffd0` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-7a05ffd0) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261030-37bd0a3b` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-37bd0a3b) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261030-578ab5a0` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-578ab5a0) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261030-d8e2c726` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d8e2c726) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261030-137d67de` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-137d67de) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261030-426ebc2e` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-426ebc2e) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261030-eb398db5` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261030-8bbc9f02` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-8bbc9f02) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261030-c9277f2d` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c9277f2d) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261030-c9277f2d` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c9277f2d) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261030-c9e04255` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c9e04255) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261030-f2c883f7` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-f2c883f7) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261030-f0adeed0` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-f0adeed0) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261030-804cee04` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-804cee04) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261030-2e83de2f` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-2e83de2f) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261030-b907dd49` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-b907dd49) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261030-d3cfbf91` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d3cfbf91) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261030-509e56c1` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-509e56c1) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261030-7a05ffd0`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-7a05ffd0`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> COMPLETED
- PASS: MECH-KEYBOARD stock 100 -> 99 (expected -1)
- PASS: MECH-KEYBOARD (sold, writtenOff) (0, 0) -> (0, 0) (expected unchanged)
- PASS: stored lines [('L1', Decimal('3499'))] (expected [('L1', 3499)])
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹3499: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I4 intent PI-ORD-20261030-7a05ffd0: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T08:59:18.034Z  PENDING             Order received via API
2026-10-30T08:59:19.407Z  PROCESSING          Saga workflow started
2026-10-30T08:59:19.570Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T08:59:19.711Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261030-7a05ffd0
2026-10-30T08:59:25.055Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-d4b5441e89dd (confirmed by webhook)
2026-10-30T08:59:25.098Z  COMPLETED           Order fulfilled - payment PAY-d4b5441e89dd captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261030-37bd0a3b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-37bd0a3b`

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
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261030-37bd0a3b: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T08:59:28.194Z  PENDING             Order received via API
2026-10-30T08:59:28.425Z  PROCESSING          Saga workflow started
2026-10-30T08:59:28.539Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T08:59:28.686Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261030-37bd0a3b
2026-10-30T08:59:32.782Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-10-30T08:59:33.894Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T08:59:33.950Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261030-578ab5a0`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-578ab5a0`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 99 -> 98 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹26990: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I4 intent PI-ORD-20261030-578ab5a0: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T08:59:35.677Z  PENDING             Order received via API
2026-10-30T08:59:35.943Z  PROCESSING          Saga workflow started
2026-10-30T08:59:36.043Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T08:59:36.187Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-10-30T08:59:38.351Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-10-30T08:59:42.525Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261030-578ab5a0
2026-10-30T08:59:47.645Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-33f5ca3747ed (confirmed by webhook)
2026-10-30T08:59:47.694Z  COMPLETED           Order fulfilled - payment PAY-33f5ca3747ed captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261030-d8e2c726`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d8e2c726`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261030-d8e2c726: none (payment never requested) (expected none)

statusHistory:
```
2026-10-30T08:59:49.614Z  PENDING             Order received via API
2026-10-30T08:59:51.247Z  PROCESSING          Saga workflow started
2026-10-30T08:59:51.354Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-30T08:59:51.403Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261030-137d67de`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-137d67de`

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
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹24999
- PASS: I4 intent PI-ORD-20261030-137d67de: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T08:59:52.554Z  PENDING             Order received via API
2026-10-30T08:59:52.750Z  PROCESSING          Saga workflow started
2026-10-30T08:59:52.872Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T08:59:53.006Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261030-137d67de
2026-10-30T08:59:57.155Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-ed633bfee9b8 (confirmed by webhook)
2026-10-30T08:59:57.201Z  COMPLETED           Order fulfilled - payment PAY-ed633bfee9b8 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261030-426ebc2e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-426ebc2e`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹799: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I4 intent PI-ORD-20261030-426ebc2e: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:00:04.232Z  PENDING             Order received via API
2026-10-30T09:00:04.587Z  PROCESSING          Saga workflow started
2026-10-30T09:00:04.720Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:00:04.855Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261030-426ebc2e
2026-10-30T09:00:06.981Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-85befeb9cf14 (confirmed by webhook)
2026-10-30T09:00:07.029Z  COMPLETED           Order fulfilled - payment PAY-85befeb9cf14 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261030-eb398db5`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 260s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261030-eb398db5: none (payment never requested) (expected none)

statusHistory:
```
2026-10-30T08:59:14.594Z  PENDING             Order received via API
2026-10-30T08:59:14.888Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-30T09:00:14.885Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-30T09:01:14.883Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261030-8bbc9f02`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-8bbc9f02`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed'
- PASS: USB-MIC (stock, reserved) (18, 0) -> (18, 0) (expected unchanged)
- PASS: DemoPay balance 1000 (expected 1000, untouched)
- PASS: no DEBIT ledger entry
- PASS: ReleaseInventory ran (compensation)
- PASS: I2 FAILED -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261030-8bbc9f02: FAILED (expected FAILED)

statusHistory:
```
2026-10-30T09:00:26.313Z  PENDING             Order received via API
2026-10-30T09:00:26.725Z  PROCESSING          Saga workflow started
2026-10-30T09:00:26.846Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:00:26.966Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261030-8bbc9f02
2026-10-30T09:00:30.132Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-30T09:00:30.404Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:00:30.449Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261030-c9277f2d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c9277f2d`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹2299: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I4 intent PI-ORD-20261030-c9277f2d: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:00:31.838Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-30T09:00:31.956Z  PROCESSING          Saga workflow started
2026-10-30T09:00:32.050Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:00:32.186Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-c9277f2d
2026-10-30T09:00:35.319Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-aaa5e087166f (confirmed by webhook)
2026-10-30T09:00:35.367Z  COMPLETED           Order fulfilled - payment PAY-aaa5e087166f captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261030-c9277f2d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c9277f2d`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-30T09:00:31.838Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-30T09:00:31.956Z  PROCESSING          Saga workflow started
2026-10-30T09:00:32.050Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:00:32.186Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261030-c9277f2d
2026-10-30T09:00:35.319Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-aaa5e087166f (confirmed by webhook)
2026-10-30T09:00:35.367Z  COMPLETED           Order fulfilled - payment PAY-aaa5e087166f captured
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

orderId: `ORD-20261030-c9e04255`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-c9e04255`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (23 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-30T09:00:46.015Z  PENDING             Order received via API
2026-10-30T09:00:46.498Z  PROCESSING          Saga workflow started
2026-10-30T09:00:46.602Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:00:46.734Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261030-c9e04255
2026-10-30T09:00:48.881Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-25f1f5bdb8dc (confirmed by webhook)
2026-10-30T09:00:48.928Z  COMPLETED           Order fulfilled - payment PAY-25f1f5bdb8dc captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261030-f2c883f7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-f2c883f7`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261030-c5afe7a4, B ORD-20261030-f2c883f7
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261030-c5afe7a4 COMPLETED
- PASS: ORD-20261030-f2c883f7 COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I4 intent PI-ORD-20261030-f2c883f7: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:00:54.232Z  PENDING             Order received via API
2026-10-30T09:00:54.604Z  PROCESSING          Saga workflow started
2026-10-30T09:00:54.838Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:00:54.966Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-f2c883f7
2026-10-30T09:00:58.103Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-577fe85b0c4e (confirmed by webhook)
2026-10-30T09:00:58.146Z  COMPLETED           Order fulfilled - payment PAY-577fe85b0c4e captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261030-e2e17dff)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261030-f0adeed0`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-f0adeed0`

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
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261030-f0adeed0: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-10-30T08:59:14.778Z  PENDING             Order received via API
2026-10-30T08:59:15.143Z  PROCESSING          Saga workflow started
2026-10-30T08:59:15.259Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T08:59:15.406Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261030-f0adeed0
2026-10-30T09:01:15.713Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:01:15.751Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261030-804cee04`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-804cee04`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261030-804cee04 REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261030-804cee04: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-30T08:59:14.954Z  PENDING             Order received via API
2026-10-30T08:59:15.204Z  PROCESSING          Saga workflow started
2026-10-30T08:59:15.309Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T08:59:15.506Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261030-804cee04
2026-10-30T09:01:15.653Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-30T09:01:15.694Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-10-30T09:01:46.560Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-ec2ed4bdab8c, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261030-2e83de2f`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-2e83de2f`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: exactly one PAYMENT_CAPTURED in statusHistory
- PASS: webhook log lines with result 'duplicate' for this intent: 1 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹6499: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I4 intent PI-ORD-20261030-2e83de2f: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:01:01.572Z  PENDING             Order received via API
2026-10-30T09:01:02.033Z  PROCESSING          Saga workflow started
2026-10-30T09:01:02.166Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:01:02.306Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261030-2e83de2f
2026-10-30T09:01:05.442Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-9e719fa0ba59 (confirmed by webhook)
2026-10-30T09:01:05.489Z  COMPLETED           Order fulfilled - payment PAY-9e719fa0ba59 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261030-b907dd49`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-b907dd49`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: 'webhook_signature_rejected' log lines since this order: 1 (expected >= 1)
- PASS: DemoPay logged the 401 for its forged callback, then sent the genuine one
- PASS: CloudWatch OrderSaga/WebhookSignatureFailures during this run: 6 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I4 intent PI-ORD-20261030-b907dd49: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:01:13.191Z  PENDING             Order received via API
2026-10-30T09:01:13.292Z  PROCESSING          Saga workflow started
2026-10-30T09:01:13.412Z  RESERVED            Reserved stock for 1 product(s)
2026-10-30T09:01:13.525Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261030-b907dd49
2026-10-30T09:01:17.685Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-254d13e9034b (confirmed by webhook)
2026-10-30T09:01:17.736Z  COMPLETED           Order fulfilled - payment PAY-254d13e9034b captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 599 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) -> (12, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261030-009f230f7b exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (13, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261030-9ec8c7bcaf -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (14, 0, 0) (expected (14, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-10-30T09:01:33.291Z  HOLD                HOLD-20261030-9ec8c7bcaf and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261030-fb0a297ad5 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 40.1 s after expiresAt 2026-10-30T08:59:47.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved) (100, 0, 0) -> (99, 0, 1): the 3 held units went back (held 0, stock + reserved 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-10-30T08:59:17.175Z  ACTIVE              HOLD-20261030-fb0a297ad5: 3 x DESK-MAT held for 30 s
2026-10-30T08:59:47.000Z  expiresAt           the schedule's at() time
2026-10-30T09:00:27.107Z  EXPIRED             by the schedule, 40.1 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261030-edc071d7df (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved + sold + writtenOff - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261030-d3cfbf91`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-d3cfbf91`

Checks:
- PASS: POST /holds -> 201 HOLD-20261030-c89a8b49ed
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261030-c89a8b49ed'
- PASS: hold CONSUMED by ORD-20261030-d3cfbf91 (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (98, 0, 2) -> (97, 0, 3) (stock -1 once, at hold time; held -> reserved)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I4 intent PI-ORD-20261030-d3cfbf91: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:01:36.831Z  PENDING             Order received via API
2026-10-30T09:01:37.350Z  PROCESSING          Saga workflow started
2026-10-30T09:01:37.488Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261030-c89a8b49ed
2026-10-30T09:01:37.726Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261030-d3cfbf91
2026-10-30T09:01:42.878Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-0a9798a3682f (confirmed by webhook)
2026-10-30T09:01:42.923Z  COMPLETED           Order fulfilled - payment PAY-0a9798a3682f captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261030-509e56c1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261030-509e56c1`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261030-6bab24508d
- PASS: hold HOLD-20261030-6bab24508d EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261030-6bab24508d had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (14, 0, 0) -> (13, 0, 1) (a normal fresh reservation)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I4 intent PI-ORD-20261030-509e56c1: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-30T09:03:38.527Z  PENDING             Order received via API
2026-10-30T09:03:38.891Z  PROCESSING          Saga workflow started
2026-10-30T09:03:39.212Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261030-6bab24508d had ended, so reserved afresh)
2026-10-30T09:03:39.445Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261030-509e56c1
2026-10-30T09:03:43.845Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-df286102e676 (confirmed by webhook)
2026-10-30T09:03:43.991Z  COMPLETED           Order fulfilled - payment PAY-df286102e676 captured
```
