# End-to-end tests: every saga path, including DemoPay wallet checks

Run: 2026-10-29 09:32:43 UTC · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
Command: `python scripts/e2e_test.py` (after `python scripts/seed_inventory.py`) · Duration: 288s

**Result: 14/14 scenarios passed.**

| # | Scenario | Result | orderId | Execution (console) |
|---|----------|--------|---------|---------------------|
| a | simulate=none -> COMPLETED, stock decreased, wallet debited once | PASS | `ORD-20261029-a886d6cc` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a886d6cc) |
| b | payment_declined -> FAILED, stock restored by compensation | PASS | `ORD-20261029-c95cd39b` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c95cd39b) |
| c | payment_flaky -> retried twice, then COMPLETED | PASS | `ORD-20261029-05b7dd19` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-05b7dd19) |
| d | out_of_stock -> FAILED, nothing reserved, no compensation needed | PASS | `ORD-20261029-6c9af410` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-6c9af410) |
| e | same Idempotency-Key sent 3x -> exactly 1 order, 1 execution | PASS | `ORD-20261029-6621c5aa` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-6621c5aa) |
| f | same {orderId} delivered 3x via SQS -> exactly 1 execution | PASS | `ORD-20261029-a2a2a97e` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a2a2a97e) |
| g | poison message -> DLQ after 3 receives, order stays PENDING | PASS | `ORD-20261029-12185014` | none started (by design) |
| h | wallet balance too low -> REAL decline, stock released, nothing debited | PASS | `ORD-20261029-195dd54b` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-195dd54b) |
| i | crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox | PASS | `ORD-20261029-e71041f5` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e71041f5) |
| j | MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution | PASS | `ORD-20261029-e71041f5` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e71041f5) |
| k | auth gate: no/tampered/forged/ID token -> 401, access token with email claims -> 200, /products public | PASS | `None` | none started (by design) |
| l | order isolation: A can't read B's order (404), each list shows only its owner's orders | PASS | `ORD-20261029-5f6d77c9` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-5f6d77c9) |
| m | wallet isolation: A's reset (with B's ids in the body) changes only A's wallet | PASS | `None` | none started (by design) |
| n | per-user idempotency: B reusing A's Idempotency-Key gets B's own order | PASS | `ORD-20261029-3f2bc669` | [open](https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/v2/executions/details/arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-3f2bc669) |

## a) simulate=none -> COMPLETED, stock decreased, wallet debited once - PASS

orderId: `ORD-20261029-a886d6cc`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a886d6cc`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: statusHistory PENDING -> PROCESSING -> RESERVED -> PAYMENT_CAPTURED -> COMPLETED
- PASS: MECH-KEYBOARD stock 97 -> 96 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DemoPay balance 1000000 -> 996501 (expected -3499)
- PASS: DEBIT ledger entries for this order: 1 (expected 1)

statusHistory:
```
2026-10-29T09:27:57.186Z  PENDING             Order received via API
2026-10-29T09:27:57.393Z  PROCESSING          Saga workflow started
2026-10-29T09:27:57.523Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:27:57.688Z  PAYMENT_CAPTURED    ₹3,499 debited from DemoPay · balance ₹9,96,501 (attempt 1)
2026-10-29T09:27:57.745Z  COMPLETED           Order fulfilled - payment PAY-2890721c1b16 captured
```

## b) payment_declined -> FAILED, stock restored by compensation - PASS

orderId: `ORD-20261029-c95cd39b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-c95cd39b`

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
2026-10-29T09:28:01.087Z  PENDING             Order received via API
2026-10-29T09:28:01.528Z  PROCESSING          Saga workflow started
2026-10-29T09:28:01.658Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:01.814Z  PAYMENT_DECLINED    Attempt 1: Card declined by issuer (simulated)
2026-10-29T09:28:04.159Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T09:28:04.218Z  FAILED              PaymentDeclined: Card declined by issuer (simulated)
```

## c) payment_flaky -> retried twice, then COMPLETED - PASS

orderId: `ORD-20261029-05b7dd19`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-05b7dd19`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: paymentAttempts 3 (expected 3)
- PASS: 2 PAYMENT_RETRY entries (expected 2)
- PASS: ANC-HEADPHONES stock 97 -> 96 (expected -1)
- PASS: execution SUCCEEDED (expected SUCCEEDED)
- PASS: DEBIT ledger entries after 3 attempts: 1 (expected 1)

statusHistory:
```
2026-10-29T09:28:06.706Z  PENDING             Order received via API
2026-10-29T09:28:07.029Z  PROCESSING          Saga workflow started
2026-10-29T09:28:07.140Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:07.268Z  PAYMENT_RETRY       Attempt 1 failed: Payment gateway timeout on attempt 1 (simulated) - retrying
2026-10-29T09:28:09.412Z  PAYMENT_RETRY       Attempt 2 failed: Payment gateway timeout on attempt 2 (simulated) - retrying
2026-10-29T09:28:13.627Z  PAYMENT_CAPTURED    ₹26,990 debited from DemoPay · balance ₹9,69,511 (attempt 3)
2026-10-29T09:28:13.674Z  COMPLETED           Order fulfilled - payment PAY-95e64732c2f1 captured
```

## d) out_of_stock -> FAILED, nothing reserved, no compensation needed - PASS

orderId: `ORD-20261029-6c9af410`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-6c9af410`

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
2026-10-29T09:28:16.368Z  PENDING             Order received via API
2026-10-29T09:28:16.532Z  PROCESSING          Saga workflow started
2026-10-29T09:28:16.652Z  OUT_OF_STOCK        Insufficient stock for: 4K-MONITOR (simulated)
2026-10-29T09:28:16.707Z  FAILED              OutOfStock: Insufficient stock for: 4K-MONITOR (simulated)
```

## e) same Idempotency-Key sent 3x -> exactly 1 order, 1 execution - PASS

orderId: `ORD-20261029-6621c5aa`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-6621c5aa`

Checks:
- PASS: HTTP codes [202, 200, 200] (expected [202, 200, 200])
- PASS: distinct orderIds returned: 1 (expected 1)
- PASS: duplicate flags [False, True, True]
- PASS: orders with this (user-scoped) key in DynamoDB: 1 (expected 1)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1, not 3)
- PASS: 4K-MONITOR stock 98 -> 97 (expected -1, not -3)
- PASS: DEBIT ledger entries: 1 (expected 1, not 3)

statusHistory:
```
2026-10-29T09:28:19.487Z  PENDING             Order received via API
2026-10-29T09:28:20.027Z  PROCESSING          Saga workflow started
2026-10-29T09:28:20.158Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:20.308Z  PAYMENT_CAPTURED    ₹24,999 debited from DemoPay · balance ₹9,44,512 (attempt 1)
2026-10-29T09:28:20.345Z  COMPLETED           Order fulfilled - payment PAY-8f189b5c6b9f captured
```

## f) same {orderId} delivered 3x via SQS -> exactly 1 execution - PASS

orderId: `ORD-20261029-a2a2a97e`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a2a2a97e`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: PROCESSING entries in statusHistory: 1 (expected 1)
- PASS: 'Duplicate message ignored' log lines for this order: 2 (expected >= 1)
- PASS: DEBIT ledger entries: 1 (expected 1)

statusHistory:
```
2026-10-29T09:28:27.885Z  PENDING             Order received via API
2026-10-29T09:28:28.337Z  PROCESSING          Saga workflow started
2026-10-29T09:28:28.472Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:28.648Z  PAYMENT_CAPTURED    ₹799 debited from DemoPay · balance ₹9,43,713 (attempt 1)
2026-10-29T09:28:28.689Z  COMPLETED           Order fulfilled - payment PAY-ed60c81db82e captured
```

## g) poison message -> DLQ after 3 receives, order stays PENDING - PASS

orderId: `ORD-20261029-12185014`

Checks:
- PASS: POST /orders returned 202 (expected 202)
- PASS: message found in order-saga-orders-dlq after 283s
- PASS: order status PENDING (expected PENDING)
- PASS: no execution was started
- PASS: start_workflow ERROR log lines with this orderId: 3 (expected >= 3, one per receive)
- PASS: order-saga-outbox-dlq messages: 0 (expected 0: the pipe delivered it)

statusHistory:
```
2026-10-29T09:27:56.289Z  PENDING             Order received via API
2026-10-29T09:27:56.650Z  DELIVERY_RETRY      Delivery attempt 1 of 3 failed; SQS will retry
2026-10-29T09:28:56.638Z  DELIVERY_RETRY      Delivery attempt 2 of 3 failed; SQS will retry
2026-10-29T09:29:56.640Z  DEAD_LETTERED       Delivery attempt 3 of 3 failed; SQS moves the message to the dead-letter queue
```

## h) wallet balance too low -> REAL decline, stock released, nothing debited - PASS

orderId: `ORD-20261029-195dd54b`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-195dd54b`

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
2026-10-29T09:28:48.545Z  PENDING             Order received via API
2026-10-29T09:28:49.105Z  PROCESSING          Saga workflow started
2026-10-29T09:28:49.207Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:49.348Z  PAYMENT_DECLINED    Attempt 1: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
2026-10-29T09:28:49.563Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
2026-10-29T09:28:49.595Z  FAILED              PaymentDeclined: Insufficient wallet balance: ₹1,000 available, ₹5,999 needed
```

## i) crash simulation: order row written directly (no API, no SQS) -> COMPLETED via the outbox - PASS

orderId: `ORD-20261029-e71041f5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e71041f5`

Checks:
- PASS: order status COMPLETED (expected COMPLETED)
- PASS: executions: 1 (expected 1)
- PASS: DEBIT ledger entries: 1 (expected 1)
- PASS: INSERT records for this order in the orders stream: 1 (expected 1)

statusHistory:
```
2026-10-29T09:28:52.201Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-29T09:28:52.109Z  PROCESSING          Saga workflow started
2026-10-29T09:28:52.226Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:52.368Z  PAYMENT_CAPTURED    ₹2,299 debited from DemoPay · balance ₹9,41,414 (attempt 1)
2026-10-29T09:28:52.408Z  COMPLETED           Order fulfilled - payment PAY-37901b25021e captured
```

## j) MODIFY on an existing order (status -> PENDING) does NOT start a new delivery or execution - PASS

orderId: `ORD-20261029-e71041f5`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e71041f5`

Checks:
- PASS: status PENDING (expected PENDING: start_workflow never picked it up)
- PASS: new start_workflow log lines for this order after the MODIFY: 0 (expected 0)
- PASS: executions: 1 (expected 1, unchanged)

statusHistory:
```
2026-10-29T09:28:52.201Z  PENDING             Order row written directly to DynamoDB by e2e_test.py (crash simulation: no SQS send)
2026-10-29T09:28:52.109Z  PROCESSING          Saga workflow started
2026-10-29T09:28:52.226Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:28:52.368Z  PAYMENT_CAPTURED    ₹2,299 debited from DemoPay · balance ₹9,41,414 (attempt 1)
2026-10-29T09:28:52.408Z  COMPLETED           Order fulfilled - payment PAY-37901b25021e captured
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

orderId: `ORD-20261029-5f6d77c9`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-5f6d77c9`

Checks:
- PASS: B: POST /orders -> 202 (expected 202)
- PASS: B reads B's own order: COMPLETED (expected COMPLETED)
- PASS: A: GET /orders/<B's order> -> 404 (expected 404, not 403)
- PASS: the 404 for B's order is worded exactly like the 404 for an order that doesn't exist
- PASS: A's GET /orders (45 orders) doesn't contain B's order
- PASS: B's GET /orders (11 orders) contains B's order
- PASS: A's and B's order lists share no orderId
- PASS: every order in A's list is owned by A's sub (owners seen: 1)

statusHistory:
```
2026-10-29T09:29:02.165Z  PENDING             Order received via API
2026-10-29T09:29:02.655Z  PROCESSING          Saga workflow started
2026-10-29T09:29:02.762Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:29:02.908Z  PAYMENT_CAPTURED    ₹1,299 debited from DemoPay · balance ₹9,98,701 (attempt 1)
2026-10-29T09:29:02.944Z  COMPLETED           Order fulfilled - payment PAY-105a95fed606 captured
```

## m) wallet isolation: A's reset (with B's ids in the body) changes only A's wallet - PASS

orderId: `None`

Checks:
- PASS: POST /wallet/reset as A -> 200, walletId = A's sub
- PASS: A's balance is now 4321 (expected 4321)
- PASS: B's wallet unchanged: balance 998701 -> 998701, 15 -> 15 ledger entries

## n) per-user idempotency: B reusing A's Idempotency-Key gets B's own order - PASS

orderId: `ORD-20261029-3f2bc669`
Execution ARN: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-3f2bc669`

Checks:
- PASS: A -> 202, then B with the SAME key -> 202 (both 202 = new orders)
- PASS: different orders: A ORD-20261029-ac5afe5a, B ORD-20261029-3f2bc669
- PASS: A again with the key -> 200, duplicate=True, the original order
- PASS: B's order is owned by B's sub
- PASS: A can't read the order B made with A's key -> 404 (expected 404)
- PASS: ORD-20261029-ac5afe5a COMPLETED
- PASS: ORD-20261029-3f2bc669 COMPLETED

statusHistory:
```
2026-10-29T09:29:08.305Z  PENDING             Order received via API
2026-10-29T09:29:08.875Z  PROCESSING          Saga workflow started
2026-10-29T09:29:08.985Z  RESERVED            Reserved stock for 1 product(s)
2026-10-29T09:29:09.128Z  PAYMENT_CAPTURED    ₹1,799 debited from DemoPay · balance ₹9,96,902 (attempt 1)
2026-10-29T09:29:09.171Z  COMPLETED           Order fulfilled - payment PAY-98254b355704 captured
```
