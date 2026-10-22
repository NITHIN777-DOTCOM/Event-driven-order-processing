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
```
