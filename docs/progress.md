# Progress

Use this to resume work in a new session. See CLAUDE.md for the full spec and the phase plan.

## Current phase
**Phase 3 — Monitoring: DONE (2026-10-22).** Next: **Phase 4 — Frontend (S3 + CloudFront).**

## Done
### Phase 0
- Environment verified: IAM user `order-saga-admin`, region `ap-south-1`, Terraform 1.16.6,
  local Python 3.11.9 (accepted; the Lambda runtime is python3.12), git, origin remote.
- `infra/bootstrap` (LOCAL state, do not delete `infra/bootstrap/terraform.tfstate`):
  S3 `order-saga-tfstate-876889172858` (versioned, SSE-S3, private, TLS-only, 30-day noncurrent expiry)
  and budget `order-saga-monthly-budget` (5 USD; 50%/80% actual, 100% forecast).
- `infra/main` uses an S3 backend (`main/terraform.tfstate`, `use_lockfile = true`).

### Phase 1
- DynamoDB `order-saga-orders`/`-inventory`; SQS `order-saga-orders-queue` + DLQ; SNS
  `order-saga-notifications`/`-ops-alerts` (both email subscriptions CONFIRMED); Lambdas (arm64, py3.12,
  X-Ray, 7-day logs, one role each); STANDARD state machine `order-saga-workflow`; HTTP API `order-saga-api`.
- API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`
- Evidence: `docs/evidence/phase1-happy-path.md`.

### Phase 2
- New: Lambda `order-saga-release-inventory` (idempotent compensation); DynamoDB `order-saga-idempotency`
  (TTL `expiresAt`, 24 h).
- ASL: Retry (PaymentTransientError 2s/x3/backoff 2; Lambda service errors 1s/x2/backoff 2), Catch to
  ReleaseInventory -> DescribeFailure (JSONata Pass) -> MarkOrderFailed -> NotifyCustomerFailure -> OrderFailed.
- create_order: Idempotency-Key (generated if missing), transaction {key + order}, 200 duplicate replay,
  409 if the key is reused with a different body.
- start_workflow: reads the order, rejects poison messages, conditional PENDING->PROCESSING, DescribeExecution
  to detect duplicates, ExecutionAlreadyExists = success. Timeout 10 s; queue visibility 60 s.
- process_payment: simulate modes, paymentAttempts counter, PAYMENT_RETRY entries, no double charge.
- Unit tests: 37 passed, 96% coverage. Live e2e: `scripts/e2e_test.py` 7/7 passed
  (see `docs/evidence/phase2-failure-tests.md`).
- The DLQ intentionally still holds the poison message for ORD-20261022-7b1a4028 (for screenshots). Do NOT purge it.

### Phase 3
- `infra/main/monitoring.tf`: dashboard `order-saga-dashboard` (7 rows); 6 alarms (8 alarm metrics, free tier)
  -> `order-saga-ops-alerts` with ok_actions; 4 saved queries in the `order-saga/` folder.
- X-Ray: botocore patched via `src/common/tracing.py` + the AWS Powertools layer (pinned v40, arm64, py3.12).
- Scripts: `generate_traffic.py` (40 orders: 32 COMPLETED / 8 FAILED as expected), `collect_evidence.py`.
- Alarm states: dlq-not-empty = ALARM (Phase 2 poison message; ops email sent 11:55 UTC); the other 5 = OK.
- Evidence: `docs/evidence/phase3-monitoring.md` + 15 PNGs in `docs/evidence/phase3/`.
- Known gap: the Step Functions state-machine segment doesn't show up in X-Ray (tracing on, IAM OK, AssumeRole OK).
  Trace propagation through SFN to the Lambdas works. See the notes in the evidence file.

## Next (Phase 4)
- Frontend on S3 + CloudFront (OAC), calling the API; tighten CORS to the CloudFront domain.

## Known limitations / ideas (good viva points)
- If create_order crashes after the DynamoDB transaction but before SQS SendMessage, the order stays PENDING,
  and a client retry only replays it. Fix: a transactional outbox (DynamoDB Streams -> Pipes -> SQS).
- HTTP APIs (API Gateway v2) don't support X-Ray tracing; only REST APIs do.

## Blockers / notes
- None.
- Local dev: `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`;
  run the tests with `.venv\Scripts\python -m pytest --cov=src`.
- `terraform.tfvars` files are gitignored; copy them from `*.tfvars.example` on a new machine.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before AWS CLI calls that take `/aws/...` log group names.
