# End-to-end tests: every saga path, including DemoPay wallet checks

Run: 2026-10-22 13:21:40 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 200s

**Result: 8/8 scenarios passed.**

| # | Scenario | Result | orderId | Execution (console) |
|---|----------|--------|---------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261022-fc46203c` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-fc46203c) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261022-817ed6d7` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-817ed6d7) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261022-28982171` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-28982171) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261022-daed8016` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-daed8016) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261022-e80b7218` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-e80b7218) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261022-34002b29` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-34002b29) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261022-e99e5d9d` | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261022-0e05500e` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-0e05500e) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261022-fc46203c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-fc46203c`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_CAPTURED -> COMPLETED
- PASS: MECH-KEYBOARD stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)

statusHistory:
```
2026-10-22T13:18:22.283Z  PENDING             Order received via API
2026-10-22T13:18:22.428Z  PROCESSING          Saga workflow started
2026-10-22T13:18:23.348Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T13:18:24.174Z  PAYMENT_CAPTURED    ₹3,499 debited from DemoPay · balance ₹9,96,501 (attempt 1)
2026-10-22T13:18:24.222Z  COMPLETED           Order fulfilled - payment PAY-47c19111d18c captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261022-817ed6d7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-817ed6d7`

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
2026-10-22T13:18:26.325Z  PENDING             Order received via API
2026-10-22T13:18:26.385Z  PROCESSING          Saga workflow started
2026-10-22T13:18:26.514Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T13:18:26.654Z  PAYMENT_DECLINED    Attempt 1: Card declined by issuer (simulated)
2026-10-22T13:18:28.332Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-22T13:18:28.380Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261022-28982171`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-28982171`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)

statusHistory:
```
2026-10-22T13:18:29.364Z  PENDING             Order received via API
2026-10-22T13:18:29.429Z  PROCESSING          Saga workflow started
2026-10-22T13:18:29.580Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T13:18:29.695Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway timeout on attempt 1 (simulated) - retrying
2026-10-22T13:18:31.854Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway timeout on attempt 2 (simulated) - retrying
2026-10-22T13:18:36.015Z  PAYMENT_CAPTURED    ₹26,990 debited from DemoPay · balance ₹9,69,511 (attempt 3)
2026-10-22T13:18:36.061Z  COMPLETED           Order fulfilled - payment PAY-c522f6c45c64 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261022-daed8016`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-daed8016`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)
- PASS: DEBIT ledger entries: 0 (expected 0)

statusHistory:
```
2026-10-22T13:18:38.684Z  PENDING             Order received via API
2026-10-22T13:18:38.751Z  PROCESSING          Saga workflow started
2026-10-22T13:18:38.887Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-22T13:18:38.928Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261022-e80b7218`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-e80b7218`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: 4K-MONITOR stock 100 -> 99 (expected -1, not -3)
- PASS: DEBIT ledger entries: 1 (expected 1, not 3)

statusHistory:
```
2026-10-22T13:18:41.624Z  PENDING             Order received via API
2026-10-22T13:18:41.688Z  PROCESSING          Saga workflow started
2026-10-22T13:18:41.828Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T13:18:41.955Z  PAYMENT_CAPTURED    ₹24,999 debited from DemoPay · balance ₹9,44,512 (attempt 1)
2026-10-22T13:18:41.991Z  COMPLETED           Order fulfilled - payment PAY-9bcde9db5516 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261022-34002b29`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-34002b29`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)

statusHistory:
```
2026-10-22T13:18:42.744Z  PENDING             Order received via API
2026-10-22T13:18:42.826Z  PROCESSING          Saga workflow started
2026-10-22T13:18:42.942Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T13:18:43.058Z  PAYMENT_CAPTURED    ₹799 debited from DemoPay · balance ₹9,43,713 (attempt 1)
2026-10-22T13:18:43.093Z  COMPLETED           Order fulfilled - payment PAY-31f82ce9bce6 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261022-e99e5d9d`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 197s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)

statusHistory:
```
2026-10-22T13:18:21.564Z  PENDING             Order received via API
2026-10-22T13:18:22.381Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-22T13:19:21.724Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-22T13:20:21.741Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261022-0e05500e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-0e05500e`

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
2026-10-22T13:18:59.744Z  PENDING             Order received via API
2026-10-22T13:18:59.819Z  PROCESSING          Saga workflow started
2026-10-22T13:18:59.944Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T13:19:00.137Z  PAYMENT_DECLINED    Attempt 1: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-22T13:19:00.314Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-22T13:19:00.347Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```
