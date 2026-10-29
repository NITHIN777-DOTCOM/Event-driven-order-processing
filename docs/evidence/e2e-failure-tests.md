# End-to-end tests: every saga path, with DemoPay money invariants (I1-I4)

Run: 2026-10-29 10:32:55 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 212s

**Result: 19/19 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I4) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261029-7e755bfa` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-7e755bfa) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261029-0f08dad5` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-0f08dad5) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261029-01e415e1` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-01e415e1) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261029-a97e3f9b` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a97e3f9b) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261029-91f2ac59` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-91f2ac59) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261029-4ed0dd64` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-4ed0dd64) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261029-7086bb49` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261029-db3dbb07` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-db3dbb07) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261029-c3ecb63b` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c3ecb63b) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261029-c3ecb63b` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c3ecb63b) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261029-ab7f62b4` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-ab7f62b4) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261029-94885029` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-94885029) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261029-183e06ba` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-183e06ba) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261029-05f213e9` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-05f213e9) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261029-c26394e5` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c26394e5) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261029-ffc1f856` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-ffc1f856) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261029-7e755bfa`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-7e755bfa`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_PENDING -> PAYMENT_CAPTURED -> COMPLETED
- PASS: MECH-KEYBOARD stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹3499: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹3499
- PASS: I4 intent PI-ORD-20261029-7e755bfa: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:29:26.827Z  PENDING             Order received via API
2026-10-29T10:29:27.132Z  PROCESSING          Saga workflow started
2026-10-29T10:29:27.267Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:29:27.428Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261029-7e755bfa
2026-10-29T10:29:32.786Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-51745c88911f (confirmed by webhook)
2026-10-29T10:29:32.947Z  COMPLETED           Order fulfilled - payment PAY-51745c88911f captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261029-0f08dad5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-0f08dad5`

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
- PASS: I4 intent PI-ORD-20261029-0f08dad5: FAILED (expected FAILED)

statusHistory:
```
2026-10-29T10:29:34.830Z  PENDING             Order received via API
2026-10-29T10:29:34.972Z  PROCESSING          Saga workflow started
2026-10-29T10:29:35.097Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:29:35.248Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261029-0f08dad5
2026-10-29T10:29:38.349Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-10-29T10:29:38.969Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T10:29:39.021Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261029-01e415e1`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-01e415e1`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹26990: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹26990
- PASS: I4 intent PI-ORD-20261029-01e415e1: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:29:40.106Z  PENDING             Order received via API
2026-10-29T10:29:40.463Z  PROCESSING          Saga workflow started
2026-10-29T10:29:40.591Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:29:40.723Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-10-29T10:29:42.883Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-10-29T10:29:47.049Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261029-01e415e1
2026-10-29T10:29:52.213Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-ad6e155abdc1 (confirmed by webhook)
2026-10-29T10:29:52.265Z  COMPLETED           Order fulfilled - payment PAY-ad6e155abdc1 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261029-a97e3f9b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a97e3f9b`

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
- PASS: I4 intent PI-ORD-20261029-a97e3f9b: none (payment never requested) (expected none)

statusHistory:
```
2026-10-29T10:29:53.951Z  PENDING             Order received via API
2026-10-29T10:29:54.050Z  PROCESSING          Saga workflow started
2026-10-29T10:29:54.155Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-29T10:29:54.193Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261029-91f2ac59`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-91f2ac59`

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
- PASS: I4 intent PI-ORD-20261029-91f2ac59: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:29:56.990Z  PENDING             Order received via API
2026-10-29T10:29:57.334Z  PROCESSING          Saga workflow started
2026-10-29T10:29:57.440Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:29:57.569Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261029-91f2ac59
2026-10-29T10:30:00.747Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-e891e0ed9e8c (confirmed by webhook)
2026-10-29T10:30:00.793Z  COMPLETED           Order fulfilled - payment PAY-e891e0ed9e8c captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261029-4ed0dd64`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-4ed0dd64`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹799: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I4 intent PI-ORD-20261029-4ed0dd64: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:30:07.587Z  PENDING             Order received via API
2026-10-29T10:30:08.050Z  PROCESSING          Saga workflow started
2026-10-29T10:30:08.169Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:30:08.307Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261029-4ed0dd64
2026-10-29T10:30:11.449Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-2eeaf7672372 (confirmed by webhook)
2026-10-29T10:30:11.494Z  COMPLETED           Order fulfilled - payment PAY-2eeaf7672372 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261029-7086bb49`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 204s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261029-7086bb49: none (payment never requested) (expected none)

statusHistory:
```
2026-10-29T10:29:25.407Z  PENDING             Order received via API
2026-10-29T10:29:25.737Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-29T10:30:25.651Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-29T10:31:25.645Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261029-db3dbb07`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-db3dbb07`

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
- PASS: I4 intent PI-ORD-20261029-db3dbb07: FAILED (expected FAILED)

statusHistory:
```
2026-10-29T10:30:30.545Z  PENDING             Order received via API
2026-10-29T10:30:30.917Z  PROCESSING          Saga workflow started
2026-10-29T10:30:31.050Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:30:31.170Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261029-db3dbb07
2026-10-29T10:30:36.323Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-29T10:30:36.572Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T10:30:36.610Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261029-c3ecb63b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c3ecb63b`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹2299: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I4 intent PI-ORD-20261029-c3ecb63b: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:30:38.481Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-29T10:30:38.661Z  PROCESSING          Saga workflow started
2026-10-29T10:30:38.780Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:30:38.904Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261029-c3ecb63b
2026-10-29T10:30:44.065Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-41013eeadfa4 (confirmed by webhook)
2026-10-29T10:30:44.117Z  COMPLETED           Order fulfilled - payment PAY-41013eeadfa4 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261029-c3ecb63b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c3ecb63b`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-29T10:30:38.481Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-29T10:30:38.661Z  PROCESSING          Saga workflow started
2026-10-29T10:30:38.780Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:30:38.904Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261029-c3ecb63b
2026-10-29T10:30:44.065Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-41013eeadfa4 (confirmed by webhook)
2026-10-29T10:30:44.117Z  COMPLETED           Order fulfilled - payment PAY-41013eeadfa4 captured
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

orderId: `ORD-20261029-ab7f62b4`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-ab7f62b4`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (14 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-29T10:30:53.505Z  PENDING             Order received via API
2026-10-29T10:30:53.632Z  PROCESSING          Saga workflow started
2026-10-29T10:30:53.740Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:30:53.884Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261029-ab7f62b4
2026-10-29T10:30:57.045Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-3b25baa479f3 (confirmed by webhook)
2026-10-29T10:30:57.090Z  COMPLETED           Order fulfilled - payment PAY-3b25baa479f3 captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 19 -> 19 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261029-94885029`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-94885029`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261029-58abca4c, B ORD-20261029-94885029
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261029-58abca4c COMPLETED
- PASS: ORD-20261029-94885029 COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I4 intent PI-ORD-20261029-94885029: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:31:01.790Z  PENDING             Order received via API
2026-10-29T10:31:02.187Z  PROCESSING          Saga workflow started
2026-10-29T10:31:02.376Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:31:02.509Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261029-94885029
2026-10-29T10:31:04.667Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-27c878f1f2c0 (confirmed by webhook)
2026-10-29T10:31:04.709Z  COMPLETED           Order fulfilled - payment PAY-27c878f1f2c0 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261029-e2e1e811)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261029-183e06ba`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-183e06ba`

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
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261029-183e06ba: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-10-29T10:29:26.147Z  PENDING             Order received via API
2026-10-29T10:29:26.659Z  PROCESSING          Saga workflow started
2026-10-29T10:29:26.950Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:29:27.185Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261029-183e06ba
2026-10-29T10:31:27.366Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T10:31:27.403Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261029-05f213e9`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-05f213e9`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261029-05f213e9 REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261029-05f213e9: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-29T10:29:26.406Z  PENDING             Order received via API
2026-10-29T10:29:27.580Z  PROCESSING          Saga workflow started
2026-10-29T10:29:27.823Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:29:27.983Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261029-05f213e9
2026-10-29T10:31:28.195Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T10:31:28.238Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-10-29T10:31:59.251Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-6d52164f8a1c, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261029-c26394e5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c26394e5`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: exactly one PAYMENT_CAPTURED in statusHistory
- PASS: webhook log lines with result 'duplicate' for this intent: 1 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹6499: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I4 intent PI-ORD-20261029-c26394e5: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:31:09.245Z  PENDING             Order received via API
2026-10-29T10:31:09.635Z  PROCESSING          Saga workflow started
2026-10-29T10:31:09.763Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:31:09.883Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261029-c26394e5
2026-10-29T10:31:14.043Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-497b2116b601 (confirmed by webhook)
2026-10-29T10:31:14.090Z  COMPLETED           Order fulfilled - payment PAY-497b2116b601 captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261029-ffc1f856`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-ffc1f856`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: 'webhook_signature_rejected' log lines since this order: 1 (expected >= 1)
- PASS: DemoPay logged the 401 for its forged callback, then sent the genuine one
- PASS: CloudWatch OrderSaga/WebhookSignatureFailures during this run: 6 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I4 intent PI-ORD-20261029-ffc1f856: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T10:31:22.785Z  PENDING             Order received via API
2026-10-29T10:31:23.147Z  PROCESSING          Saga workflow started
2026-10-29T10:31:23.283Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T10:31:23.408Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261029-ffc1f856
2026-10-29T10:31:27.592Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-41fe3a7bd288 (confirmed by webhook)
2026-10-29T10:31:27.641Z  COMPLETED           Order fulfilled - payment PAY-41fe3a7bd288 captured
```
