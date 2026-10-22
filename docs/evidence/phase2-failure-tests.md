# Phase 2 evidence: failure-path end-to-end tests

Run: 2026-10-22 11:10:38 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 187s

**Result: 7/7 scenarios passed.**

| # | Scenario | Result | orderId | Execution (console) |
|---|----------|--------|---------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased | PASS | `ORD-20261022-8bce2d2e` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-8bce2d2e) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261022-d013dc28` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-d013dc28) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261022-b9e10dcc` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-b9e10dcc) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261022-5749cf06` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-5749cf06) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261022-11dc8028` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-11dc8028) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261022-4554ceea` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-4554ceea) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261022-7b1a4028` | none started (by design) |

## a) simulate=none -> COMPLETED, stock decreased - PASS

orderId: `ORD-20261022-8bce2d2e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-8bce2d2e`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_CAPTURED -> COMPLETED
- PASS: MECH-KEYBOARD stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-22T11:07:32.482Z  PENDING             Order received via API
2026-10-22T11:07:32.550Z  PROCESSING          Saga workflow started
2026-10-22T11:07:32.758Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T11:07:32.880Z  PAYMENT_CAPTURED    Payment PAY-3d379f82641b captured: INR 3499.00 (attempt 1)
2026-10-22T11:07:32.918Z  COMPLETED           Order fulfilled - payment PAY-3d379f82641b captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261022-d013dc28`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-d013dc28`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'PaymentDeclined: Card declined by issuer (simulated)'
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> INVENTORY_RELEASED -> FAILED
- PASS: USBC-HUB (stock, reserved) (100, 0) -> (100, 0) (expected unchanged after release)
- PASS: execution FAILED (expected FAILED)
- PASS: execution error 'OrderFailed' (expected OrderFailed)
- PASS: ReleaseInventory ran
- PASS: last state ['OrderFailed'] (expected OrderFailed)

statusHistory:
```
2026-10-22T11:07:35.400Z  PENDING             Order received via API
2026-10-22T11:07:35.470Z  PROCESSING          Saga workflow started
2026-10-22T11:07:35.597Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T11:07:35.881Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-22T11:07:35.928Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261022-b9e10dcc`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-b9e10dcc`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 100 -> 99 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)

statusHistory:
```
2026-10-22T11:07:38.081Z  PENDING             Order received via API
2026-10-22T11:07:38.143Z  PROCESSING          Saga workflow started
2026-10-22T11:07:38.270Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T11:07:38.363Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway timeout on attempt 1 (simulated) - retrying
2026-10-22T11:07:40.500Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway timeout on attempt 2 (simulated) - retrying
2026-10-22T11:07:44.640Z  PAYMENT_CAPTURED    Payment PAY-3d1105d6e8ab captured: INR 26990.00 (attempt 3)
2026-10-22T11:07:44.662Z  COMPLETED           Order fulfilled - payment PAY-3d1105d6e8ab captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261022-5749cf06`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-5749cf06`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status FAILED (expected FAILED)
- PASS: failureReason 'OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)'
- PASS: 4K-MONITOR (stock, reserved) (100, 0) -> (100, 0) (expected unchanged)
- PASS: execution FAILED (expected FAILED)
- PASS: ReleaseInventory NOT run (states: ReserveInventory -> DescribeFailure -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed)

statusHistory:
```
2026-10-22T11:07:47.080Z  PENDING             Order received via API
2026-10-22T11:07:47.149Z  PROCESSING          Saga workflow started
2026-10-22T11:07:47.272Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261022-11dc8028`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-11dc8028`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: 4K-MONITOR stock 100 -> 99 (expected -1, not -3)

statusHistory:
```
2026-10-22T11:07:49.680Z  PENDING             Order received via API
2026-10-22T11:07:49.748Z  PROCESSING          Saga workflow started
2026-10-22T11:07:49.864Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T11:07:49.980Z  PAYMENT_CAPTURED    Payment PAY-4fec30c91f3f captured: INR 24999.00 (attempt 1)
2026-10-22T11:07:50.004Z  COMPLETED           Order fulfilled - payment PAY-4fec30c91f3f captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261022-4554ceea`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-4554ceea`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)

statusHistory:
```
2026-10-22T11:07:50.420Z  PENDING             Order received via API
2026-10-22T11:07:50.487Z  PROCESSING          Saga workflow started
2026-10-22T11:07:50.609Z  RESERVED            Reserved stock for 1 product(s)
2026-10-22T11:07:50.740Z  PAYMENT_CAPTURED    Payment PAY-acb31f1590a6 captured: INR 799.00 (attempt 1)
2026-10-22T11:07:50.764Z  COMPLETED           Order fulfilled - payment PAY-acb31f1590a6 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261022-7b1a4028`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 185s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)

statusHistory:
```
2026-10-22T11:07:31.921Z  PENDING             Order received via API
```
