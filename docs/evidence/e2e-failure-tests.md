# End-to-end tests: every saga path, including DemoPay wallet checks

Run: 2026-10-28 16:16:00 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 194s

**Result: 10/10 scenarios passed.**

| # | Scenario | Result | orderId | Execution (console) |
|---|----------|--------|---------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261028-5ec707d8` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-5ec707d8) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261028-9034d4d7` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-9034d4d7) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261028-8a30a839` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-8a30a839) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261028-8ae80c14` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-8ae80c14) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261028-69b825e6` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-69b825e6) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261028-0e20bb65` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-0e20bb65) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261028-b859a61f` | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261028-8cf69754` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-8cf69754) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261028-74eb8439` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-74eb8439) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261028-74eb8439` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-74eb8439) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261028-5ec707d8`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-5ec707d8`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_CAPTURED -> COMPLETED
- PASS: MECH-KEYBOARD stock 95 -> 94 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)

statusHistory:
```
2026-10-28T16:12:45.725Z  PENDING             Order received via API
2026-10-28T16:12:46.108Z  PROCESSING          Saga workflow started
2026-10-28T16:12:46.220Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:12:46.380Z  PAYMENT_CAPTURED    ₹3,499 debited from DemoPay · balance ₹9,96,501 (attempt 1)
2026-10-28T16:12:46.420Z  COMPLETED           Order fulfilled - payment PAY-46309e3d0739 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261028-9034d4d7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-9034d4d7`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Card declined by issuer (simulated)'
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_DECLINED -> INVENTORY_RELEASED -> FAILED
- PASS: USBC-HUB (stock, reserved) (100, 0) -> (100, 0) (expected unchanged after release)
- PASS: execution FAILED (expected FAILED)
- PASS: execution error 'OrderFailed' (expected OrderFailed)
- PASS: ReleaseInventory ran
- PASS: last state ['OrderFailed'] (expected OrderFailed)
- PASS: RefundPayment ran (a no-op: nothing was charged)
- PASS: DEBIT ledger entries: 0 (expected 0, card declined before debit)

statusHistory:
```
2026-10-28T16:12:49.329Z  PENDING             Order received via API
2026-10-28T16:12:49.601Z  PROCESSING          Saga workflow started
2026-10-28T16:12:49.698Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:12:49.820Z  PAYMENT_DECLINED    Attempt 1: Card declined by issuer (simulated)
2026-10-28T16:12:51.557Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-28T16:12:51.650Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261028-8a30a839`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-8a30a839`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 91 -> 90 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)

statusHistory:
```
2026-10-28T16:12:54.585Z  PENDING             Order received via API
2026-10-28T16:12:54.877Z  PROCESSING          Saga workflow started
2026-10-28T16:12:55.000Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:12:55.140Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway timeout on attempt 1 (simulated) - retrying
2026-10-28T16:12:57.267Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway timeout on attempt 2 (simulated) - retrying
2026-10-28T16:13:01.460Z  PAYMENT_CAPTURED    ₹26,990 debited from DemoPay · balance ₹9,69,511 (attempt 3)
2026-10-28T16:13:01.498Z  COMPLETED           Order fulfilled - payment PAY-9f2182c9b6e2 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261028-8ae80c14`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-8ae80c14`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (98, 2) -> (98, 2) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)

statusHistory:
```
2026-10-28T16:13:04.105Z  PENDING             Order received via API
2026-10-28T16:13:04.612Z  PROCESSING          Saga workflow started
2026-10-28T16:13:04.719Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-28T16:13:04.768Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261028-69b825e6`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-69b825e6`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1, not 3)
- PASS: 4K-MONITOR stock 98 -> 97 (expected -1, not -3)
- PASS: DEBIT ledger entries: 1 (expected 1, not 3)

statusHistory:
```
2026-10-28T16:13:07.169Z  PENDING             Order received via API
2026-10-28T16:13:07.356Z  PROCESSING          Saga workflow started
2026-10-28T16:13:07.445Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:13:07.560Z  PAYMENT_CAPTURED    ₹24,999 debited from DemoPay · balance ₹9,44,512 (attempt 1)
2026-10-28T16:13:07.598Z  COMPLETED           Order fulfilled - payment PAY-b92ff4606547 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261028-0e20bb65`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-0e20bb65`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)

statusHistory:
```
2026-10-28T16:13:10.225Z  PENDING             Order received via API
2026-10-28T16:13:10.353Z  PROCESSING          Saga workflow started
2026-10-28T16:13:10.452Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:13:10.580Z  PAYMENT_CAPTURED    ₹799 debited from DemoPay · balance ₹9,43,713 (attempt 1)
2026-10-28T16:13:10.622Z  COMPLETED           Order fulfilled - payment PAY-9232c40d4ab5 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261028-b859a61f`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 191s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)

statusHistory:
```
2026-10-28T16:12:45.007Z  PENDING             Order received via API
2026-10-28T16:12:45.351Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-28T16:13:45.351Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-28T16:14:45.371Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261028-8cf69754`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-8cf69754`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed'
- PASS: USB-MIC (stock, reserved) (18, 0) -> (18, 0) (expected unchanged)
- PASS: DemoPay balance 1000 (expected 1000, untouched)
- PASS: no DEBIT ledger entry
- PASS: ReleaseInventory ran (compensation)

statusHistory:
```
2026-10-28T16:13:27.744Z  PENDING             Order received via API
2026-10-28T16:13:28.125Z  PROCESSING          Saga workflow started
2026-10-28T16:13:28.255Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:13:28.380Z  PAYMENT_DECLINED    Attempt 1: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-28T16:13:28.600Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-28T16:13:28.642Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261028-74eb8439`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-74eb8439`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)

statusHistory:
```
2026-10-28T16:13:32.349Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-28T16:13:31.157Z  PROCESSING          Saga workflow started
2026-10-28T16:13:31.272Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:13:31.420Z  PAYMENT_CAPTURED    ₹2,299 debited from DemoPay · balance ₹9,41,414 (attempt 1)
2026-10-28T16:13:31.456Z  COMPLETED           Order fulfilled - payment PAY-7c4bcabe5b2e captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261028-74eb8439`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-74eb8439`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-28T16:13:32.349Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-28T16:13:31.157Z  PROCESSING          Saga workflow started
2026-10-28T16:13:31.272Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T16:13:31.420Z  PAYMENT_CAPTURED    ₹2,299 debited from DemoPay · balance ₹9,41,414 (attempt 1)
2026-10-28T16:13:31.456Z  COMPLETED           Order fulfilled - payment PAY-7c4bcabe5b2e captured
```
