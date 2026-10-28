# Interview prep: Order Saga

One section per feature, with the same headings each time. Rules for this file:
- **Numbers** are measured results only, with the evidence file they came from. No estimates.
- **Debugging story** is a real incident recorded in `docs/evidence/` or git history, or "None recorded".
- Every feature added or changed updates this file in the same commit (see CLAUDE.md).

Evidence referenced below:
`docs/evidence/phase1-happy-path.md`, `docs/evidence/phase2-failure-tests.md`,
`docs/evidence/e2e-failure-tests.md` (latest e2e run, 8/8, 2026-10-22 13:21 UTC),
`docs/evidence/phase3-monitoring.md`, `docs/evidence/phase5-cicd.md`.

---

## 1. Idempotent order creation (Idempotency-Key + idempotency table)

### What
`POST /orders` accepts an `Idempotency-Key` header. Retrying with the same key returns the original
order (HTTP 200, `duplicate: true`) instead of creating a second one.

### Why (the problem it solves)
Clients retry: network timeouts, double-clicks, proxies. Without a key, every retry is a new order,
a new stock reservation and a new charge.

### How
- `src/lambdas/create_order/handler.py`: reads the header (or generates a UUID and returns it), validates it
  against `^[A-Za-z0-9_.:\-]{1,128}$`, and hashes the normalised body (SHA-256, `request_fingerprint`).
- Fast path: a `ConsistentRead` GetItem on DynamoDB `order-saga-idempotency` (PK `idempotencyKey`). If the key
  exists, `replay()` returns the stored order: 200 when the hash matches, **409** when the key was reused
  with a different body.
- Write path: ONE `TransactWriteItems` puts the idempotency record (`attribute_not_exists(idempotencyKey)`)
  and the PENDING order (`attribute_not_exists(orderId)`). There's never an order without its key, or a key
  without its order.
- If two requests with the same key race, the loser gets `TransactionCanceledException`
  (`ConditionalCheckFailed` on item 0) and replays the winner's order.
- Records expire via DynamoDB TTL on `expiresAt` after 24 h (`infra/main/dynamodb.tf`), at no cost.

### Trade-offs / alternatives considered
- A separate table rather than a GSI on orders: a GSI is eventually consistent, so it can't enforce uniqueness.
- The key is server-generated when missing, so a client that never sends one gets no retry protection.
- The 24 h TTL means a retry after a day creates a new order. That's normal for payment-style APIs.
- Prices come from the inventory table, not the client (`price_items`), so the fingerprint can't be used to
  change what's charged.

### Numbers
- Same key sent 3×: HTTP `[202, 200, 200]`, 1 distinct orderId, 1 order in DynamoDB, 1 execution, stock −1
  (not −3), 1 DEBIT ledger entry (not 3). Order `ORD-20261022-e80b7218`, `e2e-failure-tests.md` scenario e.

### Likely interview questions
1. *Why a transaction rather than two conditional puts?* Two puts can half-succeed (a key with no order, or the
   reverse). The transaction makes both or neither.
2. *What if the same key arrives with a different body?* 409. Replaying the old order would silently
   ignore what the client asked for.
3. *What if the Lambda crashes after the transaction but before SQS?* The order stays PENDING and a retry only
   replays it. That's the outbox gap (Known gaps, fixed in step 1.1).
4. *Why ConsistentRead?* An eventually consistent read could miss a key written milliseconds earlier.
   The transaction condition is still the real guard.

### Debugging story
None recorded.

---

## 2. Conditional inventory reservation (no oversell)

### What
Saga step 1, `ReserveInventory`, decrements stock for every item only if enough is left, all items or none.

### Why (the problem it solves)
Concurrent orders for the last units must not drive stock below zero. And a multi-item order must not end
up half-reserved.

### How
- `src/lambdas/reserve_inventory/handler.py`: one `TransactWriteItems` with an Update per item on
  `order-saga-inventory`, `SET stock = stock - :qty, reserved = reserved + :qty` with condition
  `attribute_exists(productId) AND stock >= :qty`, plus the order's RESERVED update.
- The order records `reservedItems`, so compensation releases exactly that.
- On `TransactionCanceledException`, the cancellation reasons name the short product(s), and it raises
  `OutOfStock`. The state machine catches it and skips ReleaseInventory (nothing was reserved).
- Idempotent on retry: if `reservedItems` already exists, it doesn't reserve again.
- `MAX_ITEMS = 20` in create_order keeps an order well under the DynamoDB transaction item limit.

### Trade-offs / alternatives considered
- The condition check happens on the write itself. That's lock-free and avoids read-then-write races,
  with no SELECT FOR UPDATE.
- Stock is reserved for the whole saga. A failed payment gives it back via compensation, but stock is held
  while payment runs. Time-limited holds are planned in step 2.2.
- A transaction costs 2× write units compared with single updates, in exchange for all-or-nothing behaviour.

### Numbers
- Out of stock: stock/reserved `(100, 0) -> (100, 0)` unchanged and ReleaseInventory not run (scenario d; that
  run uses `simulate=out_of_stock`).
- A real decline after reservation: USB-MIC `(18, 0) -> (18, 0)` after compensation (scenario h).
- A concurrent oversell race test: none recorded yet (planned in step 3.1).

### Likely interview questions
1. *How do you prevent oversell without locks?* A conditional update (`stock >= :qty`) evaluated atomically
   by DynamoDB on the item.
2. *Why put all items in one transaction?* Otherwise item 1 succeeds, item 2 fails, and you have to undo
   item 1 by hand.
3. *What happens on a Lambda retry after a successful reserve?* `reservedItems` is already set, so it's a no-op.

### Debugging story
None recorded.

---

## 3. DemoPay wallet: atomic debit and idempotent refund

### What
`ProcessPayment` debits the customer's DemoPay wallet. `RefundPayment` is the compensation that credits it
back if a later step fails.

### Why (the problem it solves)
Money must move exactly once: not twice on retries, not lost on a crash between the "balance" and "ledger"
writes, and always given back when the saga fails after charging.

### How
- `src/lambdas/process_payment/handler.py` + `src/common/wallet.py`: one `TransactWriteItems` across 3 tables:
  - `order-saga-wallets`: `balance = :after`, condition `balance = :before` (optimistic concurrency).
  - `order-saga-wallet-txns`: a DEBIT ledger row (PK `walletId`, SK `txnId = <ISO ts>#<random>`).
  - `order-saga-orders`: sets `paymentId`, `paidAmount`, `walletId`, condition `attribute_not_exists(paymentId)`.
- Cancellation reason on item 2 (orders): a concurrent attempt already paid, so it returns that paymentId and
  charges nothing. On item 0 (wallet): the balance changed, so it re-reads and retries (`MAX_BALANCE_CONFLICTS = 3`),
  then raises `PaymentTransientError` so Step Functions retries.
- A balance below the total raises `PaymentDeclined` (a real decline). `simulate` modes run before any money moves.
- `src/lambdas/refund_payment/handler.py`: a no-op if nothing was charged or it's already refunded. Otherwise one
  transaction: balance += paidAmount, a CREDIT row, and `refunded = true` with condition
  `attribute_exists(paymentId) AND attribute_not_exists(refunded)`.

### Trade-offs / alternatives considered
- Ledger in a separate table rather than a list on the wallet: items cap at 400 KB, and "latest 20" is one Query.
- Optimistic concurrency (`balance = :before`) rather than an `ADD` counter: it makes `balanceAfter` in the
  ledger exact, at the cost of retries under contention on one wallet.
- Simulated money: a real gateway would be async with webhooks (planned in step 2.1, waitForTaskToken + HMAC).
- Today wallets are keyed by email with no auth (Known gaps, fixed in step 1.2).

### Numbers
- Happy path: balance `1000000 -> 996501` (−3499), 1 DEBIT entry (scenario a).
- Flaky payment: 3 attempts, 2 PAYMENT_RETRY entries, **1** DEBIT (scenario c).
- Insufficient balance: "₹1,000 available, ₹5,999 needed" → FAILED, balance still 1000, no DEBIT (scenario h).
- Deploy smoke tests: 1 DEBIT per order (`ORD-20261022-79bff2ed`, `ORD-20261022-631bd265`, `phase5-cicd.md`).

### Likely interview questions
1. *How do you guarantee no double charge?* The order update in the same transaction requires
   `attribute_not_exists(paymentId)`, so a second debit can't commit. A retry sees `paymentId` and returns it.
2. *Why can't the refund run twice?* Its transaction requires `attribute_not_exists(refunded)`.
3. *Why refund before releasing inventory?* Compensation runs in reverse order of the forward steps.
4. *What about two orders paying from the same wallet at once?* The `balance = :before` condition makes one lose,
   and it re-reads and retries with the new balance.

### Debugging story
None recorded.

---

## 4. Saga orchestration (Step Functions)

### What
STANDARD state machine `order-saga-workflow` (`statemachine/order_saga.asl.json`, rendered by `infra/main/sfn.tf`)
that reserves stock, takes payment, completes and notifies, and compensates in reverse on failure.

### Why (the problem it solves)
A distributed transaction across stock, money and the order record, with no 2PC. Every failure path ends in a
consistent state, and the execution graph shows exactly what happened.

### How
- Forward path: `ReserveInventory → ProcessPayment → MarkOrderCompleted → NotifyCustomer → OrderCompleted`.
- Retry: `PaymentTransientError` interval 2 s, MaxAttempts 3, BackoffRate 2. Lambda service errors
  (`Lambda.ServiceException`, `AWSLambdaException`, `SdkClientException`, `TooManyRequestsException`) 1 s, ×2,
  backoff 2.
- Catch: `OutOfStock`/States.ALL on ReserveInventory → `DescribeFailure` (no compensation). `PaymentDeclined`/States.ALL
  on ProcessPayment, and States.ALL on MarkOrderCompleted → `RefundPayment → ReleaseInventory → DescribeFailure →
  MarkOrderFailed → NotifyCustomerFailure → OrderFailed`. Compensation steps retry States.ALL 3× and still continue on failure.
- `MarkOrderCompleted`/`MarkOrderFailed` are direct `dynamodb:updateItem` integrations and `Notify*` are direct
  `sns:publish`, so there's no Lambda for glue. Each appends `{status, timestamp, detail}` to `statusHistory`.
- `DescribeFailure` is a JSONata Pass state that turns the caught error into a readable `failureReason`.
- Logging: level ALL with execution data, to `/aws/vendedlogs/states/...`, 7-day retention.

### Trade-offs / alternatives considered
- Orchestration (Step Functions) rather than choreography (events between services): one place to see and change
  the flow, at the cost of a central dependency.
- STANDARD rather than EXPRESS: exactly-once state transitions, executions up to a year, and a visual history
  for the demo. EXPRESS is cheaper at volume (comparison planned in step 3.4).
- Direct service integrations cut Lambda cost and cold starts but are less flexible than code.

### Numbers
- Flaky payment backoff seen in the timeline: retries at +2.16 s and +4.16 s (scenario c timestamps
  `13:18:29.695 → 31.854 → 36.015`).
- One 60-minute window of mixed generated traffic: 48 started, 37 succeeded, 11 failed (the failures are the
  intentional simulate modes) — `phase3-monitoring.md`.
- Smoke orders completed in 4.4 s and 0.9 s end to end (`phase5-cicd.md`).

### Likely interview questions
1. *Why compensate in reverse order?* Each compensation undoes the most recent step's effect, so the system
   passes back through states that were valid.
2. *What if a compensation itself fails?* It retries 3×, then the Catch moves on and records `refundError`/
   `releaseError` in the state. Today that's visible in the execution, not alerted (see Known gaps).
3. *Why not retry PaymentDeclined?* It's permanent. Retrying wastes time and can annoy a real payment provider.
4. *Why direct integrations?* Fewer moving parts, no code to test for a single UpdateItem/Publish.

### Debugging story
None recorded.

---

## 5. Queue consumer: start_workflow (exactly one saga per order)

### What
SQS `order-saga-orders-queue` → Lambda `order-saga-start-workflow`, which starts one execution per order,
with a DLQ for messages that can never succeed.

### Why (the problem it solves)
SQS is at-least-once, so duplicates happen. Poison messages must not block the queue or retry forever.

### How
- Event source mapping (`infra/main/queue.tf`): batch size 10, `ReportBatchItemFailures` (only failed messages
  are retried), `maximum_concurrency = 5`.
- Queue: visibility timeout 60 s (6× the 10 s Lambda timeout), long polling 20 s, redrive to
  `order-saga-orders-dlq` after `maxReceiveCount = 3`. DLQ retention 14 days.
- `src/lambdas/start_workflow/handler.py`, guard 1: conditional `PENDING → PROCESSING` update.
- Guard 2: execution name = orderId, so `ExecutionAlreadyExists` is treated as success. `DescribeExecution`
  catches duplicates of orders already started.
- Demo `simulate` values (validated in create_order): `none`, `payment_declined`, `payment_flaky`, `out_of_stock`,
  `poison` (start_workflow raises every time, so the message is dead-lettered). Each failed delivery is written
  to the timeline (DELIVERY_RETRY / DEAD_LETTERED).

### Trade-offs / alternatives considered
- A queue between the API and Step Functions (rather than the API calling StartExecution) absorbs spikes and lets
  the API answer 202 quickly, at the cost of one more hop.
- Max concurrency 5 fits a new account's low concurrency limit. It caps throughput by design.
- Execution names are unique per state machine for 90 days. That's fine because orderIds are unique.

### Numbers
- Same `{orderId}` delivered 3×: 1 execution, 1 PROCESSING entry, 2 "Duplicate message ignored" log lines, 1 DEBIT
  (scenario f).
- Poison message: in the DLQ after 197 s (185 s in the Phase 2 run), 3 ERROR log lines (one per receive),
  order stays PENDING, no execution (scenario g; `phase2-failure-tests.md`).

### Likely interview questions
1. *Why ReportBatchItemFailures?* Without it, one bad message makes the whole batch of 10 retry, which
   re-processes the 9 good ones.
2. *Why visibility timeout ≥ 6× the function timeout?* AWS guidance for Lambda consumers, so a message isn't
   redelivered while it's still being processed (including retries of throttled invocations).
3. *How do you get exactly-once from at-least-once?* Idempotent consumers: a conditional state change plus a
   deterministic execution name.
4. *What do you do with the DLQ?* An alarm fires (`order-saga-dlq-not-empty`). Inspect it, fix the cause, then
   redrive to the source queue.

### Debugging story
None recorded.

---

## 6. CI/CD with GitHub Actions + OIDC

### What
`.github/workflows/ci.yml` (tests, Terraform checks, frontend build, plan comment on PRs) and `deploy.yml`
(apply + publish + smoke test after green CI on main). No AWS keys are stored anywhere.

### Why (the problem it solves)
Repeatable deploys of exactly the tested commit, review of infra changes before merge, and no long-lived
credentials to leak.

### How
- `infra/bootstrap/github_oidc.tf`: OIDC provider `token.actions.githubusercontent.com`. Trust uses `StringEquals`
  on `aud = sts.amazonaws.com` and on the **immutable** `sub`
  `repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651:<ref>`.
- `order-saga-github-plan-role`: only `...:pull_request`. ReadOnlyAccess + write on only the state lock key.
- `order-saga-github-deploy-role`: only `...:ref:refs/heads/main`. Permissions scoped to `order-saga-*` ARNs;
  `iam:PassRole` limited by `iam:PassedToService`; Cognito access gated on `Project=aws-order-saga` tags.
  An explicit **Deny `iam:*` on both CI roles** stops the pipeline editing its own trust or permissions.
  Max session 1 h.
- CI: pytest with an 85% coverage gate, `terraform fmt -check` + `validate`, `npm run typecheck` + build.
  Deploy: `workflow_run` on CI success (push events only), checks out `workflow_run.head_sha`, concurrency
  `deploy-main` without cancel, then plan → apply, `deploy_frontend.py`, `smoke_test.py`.

### Trade-offs / alternatives considered
- OIDC rather than access keys: nothing to rotate or leak. The cost is a one-time bootstrap stack.
- The bootstrap stack (OIDC + roles) is applied locally, never by CI, so the pipeline can't widen its own access.
- A scoped policy rather than AdministratorAccess: more work every time a new service is added (this step added
  Pipes, Cognito, SSM).
- The plan role can read SSM SecureStrings (ReadOnlyAccess + the AWS-managed key), which `terraform plan` needs to
  refresh them. It's only assumable from PRs in this repo, not forks.

### Numbers
- 65 unit tests, 95% coverage (local run 2026-10-28; CI gate 85%).
- CI on main 1m34s–1m44s; Deploy 2m03s and 2m42s (`gh run list`, runs 39788933269, 39791901048, 39791148585,
  39792175943).
- PR plan comment: "Plan: 0 to add, 0 to change, 0 to destroy" (PR #1, `phase5-cicd.md`).

### Likely interview questions
1. *How does GitHub get AWS credentials?* It gets a signed JWT per run, and STS `AssumeRoleWithWebIdentity` checks
   `aud` + `sub` against the trust policy, returning 1-hour credentials.
2. *Why two roles?* PRs (possibly from less-trusted branches) only need to read. Only main can change infrastructure.
3. *What stops the deploy role escalating?* An explicit Deny on IAM actions against both CI roles. Deny always wins.
4. *Why the immutable subject?* It embeds numeric owner/repo IDs, so a deleted and re-created repo with the same
   name can't assume the roles.

### Debugging story
The first Deploy run (39789175044) failed with "Could not assume role with OIDC". CloudTrail showed
`AssumeRoleWithWebIdentity` → `AccessDenied` and the token's actual `sub`, which used GitHub's immutable format
with numeric IDs (`gh api repos/<owner>/<repo>/actions/oidc/customization/sub` → `use_immutable_subject: true`).
The trust policy expected the name-only form. The fix (commit `0feb368`) pinned the ID-based prefix via
`var.github_oidc_subject_prefix`. The next Deploy succeeded (39791148585). Source: `phase5-cicd.md`.

Also recorded: CI-built Lambda zips are byte-identical to the Windows-built ones because `.gitattributes` keeps LF
line endings, so CI's plan shows "No changes" instead of redeploying every function (`phase5-cicd.md`).

---

## 7. Observability (logs, metrics, alarms, tracing)

### What
Structured JSON logs with orderId on every line, a CloudWatch dashboard, 6 alarms to an ops SNS topic,
saved Logs Insights queries, and X-Ray traces across Lambdas, SQS and Step Functions.

### Why (the problem it solves)
To answer "what happened to order X?" and "is the system healthy?" in minutes, from the console, for a
live demo and for on-call.

### How
- `src/common/logger.py`: one JSON object per line with `timestamp, level, service, message, orderId, ...`.
  `bind()` carries context.
- `infra/main/monitoring.tf`: dashboard `order-saga-dashboard`. Alarms `dlq-not-empty` (>0, 60 s),
  `start-workflow-errors` (≥1 in 5 min), `api-5xx` (≥1 in 5 min), `queue-backlog` (oldest message >300 s),
  `sfn-timeouts-aborts` (≥1 in 5 min), `high-order-failure-rate` (failed/started >0.5 over 15 min, using
  `IF(started >= 5, ...)` so a single failure at low volume doesn't page). All send to `order-saga-ops-alerts`,
  with OK actions too.
- 4 saved queries in `order-saga/` (trace one order, failures by reason, duplicates ignored, slowest invocations).
- X-Ray: active tracing on Lambdas and the state machine. `src/common/tracing.py` patches botocore (via the
  AWS-managed Powertools layer, pinned) so every DynamoDB/SQS/SFN call is a subsegment.
- Log retention 7 days on every log group, created by Terraform.

### Trade-offs / alternatives considered
- A small hand-written logger rather than Powertools Logger: no dependency in unit tests, same JSON shape.
- The business alarm uses a volume guard to avoid false pages, and so misses failures at very low volume.
- **Known X-Ray gaps:** API Gateway HTTP APIs don't support X-Ray (only REST APIs), so traces start at the Lambda.
  And the state machine's own segment doesn't show on the service map, although trace propagation through it to
  the Lambdas works.

### Numbers
- The dlq-not-empty alarm went to ALARM on 1 message and sent the ops email (`phase3-monitoring.md`).
- One order (`ORD-20261022-13c33683`) traced across create_order → start_workflow → SFN → Lambdas with one saved
  query, in time order (`phase3-monitoring.md`).
- 23 edges on the X-Ray service map in that capture.

### Likely interview questions
1. *How do you trace one order end to end?* The orderId is on every log line and is the execution name. One
   Logs Insights query across the Lambda and SFN log groups, plus one X-Ray trace ID.
2. *Which alarm would page first if the consumer broke?* `start-workflow-errors`, then `queue-backlog`, then
   `dlq-not-empty`.
3. *Why alert on failure rate rather than a count?* Some failures are business-normal (declines). A rate with a
   minimum volume separates incidents from noise.

### Debugging story
The state machine's segment (`AWS::StepFunctions::StateMachine`) never appeared on the X-Ray map. Checked:
tracing enabled, the role has the 4 X-Ray permissions, and `AssumeRole` succeeded in CloudTrail. The Lambdas it
invokes do appear in the same trace, so the header is propagated. **Unresolved**, documented as a known gap
(`phase3-monitoring.md`, "Notes on tracing").

---

## 8. Known gaps (and where they get fixed)

### What
Design limits found and documented, each with a planned fix.

### Why (the problem it solves)
Being able to say what's wrong with your own design, and how you'd fix it, is a stronger signal than
claiming there are no gaps.

### How
- **Outbox gap** (being fixed in step 1.1; commit A adds the stream + pipe NEXT TO the direct send,
  commit B removes the direct send): `create_order` commits the DynamoDB transaction, *then* calls
  `sqs.send_message` (`enqueue_order`). A crash in between leaves the order PENDING forever, and a client retry
  only replays it. Fix: DynamoDB Streams on `order-saga-orders` → EventBridge Pipe (filter `INSERT`) → SQS,
  so the write to the table *is* the publish.
- **Email-keyed wallets with no authentication** (fixed in step 1.2): `GET /wallet?email=` and
  `POST /wallet/reset` accept any email, and `customerEmail` on orders comes from the client
  (`src/lambdas/wallet_api/handler.py`, `src/common/wallet.py`). Fix: Cognito with a JWT authorizer;
  key wallets and orders by the token's `sub`.
- **Constant `gsi1pk` hot partition** (fixed in step 1.2): every order uses `gsi1pk = "ORDER"`, so all
  "recent orders" writes and reads hit one GSI partition (`infra/main/dynamodb.tf`). Fix: per-user partition
  keys once orders are user-keyed.
- Compensation failures are recorded in the execution (`refundError`/`releaseError`) but not alerted on.
- HTTP API has no X-Ray; the SFN segment is missing from the map (section 7).

### Trade-offs / alternatives considered
- Outbox options: Streams + Pipes (chosen, no code), Streams + Lambda (code to own), or a polling relay
  (latency, cost when idle).

### Numbers
None recorded.

### Likely interview questions
1. *What's the dual-write problem?* Writing to two systems (DB + queue) without a shared transaction: one can
   succeed and the other fail. An outbox makes the DB the single write.
2. *Why is a constant partition key a problem?* All traffic goes to one partition, which has a per-partition
   throughput limit, so it throttles long before the table does.

### Debugging story
None recorded.
