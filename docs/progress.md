# Progress

Use this to resume work in a new session. See CLAUDE.md for the full spec and the phase plan.

## Current phase
**Upgrade step 2.4 — customer cancellation mid-saga: DONE (2026-10-30, report docs/evidence/upgrade-2.4-report.md).**
Now: step 3.1 oversell race test (IN PROGRESS, see "Step 3.1" below). Step 2.3 is DONE (report docs/evidence/upgrade-2.3-report.md).
(Step-by-step notes for 2.1 to 2.4 are in the "Step 2.x" sections below.)
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

### Step 1.2 (Cognito auth + user-keyed data): DONE
- Bootstrap: deploy role + `cognito-idp:AdminInitiateAuth` (applied locally 2026-10-28, 1 changed; re-plan: no changes).
- Commit A: `infra/main/auth.tf` (pool `order-saga-users` ESSENTIALS, managed login v2 domain, `spa` + `automation`
  clients, branding), config.json `auth` block, CORS allows `authorization`; `scripts/create_test_users.py` (users A/B,
  passwords in SSM `/order-saga/test-users/a|b`), `scripts/auth_tokens.py`; every API script sends the ID token;
  deploy.yml ensures the test users before the smoke test; frontend login (oidc-client-ts 3.5.0 + react-oidc-context
  3.3.1). API still has NO authorizer; backend unchanged.
- Commit A `ceebe0e` green. Fixes: `e48fbf6` spa client `explicit_auth_flows = ["ALLOW_CUSTOM_AUTH"]` (an empty list
  left SRP password auth open); `bcff9c8` deploy role + `cognito-idp:ListUserPoolClients` (bootstrap, applied after "APPLY").
- Commit B: JWT authorizer `order-saga-cognito-jwt` (all routes but GET /products), `src/common/auth.py` (identity only
  from claims), orders carry userId/walletId, gsi1pk = USER#<sub>, gsi1sk = <createdAt>#<orderId>, GET /orders/{id}
  404 for others' orders, wallets keyed by sub, idempotency keys stored as <sub>#<key>. e2e adds k-n (auth + isolation).
- Commit B `2c1444b` green (Deploy 40736924726, apply 1 added / 15 changed). Live e2e 14/14 (adds k-n); unit tests 81, 94%.
  Evidence: docs/evidence/upgrade-1.2-auth.md. Test users: order-saga-test-a/b@example.com (creds in SSM, never printed).
- Orders DLQ: 11 messages + 1 in flight (the UI run's poison order) = 12 (each e2e/UI run adds its poison order). Do NOT purge or redrive. UI suite 6/6.

### Step 2.0 (access tokens for the API): DONE
- Lambda `order-saga-pre-token` (V2_0 pre-token-generation trigger on `order-saga-users`, Essentials): adds `email` +
  `email_verified` to ACCESS tokens only. Invoke permission scoped to the pool ARN. No bootstrap change was needed
  (deploy role already had lambda:* on order-saga-* and cognito-idp:UpdateUserPool).
- Commit A `e1a8a3c` (both token types accepted; frontend, scripts/auth_tokens.py, CI send the access token): CI +
  Deploy 40848092637 green (5 added / 14 changed), live e2e 14/14.
- Commit B `59ad7cd` (access only; `token_use = id` -> 401): CI 40849234155 + Deploy 40849337652 green (0 added /
  11 changed), live e2e 14/14 (k adds ID token -> 401 x3), UI 6/6, unit 105 / 94.5%.
- Evidence: docs/evidence/upgrade-2.0-access-tokens.md, report docs/evidence/upgrade-2.0-report.md.
- Orders DLQ grows by one poison order per e2e/UI run (4 more today). Do NOT purge or redrive.

### Step 2.1 (async payment: waitForTaskToken + HMAC webhook + 120 s timeout)
- A `b2cdc15` (+ `59bcbaa`, `2d926ed`): tables order-saga-payments / order-saga-psp-transactions, queue
  order-saga-psp-requests (+ DLQ, maxReceiveCount 5), payment_provider "DemoPay", POST /webhooks/payment (no JWT) +
  payment_webhook, SSM SecureString /order-saga/psp/webhook-secret (scripts/create_webhook_secret.py, run by Deploy),
  alarms psp-dlq-not-empty + webhook-signature-failures (10 alarms), dashboard row 8. Live: 401 x4, unknown intent 404.
- B `47fac57` (+ `108e8a9`): RequestPayment (waitForTaskToken, TimeoutSeconds 120) -> MarkPaymentTimedOut on
  States.Timeout; refund via DemoPay; process_payment removed (log group kept: `retired_log_groups` in lambda.tf).
- B's first apply failed on the SFN Description tag (parentheses). The old function was already gone: 32 orders in
  that window failed safely (net 0, stock released). Any tag value: letters, digits, spaces, _ . : = + - @ only.
- Live e2e 19/19 (p timeout, q late refund, r duplicate webhook, s bad signature; I1-I4 checked per order);
  capture_ui 7/7, 0 console errors. Unit tests 166, 94%. Evidence: docs/evidence/upgrade-2.1-async-payment.md,
  report: docs/evidence/upgrade-2.1-report.md.
- Known gap (interview-prep §11): no reconciliation job for intents stuck REQUESTED if a saga dies outside its timeout.
- Orders DLQ: 2 more poison orders today (e2e + UI run). Do NOT purge or redrive.

### Step 2.2 (checkout holds: 10-min reservation, EventBridge Scheduler expiry)
- Part 0 `b6ed9e3`: 2.1 postmortem (interview-prep §10), `infra/modules/tag_values` validates every Description tag
  at plan time (+ `terraform test` in CI), CLAUDE.md rules: expand -> migrate -> contract; Description tags only via module.tags.
- Bootstrap (applied locally after "APPLY", 2 changed): deploy role may manage schedule-group/order-saga-*; state
  bucket Description "Terraform remote state ... stack infra main" (no "/").
- A `08e8460`: table order-saga-holds (TTL purgeAt, clean-up only), holds_api (POST /holds, GET /holds/current,
  DELETE /holds/{holdId}), schedule group order-saga-holds + order-saga-holds-scheduler-role, hold_expiry Lambda,
  SSM String /order-saga/auth/client-ids (automation client may pick 30-600 s; spa always 600 s), alarm
  hold-expiry-errors (11 alarms), dashboard row 9. Deploy: 22 added, 17 changed, 0 destroyed. Live e2e 23/24 (u's test
  compared a shared counter exactly; fixed in B).
- B `e2a90b8`: create_order validates holdId; ReserveInventory consumes the hold (one transaction) or falls back;
  storefront countdown (frontend/src/hold.ts). Deploy: 1 added, 5 changed, 0 destroyed.
- Live e2e 26/26 (t-z), UI suite 8/8 (0 console errors; fake-clock expiry shots). Unit tests 217, 94%. Schedule lag 11.8 / 20.1 / 45.9 s (not
  second-precise; expiry is also logical). App stack 156 resources. Evidence: docs/evidence/upgrade-2.2-holds.md.
- inventory items now carry `held`; seed_inventory.py resets it to 0. I5: seeded = stock + held + reserved.
- Docs commit `2609948`: CI 40868893996 + Deploy 40869067633 both green (recorded here in step 2.3; the 2.2 report
  said it was here before it was).

### Step 2.3 (per-item fulfillment, partial refunds, write-offs)
- Spec: reservation stays all-or-nothing; after payment an inline Map `FulfillItems` fulfils each line; an unavailable
  line is refunded (DemoPay line refund) and written off; the order ends PARTIALLY_FULFILLED (all lines unavailable ->
  full refund, FAILED). New invariants I6 (net = fulfilled lines) and I7 (refunds <= charge, once per line); I5 now
  seeded = stock + held + reserved + sold + writtenOff.
- Commit A (expand, NOT wired into the saga): Lambdas order-saga-fulfill-item / order-saga-write-off-lines, table
  order-saga-write-offs, DemoPay line refund (idempotent per (intent, line), running `refundedAmount` cap on the CHARGE
  record), refund_payment `lineIds` mode, per-line lineId + lineAmount stored by create_order, release_inventory
  aware of sold / written-off lines, reserve_inventory returns `lines` (dropped by the old ResultSelector),
  alarm order-saga-refund-or-write-off-errors, fulfillment metric filters + dashboard row.
  seed_inventory.py also resets sold / writtenOff and writes `seededAt`; e2e I5 uses all five counters and checks
  writtenOff against the write-off records since `seededAt`; scenario a asserts an old-definition COMPLETED order
  moves nothing to `sold`. `scripts/fulfillment_check.py` = live direct-invoke check of the new pieces.
  jsonata-python==0.7.1 pinned in requirements-dev.txt (Map summary expression tests, commit B).
- Commit A `25a6b90`: CI + Deploy green (15 added, 22 changed, 0 destroyed). Live: fulfillment_check.py 19/19
  (order ORD-20261030-399cf6c3: concurrent L1+L3 fulfil, L2 written off + refunded once, I7 probe RefundRejected,
  I6 net 15395 = L1 + L3); full e2e 26/26 on A (old path unchanged; scenario a: sold unchanged). Evidence:
  docs/evidence/upgrade-2.3/fulfillment-check.md, e2e-commit-A.md.
- Commit B: Map FulfillItems (inline, MaxConcurrency 5, Catch per iteration -> LineUnavailable) + SummarizeFulfillment
  (JSONata, unit-tested with jsonata-python on the real ASL) + Choice FulfillmentOutcome; PartialRefund /
  WriteOffLines / MarkOrderPartiallyFulfilled / NotifyCustomerPartial; RefundAllLines / WriteOffAllLines /
  DescribeAllUnavailable -> MarkOrderFailed. create_order accepts item_unavailable + simulateLine (1..n | "all").
  refund_payment refuses FULFILLED lines. GET /orders(/{id}) return lines (list: BatchGetItem). Feed rows, tracker
  "Delivered / Cancelled — refunded", "Partially fulfilled" badge. e2e: a/y/z now expect sold; new za/zb/zc; I3
  per line; I6/I7 for every order. capture_ui: partial order + wallet credit. scripts/inflight_check.py.
  Plan: 0 added, 20 changed, 0 destroyed. Unit tests 266, 93%.
- B `89f355f`: CI 41032228377 + Deploy 41032444445 green (0 added, 20 changed, 0 destroyed). Live e2e 28/29 (u: test
  summed stock + reserved, l's desk mat now ends in sold; I5 passed), then 29/29 after the fix. inflight_check during
  B: inconclusive (probe product USB-MIC has 18 units, ran out before the update).
- B fix `e464e66`: wallet shows refund notes; e2e u pool = all counters but held; inflight_check MECH-KEYBOARD + generic
  definition compare; Map comment. CI 41034908817 + Deploy 41035114664 green (0 added, 1 changed). inflight_check
  PASS (ORD-20261030-62b512cd started 4.1 s before the update, finished on the old definition). UI suite 9/9, 0
  console errors. Evidence: docs/evidence/upgrade-2.3-fulfillment.md (+ upgrade-2.3/).
- Executions per order: old definition 5 states, 1 line 9, 3-line partial 14. Map 0.14-0.23 s.
- Known nit (fixed in step 2.4): the write-off feed row repeated the item name.
- Docs commit `2a6ca16`: CI 41036078786 + Deploy 41036264119 both green (recorded after they finished).

### Step 2.4 (customer cancellation mid-saga)
- Design: ONE conditional write on the order item decides every race. Cancel: status in the window (RESERVED,
  PAYMENT_RETRY, PAYMENT_PENDING, PAYMENT_CAPTURED) + no cancelRequestedAt + cancellable=true -> CANCEL_REQUESTED.
  Webhook capture/decline and BeginFulfillment (PAYMENT_CAPTURED -> FULFILLING) require no cancelRequestedAt.
  Cancel reaches a saga waiting for payment with SendTaskFailure "OrderCancelled" on the token stored on the intent
  (TaskTimedOut / InvalidToken = race lost / already handled). Never StopExecution.
- DemoPay "void" (conditional CHARGE record, outcome VOIDED) so cancelling while the payment is pending takes
  nothing; a charge that wins the race is refunded once ("refund what's left", I7).
- The `cancellable` stamp is written by reserve_inventory ONLY when the state machine passes "cancellable": true
  (the new definition), so orders on the old definition stay 409 NOT_CANCELLABLE.
- New: Lambdas order-saga-cancel-order (POST /orders/{id}/cancel, CANCEL_ENABLED=false in A -> 503) and
  order-saga-begin-fulfillment (not called before B); alarm order-saga-cancellation-errors; metric
  OrderSaga/CancelEvents (4 filters) + dashboard row y=65; outputs cancellation_function_names; simulate
  payment_slow (20 s), fulfillment_slow (B: 10 s waits), payment_manual (test harness triggers the charge).
- IAM: cancel-order (orders Get/Update, payments Get, states:SendTaskFailure on the state machine ARN);
  begin-fulfillment (orders Get/Update); payment-webhook + orders GetItem; SFN role + invoke begin-fulfillment.
- Legacy cleanup `scripts/migrate_legacy_sold.py` (dry-run default, --apply, --check). Dry-run before A: 454 orders,
  233 legacy COMPLETED, all reserved before the last seed (2026-10-30T09:43:09Z) -> 0 units to move, 233 to mark.
- Commit A: plan 16 added, 41 changed, 0 destroyed (changes = new code hashes, policies re-read, the definition's
  formatting only). Unit tests 303, 93%. Pre-APPLY review: the losing webhook (success or decline) also answers the
  token with SendTaskFailure "OrderCancelled", and a retried cancel answers it whenever the intent is not SUCCEEDED, so a
  cancel Lambda that dies between its write and SendTaskFailure still reaches the cancel branch.
- Commit A `eb9a4ab`: CI 41043851030 + Deploy 41044113358 green (16 added, 22 changed, 0 destroyed). e2e 28/29 (g:
  the poison message was in the DLQ, but a 10-message peek with nothing hidden missed it among 27), then 29/29; UI
  9/9. Evidence docs/evidence/upgrade-2.4/e2e-commit-A.md.
- Legacy cleanup (APPLY): 505 scanned, 233 marked, 0 units moved; --check PASS before and after; re-run finds 0.
- e2e g made deterministic (review): DLQ count must rise by exactly 1, then a sweep with VisibilityTimeout 30 until
  the message is found or every message seen, then visibility 0 for all; nothing deleted.
- Commit B `48e7d8e` (APPLY, incl. the SFN GetItem): state machine cancel branch + CheckCancelBeforeFailing (the
  timeout + cancel case ends CANCELLED; fallback Catch -> MarkOrderFailed), CANCEL_ENABLED=true, storefront, feed,
  refund note. CI 41060910418 + Deploy 41061113800 green (0 added, 21 changed). inflight_check PASS: 2 straddled on
  the old definition, 13 old orders 409 NOT_CANCELLABLE; the cancel Lambda flipped ~2 min before the state machine
  (the stamp held). e2e 35/35 (race x20: 14 nothing charged, 4 late charge refunded, 2 payment won, 0 both); I1-I9.
- B fix `fd8709a`: the CANCEL_REQUESTED entry names the reason once; capture_ui waits for the tracker, prints UTF-8.
  CI 41064702078 + Deploy 41065249876 green. UI 10/10. Unit tests 327, 93%.
- Full e2e re-run on the B fix deploy (it redeployed 19 Lambdas): 35/35 in 403 s, 2026-10-30 15:10 UTC (race x20:
  15 nothing charged, 4 late charge refunded, 1 payment won, 0 both); I1-I9. Evidence upgrade-2.4/e2e-commit-B-fix.md.
- States per one-line COMPLETED order 9 -> 12; cancel while waiting 8; after payment 12.
- Docs commit: evidence docs/evidence/upgrade-2.4-cancellation.md, report, README, interview-prep section 13 numbers +
  debugging story. Docs commit `cb5b002`: CI 41066644918 + Deploy 41066893944 green (0 changed; recorded after they finished).

### Step 3.1 (oversell race test) — IN PROGRESS
- Pre-flight: Lambda account concurrency 400 (unreserved 400, no reserved concurrency anywhere); API stage
  `$default` burst 100 / rate 50 rps, no route overrides.
- Prep `8471de8`: GET /products hides `listed = false` (the RACE-* test products); e2e SEEDED_AT = demo catalogue
  only. CI 41181937338 + Deploy 41182050402 green.
- Harness `scripts/oversell_race.py` (160 Cognito race buyers race-001..160: one ACTIVE hold per user, so each hold
  attempt has its own buyer); negative control `tests/race/` (BrokenReserve 40 of 5 claimed; real code exactly 5).
- Run `before-fix` (2026-10-31): exactly 20/20 and 10/10 claimed, never more, 0 ERROR, 0 throttled, I1-I9, recovery
  652 s; but FAIL: 112 holds got 409 with 3-14 units available, 5 orders "Insufficient stock for: one or more items":
  TransactionConflict read as out of stock. Fix next (separate commit), then re-run.
- Fix 1 `bbc7bcd` (common/transact.py: retry TransactionConflict on every stock path; 8 tries, 20-400 ms): CI
  41183372836 + Deploy 41183541011 green (0 added, 19 changed). Harness commit `56ae364`'s CI 41183356083 was
  superseded (cancel-in-progress) by bbc7bcd's, which tested the same tree plus the fix.
- Run `after-fix-1`: 0 phantom out-of-stock (was 112), 20/20 + 10/10, I1-I9, I5, recovery 646 s; FAIL: 1 hold per
  round ran out of conflict retries -> 503. Fix 2: 10 tries, 50 ms-1 s, and a consistent stock read before a 503.

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
  ORD-20261022-7b1a4028 and the outbox DLQ probe), so `order-saga-dlq-not-empty` is in ALARM (12 after step 1.2). Do NOT purge or redrive it.

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

## Next (upgrade Phase 3)
- 3.1 oversell race test, then 3.2 invariant/chaos checker, 3.3 k6 load test, 3.4 Standard vs Express + cost per
  1,000 orders, 3.5 README rewrite + demo video. Wait for the step spec.

## Known limitations / ideas (good viva points)
- (Fixed in 1.2) Wallets/orders are keyed by the Cognito `sub`; the API has a JWT authorizer.
- No Content-Security-Policy header yet (tokens are in sessionStorage). (Fixed in 2.0) The API takes access tokens only.
- No reconciliation job for payment intents left REQUESTED if a saga dies outside its own timeout (2.1).
- Cognito's default email sender is limited to a few dozen emails/day (sign-up codes).
- (Fixed in 1.1) The create_order dual write is gone: transactional outbox via DynamoDB Streams -> Pipes -> SQS.
- No sweeper for orders stuck in PENDING if delivery fails beyond the stream's 24 h retention.
- HTTP APIs (API Gateway v2) don't support X-Ray tracing; only REST APIs do.

## Blockers / notes
- None.
- Local dev: `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`;
  run the tests with `.venv\Scripts\python -m pytest --cov=src`.
- `terraform.tfvars` files are gitignored; copy them from `*.tfvars.example` on a new machine.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before AWS CLI calls that take `/aws/...` log group names.
