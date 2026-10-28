# End-to-end tests: every saga path, including DemoPay wallet checks

Run: 2026-10-28 17:45:40 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 226s

**Result: 14/14 scenarios passed.**

| # | Scenario | Result | orderId | Execution (console) |
|---|----------|--------|---------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261028-fd7f2ff3` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-fd7f2ff3) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261028-5b827a2b` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-5b827a2b) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261028-ea2f10d0` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-ea2f10d0) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261028-bf27518c` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-bf27518c) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261028-f5bd29d7` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-f5bd29d7) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261028-f20b357e` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-f20b357e) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261028-4d66d9c4` | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261028-a8fa4e9c` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-a8fa4e9c) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261028-d705754d` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-d705754d) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261028-d705754d` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-d705754d) |
| k | auth gate: no/tampered/forged token -> 401, access token -> 403, /products public | PASS | `None` | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261028-007c022f` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-007c022f) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261028-660da4c0` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-660da4c0) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261028-fd7f2ff3`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-fd7f2ff3`

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
2026-10-28T17:41:57.059Z  PENDING             Order received via API
2026-10-28T17:41:57.590Z  PROCESSING          Saga workflow started
2026-10-28T17:41:57.892Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:41:58.172Z  PAYMENT_CAPTURED    ₹3,499 debited from DemoPay · balance ₹9,96,501 (attempt 1)
2026-10-28T17:41:58.227Z  COMPLETED           Order fulfilled - payment PAY-b84816d69765 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261028-5b827a2b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-5b827a2b`

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
2026-10-28T17:42:00.825Z  PENDING             Order received via API
2026-10-28T17:42:01.317Z  PROCESSING          Saga workflow started
2026-10-28T17:42:01.446Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:01.556Z  PAYMENT_DECLINED    Attempt 1: Card declined by issuer (simulated)
2026-10-28T17:42:01.938Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-28T17:42:01.987Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261028-ea2f10d0`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-ea2f10d0`

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
2026-10-28T17:42:03.879Z  PENDING             Order received via API
2026-10-28T17:42:04.328Z  PROCESSING          Saga workflow started
2026-10-28T17:42:04.438Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:04.552Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway timeout on attempt 1 (simulated) - retrying
2026-10-28T17:42:06.702Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway timeout on attempt 2 (simulated) - retrying
2026-10-28T17:42:10.872Z  PAYMENT_CAPTURED    ₹26,990 debited from DemoPay · balance ₹9,69,511 (attempt 3)
2026-10-28T17:42:10.909Z  COMPLETED           Order fulfilled - payment PAY-82e537fdba85 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261028-bf27518c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-bf27518c`

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
2026-10-28T17:42:13.259Z  PENDING             Order received via API
2026-10-28T17:42:13.575Z  PROCESSING          Saga workflow started
2026-10-28T17:42:13.686Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-28T17:42:13.727Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261028-f5bd29d7`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-f5bd29d7`

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

statusHistory:
```
2026-10-28T17:42:16.144Z  PENDING             Order received via API
2026-10-28T17:42:16.591Z  PROCESSING          Saga workflow started
2026-10-28T17:42:16.721Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:16.892Z  PAYMENT_CAPTURED    ₹24,999 debited from DemoPay · balance ₹9,44,512 (attempt 1)
2026-10-28T17:42:16.931Z  COMPLETED           Order fulfilled - payment PAY-db776766b803 captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261028-f20b357e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-f20b357e`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)

statusHistory:
```
2026-10-28T17:42:21.800Z  PENDING             Order received via API
2026-10-28T17:42:22.067Z  PROCESSING          Saga workflow started
2026-10-28T17:42:22.182Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:22.332Z  PAYMENT_CAPTURED    ₹799 debited from DemoPay · balance ₹9,43,713 (attempt 1)
2026-10-28T17:42:22.370Z  COMPLETED           Order fulfilled - payment PAY-d9ac3a0a3677 captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261028-4d66d9c4`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 222s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)

statusHistory:
```
2026-10-28T17:41:56.439Z  PENDING             Order received via API
2026-10-28T17:41:56.931Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-28T17:42:56.823Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-28T17:43:56.833Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261028-a8fa4e9c`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-a8fa4e9c`

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
2026-10-28T17:42:41.959Z  PENDING             Order received via API
2026-10-28T17:42:42.329Z  PROCESSING          Saga workflow started
2026-10-28T17:42:42.447Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:42.592Z  PAYMENT_DECLINED    Attempt 1: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-28T17:42:42.796Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-28T17:42:42.831Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261028-d705754d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-d705754d`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)

statusHistory:
```
2026-10-28T17:42:44.913Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-28T17:42:45.363Z  PROCESSING          Saga workflow started
2026-10-28T17:42:45.475Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:45.632Z  PAYMENT_CAPTURED    ₹2,299 debited from DemoPay · balance ₹9,41,414 (attempt 1)
2026-10-28T17:42:45.671Z  COMPLETED           Order fulfilled - payment PAY-4cd9dcfd05b1 captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261028-d705754d`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-d705754d`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-28T17:42:44.913Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-28T17:42:45.363Z  PROCESSING          Saga workflow started
2026-10-28T17:42:45.475Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:45.632Z  PAYMENT_CAPTURED    ₹2,299 debited from DemoPay · balance ₹9,41,414 (attempt 1)
2026-10-28T17:42:45.671Z  COMPLETED           Order fulfilled - payment PAY-4cd9dcfd05b1 captured
```

## k) auth gate: no/tampered/forged token -> 401, access token -> 403, /products public - PASS

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
- PASS: GET /wallet with an ACCESS token (no email claim) -> 403 (expected 403: Send the ID token: it must carry a verified email)

## l) order isolation: A can't read B's order (404), each list shows only its owner's orders - PASS

orderId: `ORD-20261028-007c022f`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-007c022f`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (18 orders) doesn't contain B's order
- PASS: B's GET /orders (5 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-28T17:42:51.801Z  PENDING             Order received via API
2026-10-28T17:42:52.093Z  PROCESSING          Saga workflow started
2026-10-28T17:42:52.216Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:52.352Z  PAYMENT_CAPTURED    ₹1,299 debited from DemoPay · balance ₹9,98,701 (attempt 1)
2026-10-28T17:42:52.397Z  COMPLETED           Order fulfilled - payment PAY-198a08d576a1 captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 7 -> 7 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261028-660da4c0`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-660da4c0`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261028-418dd2b7, B ORD-20261028-660da4c0
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261028-418dd2b7 COMPLETED
- PASS: ORD-20261028-660da4c0 COMPLETED

statusHistory:
```
2026-10-28T17:42:57.278Z  PENDING             Order received via API
2026-10-28T17:42:57.841Z  PROCESSING          Saga workflow started
2026-10-28T17:42:57.961Z  RESERVED            Reserved stock for 1 product(s)
2026-10-28T17:42:58.112Z  PAYMENT_CAPTURED    ₹1,799 debited from DemoPay · balance ₹9,96,902 (attempt 1)
2026-10-28T17:42:58.150Z  COMPLETED           Order fulfilled - payment PAY-554d5ca0a18f captured
```
