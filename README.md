# Event-Driven E-Commerce Order Processing on AWS

> 🚧 **Work in progress.** It is being built phase by phase. See [docs/progress.md](docs/progress.md).

A serverless, event-driven order-processing system on AWS that uses the **saga pattern**. An API Gateway
HTTP API accepts orders idempotently and stores them in DynamoDB. The orders are queued on SQS, which has a
dead-letter queue. A Step Functions workflow then reserves inventory and processes a simulated payment, with
retries for transient errors. If a step fails, the workflow runs compensating actions that release the
inventory and mark the order FAILED. Customers and operators are notified through SNS. Everything is defined
in Terraform (region `ap-south-1`) and traced with X-Ray, monitored with CloudWatch dashboards and alarms,
and kept within a $5/month budget.

## Quick start (after `terraform apply` in `infra/main`)

```powershell
python -m venv .venv; .venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts\seed_inventory.py              # 5 products, stock 100
.venv\Scripts\python scripts\place_order.py --simulate none # place an order and follow it to COMPLETED
.venv\Scripts\python -m pytest --cov=src                    # unit tests (moto, no AWS needed)
.venv\Scripts\python scripts\e2e_test.py                    # all 7 failure scenarios against the live API (~3 min)
```

## Monitoring

- **Dashboard** `order-saga-dashboard`: orders (started, succeeded, failed, success rate, duration), API, queue and
  DLQ, the 6 Lambdas, DynamoDB, and a table of the latest failed orders with their reasons.
  `scripts\generate_traffic.py` sends 40 mixed orders over 4 minutes to fill it.
- **Alarms** go to SNS `order-saga-ops-alerts`. A compensated order is a *business* outcome, not a fault, so
  system alarms cover the DLQ, consumer crashes, API 5xx, timed-out or aborted executions and queue backlog. A
  separate business alarm fires when more than 50% of orders fail, and only once at least 5 orders have started.
- **Saved Logs Insights queries** live in the `order-saga/` folder: *Trace one order*, *Failed orders by reason*,
  *Duplicate messages ignored* and *Slowest Lambda invocations*.
- **X-Ray**: active tracing is on every Lambda and the state machine, and botocore is patched through the
  AWS-managed Powertools layer, so there's no Docker build. One trace follows an order from the API Lambda
  through SQS and Step Functions to DynamoDB.
- `scripts\collect_evidence.py --order-id <id>` exports alarm states, graphs, the service map and an order trace.

## Demo: forcing each saga path

Every order can carry `"simulate"`, which picks the path it takes:

| `--simulate` | What happens | Final status |
|---|---|---|
| `none` | Reserve, then pay, then complete, then email | COMPLETED |
| `payment_flaky` | Payment fails twice (`PaymentTransientError`), and Step Functions retries it after 2 s and then 4 s | COMPLETED |
| `payment_declined` | `PaymentDeclined`, then **ReleaseInventory** (compensation), then FAILED, then email | FAILED |
| `out_of_stock` | `OutOfStock`, then FAILED (nothing was reserved, so there's nothing to release) | FAILED |
| `poison` | `start_workflow` rejects the SQS message, which goes to the **DLQ** after 3 receives | stays PENDING |

Duplicate protection: `place_order.py --repeat 3` sends one `Idempotency-Key` three times. You get back one order and one
execution, and only one charge.

### Why the poison message reaches the DLQ in about 3 minutes

SQS moves a message to the dead-letter queue only after it has been received `maxReceiveCount` (3) times. A
message that failed becomes visible again only when its **visibility timeout** expires, so the wait is roughly
`maxReceiveCount x visibility timeout`.

AWS recommends a visibility timeout of at least **6x the consumer Lambda's timeout**, so that a message is never
redelivered while a slow invocation is still working on it. `start_workflow` only calls `StartExecution`, so its
timeout is set to **10 s**. That makes the queue's visibility timeout **60 s**, and a poison message lands in
`order-saga-orders-dlq` after 3 x 60 s, about **3 minutes**. With the default 30 s timeout, the visibility timeout
would be 180 s and the wait would be 9 minutes, which is too long for a live demo.
