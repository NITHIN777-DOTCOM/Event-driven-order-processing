# Interview prep: Order Saga

One section per feature, with the same headings each time. Rules for this file:
- **Numbers** are measured results only, with the evidence file they came from. No estimates.
- **Debugging story** is a real incident recorded in `docs/evidence/` or git history, or "None recorded".
- Every feature added or changed updates this file in the same commit (see CLAUDE.md).

Evidence referenced below:
`docs/evidence/phase1-happy-path.md`, `docs/evidence/phase2-failure-tests.md`,
`docs/evidence/e2e-failure-tests.md` (latest e2e run, 8/8, 2026-10-22 13:21 UTC),
`docs/evidence/phase3-monitoring.md`, `docs/evidence/phase5-cicd.md`, `docs/evidence/upgrade-1.1-outbox.md`,
`docs/evidence/upgrade-1.2-auth.md`.

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

## 8. Transactional outbox (DynamoDB Streams → EventBridge Pipes → SQS)

### What
`create_order` makes exactly one write, the DynamoDB transaction that saves the PENDING order. The order row
*is* the outbox record: the `order-saga-orders` stream feeds the pipe `order-saga-orders-outbox`, which
delivers `{"orderId": ...}` to `order-saga-orders-queue`. `create_order` has no SQS code and no SQS permission.

### Why (the problem it solves)
The dual write. Before step 1.1, `create_order` committed the order and *then* called `sqs.send_message`.
Two systems, no shared transaction: if the Lambda crashed, timed out or got throttled by SQS between the two,
the order sat PENDING forever. A client retry with the same Idempotency-Key only replayed the stuck order,
because the idempotency record had already committed. You can't fix that by reordering (send first and the
message can point to an order that never got saved) or by retrying in the same process (the process is what
died). The fix is to make the database write the only write and derive the message from it.

### How
- Stream on `order-saga-orders`, view type `NEW_IMAGE` (`infra/main/dynamodb.tf`).
- Pipe `order-saga-orders-outbox` (`infra/main/outbox.tf`):
  - filter `{"eventName": ["INSERT"], "dynamodb": {"NewImage": {"status": {"S": ["PENDING"]}}}}`. Every saga
    step writes a MODIFY to the same row, and forwarding those would restart the saga.
  - input template `{"orderId": "<$.dynamodb.NewImage.orderId.S>"}`: byte-for-byte the body the old
    `enqueue_order` sent, so `start_workflow` didn't change (it reads only `orderId` and loads the rest from the table).
  - `batch_size = 1` (one record → one SQS message), `starting_position = TRIM_HORIZON`, `maximum_retry_attempts = 5`,
    `maximum_record_age_in_seconds = 3600`, then DLQ `order-saga-outbox-dlq`.
  - its own role: `DescribeStream`/`GetRecords`/`GetShardIterator` on this stream ARN only, `sqs:SendMessage` on the
    orders queue and the outbox DLQ only; trust limited by `aws:SourceAccount` + `aws:SourceArn`.
- Delivery is **at least once**. Duplicates are safe because `start_workflow` is an idempotent consumer: a conditional
  PENDING→PROCESSING update plus execution name = orderId (`ExecutionAlreadyExists` = success).
- Guardrail: a Terraform `precondition` on the Lambda role policies fails any plan that gives `create_order` an `sqs:`
  permission (`infra/main/iam.tf`). There's also a unit test that the handler loads with no queue configured and sends nothing.
- Alarms `order-saga-outbox-dlq-not-empty` and `order-saga-outbox-pipe-failures` (pipe `ExecutionFailed`) → ops-alerts.
  The dashboard has a row for pipe invocations/failures, pipe duration, stream `GetRecords` calls and the outbox DLQ.
- Rollout in two commits so delivery never stopped: (A) add the stream + pipe *next to* the direct send, so every order
  was delivered twice and the idempotent consumer was proven live; then (B) remove the direct send and its IAM permission.

### Trade-offs / alternatives considered
- **Pipes vs a Lambda relay on the stream** (both use the stream; neither needs custom polling):

  | | EventBridge Pipe (chosen) | Lambda on the stream |
  |---|---|---|
  | Idle polling cost | Pipes' stream reads aren't on AWS's free list. **Estimated, not measured:** ≈ $1.57/month (4 polls/s × 30 days ≈ 10.4M reads, minus the 2.5M free tier, at $0.02/100K) | $0: GetRecords made by Lambda triggers aren't charged |
  | Per-order cost | $0.40 per million pipe requests, counted after filtering | one Lambda invocation + one SendMessage |
  | Code to own | none: filter + input template are configuration | ~30 lines + tests + its own role, log group and alarms |
  | Retries / DLQ | `MaximumRetryAttempts`, `MaximumRecordAgeInSeconds`, SQS/SNS DLQ on the pipe | the same knobs on the event source mapping, plus `BisectBatchOnFunctionError` and an on-failure destination |
  | Filtering | before the target, filtered events not billed | ESM filter criteria, filtered events not invoked |

  **Why Pipes:** zero code on the delivery path (nothing to unit-test or patch), the console shows source → filter →
  target as one resource, and the extra ≈ $1.6/month at idle was explicitly accepted. If cost mattered more than
  "no code", the Lambda relay is the better choice, and this is the trade-off I'd describe in an interview.
- **A polling relay** (a scheduled Lambda scanning for PENDING rows): adds latency equal to the schedule interval,
  costs something even when idle, and needs its own "already sent" bookkeeping. The stream already gives ordered,
  exactly-the-new-rows change data.
- **INSERT-only filtering** rather than "status = PENDING" alone: a later MODIFY that sets the status back to PENDING
  (a bug, a manual fix) would re-enter the queue. eventName is a property of the change, not of the data.
- **TRIM_HORIZON** rather than LATEST: AWS warns a LATEST pipe can miss events for several minutes after creation or
  after its polling settings change. The stream keeps only 24 h, and re-reading a record is a harmless duplicate.
- **`batch_size = 1`** gives exactly one message per order and simple failure isolation. It limits throughput per shard
  (one in-flight batch per shard); `parallelization_factor` (up to 10) is the lever if the load test in 3.3 needs it.
- **No pipe log group:** the pipe's metrics, the outbox DLQ and the pipe's `StateReason` cover failures. Pipe logging
  would also need extra deploy-role permissions for a new log-group prefix.

### Numbers
- Commit A (direct send + pipe both active), 10 orders: every order was delivered **twice** (start_workflow logged
  1 start + 1 "Duplicate message ignored", from two different SQS message IDs) and still had exactly **1 execution and
  1 DEBIT** (`docs/evidence/upgrade-1.1/before.md`).
- Before (direct send), median of 10: PENDING→PROCESSING **72 ms**, PENDING→COMPLETED **366 ms**, client
  POST→COMPLETED **688 ms** (`before.md`).
- After (pipe only), median of 10: PENDING→PROCESSING **346 ms** (+274), PENDING→COMPLETED **645 ms** (+279),
  client POST→COMPLETED **1125 ms** (+437); p95 delivery 542 ms (`after.md`). The extra ~0.3 s is stream polling
  (4/s per shard) plus the pipe hop.
- Crash simulation: a row written straight into DynamoDB (no API, no SQS send) → COMPLETED, 1 execution, 1 DEBIT,
  1 stream INSERT (`e2e-failure-tests.md` scenario i, `ORD-20261028-74eb8439`).
- MODIFY that sets status back to PENDING → 0 new deliveries in 45 s (scenario j). Same Idempotency-Key ×3 → 1 stream INSERT (scenario e).
- create_order role: every `sqs:*` action → `implicitDeny` (`iam simulate-principal-policy`); the Terraform
  precondition failed a plan that re-added `sqs:SendMessage` (`docs/evidence/upgrade-1.1-outbox.md`).
- Idle cost: **not measured**. The ≈ $1.6/month figure is an estimate from AWS's documented polling rate and pricing
  (`docs/evidence/upgrade-1.1-outbox.md`); `scripts/outbox_check.py cost` can measure it.

### Likely interview questions
1. *What if the pipe delivers twice?* start_workflow is idempotent: the PENDING→PROCESSING update is conditional, and
   the execution is named after the orderId, so a second StartExecution gets `ExecutionAlreadyExists` (or, while the
   first is still starting with identical input, the same execution back). Commit A ran *every* order twice in production
   and got exactly one execution and one charge each.
2. *What if the stream record expires (24 h)?* The pipe gives up long before that: after 5 failed attempts or once the
   record is 1 h old, it writes to the outbox DLQ and the alarm fires. The order row is still PENDING in the table, so
   recovery is to send `{"orderId": ...}` to the orders queue. What isn't covered is an outage longer than the stream's
   24 h that loses the record before the pipe even reads it. That needs a sweeper (see Known gaps).
3. *Why not a DynamoDB transaction that also writes to SQS?* There isn't one: `TransactWriteItems` only covers
   DynamoDB tables, and SQS has no two-phase commit. That's exactly why the outbox exists: put the message in the same
   database transaction as the state, then relay it.
4. *Why not send to SQS first, then write the order?* Then a crash leaves a message pointing at an order that doesn't
   exist (start_workflow would dead-letter it), and the client's retry creates the order without a message.
5. *What does the outbox DLQ receive?* AWS doesn't document the body for stream sources, and I couldn't trigger a real
   one without breaking the live pipe. My probe (an orderId SQS should reject) was JSON-escaped and delivered, so it
   failed later in start_workflow instead. So I designed recovery not to depend on it: the DLQ message gives either the
   orderId or a shard + sequence range (read it from the stream within the remaining ~23 h); either way, re-send
   `{orderId}` to the queue, and the order row stays PENDING as the source of truth.
6. *Why filter on INSERT if new orders are always PENDING anyway?* Because every saga step modifies the row, and a
   status that goes back to PENDING (a bug or a manual edit) must not restart a saga. Insert-only means only a new order
   can trigger a saga.

### Debugging story
The first "before" timing run reported 1 of 10 orders as **not** delivered twice (0 start / 0 duplicate log lines),
even though it had exactly 1 execution and 1 DEBIT. The logs did contain both deliveries, from two different SQS message
IDs. The script filtered CloudWatch Logs by a start time taken from the *local* clock, which runs ahead of AWS's
timestamps, so the first order's lines fell before the window. Fix: widen the window by 2 minutes (orderIds are unique,
so nothing else can match). For the MODIFY test, the check now compares this order's log-line count before and after,
with no time window at all, because a clock-dependent window there could hide a line and fake a pass.
(`scripts/outbox_check.py`, `scripts/e2e_test.py`.)

---

## 9. Authentication and row-level isolation (Cognito + JWT authorizer)

### What
- Cognito user pool `order-saga-users` (Essentials plan): email is the username, open self-sign-up with an emailed
  verification code, `PreventUserExistenceErrors` on, MFA off. Managed login (v2) on the free prefix domain
  `order-saga-<account id>.auth.ap-south-1.amazoncognito.com`.
- App client **`spa`** (the storefront): public, no secret, **authorization code + PKCE only**, scopes
  openid/email/profile, callback `<origin>/auth/callback` for the CloudFront URL and `http://localhost:5173`,
  60-minute ID/access tokens, 7-day refresh token with **rotation**, and no usable password API flow
  (`explicit_auth_flows = ["ALLOW_CUSTOM_AUTH"]`, with no custom-auth triggers; see the debugging story).
- App client **`automation`** (scripts and CI only): `ADMIN_USER_PASSWORD_AUTH`, which is an IAM-signed admin call.
- Two test users (A and B) created by `scripts/create_test_users.py`; their passwords are random and live only in
  SSM SecureStrings (`/order-saga/test-users/a|b`). `scripts/auth_tokens.py` signs in and caches the tokens; every
  API-calling script and the CI smoke test uses it.
- Storefront: browsing is public; checkout, wallet, orders and the tracker send signed-out visitors to managed login
  and back. Every API call carries the ID token. Checkout no longer asks for an email: it's the account's.
- API: a **JWT authorizer** (`order-saga-cognito-jwt`) on every route except `GET /products`. The Lambdas take the
  caller **only from the verified claims**: `userId = sub`, `email = email` (required to be `email_verified`).
- **Row-level isolation:** orders store `userId` + `walletId`; `GET /orders` queries only the caller's partition
  (`gsi1pk = USER#<sub>`); `GET /orders/{id}` answers **404, not 403**, for someone else's order; `GET /wallet` and
  `POST /wallet/reset` act only on the caller's wallet (keyed by `sub`) and have no email/user parameter.
- **Idempotency keys are scoped per user** (stored as `<sub>#<Idempotency-Key>`).

### Why (the problem it solves)
Before this, DemoPay wallets were keyed by an email the client typed, so anyone could open or reset anyone's wallet,
and `GET /orders` listed everybody's orders. Identity has to come from something the user proves (a password
behind Cognito), carried as a signed token the API can verify without calling back to Cognito.

### How
- `infra/main/auth.tf`: pool, domain (`managed_login_version = 2`), both clients, and a managed-login style for the
  `spa` client (`aws_cognito_managed_login_branding`, which needed AWS provider 6.x: upgraded in its own commit first,
  with a no-changes plan).
- `config.json` (written by Terraform, so it changes in the same apply as the clients) carries the issuer URL, pool
  ID, SPA client ID and domain. None of them are secrets.
- Frontend `src/auth.tsx`: `oidc-client-ts` + `react-oidc-context`. `UserManager` discovers the endpoints from the
  issuer, adds PKCE, stores the user in `sessionStorage` and renews tokens with the refresh token. Sign-out revokes
  the refresh token, clears local state, then calls Cognito's `/logout?client_id=&logout_uri=` (Cognito's own
  endpoint, not the standard OIDC end-session one).
- `<RequireAuth>` wraps the protected routes and passes the current path through the OIDC `state`, so the user
  lands back where they started; `/auth/callback` only accepts same-site paths from it.
- The **ID token** is sent as `Authorization`: the API needs the user's id (`sub`) and *verified* email, and Cognito
  puts the email only in the ID token. API Gateway's JWT authorizer can validate it (its `aud` is the app client).
- CI: the deploy job runs `create_test_users.py` (idempotent) before the smoke test. The deploy role got
  `cognito-idp:AdminInitiateAuth` and `cognito-idp:ListUserPoolClients`, scoped to pools tagged `Project=aws-order-saga`.
- `aws_apigatewayv2_authorizer.cognito` (`infra/main/api.tf`): type JWT, identity source `$request.header.Authorization`,
  issuer `https://cognito-idp.ap-south-1.amazonaws.com/<pool id>`, audience = both app clients. API Gateway fetches and
  caches the pool's public keys and checks signature, issuer, audience and expiry; a bad token is a 401 before any
  Lambda runs (and before any Lambda cost). Each route in `local.api_routes` has an `auth` flag.
- `src/common/auth.py` `caller_from(event)`: reads `requestContext.authorizer.jwt.claims`; no `sub` → 401 (fails
  closed if a route ever lost its authorizer); no `email` claim (an access token) or `email_verified != "true"` → 403.
  Body fields like `customerEmail`, `userId`, `walletId` and `?email=` are ignored everywhere.
- `create_order`: `userId`, `walletId = sub`, `customerEmail` = the verified claim; `gsi1pk = USER#<sub>`,
  `gsi1sk = <createdAt>#<orderId>` (the suffix keeps two orders in the same millisecond distinct and stably ordered);
  idempotency record key `<sub>#<key>` (the response still echoes the client's own key).
- `process_payment` charges `order.walletId` (set at checkout from the token), never `wallet_id(customerEmail)`.
  `refund_payment` already used `walletId`. An order without one (pre-1.2 rows) is declined, not guessed.
- Legacy rows (email-keyed wallets, orders with `gsi1pk = "ORDER"` and no `userId`) are left untouched; the API can't
  reach them any more (404 / not listed).

### Trade-offs / alternatives considered
- **Authorization code + PKCE vs implicit flow:** implicit returns tokens in the URL fragment (browser history,
  referrers, extensions) and can't use refresh tokens; OAuth 2.0 Security BCP deprecates it. Code + PKCE swaps a
  one-time code for tokens over a back-channel POST, and PKCE stops a stolen code from being redeemed by anyone
  without the verifier. The `spa` client allows only `code`.
- **oidc-client-ts vs Amplify:** the app needs redirect, code exchange, refresh and sign-out. A standard OIDC client
  does exactly that and isn't tied to AWS; it added about 19 kB gzipped (bundle 70.7 → 90.1 kB). Amplify Auth
  brings much more (its own UI and API abstractions) than this needs.
- **Token storage (sessionStorage):** any script on the origin can read it, so an XSS bug could steal a token.
  Mitigated by no third-party scripts, React's escaping, 60-minute tokens, refresh-token rotation and
  sessionStorage (gone when the tab closes). Not done: a Content-Security-Policy header. The stronger design is a
  backend-for-frontend holding tokens in an HttpOnly cookie, which needs a server component.
- **Separate automation client vs password auth on the SPA client:** scripts need a non-interactive sign-in. Putting
  `USER_PASSWORD_AUTH` on the public client would let anyone on the internet try passwords against the API directly.
  `ADMIN_USER_PASSWORD_AUTH` on its own client requires AWS credentials with `cognito-idp:AdminInitiateAuth` on this
  pool, so only the deploy role and the admin user can use it.
- **Test-user passwords outside Terraform:** a password set in Terraform ends up in plain text in the state file.
  SSM SecureString (AWS-managed key, free tier) keeps it encrypted; Secrets Manager is off-limits here (cost) and
  adds rotation this doesn't need.
- **No M2M (client-credentials) client:** Cognito charges for M2M token requests, and the scripts must act *as a
  user* anyway, to prove per-user isolation.
- **Email sender:** Cognito's default sender is free but limited to a few dozen emails per day per account
  (verification codes, password resets). Enough for a demo; production would use SES.
- **`sub` vs email as the key:** an email can change (`attributes_require_verification_before_update`) or be deleted
  and re-registered by someone else; `sub` is immutable and never reused. Keying wallets by email would hand a new
  account the old owner's money and history.
- **404 vs 403 for another user's order:** 403 says "this exists, but not for you", which lets a caller enumerate
  valid orderIds. 404 with the same wording as a missing order reveals nothing. Same principle as
  `PreventUserExistenceErrors` on sign-in.
- **Per-user idempotency scope:** a global key space lets user B replay user A's order (and read its id) just by
  sending A's key, and lets one user's key "block" another's. Scoping by `sub` makes keys private, and two clients
  that happen to pick the same key (e.g. a naive `checkout-1`) can't collide.
- **JWT authorizer vs Lambda authorizer:** the JWT authorizer is configuration, verifies Cognito tokens natively and
  costs nothing extra. A Lambda authorizer is needed only for custom logic (API keys, external IdPs, per-request
  policy) and adds a cold-startable hop plus code to own. Ownership checks stay in the handlers either way, because
  "is this row yours?" needs the data.
- **Per-user GSI partition vs one `ORDER` partition:** one constant key makes every order write and every list read
  hit a single GSI partition (a hot key at scale). `USER#<sub>` spreads them and makes "my orders" a direct Query.
  What's lost: an admin "all orders" view now needs a scan or a separate index (not needed here).

### Numbers
- Frontend bundle with the OIDC libraries: 302.99 kB (90.13 kB gzipped), up from 227.16 kB (70.74 kB gzipped).
- `spa` client live: `InitiateAuth` USER_SRP_AUTH → "USER_SRP_AUTH is not enabled for the client";
  USER_PASSWORD_AUTH → "flow not enabled for this client"; CUSTOM_AUTH → "Custom auth lambda trigger is not configured".
- Unit tests: 81 passed, 94% coverage (adds claims-only identity, 404 for others' orders, wallet isolation,
  per-user idempotency).
- Live E2E after commit B: **14/14** (`docs/evidence/upgrade-1.2-auth.md`, `e2e-failure-tests.md`):
  - no token on any protected route → **401**; tampered signature → 401; payload forged with user B's `sub` → 401;
    access token (no email) → **403**; `GET /products` without a token → 200 (scenario k);
  - A reading B's order `ORD-20261028-007c022f` → **404**, same wording as a missing order; A's list (18) and B's (5)
    share no orderId (l);
  - A's reset with B's ids in the body → A = ₹4,321, **B unchanged** (₹9,98,701, 7 → 7 ledger entries) (m);
  - B reusing A's key → B's own order `ORD-20261028-660da4c0` (202), A's replay → 200 duplicate (n).
- Browser: protected page → managed login with `code_challenge_method=S256` → back on the page; tokens only in
  `sessionStorage`; 0 console errors.

### Likely interview questions
1. *Why PKCE if there's no client secret?* Exactly because there's none: anyone can see a public client's ID, so
   PKCE binds the code to the browser that started the login. A stolen code is useless without the verifier.
2. *Why send the ID token and not the access token?* The API needs the verified email, which Cognito puts only in
   the ID token. The OIDC purist answer is "access tokens for APIs": the alternative is the access token plus a
   pre-token-generation Lambda that adds the email to it, at the cost of one more Lambda.
3. *Where are the tokens stored, and what if there's an XSS bug?* sessionStorage; an XSS bug could read them. The
   damage is limited by 60-minute tokens and refresh-token rotation; the real fix is a BFF with HttpOnly cookies.
4. *How does CI sign in without a browser?* As a real test user, via `AdminInitiateAuth` on a separate client. That
   call is IAM-signed, so the password flow isn't exposed publicly, and the password comes from an SSM SecureString.
5. *Why 404 and not 403 for someone else's order?* So the response can't be used to discover which orderIds exist.
6. *Why key by `sub` and not email?* Emails change and get re-registered; `sub` is immutable and unique per user.
7. *What stops a user from putting someone else's email in the order body?* The handlers never read identity from
   the body: owner, wallet and email all come from the verified token claims. A unit test sends spoofed fields and
   asserts they're ignored.
8. *If the JWT authorizer already checked the token, why check ownership in the Lambda?* The authorizer answers
   "who are you"; only the data can answer "is this order yours". Authentication at the edge, authorization next to
   the data.
9. *What happens to tokens when the user signs out?* The refresh token is revoked at Cognito (token revocation is
   on), local tokens are cleared, and the managed-login session cookie is ended via `/logout`. An already-issued ID
   token stays valid until it expires (≤ 60 min): JWT validation is stateless; that's the trade-off.

### Debugging story
**"No auth flows" turned out to mean "the default auth flows".** The `spa` client was first deployed with
`explicit_auth_flows = []`, meant as "browser sign-in only". The live checks after commit A (`ceebe0e`) showed
`InitiateAuth USER_PASSWORD_AUTH` correctly refused ("USER_PASSWORD_AUTH flow not enabled for this client"), but
`InitiateAuth USER_SRP_AUTH` with the test user's email answered with a `PASSWORD_VERIFIER` challenge. So the SRP
password flow was open on the public client: `describe-user-pool-client` showed `ExplicitAuthFlows: null`, and Cognito
treats "not set" as its defaults (SRP + custom + refresh). Listing `ALLOW_REFRESH_TOKEN_AUTH` wasn't an option: Cognito
rejects it when refresh-token rotation is on. The fix was to list only `ALLOW_CUSTOM_AUTH`, which replaces the
defaults and can't complete because the pool has no custom-auth Lambda triggers. The re-test is in
`docs/evidence/upgrade-1.2-auth.md`. Lesson: verify a deny with a real call; an empty list in IaC isn't proof.

**The fix's own deploy then failed with `AccessDenied` on `cognito-idp:ListUserPoolClients`.** Creating the clients in
commit A never needed it; *updating* one does, because the AWS provider lists the pool's clients first. CloudTrail
showed it as the deploy role's only denied Cognito call (run 40734477999, 17:19:30Z). The plan had passed and the apply
stopped at that call, so nothing had changed. The fix was one action added to the bootstrap policy, scoped like the
others to project-tagged pools, then the deploy re-ran green. Lesson: least-privilege policies written from the
"create" path miss what the "update" path needs; CloudTrail names the exact action.

---

## 10. Known gaps (and where they get fixed)

### What
Design limits found and documented, each with a planned fix.

### Why (the problem it solves)
Being able to say what's wrong with your own design, and how you'd fix it, is a stronger signal than
claiming there are no gaps.

### How
- ~~Outbox gap~~ **fixed in step 1.1**: see section 8.
- **No sweeper for orders stuck in PENDING** if delivery fails beyond the stream's 24 h retention (for example the
  pipe is stopped or broken for over a day, or a record's details in the outbox DLQ are never acted on). The order row
  stays PENDING and nothing re-sends it. Fix: a scheduled sweeper that queries PENDING orders older than N minutes
  (the `gsi1` index already projects `status`) and re-sends `{"orderId": ...}`. That's safe because start_workflow is idempotent.
- ~~Email-keyed wallets, no authentication~~ and ~~constant `gsi1pk` hot partition~~ **fixed in step 1.2**: see section 9.
- **No Content-Security-Policy header** on the storefront. Tokens are in sessionStorage, so XSS is the main token-theft
  risk. Fix: a CloudFront response-headers policy with a strict CSP (`script-src 'self'`, `connect-src` = the API and
  the Cognito domains).
- **ID token used as the API credential** (section 9). Fix if needed: access token + a pre-token-generation trigger
  that adds the verified email.
- Compensation failures are recorded in the execution (`refundError`/`releaseError`) but not alerted on.
- HTTP API has no X-Ray; the SFN segment is missing from the map (section 7).

### Trade-offs / alternatives considered
- Sweeper vs nothing: a sweeper adds a scheduled job and a "how old is stuck?" threshold, but it's the only safety
  net for anything the stream never delivered.

### Numbers
None recorded.

### Likely interview questions
1. *What's the dual-write problem?* Writing to two systems (DB + queue) without a shared transaction: one can
   succeed and the other fail. An outbox makes the DB the single write.
2. *Why is a constant partition key a problem?* All traffic goes to one partition, which has a per-partition
   throughput limit, so it throttles long before the table does.

### Debugging story
None recorded.
