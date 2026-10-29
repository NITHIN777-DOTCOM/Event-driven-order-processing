# End-to-end tests: every saga path, with DemoPay money invariants (I1-I4)

Run: 2026-10-29 11:46:18 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 251s

**Result: 26/26 scenarios passed.**

| # | Scenario | Result | orderId | Intent · ledger (I1-I4) | Execution (console) |
|---|----------|--------|---------|--------------------------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261029-405e2e1c` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹3499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-405e2e1c) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261029-2c819857` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-2c819857) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261029-13828837` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹26990 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-13828837) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261029-39c23806` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-39c23806) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261029-7a41de99` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹24999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-7a41de99) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261029-fcbda747` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-fcbda747) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261029-59f60843` | - · ledger 0 DEBIT / 0 CREDIT, net ₹0 | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261029-e92732df` | FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e92732df) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261029-392ed320` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹2299 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-392ed320) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261029-392ed320` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-392ed320) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | - | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261029-c49750b5` | - | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c49750b5) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | - | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261029-9dcbb335` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-9dcbb335) |
| o | payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op | PASS | `None` | - | none started (by design) |
| p | payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged | PASS | `ORD-20261029-46794fa6` | TIMED_OUT · ledger 0 DEBIT / 0 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-46794fa6) |
| q | payment_late -> charged after the timeout, refunded automatically, order stays FAILED | PASS | `ORD-20261029-bb19bc8a` | REFUNDED · ledger 1 DEBIT / 1 CREDIT, net ₹0 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-bb19bc8a) |
| r | webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once | PASS | `ORD-20261029-e879bbd6` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹6499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e879bbd6) |
| s | webhook_bad_signature -> forged callback rejected (401), genuine one completes the order | PASS | `ORD-20261029-8610ce48` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹4999 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-8610ce48) |
| t | checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases | PASS | `None` | - | none started (by design) |
| u | 30 s hold expired by its EventBridge Scheduler schedule, stock restored | PASS | `None` | - | none started (by design) |
| v | two users race for the last unit -> exactly one hold (201), the other 409 | PASS | `None` | - | none started (by design) |
| w | hold ownership: B can't release or see A's hold (404) | PASS | `None` | - | none started (by design) |
| x | I5 stock conservation for every product: seeded = stock + held + reserved; held = ACTIVE holds | PASS | `None` | - | none started (by design) |
| y | order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold | PASS | `ORD-20261029-e5331e73` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹1799 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e5331e73) |
| z | order after its 30 s hold expired -> reserved afresh (the hold isn't reused) | PASS | `ORD-20261029-1599e6c9` | SUCCEEDED · ledger 1 DEBIT / 0 CREDIT, net ₹5499 | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-1599e6c9) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261029-405e2e1c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-405e2e1c`

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
- PASS: I4 intent PI-ORD-20261029-405e2e1c: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:42:14.021Z  PENDING             Order received via API
2026-10-29T11:42:14.235Z  PROCESSING          Saga workflow started
2026-10-29T11:42:14.368Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:14.572Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261029-405e2e1c
2026-10-29T11:42:16.716Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-8a6c728de6e7 (confirmed by webhook)
2026-10-29T11:42:16.762Z  COMPLETED           Order fulfilled - payment PAY-8a6c728de6e7 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261029-2c819857`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-2c819857`

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
- PASS: I4 intent PI-ORD-20261029-2c819857: FAILED (expected FAILED)

statusHistory:
```
2026-10-29T11:42:20.399Z  PENDING             Order received via API
2026-10-29T11:42:20.787Z  PROCESSING          Saga workflow started
2026-10-29T11:42:20.928Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:21.067Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,998 · intent PI-ORD-20261029-2c819857
2026-10-29T11:42:24.159Z  PAYMENT_DECLINED    Card declined by issuer (simulated)
2026-10-29T11:42:25.898Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T11:42:25.946Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261029-13828837`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-13828837`

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
- PASS: I4 intent PI-ORD-20261029-13828837: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:42:28.239Z  PENDING             Order received via API
2026-10-29T11:42:28.857Z  PROCESSING          Saga workflow started
2026-10-29T11:42:28.987Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:29.110Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway busy on attempt 1 (simulated) - retrying
2026-10-29T11:42:31.286Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway busy on attempt 2 (simulated) - retrying
2026-10-29T11:42:35.470Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹26,990 · intent PI-ORD-20261029-13828837
2026-10-29T11:42:38.636Z  PAYMENT_CAPTURED    ₹26,990 captured by DemoPay · PAY-1c2014fb4fb8 (confirmed by webhook)
2026-10-29T11:42:38.692Z  COMPLETED           Order fulfilled - payment PAY-1c2014fb4fb8 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261029-39c23806`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-39c23806`

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
- PASS: I4 intent PI-ORD-20261029-39c23806: none (payment never requested) (expected none)

statusHistory:
```
2026-10-29T11:42:40.302Z  PENDING             Order received via API
2026-10-29T11:42:40.817Z  PROCESSING          Saga workflow started
2026-10-29T11:42:40.922Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-29T11:42:40.960Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261029-7a41de99`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-7a41de99`

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
- PASS: I4 intent PI-ORD-20261029-7a41de99: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:42:43.463Z  PENDING             Order received via API
2026-10-29T11:42:43.814Z  PROCESSING          Saga workflow started
2026-10-29T11:42:43.943Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:44.091Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹24,999 · intent PI-ORD-20261029-7a41de99
2026-10-29T11:42:48.220Z  PAYMENT_CAPTURED    ₹24,999 captured by DemoPay · PAY-b517dffd7592 (confirmed by webhook)
2026-10-29T11:42:48.265Z  COMPLETED           Order fulfilled - payment PAY-b517dffd7592 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261029-fcbda747`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-fcbda747`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹799: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹799
- PASS: I4 intent PI-ORD-20261029-fcbda747: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:42:55.319Z  PENDING             Order received via API
2026-10-29T11:42:55.579Z  PROCESSING          Saga workflow started
2026-10-29T11:42:55.693Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:55.806Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹799 · intent PI-ORD-20261029-fcbda747
2026-10-29T11:42:59.942Z  PAYMENT_CAPTURED    ₹799 captured by DemoPay · PAY-90a22559398c (confirmed by webhook)
2026-10-29T11:43:00.015Z  COMPLETED           Order fulfilled - payment PAY-90a22559398c captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261029-59f60843`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 234s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)
- PASS: I2 PENDING -> net charge 0: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 0 DEBIT / 0 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261029-59f60843: none (payment never requested) (expected none)

statusHistory:
```
2026-10-29T11:42:09.827Z  PENDING             Order received via API
2026-10-29T11:42:10.252Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-29T11:43:10.245Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-29T11:44:10.252Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261029-e92732df`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e92732df`

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
- PASS: I4 intent PI-ORD-20261029-e92732df: FAILED (expected FAILED)

statusHistory:
```
2026-10-29T11:43:17.883Z  PENDING             Order received via API
2026-10-29T11:43:18.356Z  PROCESSING          Saga workflow started
2026-10-29T11:43:18.464Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:43:18.609Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,999 · intent PI-ORD-20261029-e92732df
2026-10-29T11:43:23.783Z  PAYMENT_DECLINED    Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-29T11:43:24.015Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T11:43:24.076Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261029-392ed320`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-392ed320`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹2299: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹2299
- PASS: I4 intent PI-ORD-20261029-392ed320: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:43:25.977Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-29T11:43:25.854Z  PROCESSING          Saga workflow started
2026-10-29T11:43:25.978Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:43:26.104Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261029-392ed320
2026-10-29T11:43:31.243Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-9a44356d7571 (confirmed by webhook)
2026-10-29T11:43:31.286Z  COMPLETED           Order fulfilled - payment PAY-9a44356d7571 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261029-392ed320`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-392ed320`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-29T11:43:25.977Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-29T11:43:25.854Z  PROCESSING          Saga workflow started
2026-10-29T11:43:25.978Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:43:26.104Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹2,299 · intent PI-ORD-20261029-392ed320
2026-10-29T11:43:31.243Z  PAYMENT_CAPTURED    ₹2,299 captured by DemoPay · PAY-9a44356d7571 (confirmed by webhook)
2026-10-29T11:43:31.286Z  COMPLETED           Order fulfilled - payment PAY-9a44356d7571 captured
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

orderId: `ORD-20261029-c49750b5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c49750b5`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (50 orders) doesn't contain B's order
- PASS: B's GET /orders (20 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-29T11:43:42.358Z  PENDING             Order received via API
2026-10-29T11:43:42.622Z  PROCESSING          Saga workflow started
2026-10-29T11:43:42.959Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:43:43.091Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,299 · intent PI-ORD-20261029-c49750b5
2026-10-29T11:43:48.256Z  PAYMENT_CAPTURED    ₹1,299 captured by DemoPay · PAY-30de032b95bb (confirmed by webhook)
2026-10-29T11:43:48.306Z  COMPLETED           Order fulfilled - payment PAY-30de032b95bb captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 20 -> 20 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261029-9dcbb335`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-9dcbb335`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261029-7fa0e276, B ORD-20261029-9dcbb335
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261029-7fa0e276 COMPLETED
- PASS: ORD-20261029-9dcbb335 COMPLETED
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I4 intent PI-ORD-20261029-9dcbb335: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:43:53.438Z  PENDING             Order received via API
2026-10-29T11:43:53.700Z  PROCESSING          Saga workflow started
2026-10-29T11:43:53.815Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:43:53.964Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261029-9dcbb335
2026-10-29T11:43:59.096Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-ee53c3ee6fe9 (confirmed by webhook)
2026-10-29T11:43:59.144Z  COMPLETED           Order fulfilled - payment PAY-ee53c3ee6fe9 captured
```

## o) payment webhook: unsigned/forged/stale/future -> 401; valid signature, unknown intent -> 404 no-op - PASS

orderId: `None`

Checks:
- PASS: POST /webhooks/payment no signature headers -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment signed with a wrong secret -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min old (replay) -> 401 (expected 401: invalid or missing signature)
- PASS: POST /webhooks/payment timestamp 10 min in the future -> 401 (expected 401: invalid or missing signature)
- PASS: valid signature, unknown intent -> 404 (expected 404: unknown payment intent PI-ORD-20261029-e2ed60a2)
- PASS: no payment intent was created
- PASS: a user's JWT is no substitute for the signature -> 401 (expected 401)

## p) payment_timeout -> no callback in 120 s, compensated, FAILED, nothing charged - PASS

orderId: `ORD-20261029-46794fa6`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-46794fa6`

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
- PASS: I4 intent PI-ORD-20261029-46794fa6: TIMED_OUT (expected TIMED_OUT)

statusHistory:
```
2026-10-29T11:42:10.601Z  PENDING             Order received via API
2026-10-29T11:42:11.002Z  PROCESSING          Saga workflow started
2026-10-29T11:42:11.151Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:11.313Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹32,999 · intent PI-ORD-20261029-46794fa6
2026-10-29T11:44:11.591Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T11:44:11.631Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
```

## q) payment_late -> charged after the timeout, refunded automatically, order stays FAILED - PASS

orderId: `ORD-20261029-bb19bc8a`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-bb19bc8a`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED: timed out at 120 s)
- PASS: failureReason 'PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s'
- PASS: PODCAST-MIC (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: intent PI-ORD-20261029-bb19bc8a REFUNDED (expected REFUNDED)
- PASS: order still FAILED after the late callback (it is never revived)
- PASS: exactly one PAYMENT_REFUNDED in statusHistory
- PASS: I2 FAILED -> net charge 0: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 1 CREDIT, net ₹0
- PASS: I4 intent PI-ORD-20261029-bb19bc8a: REFUNDED (expected REFUNDED)

statusHistory:
```
2026-10-29T11:42:10.879Z  PENDING             Order received via API
2026-10-29T11:42:11.263Z  PROCESSING          Saga workflow started
2026-10-29T11:42:11.391Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:42:11.526Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261029-bb19bc8a
2026-10-29T11:44:11.746Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T11:44:11.786Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
2026-10-29T11:44:42.556Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-f99c422cdfe0, the order had already failed)
```

## r) webhook_duplicate -> callback delivered twice, COMPLETED, wallet debited once - PASS

orderId: `ORD-20261029-e879bbd6`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e879bbd6`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: exactly one PAYMENT_CAPTURED in statusHistory
- PASS: webhook log lines with result 'duplicate' for this intent: 1 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹6499: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹6499
- PASS: I4 intent PI-ORD-20261029-e879bbd6: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:44:01.222Z  PENDING             Order received via API
2026-10-29T11:44:01.401Z  PROCESSING          Saga workflow started
2026-10-29T11:44:01.515Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:44:01.624Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹6,499 · intent PI-ORD-20261029-e879bbd6
2026-10-29T11:44:03.760Z  PAYMENT_CAPTURED    ₹6,499 captured by DemoPay · PAY-f4c319deed9c (confirmed by webhook)
2026-10-29T11:44:03.798Z  COMPLETED           Order fulfilled - payment PAY-f4c319deed9c captured
```

## s) webhook_bad_signature -> forged callback rejected (401), genuine one completes the order - PASS

orderId: `ORD-20261029-8610ce48`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-8610ce48`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: 'webhook_signature_rejected' log lines since this order: 1 (expected >= 1)
- PASS: DemoPay logged the 401 for its forged callback, then sent the genuine one
- PASS: CloudWatch OrderSaga/WebhookSignatureFailures during this run: 6 (expected >= 1)
- PASS: I1 COMPLETED -> one DEBIT of ₹4999: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹4999
- PASS: I4 intent PI-ORD-20261029-8610ce48: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:44:13.138Z  PENDING             Order received via API
2026-10-29T11:44:13.413Z  PROCESSING          Saga workflow started
2026-10-29T11:44:13.517Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T11:44:13.648Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹4,999 · intent PI-ORD-20261029-8610ce48
2026-10-29T11:44:15.798Z  PAYMENT_CAPTURED    ₹4,999 captured by DemoPay · PAY-4d4c05c966be (confirmed by webhook)
2026-10-29T11:44:15.842Z  COMPLETED           Order fulfilled - payment PAY-4d4c05c966be captured
```

## t) checkout hold: stock -> held + expiry schedule; 2nd hold releases the 1st; 400/409; DELETE releases - PASS

orderId: `None`

Checks:
- PASS: POST /holds -> 201 ACTIVE (expected 201 ACTIVE)
- PASS: no durationSeconds -> 600 s, secondsLeft 598 (expected 600)
- PASS: COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) -> (12, 2, 0) (2 units stock -> held)
- PASS: one-time schedule HOLD-20261029-9ddf5a2162 exists in order-saga-holds
- PASS: GET /holds/current returns it
- PASS: 2nd POST /holds -> 201 (expected 201)
- PASS: 1st hold RELEASED (expected RELEASED: one ACTIVE hold per user)
- PASS: 1st hold's schedule deleted
- PASS: COMPACT-KEYBOARD now (13, 1, 0) (only the 2nd hold's 1 unit held)
- PASS: quantity 6 (cap 5) -> 400 (expected 400: items[0].quantity must be an integer from 1 to 5 (hold limit per product))
- PASS: durationSeconds 10 (min 30) -> 400 (expected 400)
- PASS: out of stock -> 409, productId WEBCAM-1080P (expected 409 WEBCAM-1080P)
- PASS: DELETE /holds/HOLD-20261029-bc0c27d751 -> 200 RELEASED (expected 200 RELEASED)
- PASS: COMPACT-KEYBOARD back to (14, 0, 0) (expected (14, 0, 0))
- PASS: no current hold, schedule deleted

statusHistory:
```
2026-10-29T11:44:31.041Z  HOLD                HOLD-20261029-bc0c27d751 and its predecessors
```

## u) 30 s hold expired by its EventBridge Scheduler schedule, stock restored - PASS

orderId: `None`

Checks:
- PASS: POST /holds (automation client, 30 s) -> 201
- PASS: hold HOLD-20261029-79cb7f26e9 EXPIRED (expected EXPIRED)
- PASS: expired by: schedule (expected the schedule, not a lazy read)
- PASS: released 20.1 s after expiresAt 2026-10-29T11:42:43.000Z (EventBridge Scheduler precision)
- PASS: DESK-MAT (stock, held, reserved) (100, 0, 0) -> (99, 0, 1): the 3 held units went back (held 0, stock + reserved 100)
- PASS: schedule deleted itself after firing (ActionAfterCompletion DELETE)

statusHistory:
```
2026-10-29T11:42:13.233Z  ACTIVE              HOLD-20261029-79cb7f26e9: 3 x DESK-MAT held for 30 s
2026-10-29T11:42:43.000Z  expiresAt           the schedule's at() time
2026-10-29T11:43:03.136Z  EXPIRED             by the schedule, 20.1 s after expiresAt
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
- PASS: B: DELETE /holds/HOLD-20261029-6385e5e2dd (A's) -> 404 (expected 404, same as a missing hold)
- PASS: B's GET /holds/current never shows A's hold
- PASS: A's hold is still ACTIVE
- PASS: A can release it

## x) I5 stock conservation for every product: seeded = stock + held + reserved; held = ACTIVE holds - PASS

orderId: `None`

Checks:
- PASS: I5 holds for all 16 products

## y) order with holdId -> ReserveInventory consumes the hold (held -> reserved, stock moved once); B can't use A's hold - PASS

orderId: `ORD-20261029-e5331e73`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e5331e73`

Checks:
- PASS: POST /holds -> 201 HOLD-20261029-c0177385c9
- PASS: B: POST /orders with A's holdId -> 400 (expected 400: holdId is not one of your checkout holds)
- PASS: A: POST /orders with holdId -> 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) from checkout hold HOLD-20261029-c0177385c9'
- PASS: hold CONSUMED by ORD-20261029-e5331e73 (expected CONSUMED by this order)
- PASS: LAPTOP-STAND (stock, held, reserved) (98, 0, 2) -> (97, 0, 3) (stock -1 once, at hold time; held -> reserved)
- PASS: expiry schedule deleted, no current hold
- PASS: I1 COMPLETED -> one DEBIT of ₹1799: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹1799
- PASS: I4 intent PI-ORD-20261029-e5331e73: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:44:35.238Z  PENDING             Order received via API
2026-10-29T11:44:35.741Z  PROCESSING          Saga workflow started
2026-10-29T11:44:35.986Z  RESERVED            Reserved stock for 1 product(s) from checkout hold HOLD-20261029-c0177385c9
2026-10-29T11:44:36.202Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹1,799 · intent PI-ORD-20261029-e5331e73
2026-10-29T11:44:38.335Z  PAYMENT_CAPTURED    ₹1,799 captured by DemoPay · PAY-288090e40722 (confirmed by webhook)
2026-10-29T11:44:38.405Z  COMPLETED           Order fulfilled - payment PAY-288090e40722 captured
```

## z) order after its 30 s hold expired -> reserved afresh (the hold isn't reused) - PASS

orderId: `ORD-20261029-1599e6c9`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-1599e6c9`

Checks:
- PASS: POST /holds (30 s) -> 201 HOLD-20261029-9f0f6c3fe2
- PASS: hold HOLD-20261029-9f0f6c3fe2 EXPIRED (expected EXPIRED)
- PASS: POST /orders with the expired holdId -> 202 (expected 202: the order still goes ahead)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: RESERVED detail: 'Reserved stock for 1 product(s) (checkout hold HOLD-20261029-9f0f6c3fe2 had ended, so reserved afresh)'
- PASS: COMPACT-KEYBOARD (14, 0, 0) -> (13, 0, 1) (a normal fresh reservation)
- PASS: the expired hold stays EXPIRED (never revived)
- PASS: I1 COMPLETED -> one DEBIT of ₹5499: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I3 no double charge / double refund: ledger 1 DEBIT / 0 CREDIT, net ₹5499
- PASS: I4 intent PI-ORD-20261029-1599e6c9: SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-29T11:46:09.257Z  PENDING             Order received via API
2026-10-29T11:46:09.523Z  PROCESSING          Saga workflow started
2026-10-29T11:46:09.827Z  RESERVED            Reserved stock for 1 product(s) (checkout hold HOLD-20261029-9f0f6c3fe2 had ended, so reserved afresh)
2026-10-29T11:46:10.059Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹5,499 · intent PI-ORD-20261029-1599e6c9
2026-10-29T11:46:12.407Z  PAYMENT_CAPTURED    ₹5,499 captured by DemoPay · PAY-f3a010f108de (confirmed by webhook)
2026-10-29T11:46:12.562Z  COMPLETED           Order fulfilled - payment PAY-f3a010f108de captured
```
