# Progress

Use this to resume work in a new session. See CLAUDE.md for the full spec and the phase plan.

## Current phase
**Upgrade step 1.1 — Transactional outbox: DONE (2026-10-28).** Next: **1.2 Cognito + user-keyed wallets/orders.**
(Original phases P0–P5 are done. The old P6 load test and P7 docs are folded into upgrade Phase 3.)

## Upgrade plan (toward a 9/10 resume project)
- Phase 1 Foundation: 1.0 prep | 1.1 outbox (DynamoDB Streams -> EventBridge Pipes -> SQS) |
  1.2 Cognito + user-keyed wallets/orders
- Phase 2 Saga features: 2.1 async payment (waitForTaskToken + HMAC webhook + timeout) | 2.2 reservation holds
  with TTL | 2.3 multi-item orders with partial compensation | 2.4 mid-saga cancellation
- Phase 3 Proof + presentation: 3.1 oversell race test | 3.2 invariant/chaos checker | 3.3 k6 load test |
  3.4 Standard vs Express + cost per 1,000 orders | 3.5 README rewrite + demo video

### Step 1.0 (prep)
- Deploy role (`infra/bootstrap/github_oidc.tf`): added Pipes (pipe/order-saga-*), Cognito (create only with
  tag Project=aws-order-saga; manage only pools carrying that tag), SSM (parameter/order-saga/*), and PassRole
  now limited by iam:PassedToService to lambda, states and pipes. DynamoDB streams were already covered by
  dynamodb:* on table/order-saga-*. The plan role's ReadOnlyAccess already covers pipes/cognito-idp/ssm reads.
- New `docs/interview-prep.md` (one section per feature; update it in the same commit as any feature change).
- Bootstrap applied locally (1 changed); re-plan: no changes. Local AWS CLI upgraded 2.9.0 -> 2.39.0 (`aws pipes` works).

### Step 1.1 (transactional outbox)
- Orders table stream (NEW_IMAGE) -> pipe `order-saga-orders-outbox` (INSERT + status=PENDING filter, `{"orderId"}`
  template, batch 1, TRIM_HORIZON, 5 retries / 1 h max age) -> `order-saga-orders-queue`; DLQ `order-saga-outbox-dlq`.
  Pipe role: stream read on this stream + SendMessage on the queue/outbox DLQ only.
- create_order: no SQS code, env var or permission (Terraform precondition enforces it).
- Alarms `order-saga-outbox-dlq-not-empty`, `order-saga-outbox-pipe-failures` (8 alarms = 10 alarm metrics, the free tier);
  dashboard row 3 = outbox.
- Rollout: commit A `4814f7d` (dual delivery, 10/10 orders 1 execution + 1 DEBIT), commit B `a6c2848` (dual write removed).
  Median delivery 72 ms -> 346 ms. e2e 10/10 (adds crash simulation + MODIFY scenarios). Unit tests 67, 95%.
- Idle cost: the pipe polls the stream ~4x/s, ESTIMATED ~$1.6/month (not measured; approved). Evidence: docs/evidence/upgrade-1.1-outbox.md.
- Test row `OUTBOX-DLQ-TEST-68c7af7e<U+0001>` (status PROCESSING) is a labelled DLQ probe; leave it.

### Step 1.2 prep: AWS provider 5.x -> 6.68.x (own commit, before commit A)
- Needed for `aws_cognito_managed_login_branding`. Lock file relocked for linux_amd64 + windows_amd64.
  `terraform plan` against the live stack: No changes.

### Step 1.2 (Cognito auth + user-keyed data): IN PROGRESS
- Bootstrap: deploy role + `cognito-idp:AdminInitiateAuth` (applied locally 2026-10-28, 1 changed; re-plan: no changes).
- Commit A: `infra/main/auth.tf` (pool `order-saga-users` ESSENTIALS, managed login v2 domain, `spa` + `automation`
  clients, branding), config.json `auth` block, CORS allows `authorization`; `scripts/create_test_users.py` (users A/B,
  passwords in SSM `/order-saga/test-users/a|b`), `scripts/auth_tokens.py`; every API script sends the ID token;
  deploy.yml ensures the test users before the smoke test; frontend login (oidc-client-ts 3.5.0 + react-oidc-context
  3.3.1). API still has NO authorizer; backend unchanged.
- Commit B (next): JWT authorizer, identity from claims, user-keyed orders/wallets/GSI, per-user idempotency.

### Decisions for step 1.2 (Cognito)
- Old email-keyed wallets/orders stay as unused legacy rows (no deletion).
- GET /products stays public; checkout, orders and wallet require login.
- Open self-sign-up with email verification.
- Cognito managed login with authorization code + PKCE.

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
- The orders DLQ intentionally holds the poison messages from demo/e2e runs (9 after step 1.1, incl.
  ORD-20261022-7b1a4028 and the outbox DLQ probe), so `order-saga-dlq-not-empty` is in ALARM. Do NOT purge or redrive it.

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

### Phase 5
- infra/bootstrap/github_oidc.tf (applied locally): OIDC provider; `order-saga-github-deploy-role` (main only),
  `order-saga-github-plan-role` (PRs). The trust uses the IMMUTABLE subject
  `repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651:...`.
- .github/workflows/ci.yml (tests + coverage gate 85%, tf fmt/validate, frontend build, PR plan comment) and
  deploy.yml (workflow_run after green CI on main: apply, deploy_frontend, smoke_test; concurrency deploy-main).
- Repo variables set with gh: AWS_DEPLOY_ROLE_ARN, AWS_PLAN_ROLE_ARN, ALERT_EMAIL.
- Proven: PR #1 (footer "v1.1 · deployed by GitHub Actions") -> plan comment -> merge -> Deploy -> live.
  Evidence: docs/evidence/phase5-cicd.md.
- From now on, deploy by merging to main; local `terraform apply` in infra/main is still possible (same state + lock).

## Next (upgrade step 1.2)
- Cognito user pool + managed login (code + PKCE, self sign-up with email verification); JWT authorizer on checkout,
  orders and wallet routes (GET /products stays public); wallets/orders keyed by the token `sub`; scripts get a test user.

## Known limitations / ideas (good viva points)
- DemoPay has no authentication: wallets are keyed by email, so anyone who knows an email can view or reset it (demo only).
- (Fixed in 1.1) The create_order dual write is gone: transactional outbox via DynamoDB Streams -> Pipes -> SQS.
- No sweeper for orders stuck in PENDING if delivery fails beyond the stream's 24 h retention.
- HTTP APIs (API Gateway v2) don't support X-Ray tracing; only REST APIs do.

## Blockers / notes
- None.
- Local dev: `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`;
  run the tests with `.venv\Scripts\python -m pytest --cov=src`.
- `terraform.tfvars` files are gitignored; copy them from `*.tfvars.example` on a new machine.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before AWS CLI calls that take `/aws/...` log group names.
