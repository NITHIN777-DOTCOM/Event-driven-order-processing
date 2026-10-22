# Progress

Use this to resume work in a new session. See CLAUDE.md for the full spec and the phase plan.

## Current phase
**Phase 4.1 — Amazon-style catalog + DemoPay wallet: DONE (2026-10-22).** Next: **Phase 5 — CI/CD (GitHub Actions + OIDC).**

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

### Phase 4
- Storefront: https://dg38gx94mao9n.cloudfront.net (CloudFront `PriceClass_200`, OAC -> private S3
  `order-saga-frontend-876889172858`, SPA fallback, security headers). `config.json` is written by Terraform.
- Backend: GET /products, GET /orders (GSI `gsi1`, backfilled 52 orders), GET /orders/{id} now returns
  `feed` + `consoleLinks`. New timeline events: PAYMENT_DECLINED, OUT_OF_STOCK, DELIVERY_RETRY, DEAD_LETTERED.
  CORS = CloudFront domain + http://localhost:5173.
- Frontend: frontend/ (React 18, Vite 5, Tailwind 3, React Router 6). Pages: Shop, Checkout, Order tracker, Orders.
- Scripts: deploy_frontend.py, capture_ui.py (Playwright), backfill_order_index.py.
- Unit tests: 51 passed, 96% coverage. UI evidence: docs/evidence/ui/ (11 desktop + 5 mobile screenshots).

### Phase 4.1
- Catalogue: 16 products in 5 categories (seed_inventory.py), with category/mrp/rating/highlights/description.
  16 Unsplash photos (credits in README).
- DemoPay: tables `order-saga-wallets` + `order-saga-wallet-txns`; process_payment debits in one
  TransactWriteItems (wallet + ledger + order); new Lambdas `order-saga-refund-payment` (idempotent compensation)
  and `order-saga-wallet-api` (GET /wallet, POST /wallet/reset with an optional custom balance).
- ASL: ProcessPayment / MarkOrderCompleted failures -> RefundPayment -> ReleaseInventory -> ...
- Frontend: two-row header with search + wallet; listing with filters/sort (/, /c/:cat, /deals, /search);
  product page (/p/:id); cart page; 2-step checkout with DemoPay; wallet page; toasts.
- Tests: 65 unit tests (95% coverage); e2e_test.py 8/8 (adds wallet checks + a real low-balance decline);
  capture_ui.py: 6/6 UI scenarios with ledger checks. Evidence: docs/evidence/e2e-failure-tests.md, docs/evidence/ui/.

## Next (Phase 5)
- GitHub Actions with OIDC: tests on PRs; terraform plan/apply + deploy_frontend on main.

## Known limitations / ideas (good viva points)
- DemoPay has no authentication: wallets are keyed by email, so anyone who knows an email can view or reset it (demo only).
- If create_order crashes after the DynamoDB transaction but before SQS SendMessage, the order stays PENDING,
  and a client retry only replays it. Fix: a transactional outbox (DynamoDB Streams -> Pipes -> SQS).
- HTTP APIs (API Gateway v2) don't support X-Ray tracing; only REST APIs do.

## Blockers / notes
- None.
- Local dev: `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`;
  run the tests with `.venv\Scripts\python -m pytest --cov=src`.
- `terraform.tfvars` files are gitignored; copy them from `*.tfvars.example` on a new machine.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before AWS CLI calls that take `/aws/...` log group names.
