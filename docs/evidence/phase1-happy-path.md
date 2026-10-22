# Phase 1 evidence: happy path end-to-end

Date: 2026-10-22 · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`

Three orders were placed with `python scripts/place_order.py --simulate none`, after seeding the
inventory with `python scripts/seed_inventory.py` (5 products, stock 100 each).

## Orders

| # | orderId | Items | Total (INR) | Final status | Execution |
|---|---------|-------|-------------|--------------|-----------|
| 1 | ORD-20261022-3c4a4c87 | 2 x Wireless Mouse, 1 x Mechanical Keyboard | 5097.00 | COMPLETED | SUCCEEDED |
| 2 | ORD-20261022-ce123206 | 1 x USB-C Hub, 1 x 4K Monitor | 26998.00 | COMPLETED | SUCCEEDED |
| 3 | ORD-20261022-0c6b4fdf | 1 x ANC Headphones, 3 x Wireless Mouse | 29387.00 | COMPLETED | SUCCEEDED |

Execution ARNs:
- `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-3c4a4c87`
- `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-ce123206`
- `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-0c6b4fdf`

## Order 1: client output

```
POST https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com/orders  simulate=none
  -> HTTP 202 {"orderId": "ORD-20261022-3c4a4c87", "status": "PENDING"}
  [16:07:58] ORD-20261022-3c4a4c87 is PROCESSING
  [16:08:00] ORD-20261022-3c4a4c87 is COMPLETED

Status timeline:
  2026-10-22T10:37:57.456Z  PENDING           Order received via API
  2026-10-22T10:37:57.990Z  PROCESSING        Saga workflow started
  2026-10-22T10:37:58.884Z  RESERVED          Reserved stock for 2 product(s)
  2026-10-22T10:37:59.385Z  PAYMENT_CAPTURED  Payment PAY-f07d0a1be517 captured: INR 5097.00
  2026-10-22T10:37:59.514Z  COMPLETED         Order fulfilled - payment PAY-f07d0a1be517 captured
```

Orders 2 and 3 show the same 5-step timeline. They finished in about 0.5 s because the Lambdas were already warm.

```
ORD-20261022-ce123206: PENDING 10:38:08.374 -> PROCESSING .457 -> RESERVED .557 -> PAYMENT_CAPTURED .679 (PAY-8eb4d11e6c15) -> COMPLETED .701
ORD-20261022-0c6b4fdf: PENDING 10:38:12.116 -> PROCESSING .188 -> RESERVED .310 -> PAYMENT_CAPTURED .417 (PAY-f62a05a0f6f9) -> COMPLETED .438
```

## Step Functions

```
$ aws stepfunctions list-executions --state-machine-arn ...:stateMachine:order-saga-workflow
ORD-20261022-0c6b4fdf  SUCCEEDED  16:08:12.208 -> 16:08:12.631 (IST)
ORD-20261022-ce123206  SUCCEEDED  16:08:08.479 -> 16:08:08.953
ORD-20261022-3c4a4c87  SUCCEEDED  16:07:58.190 -> 16:07:59.711

States entered (order 1): ReserveInventory -> ProcessPayment -> MarkOrderCompleted -> NotifyCustomer -> OrderCompleted
```

## SNS publish (NotifyCustomer TaskSucceeded output from the execution history)

```
ORD-20261022-3c4a4c87  SNS MessageId = 44271317-997d-5bc3-875a-704470babcdc
ORD-20261022-ce123206  SNS MessageId = 6689c278-c958-57f8-8827-a12b20883cb0
ORD-20261022-0c6b4fdf  SNS MessageId = 4404a292-e7f2-52ae-bec7-c1c10e26a50d
```

## Inventory after the 3 orders (start: stock 100, reserved 0)

```
productId       stock reserved
4K-MONITOR        99   1
ANC-HEADPHONES    99   1
MECH-KEYBOARD     99   1
USBC-HUB          99   1
WIRELESS-MOUSE    95   5    (2 + 3)
```

## Queues

```
order-saga-orders-queue: visible 0, in flight 0   (all messages consumed)
order-saga-orders-dlq:   visible 0, in flight 0   (nothing failed)
```

## Structured JSON logs (one line per Lambda for order 1; every line carries orderId)

```json
{"timestamp": "2026-10-22T10:37:57.558Z", "level": "INFO", "service": "create_order", "message": "Order accepted", "orderId": "ORD-20261022-3c4a4c87", "totalAmount": "5097.00", "itemCount": 2, "simulate": "none"}
{"timestamp": "2026-10-22T10:37:58.201Z", "level": "INFO", "service": "start_workflow", "message": "Saga execution started", "orderId": "ORD-20261022-3c4a4c87", "executionArn": "arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261022-3c4a4c87"}
{"timestamp": "2026-10-22T10:37:58.914Z", "level": "INFO", "service": "reserve_inventory", "message": "Inventory reserved", "orderId": "ORD-20261022-3c4a4c87", "items": [["WIRELESS-MOUSE", "2"], ["MECH-KEYBOARD", "1"]]}
{"timestamp": "2026-10-22T10:37:59.491Z", "level": "INFO", "service": "process_payment", "message": "Payment captured", "orderId": "ORD-20261022-3c4a4c87", "paymentId": "PAY-f07d0a1be517", "amount": "5097.00", "currency": "INR"}
```

API access log (JSON; source IP omitted here):
```json
{"httpMethod":"POST","path":"/orders","routeKey":"POST /orders","status":"202","latencyMs":"615","integrationError":"-"}
```

Other checks: the Step Functions log group `/aws/vendedlogs/states/order-saga-workflow` had 72 events
(level ALL), and X-Ray recorded 12 traces in the 30-minute window.

## Unit tests

```
16 passed in 9.24s · total coverage 95%
```
