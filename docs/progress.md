# Progress

Use this to resume work in a new session. See CLAUDE.md for the full spec and the phase plan.

## Current phase
**Phase 1 — Core workflow: DONE (2026-10-22).** Next: **Phase 2 — Failure engineering + tests.**

## Done
### Phase 0
- Environment verified: IAM user `order-saga-admin`, region `ap-south-1`, Terraform 1.16.6,
  local Python 3.11.9 (accepted; the Lambda runtime is python3.12), git, origin remote.
- `infra/bootstrap` (LOCAL state, do not delete `infra/bootstrap/terraform.tfstate`):
  S3 `order-saga-tfstate-876889172858` (versioned, SSE-S3, private, TLS-only, 30-day noncurrent expiry)
  and budget `order-saga-monthly-budget` (5 USD; 50%/80% actual, 100% forecast).
- `infra/main` uses an S3 backend (`main/terraform.tfstate`, `use_lockfile = true`).

### Phase 1
- 43 resources in `infra/main`: DynamoDB `order-saga-orders`/`-inventory`; SQS `order-saga-orders-queue`
  (+ DLQ, maxReceiveCount 3); SNS `order-saga-notifications`/`-ops-alerts` (both email subscriptions
  CONFIRMED); 5 Lambdas (arm64, py3.12, X-Ray, 7-day logs, one role each); STANDARD state machine
  `order-saga-workflow` (ALL logging, tracing); HTTP API `order-saga-api` (CORS, JSON access logs, throttling).
- API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
- Scripts: `seed_inventory.py`, `place_order.py`, `tf_outputs.py`. Unit tests: 16 passed, 95% coverage.
- Verified 3 COMPLETED orders: see `docs/evidence/phase1-happy-path.md`.

## Next (Phase 2)
- Idempotency-Key in create_order (the hook comment is in the handler).
- simulate modes: payment_declined, payment_flaky, out_of_stock, poison (hooks in process_payment / start_workflow).
- ASL: Retry/Catch, compensation (ReleaseInventory -> MarkOrderFailed -> NotifyCustomer).
- Make start_workflow's PROCESSING update conditional so a duplicate delivery doesn't append history twice.
- Add unit tests for start_workflow.

## Blockers / notes
- None.
- Local dev: `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`;
  run the tests with `.venv\Scripts\python -m pytest --cov=src`.
- `terraform.tfvars` files are gitignored; copy them from `*.tfvars.example` on a new machine.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before AWS CLI calls that take `/aws/...` log group names.
