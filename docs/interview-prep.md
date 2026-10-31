# Interview prep: Order Saga

One section per feature, with the same headings each time. Rules for this file:
- **Numbers** are measured results only, with the evidence file they came from. No estimates.
- **Debugging story** is a real incident recorded in `docs/evidence/` or git history, or "None recorded".
- Every feature added or changed updates this file in the same commit (see CLAUDE.md).

Evidence referenced below:
`docs/evidence/phase1-happy-path.md`, `docs/evidence/phase2-failure-tests.md`,
`docs/evidence/e2e-failure-tests.md` (latest e2e run, 8/8, 2026-10-22 13:21 UTC),
`docs/evidence/phase3-monitoring.md`, `docs/evidence/phase5-cicd.md`, `docs/evidence/upgrade-1.1-outbox.md`,
`docs/evidence/upgrade-1.2-auth.md`, `docs/evidence/upgrade-2.0-access-tokens.md`,
`docs/evidence/upgrade-2.1-async-payment.md`, `docs/evidence/upgrade-2.2-holds.md`,
`docs/evidence/upgrade-2.3-fulfillment.md`.

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
- Concurrent oversell race (step 3.1, live): 200 simultaneous buyers on 20 units -> exactly 20 claimed, 180 clean
  out-of-stock, 0 errors; never stock < 0 (section 14).

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
  and back. Every API call carries the **access token** (step 2.0; it was the ID token in 1.2). Checkout no longer
  asks for an email: it's the account's.
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
- Step 1.2 sent the **ID token** as `Authorization`, because Cognito puts the email only in the ID token. Step 2.0
  switched to the **access token**: a pre-token-generation trigger adds `email` + `email_verified` to it (see
  "Access tokens for the API" below).
- CI: the deploy job runs `create_test_users.py` (idempotent) before the smoke test. The deploy role got
  `cognito-idp:AdminInitiateAuth` and `cognito-idp:ListUserPoolClients`, scoped to pools tagged `Project=aws-order-saga`.
- `aws_apigatewayv2_authorizer.cognito` (`infra/main/api.tf`): type JWT, identity source `$request.header.Authorization`,
  issuer `https://cognito-idp.ap-south-1.amazonaws.com/<pool id>`, audience = both app clients. API Gateway fetches and
  caches the pool's public keys and checks signature, issuer, audience and expiry; a bad token is a 401 before any
  Lambda runs (and before any Lambda cost). Each route in `local.api_routes` has an `auth` flag.
- `src/common/auth.py` `caller_from(event)`: reads `requestContext.authorizer.jwt.claims`; no `sub` → 401 (fails
  closed if a route ever lost its authorizer); `token_use != "access"` → 401 (step 2.0); no `email` claim or
  `email_verified != "true"` → 403.
  Body fields like `customerEmail`, `userId`, `walletId` and `?email=` are ignored everywhere.
- `create_order`: `userId`, `walletId = sub`, `customerEmail` = the verified claim; `gsi1pk = USER#<sub>`,
  `gsi1sk = <createdAt>#<orderId>` (the suffix keeps two orders in the same millisecond distinct and stably ordered);
  idempotency record key `<sub>#<key>` (the response still echoes the client's own key).
- `process_payment` charges `order.walletId` (set at checkout from the token), never `wallet_id(customerEmail)`.
  `refund_payment` already used `walletId`. An order without one (pre-1.2 rows) is declined, not guessed.
- Legacy rows (email-keyed wallets, orders with `gsi1pk = "ORDER"` and no `userId`) are left untouched; the API can't
  reach them any more (404 / not listed).

#### Access tokens for the API (step 2.0)
- **Lambda `order-saga-pre-token`**: a Cognito pre-token-generation trigger, event version **V2_0** (the version that
  can change *access* tokens; it needs the Essentials or Plus plan, and the pool is Essentials). Cognito calls it on
  every token issue (sign-in and refresh), right before signing. It copies exactly two attributes into the access
  token's `claimsToAddOrOverride`: `email` and `email_verified` (a JSON boolean, as in the ID token). Nothing else, and
  nothing for the ID token. A user without an email gets no claims (the API then answers 403).
- No AWS calls, no SDK, 5 s timeout (Cognito's limit for triggers), own role with only its log group + X-Ray. The log
  line has the trigger source, client id and `sub`, never the email.
- `aws_lambda_permission.cognito_pre_token`: principal `cognito-idp.amazonaws.com`, `source_arn` = this pool's ARN, so
  no other user pool (in any account) can invoke it.
- **`token_use` validation** in `caller_from`: `access` → continue; `id` → **401** "ID tokens are not accepted: send
  the access token"; anything else → 401. This check is necessary, not decoration: an ID token from the same pool is
  validly signed and its `aud` is one of our clients, so the JWT authorizer lets it through. Only the claim tells the
  two apart.
- Rollout in two commits so nothing broke in between: commit A deployed the trigger and accepted **both** token
  types while the frontend, `scripts/auth_tokens.py` and CI switched to the access token; commit B (after A was green
  and the live e2e passed) removed `id`.
- The JWT authorizer needed no change: HTTP API authorizers match the audience list against `aud` (ID token) **or**
  `client_id` (access token, which has no `aud`).

### Trade-offs / alternatives considered
- **Authorization code + PKCE vs implicit flow:** implicit returns tokens in the URL fragment (browser history,
  referrers, extensions) and can't use refresh tokens; OAuth 2.0 Security BCP deprecates it. Code + PKCE swaps a
  one-time code for tokens over a back-channel POST, and PKCE stops a stolen code from being redeemed by anyone
  without the verifier. The `spa` client allows only `code`.
- **Access token vs ID token for the API (step 2.0):** the two tokens have different audiences and purposes. The
  **ID token** (OIDC) is a statement *to the client app* about who signed in: `aud` = the app's client id, plus
  profile claims (name, email). The **access token** (OAuth 2.0) is a credential *for a resource server*: it carries
  `scope` and `client_id` and is what an API is meant to authorize. Sending ID tokens to APIs blurs that line: any
  service that accepts them accepts a token that was never issued for it, and it can't use scopes to limit what a
  client may do. Step 1.2 sent the ID token only because Cognito puts the email nowhere else.
- **Pre-token trigger vs the API looking the email up:** alternatives were calling Cognito `GetUser` / `AdminGetUser`
  on every request (an extra network hop and a Cognito API quota on the hot path) or caching profiles in a table.
  The trigger costs one tiny Lambda run per sign-in/refresh (not per request), keeps the API stateless, and the
  claim is signed, so it's as trustworthy as `sub`. The price: one more Lambda in the sign-in path (if it fails,
  sign-in fails; it makes no AWS calls so it's hard to break), the email in the token is as fresh as the last
  refresh (≤ 60 min), and V2_0 needs the Essentials plan (V1 can only change ID tokens).
- **Minimal claims:** the trigger adds only `email` and `email_verified`. Access tokens get sent to every API call and
  logged by proxies more often than ID tokens; every extra claim is extra personal data in transit, and the API
  doesn't need a name or phone number.
- **Two-commit rollout vs a big bang:** switching the backend to "access only" in the same deploy as the clients
  would have broken any browser tab still holding an ID-token-sending build until reload. Accepting both for one
  deploy made the switch safe; the second commit then closed the old door.
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

- **Step 2.0 (access tokens):** a fresh access token carries `token_use=access`, `client_id`, `email`,
  `email_verified=true` (JSON boolean) and no other added claim; the ID token is unchanged. Trigger: ~2 ms warm,
  ~86 ms init on a cold start, 33 MB of 256 MB used; Cognito's limit is 5 s.
- Live e2e after commit B: **14/14**; scenario k adds "access token carries the email claims → 200" and "ID token on
  GET /wallet, GET /orders, POST /orders → **401**". UI suite **6/6**, 0 console errors. Unit tests 105, 94.5%.

### Likely interview questions
1. *Why PKCE if there's no client secret?* Exactly because there's none: anyone can see a public client's ID, so
   PKCE binds the code to the browser that started the login. A stolen code is useless without the verifier.
2. *Which token does your API accept, and why?* Only the access token. The ID token is for the client app (its `aud`
   is the app, it describes the user); the access token is the credential for APIs. Cognito access tokens normally
   lack the email, so a pre-token-generation trigger (V2_0) adds `email` + `email_verified` to them. In step 1.2 the
   API took ID tokens for exactly that reason; step 2.0 fixed it.
10. *The JWT authorizer validated the token. Why do you also check `token_use`?* Because an ID token from the same
   pool is also validly signed, unexpired and names our client (in `aud`), so it passes. HTTP API authorizers check
   `aud` *or* `client_id`, so they can't tell the types apart; `token_use` can. Without the check, the "access tokens
   only" rule would be a convention, not enforcement.
11. *How does a pre-token-generation trigger work, and what can go wrong?* Cognito invokes it synchronously before it
   signs tokens, on sign-in and on every refresh; the function returns `claimsToAddOrOverride` for the ID and/or
   access token. Cognito waits up to 5 s; an error or timeout fails the sign-in. Reserved claims (e.g. `sub`, `iss`,
   `client_id`, `token_use`) can't be overridden, so a trigger bug can't change who the user is.
   Only this pool may invoke it (`source_arn` on the Lambda permission).
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
   on), local tokens are cleared, and the managed-login session cookie is ended via `/logout`. An already-issued access
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

**The JWT authorizer happily accepted the wrong token type (step 2.0).** Commit A was deliberately
"accept both"; its e2e run showed `GET /wallet` with the ID token → 200 through the same authorizer as the access
token. That's expected but easy to forget: HTTP API JWT authorizers check the audience list against `aud` *or*
`client_id`, so an ID token (aud = our client) and an access token (client_id = our client) both pass, and nothing in
the API Gateway config can say "access tokens only". So the rule lives in `caller_from` as a `token_use` check, and
commit B's e2e proves it on three routes (401 with "ID tokens are not accepted"). Side finding while decoding the
tokens: the automation client's access token has `scope = aws.cognito.signin.user.admin` (Cognito's self-service
scope, which lets the token call `GetUser`/`UpdateUserAttributes` for its own user). Not a problem here, since the
API never reads scopes, but it's why a real API would define its own resource-server scopes and check them.

## 10. Async payments and webhooks (waitForTaskToken + HMAC + timeout)

### What
Payment works like a real gateway (Razorpay/Stripe): the saga **requests** a payment, **pauses**, and resumes only
when the provider calls our **webhook**.
- `RequestPayment` is a `lambda:invoke.waitForTaskToken` task with `TimeoutSeconds: 120`. Lambda `request_payment`
  creates the payment intent `PI-<orderId>` in `order-saga-payments`, **stores the task token on it**, marks the order
  `PAYMENT_PENDING` ("Awaiting payment confirmation") and sends `{intent, order, wallet, amount}` to SQS
  `order-saga-psp-requests` with `DelaySeconds` 2–5.
- **DemoPay** (`payment_provider`, a mock external PSP) consumes that queue, debits the wallet **once per intent**, and
  POSTs a signed callback to `POST /webhooks/payment`. It also has an idempotent refund API.
- `payment_webhook` (no JWT) verifies the **HMAC-SHA256** signature and timestamp, records the outcome on the intent
  and the order, and calls `SendTaskSuccess` / `SendTaskFailure("PaymentDeclined")`.
- No callback in 120 s → `States.Timeout` → intent `TIMED_OUT` (conditional) → the existing compensation → order
  `FAILED` with "payment timeout". A success that arrives later is **refunded automatically**.
- Secret: SSM SecureString `/order-saga/psp/webhook-secret`, created by `scripts/create_webhook_secret.py` (run by
  Deploy) and cached in memory by both Lambdas. Never in Terraform state, env vars or logs.
- Alarms: `order-saga-psp-dlq-not-empty`, `order-saga-webhook-signature-failures` (log metric filter). Dashboard row 8:
  intent transitions by status, webhook latency, timeouts, signature failures + PSP DLQ.

### Why (the problem it solves)
Real payments are asynchronous: 3-D Secure, UPI approval on a phone, bank processing. A gateway answers "accepted"
and confirms later through a webhook. A synchronous Lambda that "charges and returns" can't model that and would
have to hold a connection open (and pay for it) while waiting. With a task token, Step Functions waits for free for
up to a year: Standard workflows bill per state transition, not per second of waiting.

### How
**Money invariants** (designed first; the e2e suite asserts all four for every scenario, from the wallet ledger and
the payments table):
- **I1** COMPLETED ⇒ exactly one net DEBIT for the amount. **I2** FAILED ⇒ net charge 0. **I3** no intent charged
  twice, no refund issued twice. **I4** every intent ends SUCCEEDED, FAILED, TIMED_OUT or REFUNDED.

How each one holds:
- **I3, provider side:** DemoPay writes `CHARGE#<intent>` (and `REFUND#<intent>`) in `order-saga-psp-transactions` in
  the **same DynamoDB transaction** as the wallet change and the ledger entry, conditional on `attribute_not_exists`.
  A redelivered SQS message, a duplicate request or a concurrent run finds the record and **replays the same outcome**
  (same `paymentId`, same decline). Declines are recorded too, so a top-up between deliveries can't turn a decline
  into a charge.
- **I3, our side:** the intent id is deterministic (`PI-<orderId>`), so a retried step can't create a second intent.
  Every intent transition is a conditional write (`#s = :requested`, `#s <> :refunded`).
- **I1:** the order only reaches `MarkOrderCompleted` through `SendTaskSuccess`, which the webhook sends only after it
  moved the intent REQUESTED → SUCCEEDED (in one transaction with the order's `PAYMENT_CAPTURED`).
- **I2:** every failure path after payment runs `RefundPayment`, which calls DemoPay's idempotent refund. A success
  that arrives after the saga gave up (intent `TIMED_OUT`, or `FAILED` because compensation abandoned it) is refunded
  by the webhook at once.
- **I4:** REQUESTED is left by the webhook (SUCCEEDED/FAILED), by the timeout path (TIMED_OUT) or by compensation
  (FAILED, "abandoned"). A charge discovered later moves it to REFUNDED.

**Races and how they resolve** (all decided by conditional writes; the loser re-reads and takes the other branch):

| Race | Outcome |
|---|---|
| Callback arrives just **before** the timeout, `SendTaskSuccess` just **after** | The intent is SUCCEEDED, so the saga's `MarkPaymentTimedOut` condition fails, and its `RefundPayment` sees SUCCEEDED and refunds. The webhook gets `TaskTimedOut` and **must not** refund as well (it never refunds a SUCCEEDED intent). Net 0. |
| Callback arrives **after** the timeout | The intent is TIMED_OUT, so `REQUESTED → SUCCEEDED` fails; the webhook refunds and marks REFUNDED. Net 0. |
| Saga refund and late-callback refund **at the same time** | Both call DemoPay's refund; `REFUND#<intent>` lets only one credit through; `record_refund` writes once. |
| Duplicate callback | The intent is already final, with `sagaResumedAt`: 200 no-op. |
| Captured, but `SendTaskSuccess` failed transiently | The webhook returns 500 and DemoPay retries; the intent is SUCCEEDED without `sagaResumedAt`, so the retry only resumes. |
| Step retried (new task token) | `request_payment` overwrites the stored token only while the intent is REQUESTED; if it's already final, it answers the new token itself from the stored outcome. |

**Why the task token never leaves our system:** a token is a bearer capability to complete *our* workflow step.
Handing it to a third party would let the provider (or anyone who steals its logs) resume or fail our saga
directly, skipping the signature check, idempotency and amount validation. The provider only knows the intent id;
the intent→token mapping stays in our table.

**Signature:** `X-Signature = hex(HMAC_SHA256(secret, "<X-Timestamp>.<raw body>"))`. It is verified on the **raw
bytes** (re-serialised JSON can differ), with a **±5-minute** timestamp window (replay protection; the timestamp is
inside the signed string, so it can't be changed), and compared with `hmac.compare_digest` (constant time). Missing,
forged, stale or future-dated → 401, logged as `event = webhook_signature_rejected` (the reason only, never the
signature), which feeds the `WebhookSignatureFailures` metric and alarm. A valid signature for an unknown intent →
404, no write. The amount and orderId must match the intent, or 400.

### Trade-offs / alternatives considered
- **Webhook vs polling the provider:** polling adds latency (up to the poll interval), costs requests and Lambda time
  per order per poll, and hits the provider's rate limits at scale. A webhook is immediate. Polling is still the
  right *safety net* (a reconciliation job asking "what happened to intents still REQUESTED?"), which is why the
  timeout and late-refund paths exist.
- **Auto-refund vs "void before capture":** a cancel/void call on timeout would stop a late charge from happening at
  all. Not every payment rail supports it (UPI collect, bank transfers), so a late capture must be handled anyway;
  the auto-refund covers both.
- **SQS between us and DemoPay:** simulates the network hop and gives the provider at-least-once retries for free (5
  receives, then `order-saga-psp-dlq` + alarm). The provider's processing delay is an SQS `DelaySeconds` set by the
  sender, because SQS has no consumer-side delay.
- **Refund API as a Lambda invoke:** IAM-authenticated and synchronous, standing in for an HTTPS call with an API
  key. A real provider would be HTTPS, with the same idempotency key (the intent id) in a header.
- **Separate provider table:** DemoPay's charge records are the provider's state, not ours. Mixing them into
  `order-saga-payments` would let our code "know" things only the provider can know.
- **No GSI on orderId:** the intent id is derived from the orderId, so a GetItem finds it.
- **Secret in SSM, not Secrets Manager:** a SecureString with the AWS-managed key is free; rotation is "delete it and
  re-run the script" (both Lambdas refresh within 5 minutes).
- **Timeout of 120 s:** long enough for a slow provider, short enough that stock isn't held for long. Real systems use
  minutes to hours (UPI collect: up to 10 minutes) plus a reservation TTL (step 2.2).

### Numbers
From `docs/evidence/upgrade-2.1-async-payment.md` (live, 2026-10-29):
- Live e2e **19/19**, with I1–I4 asserted for every order (4 new scenarios: timeout, late, duplicate, bad signature).
- Request → webhook: **p50 5.2 s, max 11.5 s** over 15 payments (includes DemoPay's simulated 2–5 s delay). A normal
  order now takes **6.1 s** end to end, up from **0.56 s** with the synchronous charge: that is the cost of modelling
  a real gateway, and the saga pays nothing while it waits.
- Timeout fired at **120.0 s**; the late payment arrived at **150.2 s** and was refunded at once (ledger DEBIT +
  CREDIT, net ₹0, intent REFUNDED).
- Commit A: unsigned / forged / stale / future requests → **401** ×4, unknown intent with a valid signature → **404**.
- Rollout probe: **32** orders in the half-applied window, all on the old definition, all **net ₹0**; 2 after the
  switch, both COMPLETED.
- Unit tests **166**, coverage **94%**. Extra cost: 2 alarms (~$0.20/month), SQS polling for the new queue (within
  or near the free tier); waiting in Step Functions is free.

### Likely interview questions
1. *What if the webhook is down?* DemoPay's request message isn't deleted, so SQS redelivers it (5 receives, about 10
   minutes), and each delivery replays the same charge outcome (no second debit). Meanwhile the saga times out at
   120 s and compensates. After 5 failures the request lands in `order-saga-psp-dlq` and the alarm fires; redriving it
   replays the callback, which the webhook then treats as a late success and refunds. Money is never lost, only delayed.
2. *What if the callback arrives twice?* The second finds the intent already final and resumed: 200 no-op. 200 and
   not 409, because the provider would otherwise keep retrying a callback we already applied.
3. *What if it arrives after the timeout?* The intent is TIMED_OUT, so the webhook refunds through DemoPay's
   idempotent refund and marks the intent REFUNDED. The order stays FAILED, net charge 0.
4. *Why not poll the provider instead?* See the trade-offs: latency, cost, rate limits. Polling is the fallback, not
   the main path.
5. *Why HMAC and not just "the URL is secret"?* URLs leak (logs, proxies, browser history). HMAC proves who sent the
   body and that it wasn't changed; the timestamp stops replays.
6. *Why a constant-time comparison?* `==` on strings can stop at the first differing byte, so the response time leaks
   how much of a guess was right. `hmac.compare_digest` always compares everything.
7. *What happens to the task token on a retry?* Each attempt gets a new token. `request_payment` overwrites the
   stored token, but only while the intent is still REQUESTED (a conditional write), so a late retry can't clobber a
   finished payment.
8. *Can a callback for one order change another?* No: the intent id, the orderId and the amount in the signed body
   must all match the stored intent.

**Rollout (two commits):** A deployed the provider, webhook, tables, queues, secret and alarms *next to* the old
synchronous `process_payment`, and the live e2e proved the webhook rejects unsigned, forged, stale and future-dated
calls before anything depended on it. B then switched the state machine to `RequestPayment` and removed
`process_payment`. Executions keep the definition they started with (proven live: 19 orders placed before the switch
all ran the old definition, even those finishing after it; 2 placed after ran `RequestPayment` and completed). In a
clean apply Terraform switches the state machine before deleting the old function; when the first apply failed
half-way (see the debugging story) the old-definition orders lost their function and **failed safely**: compensation
ran, every one of them ended with zero net charge and its stock released. The old function's
log group stays under Terraform (`retired_log_groups`) so removing a function never deletes its logs; the 7-day
retention ages them out.

### Debugging story
**A DynamoDB tag broke the deploy, and the fix broke CI.** Commit A's Deploy failed on `order-saga-payments` with
`ValidationException: The Tag Value provided is invalid`; everything else applied. DynamoDB tag values allow only
letters, digits, spaces and `_ . : / = + - @`, and the Description tag contained parentheses (other services had
accepted the same style). The quick fix removed them but left a comment *inside* the `tags = {}` block, which
`terraform fmt` re-aligns, so CI's `fmt -check` failed. A third commit moved the comment above the block. Lessons:
each AWS service validates tags differently, so read the failing resource's limits; and run `terraform fmt -check`
locally before every push, even for a one-line fix.

**The same lesson, one commit later, with a sharper edge.** Commit B's Deploy failed on the state machine's
Description tag (parentheses again: Step Functions allows only `_ . : = + - @` besides letters, digits and spaces).
Terraform had already **deleted `process_payment`** (an independent destroy) but had not switched the definition, so
for a few minutes the live saga pointed at a missing function. Orders in that window failed safely: the Lambda
error was caught by `States.ALL`, compensation ran, nothing was charged. The fix commit restored the deploy. Lesson:
a "remove the old thing" change is safest when the removal can only happen after the switch, so the next removal
of this kind goes in a separate commit after the switch is live.

#### Postmortem: payment step pointed at a deleted function (2026-10-29, ~3.5 min, blameless)
**Summary.** Commit B of step 2.1 (`47fac57`) replaced `process_payment` with `request_payment` and deleted the old
function in the same apply. The apply failed half-way, leaving the live state machine on the old definition with
its payment function already gone.

**Timeline (UTC).**
| Time | Event |
|---|---|
| 10:20:03 | Deploy `40856722473` starts `terraform apply` for commit B (4 add, 29 change, 3 destroy). |
| ~10:22:30 | `order-saga-process-payment` is destroyed (it had no dependents left in the new configuration, so Terraform was free to delete it early). |
| 10:22:31 | First affected order: ProcessPayment fails with `Lambda.ResourceNotFoundException`. |
| 10:22:45 | The state machine update fails: `TagResource ... InvalidParameterValueException` (a `(` in the Description tag). The apply stops; the definition is still the old one. |
| ~10:23 | Detected by the rollout probe and the Deploy watcher; the live definition and the missing function confirmed with the CLI. |
| ~10:24 | Fix `108e8a9` (tag without parentheses) pushed, CI green. |
| ~10:26 | Deploy `40857370694` switches the definition; the next orders complete on RequestPayment. |

**Impact.** 32 orders were created in the window, all by the rollout probe (no customer orders). Every one failed
**safely**: the Lambda error was caught by `States.ALL`, compensation ran (refund no-op, stock released), and each
ended FAILED with **0 ledger entries, net ₹0**. No money moved and no stock leaked; the invariants I1–I4 held.

**Root cause.** `terraform apply` is not atomic. It applies independent changes in dependency order and stops at
the first error without rolling back what already happened. The destroy of the old function did not depend on the
state machine update, so it ran first; the update then failed on a tag value that only the AWS API (not `plan`)
checked, and each AWS service has its own tag character set. Two things combined: a removal in the same apply as
the switch, and a validation that only existed at apply time.

**What went well.** The saga's own failure handling contained the damage (compensation on every error); the probe
and the money-invariant checks made the impact measurable in minutes.

**Fix.** Remove the parentheses (`108e8a9`), redeploy.

**Prevention.**
1. **Expand → migrate → contract (parallel change).** Add the new thing next to the old (expand), switch traffic
   to it and verify live (migrate), and remove the old thing only in a later commit (contract). A failed migrate
   then leaves the old path fully working. Now a CLAUDE.md rule: no removal in the same apply as its switch.
2. **Validate at plan time.** Every Description tag now comes from `module.tags` (`infra/modules/tag_values`),
   whose input validation enforces the strictest set across our services (letters, digits, spaces,
   `_ . : = + - @`, ≤ 256). A bad value fails `terraform plan` before any resource changes. Proven by `terraform
   test` in CI (including this exact value) and by a unit test that fails if a tag is written inline.

## 11. Checkout holds (10-minute reservation with precise expiry)

### What
When a signed-in user opens checkout, their cart is **held for 10 minutes**: the units are set aside so nobody else can
buy them, and a countdown shows the time left. Paying in time consumes the hold; otherwise it is released
automatically, at the expiry second, by a one-time **EventBridge Scheduler** schedule.
- Table `order-saga-holds`: `HOLD-<date>-<random>` items (userId, items, status ACTIVE → CONSUMED / RELEASED /
  EXPIRED, expiresAt, orderId once consumed) plus one pointer item `USER#<sub>` per user with an ACTIVE hold.
- API (JWT, own holds only; someone else's is a 404): `POST /holds`, `GET /holds/current`, `DELETE /holds/{holdId}`
  (Lambda `order-saga-holds-api`).
- Expiry: schedule group `order-saga-holds`, one `at(expiresAt)` schedule per hold, `ActionAfterCompletion: DELETE`,
  invoking `order-saga-hold-expiry` through the role `order-saga-holds-scheduler-role` (may invoke that one function).
- Inventory counters per product: `stock` (available), `held` (in ACTIVE holds), `reserved` (in orders).
- Saga: `POST /orders` takes an optional `holdId`; ReserveInventory consumes the hold (held → reserved)
  instead of decrementing stock again. Orders without a hold use the old path unchanged.
- Storefront: entering checkout holds the cart; a banner counts down mm:ss; at 0 it says "Your hold expired" with
  "Hold again"; leaving the page releases the hold; "Pay" sends the `holdId`.

### Why (the problem it solves)
Without a hold, two shoppers can both see "1 left", both pay, and one of them gets "out of stock" after paying (or
the shop oversells). Holding stock at checkout moves that disappointment to the moment before payment, and the
countdown makes the deal explicit. The hard parts are the edges: releasing on time when the user just walks away,
and never counting a unit twice when "pay", "expire" and "leave" happen at the same moment.

### How
**Creating a hold** (`POST /holds`): validate (≤ 10 products, ≤ 5 units each), price from inventory, release the
caller's previous hold, create the **schedule first**, then ONE `TransactWriteItems`:
1. Put pointer `USER#<sub>` with `attribute_not_exists` (one ACTIVE hold per user, enforced atomically),
2. Put the hold (ACTIVE),
3. per product: `stock = stock - q, held = held + q` with `stock >= q`.

If any product is short, the whole transaction is cancelled (nothing held) and the answer is **409 naming that
product**; the schedule is deleted again. Schedule-first means a crash in between leaves a schedule that fires on a
hold that doesn't exist (a no-op), never a hold without a schedule.

**Every transition out of ACTIVE is one transaction whose first item is the conditional status update**
(`#s = ACTIVE`), together with deleting the pointer and moving the stock:

| Transition | Stock movement | Extra condition |
|---|---|---|
| ACTIVE → CONSUMED (order) | held → reserved (stock NOT decremented again) | `expiresAtEpoch > now` |
| ACTIVE → RELEASED (user/new hold) | held → stock | |
| ACTIVE → EXPIRED (schedule or lazy read) | held → stock | |

**Races:** consume, expire and release can fire at the same moment. DynamoDB transactions are serializable, so
exactly one commits; the others are cancelled *as a whole* (their stock updates never apply) and turn into no-ops
(`lost_the_race` = cancellation code on item 0). New invariant, checked by the e2e run for every product:

> **I5 stock conservation:** seeded stock = `stock` + `held` + `reserved`, and `held` = the units in ACTIVE holds.

**Precise expiry, and the TTL trap.** DynamoDB TTL looks like the obvious tool, but TTL deletes items "typically
within a few days" of expiry; it is a garbage collector, not a timer. A hold "released" by TTL could keep stock
locked for days. Here TTL (`purgeAt` = expiry + 7 days) only cleans up finished records. The release is a one-time
schedule at the exact second. And because a schedule can still be late (or fail), **expiry is also enforced
logically**: an ACTIVE hold past `expiresAt` can't be consumed (the consume condition checks the time), and the
next read of it expires it on the spot ("lazy expiry"). The schedule's job is only to give the stock back promptly.

**Anti-hoarding:** one ACTIVE hold per user (a new hold releases the old one), at most 5 units per product, 10
minutes max. A bot can still create many accounts; per-account limits plus Cognito sign-up verification are the
cheap first line (rate limits per IP via WAF would be next).

**Duration by client:** the storefront (spa app client) always gets 600 s. Only the automation client may ask for
30–600 s, so the e2e suite tests real expiry without waiting 10 minutes. The client is the access token's verified
`client_id` claim, compared with the two client ids stored in SSM by Terraform.

**Ordering with a hold.** `create_order` checks the `holdId` up front: it must be the caller's own hold (anyone
else's, or a missing one, gives the same 400, so hold ids can't be probed), its items must match the order, and it
must not be CONSUMED already. An EXPIRED or RELEASED hold is accepted on purpose: the order still goes ahead and
ReserveInventory reserves afresh. ReserveInventory then tries ONE transaction: the hold `ACTIVE → CONSUMED` (with
`expiresAtEpoch > now`), `held → reserved` per product, and the order `→ RESERVED`. If the hold had ended (or the
transaction loses a race with the expiry), it falls back to the normal conditional decrement, which may raise
OutOfStock if someone else took the units meanwhile; the RESERVED detail says which path ran. An overdue hold whose
schedule hasn't fired yet is expired right there (`expiredBy: reserve_inventory`). Compensation is unchanged:
ReleaseInventory returns `reserved → stock` either way.

**Countdown from server time:** the API returns `expiresAt` and `serverTime`. The browser computes the
offset `serverTime - Date.now()` once and counts down to `expiresAt` in server time, so a phone whose clock is 3
minutes off still shows the right mm:ss. Leaving checkout releases the hold (`DELETE` on unmount, and a
`keepalive` fetch on `pagehide` for a closed tab); if that request is lost, the schedule releases it anyway.
Creates and releases go through a small promise queue, so React StrictMode's double mount can't let an older
create land after a newer one.

**Test-only products stay off the shelf (step 3.1).** The oversell race test needs products of its own (RACE-*), in
the same inventory table so the real hold and saga code runs against them. They carry `listed = false`, and
`GET /products` leaves those out, so shoppers (and the demo) never see them.

### Trade-offs / alternatives considered
| Option | Why not (here) |
|---|---|
| **DynamoDB TTL** as the release | Deletion lags by hours to days; deletes the record instead of returning stock; no hook to run logic. Kept for clean-up only. |
| **SQS delay queue** | `DelaySeconds` max is 15 minutes (fine for 10, but no headroom), no per-message cancel, and a consumer has to poll forever. |
| **Step Functions Wait state** per hold | Works and is precise, but costs ~4 state transitions per hold and an execution per checkout visit; cancelling needs StopExecution. Scheduler is one API call to create and one to delete. |
| **Periodic sweeper** (every minute) | Simple, but release is up to 1 min late, and it scans or queries all holds every minute even when idle. |
| **EventBridge Scheduler one-time schedule** (chosen) | Exact-time `at()`, built-in retries, deletes itself after firing, free tier 14M invocations/month; the trade-off is one more service and IAM role. |
| Reserve stock in the saga only (no holds) | The pre-step-2.2 behaviour: fine for most shops, but a user can lose the item after paying. |

Releasing the old hold before creating the new one means a refused new hold (409) leaves the user with no hold:
acceptable (they were asking to replace it), and it keeps the transaction simple (the same product can't appear twice
in one DynamoDB transaction).

### Numbers
From `docs/evidence/upgrade-2.2-holds.md` (2026-10-29, ap-south-1):
- Live e2e **26/26**: a–s unchanged plus t–z (lifecycle, schedule expiry, race, ownership, I5, order consumes the
  hold, order after expiry).
- Race for the last unit: HTTP codes **[201, 409]**, the 409 names the product, (stock, held) = (0, 1).
- Order with a hold: LAPTOP-STAND (98, 0, 2) → (97, 0, 3): stock taken **once** (at hold time), held → reserved.
- Schedule lag after `expiresAt`: **11.8 s, 20.1 s, 45.9 s** (n = 3, median 20.1 s). Within about a minute, not to
  the second.
- I5 held for all 16 products after the run. Unit tests 217, coverage 94% (41 of them on holds).
- Rollout: commit A 22 added / 17 changed / 0 destroyed; commit B 1 added / 5 changed / 0 destroyed.
- Added idle cost: $0 (Scheduler: 14 M invocations/month free).

### Likely interview questions
1. *Why not just use TTL?* TTL deletion can lag by days, it deletes rather than returning stock, and it can't run
   logic. It is a clean-up tool; the release is a schedule plus logical expiry.
2. *What if the schedule fires late (or not at all)?* Nothing breaks, the stock just comes back later. The hold is
   logically expired at `expiresAt`: consuming it fails (`expiresAtEpoch > now` in the condition) and reading it
   expires it on the spot. Failed invocations are retried by Lambda and Scheduler, and the
   `order-saga-hold-expiry-errors` alarm fires.
3. *What if two users want the last item?* Both `POST /holds` run the conditional decrement `stock >= 1`; DynamoDB
   serializes them, one commits (201), the other's whole transaction is cancelled (409 naming the product). Proven
   live with two concurrent requests.
4. *What if the user pays at 9:59 and the schedule fires at 10:00?* Whichever transaction commits first wins. If the
   consume wins, the expiry finds CONSUMED and does nothing. If the expiry wins, the consume is cancelled and
   ReserveInventory falls back to a normal reservation (or OutOfStock). Stock is never counted twice (I5).
5. *How do you stop hoarding?* One ACTIVE hold per user (pointer item in the same transaction), ≤ 5 units per
   product, 10 minutes max.
6. *Why compute the countdown from server time?* Client clocks are wrong surprisingly often; a countdown from the
   browser clock could show 7 minutes left on an expired hold. The server's `expiresAt` and `serverTime` define it.
7. *Why is the schedule created before the hold?* So there is never a hold without a schedule. The reverse failure
   (a schedule without a hold) is harmless: the expiry Lambda finds nothing and stops.

### Debugging story
**"Precise" expiry wasn't precise to the second.** The design promised release "at the expiry second". The first
live run measured the schedule firing 45.9 s after `expiresAt`, and the next ones 20.1 s and 11.8 s. With
`FlexibleTimeWindow OFF` and an `at(yyyy-mm-ddThh:mm:ss)` time, Scheduler fired within about a minute, not at the
exact second. Nothing broke, because expiry had been built as a logical rule rather than an event: past
`expiresAt` the consume condition refuses the hold, any read expires it, and the countdown hits 0:00 from server
time. The only effect is that other shoppers get the units back up to about a minute late. Lessons: measure the
timer instead of trusting its name (the expiry Lambda logs `expiryLagMs` and the dashboard graphs it), and never let
correctness depend on a timer firing on time.

**A test that owned shared state it didn't own.** Commit A's first e2e run was 23/24: u expected DESK-MAT to return
to exactly (100, 0, 0) but found (99, 0, 1). The stock invariant check (x) passed in the same run, so nothing was
lost. Scenario l had ordered a desk mat during u's 30 s window. The fix was in the test: compare what the hold
controls (held back to its earlier value; stock + reserved unchanged), not the whole counter.

## 12. Per-item fulfillment and partial refunds

### What
After the payment succeeds, each order line is fulfilled on its own. If one line can't be fulfilled (for example
it is found damaged in the warehouse), only that line is refunded and written off. The rest of the order ships, and
the order ends **PARTIALLY_FULFILLED**.
- Lambda `order-saga-fulfill-item`: picks ONE line per call (`reserved` → `sold`). It raises `ItemUnavailable`
  for a damaged line (demo: `simulate: "item_unavailable"`, `simulateLine` 1..n or `"all"`, default the last line).
- Lambda `order-saga-write-off-lines`: moves the failed lines' units `reserved` → `writtenOff`, never back on sale,
  and writes an audit record to the new table `order-saga-write-offs` (orderId, lineId, productId, quantity, reason,
  writtenOffAt).
- DemoPay line refund: `{"operation": "refund", "paymentIntentId", "lineId", "amount"}`. It is idempotent per
  (intent, line), and capped so the running refund total can never exceed the charge.
  `order-saga-refund-payment` with `{"orderId", "lineIds"}` refunds those lines at their **stored** amounts.
- Orders store per-line prices at creation: `lineId` (L1, L2, ...), `unitPrice` and `lineAmount` = quantity ×
  unit price, all from the inventory table. The total is the sum of the lines.
- Inventory counters per product: `stock`, `held`, `reserved`, `sold`, `writtenOff`.
- Saga: after RequestPayment, an inline Map `FulfillItems` over the lines (MaxConcurrency 5), a JSONata Pass
  `SummarizeFulfillment`, then the Choice `FulfillmentOutcome`: all fulfilled → MarkOrderCompleted (unchanged);
  some → PartialRefund → WriteOffLines → MarkOrderPartiallyFulfilled → NotifyCustomerPartial; none → RefundAllLines →
  WriteOffAllLines → DescribeAllUnavailable → MarkOrderFailed ("all items unavailable") → notify.
- API: `GET /orders/{id}` and `GET /orders` return every line (lineId, lineAmount, fulfillment, refundedAmount);
  the list reads them with ONE BatchGetItem for exactly the orders its Query returned (owner only).
- Storefront: each item shows "Delivered" or "Cancelled — refunded ₹X"; the orders list has a "Partially fulfilled"
  badge; the wallet ledger shows the line's CREDIT ("Refund for ORD-… line L2 (…)"). Demo scenario "Item damaged
  (partial refund)".

### Why (the problem it solves)
Reservation is still atomic and all-or-nothing, which is right *before* payment: the customer pays for a
basket that is fully in stock, or for nothing. But some failures happen only *after* payment, in the warehouse, and
they hit one item, not the whole basket. Failing and refunding the whole order for one dented box loses a sale and
annoys the customer. Real shops ship what they can and refund the rest. The hard part is the money: every rupee
refunded must match exactly the lines that didn't ship, even with retries, re-runs and concurrent iterations.

### How
**Prices are fixed at creation.** `create_order` writes each line's `lineAmount` from the server's price. A
refund always uses that stored amount, never a figure from the client or from the state machine's input, so
nobody can change what is refunded later.

**One line per Lambda call, idempotent per line.** `fulfill_item` runs ONE transaction: the line's `fulfillment =
FULFILLED` (+ ITEM_FULFILLED in the history), conditional on the line not being handled yet, together with
`reserved - q, sold + q` (conditional on `reserved >= q`). A retry finds the line handled and reports FULFILLED
again without moving stock. Up to MaxConcurrency lines of the same order update the same order item at once, so
DynamoDB can cancel one with `TransactionConflict`. The Lambda retries that with jitter and raises a retryable
`FulfillmentTransientError` only if the conflicts keep coming.

**Partial refund: idempotent and capped (I7).** DemoPay's CHARGE record keeps `refundedAmount`, the running
total. A line refund is ONE transaction: wallet credit + ledger CREDIT + refund record `REFUND#<intent>#<lineId>`
(`attribute_not_exists`, so once per line) + `refundedAmount += amount`. That last part is conditional on
`refundedAmount <= charged - amount`. DynamoDB can't evaluate `a + b <= c` in a condition, but the charge is
immutable, so the limit `c - b` is computed in code and the check is exact. The old whole-charge refund now means
"refund what is left". It goes through the same counter (guarded by "the total is still what I read"), so line and
whole refunds in any order and any interleaving can't exceed the charge.

**Write-off accounting.** A written-off unit is not available stock; it is a loss. `write_off_lines` puts the
audit record (`attribute_not_exists`, so it doubles as the idempotency record), moves `reserved` → `writtenOff`,
and marks the line WRITTEN_OFF, all in one transaction. A FULFILLED line can never be written off (it fails loudly).
If a later step compensates the whole order, ReleaseInventory takes FULFILLED lines back from `sold` and leaves
written-off units where they are.

**Invariants** (checked by the e2e run for every order and product):
> **I5** seeded stock = `stock` + `held` + `reserved` + `sold` + `writtenOff`, and `writtenOff` = the units in
> write-off records. An order that completed on the pre-2.3 definition keeps its units in `reserved`.
> **I6** net charge = the sum of the FULFILLED line amounts (COMPLETED: the total; FAILED: 0).
> **I7** refunds of an intent never exceed the charge; each line is refunded at most once.

**Inline Map with a Catch per iteration.** Each iteration is `FulfillItem` (Lambda) with Retry on
`FulfillmentTransientError` and a Catch on `States.ALL` that goes to a JSONata Pass `LineUnavailable`, which returns
`{lineId, status: UNAVAILABLE, reason}` (the reason is the Lambda's errorMessage, parsed out of the error Cause). So
an iteration never fails: the Map always finishes with one result per line, and the decision is made afterwards
on the whole picture. The money/stock steps after it (PartialRefund, WriteOffLines, …) deliberately have Retry but
NO Catch: if refunding keeps failing, the execution stops FAILED with the customer still owed money, which raises
an alarm and can be redriven, instead of carrying on to a "PARTIALLY_FULFILLED" that would be a lie. The refund also
refuses a line that is FULFILLED, so a wrong "unavailable" (e.g. the Lambda timed out after its transaction
committed) can't refund an item that shipped. The refund input is only line ids; amounts are read from the order.

**Rollout (expand → migrate).** Commit A deployed the Lambdas, the line refund, the write-off table and per-line
prices, but nothing in the saga called them. The changed live functions (create_order, reserve_inventory,
release_inventory, DemoPay refund) stayed backward compatible: reserve_inventory's new `lines` output is dropped
by the old definition's ResultSelector, and release_inventory's per-line logic only applies when a line has been
fulfilled or written off. `scripts/fulfillment_check.py` drove the new pieces by direct invoke on a real order, and the full
e2e suite re-ran to prove the old path unchanged. Commit B switches the state machine (0 added, 20 changed, 0
destroyed: nothing removed). Executions that are already running keep the definition they started with:
`scripts/inflight_check.py` placed slow orders during B's deploy and read each execution's definition with
`DescribeStateMachineForExecution`. Orders that completed on the old definition keep their units in `reserved`
for good (they were never fulfilled per line), which is why I5 sums all five counters.

### Trade-offs / alternatives considered
| Option | Why not (here) |
|---|---|
| Fail and refund the whole order when one line fails | Simple, but loses the sale of everything that *could* ship. |
| Per-item reservation (reserve what you can) | Moves partial outcomes before payment, where the customer can still choose. All-or-nothing reservation is the clearer contract. |
| **Distributed Map** | For thousands of items or S3 inputs: child executions, more cost, more moving parts. An order has ≤ 20 lines: inline is enough. |
| One Lambda fulfilling all lines in a loop | One crash mid-loop leaves partial state and no per-line retry/visibility in the console. |
| Refund amounts passed in the state | The state is input that a bug or a redrive could change. Stored line amounts are the single source of truth. |
| Return written-off units to stock | Damaged goods would be sold again; the books would hide a real loss. |

### Numbers
From `docs/evidence/upgrade-2.3-fulfillment.md` (2026-10-30, ap-south-1):
- Commit A in isolation (`fulfillment_check.py`) **19/19**. Order ₹42,385 = 3 stored lines; L1 + L3 fulfilled
  concurrently; L2 written off and refunded twice → **one** CREDIT ₹26,990. The I7 probe (refund ₹42,385 more) was
  `RefundRejected`. Net ₹15,395 = L1 + L3.
- Full e2e on commit A (old definition): **26/26**. Old-path COMPLETED orders moved nothing to `sold`.
- Commit B e2e: **29/29** (a–z plus za–zc; first run 28/29, see the debugging story). za: 1 DEBIT ₹14,994 + 1
  CREDIT ₹6,499 (line 2) → **net ₹8,495 = lines 1 + 3 (I6)**. zb: 2 CREDITs, net ₹0, intent REFUNDED. zc: hold
  consumed once. I1–I7 were checked for every order.
- Inline Map duration: **0.14–0.23 s** for 1–3 lines; executions 3.2–6.2 s end to end (the webhook dominates).
- A running execution finished on its old definition (started 4.1 s before the update, ended 6.8 s after).
- Rollout: A 15 added / 22 changed / 0 destroyed; B 0 / 20 / 0; B fix 0 / 1 / 0. Nothing removed.
- Unit tests 266, coverage 93%. The ASL's JSONata is evaluated in tests with jsonata-python.
- States entered per execution (= billed Standard transitions): old definition 5; one-line COMPLETED 9 (+4: Map,
  FulfillItem, SummarizeFulfillment, Choice); 3-line PARTIALLY_FULFILLED 14. Added idle cost: $0.

### Likely interview questions
1. *Why not fail the whole order?* The failure happened after payment and affects one item; the others are
   fine. Partial fulfillment keeps the sale and refunds exactly what didn't ship (I6).
2. *Inline vs Distributed Map?* Inline runs the iterations inside the same execution: no child executions, history
   counted in the parent (≤ 25,000 events), at most 40 iterations running at once. Distributed Map is for huge fan-outs (S3
   inputs, up to 10,000 parallel children). An order has at most 20 lines.
3. *What if the partial refund fails?* It is retried (it is idempotent per line, so retrying is safe). If it
   still fails, the execution FAILS on purpose: the order stays PAYMENT_CAPTURED, and the alarm
   `order-saga-refund-or-write-off-errors` fires. After the fix, an operator **redrives** the execution from the
   failed state. The lines already refunded are no-ops; only the missing ones move money.
4. *What if fulfillment retries after a refund?* A refunded line is written off, and fulfill_item refuses a
   WRITTEN_OFF line (`ItemUnavailable`), so it can't be sold after its money went back. A FULFILLED line can't be
   written off. Each line moves exactly once: FULFILLED or WRITTEN_OFF, never both.
5. *How can refunds never exceed the charge, even concurrently?* One running total on the charge record, updated
   in the same transaction as the money, conditional on the limit. Two concurrent refunds serialize: the second
   sees the first one's total.

### Debugging story
**A new counter broke an old test.** B's first live run was 28/29. Scenario u (a 30 s hold expires) expected the
desk mat's "stock + reserved" to be back at 100 and found 99. I5 passed in the same run, so no unit was lost.
Scenario l buys a desk mat during u's window, and since B that unit ends in `sold`, a counter u's sum didn't include.
That's the same root cause as 2.2's u failure: a test asserted on shared state it didn't own. The fix sums every
counter except `held`. Lesson: when you add a state to a conservation law, grep every test that adds up the old states.

**The proof that wasn't.** To show that running executions keep their definition, `inflight_check.py` placed slow
orders during B's deploy, and the result was "0 executions straddled the update". The probe product (USB-MIC) is
seeded with only 18 units. It ran out 1.5 min before the update, so every execution failed in 0.3 s at
ReserveInventory. The check was re-run, with a 100-unit product and a definition-to-definition comparison, during the
next deploy (also a real definition change), and passed. Report the inconclusive run as inconclusive.

## 13. Customer cancellation mid-saga

### What
A customer can cancel their own order until the warehouse starts on it. Money and stock always end up right, even
when Cancel and the payment webhook arrive at the same instant.
- `POST /orders/{id}/cancel` (Cognito JWT, owner only; anyone else gets 404, not 403). Lambda `order-saga-cancel-order`.
  Idempotent: a repeat gets the same answer (202 while cancelling, 200 once CANCELLED).
- The window: waiting for payment (RESERVED, PAYMENT_RETRY, PAYMENT_PENDING) → cancel, nothing charged. Paid but
  not fulfilling yet (PAYMENT_CAPTURED) → cancel, full refund to the wallet. FULFILLING or terminal → 409
  `TOO_LATE_TO_CANCEL` (recorded once in the history). Orders on an older definition → 409 `NOT_CANCELLABLE`.
- New statuses: `FULFILLING` (set by the new saga step BeginFulfillment, Lambda `order-saga-begin-fulfillment`),
  `CANCEL_REQUESTED`, and the terminal `CANCELLED` (distinct from FAILED). Every change is in statusHistory.
- Saga cancel branch: RefundWhatIsLeft (refund-payment: void at DemoPay, then refund what is left of any charge) →
  ReleaseInventory → MarkOrderCancelled → NotifyCustomerCancelled. Every step retries; none has a Catch.
- DemoPay got a **void** operation ("don't take this payment"), so cancelling while the payment is pending
  really takes nothing.
- Demo controls: `payment_slow` (DemoPay answers after 20 s), `fulfillment_slow` (10 s waits before and after
  BeginFulfillment), and the test-only `payment_manual` (the test harness triggers DemoPay's charge itself, to race it
  against a cancel).
- Invariants: **I8** a CANCELLED order has net charge ₹0 and all its stock back in `stock`. **I9** cancel and
  payment never both win: CANCELLED with ₹0, or the order continued normally and the cancel was rejected.

### Why (the problem it solves)
Customers change their minds, and the cheapest moment to cancel is before anything ships. But "cancel" arrives
from outside the saga, at any moment: while the saga is paused waiting for the payment provider, a millisecond
before or after the provider's success webhook, or just as the warehouse starts. If both cancel and payment
"win", the customer is charged for a cancelled order or gets an item for free. The design has to make every
interleaving end in exactly one of two outcomes.

### How
**One conditional write decides each race.** All three contenders write the same DynamoDB item, the order:
- Cancel: `SET status = CANCEL_REQUESTED, cancelRequestedAt` IF status is in the window AND no cancelRequestedAt AND
  `cancellable = true`.
- Payment webhook (capture or decline, in the same transaction as the payment intent): IF `attribute_not_exists(cancelRequestedAt)`.
  The condition is part of the transaction's Update on the order, so it runs under the webhook's existing
  `dynamodb:UpdateItem` permission. The webhook's new `dynamodb:GetItem` on orders is only for reading the order
  after the capture loses, to confirm a cancel (not a stale intent) is why.
- BeginFulfillment: `PAYMENT_CAPTURED → FULFILLING` IF status = PAYMENT_CAPTURED AND no cancelRequestedAt.
DynamoDB serializes writes to one item, so exactly one condition passes first and the others see its result.

**Reaching a saga that is paused on the payment.** The payment step is `lambda:invoke.waitForTaskToken`; its token is
stored on the payment intent (PI-orderId). The cancel Lambda calls **SendTaskFailure** with error `OrderCancelled`.
The state machine has a separate Catch for `OrderCancelled` (before the normal payment-failure Catch) that goes to
the cancel branch. If the token was already answered (the webhook got there first, or a retry replaced it),
SendTaskFailure returns `TaskTimedOut` / `InvalidToken`: the race was lost or is already handled, not a crash.
request_payment also refuses to run for a cancelled order (`OrderCancelled`), and its status writes are conditional,
so a cancel that lands mid-request is never overwritten by PAYMENT_PENDING.
A cancel can also land at the very moment the 120 s payment timeout fires: SendTaskFailure then finds the token
timed out and the saga takes the timeout path. So no failure path goes straight to MarkOrderFailed: it first reads
the order (`CheckCancelBeforeFailing`, a direct consistent `dynamodb:getItem` of `cancelRequestedAt`), and a Choice
sends a cancel-requested order to the cancel branch instead: void/refund what's left, release the stock, CANCELLED.
A unit test walks that path through the real definition (`test_saga_definition.py`).

**The four interleavings.**
1. Cancel, then webhook: the capture transaction fails on the order condition, so the intent stays REQUESTED. The
   webhook closes it as FAILED (cancelled), does NOT call SendTaskSuccess, and refunds the charge at once.
2. Webhook, then cancel (paid, not fulfilling): the saga resumes; BeginFulfillment's condition fails because of
   cancelRequestedAt and it returns `CANCEL_REQUESTED`; a Choice takes the cancel branch, which refunds everything.
3. Webhook, BeginFulfillment, then cancel: the cancel's condition fails (FULFILLING): 409, the order completes.
4. Cancel before DemoPay even charged: the cancel branch voids the intent at DemoPay first (a conditional put of
   the CHARGE record with outcome VOIDED). The charge request still queued at DemoPay finds VOIDED and takes nothing.

**Refund what's left (I7).** The cancel branch and the webhook may both try to refund the same late charge. Both call
DemoPay's "refund the remainder", which is idempotent per intent and capped by the charge's running refund total
(step 2.3). So the money goes back exactly once, and never more than was charged, whatever the order.

**Orders already running on the old definition.** The new definition passes `cancellable: true` to ReserveInventory,
which stamps the order in the same write that marks it RESERVED. The cancel API refuses unstamped orders. Stamping
in create_order would have been wrong: an order created a second before the deploy would be stamped but run on the
old definition, which has no `OrderCancelled` Catch (its States.ALL Catch would turn the cancel into a FAILED order).

**Checkout holds.** An order placed from a hold consumed it at reservation (hold CONSUMED, units held → reserved).
Cancelling releases reserved → stock once (release_inventory is idempotent), and the hold's expiry schedule finds a
CONSUMED hold and does nothing, so the stock comes back exactly once.

**Rollout (expand → migrate → switch).** Commit A deployed the cancel Lambda behind `CANCEL_ENABLED=false` (503),
BeginFulfillment (not yet called), the webhook's conditional write, the void, the stamp support, IAM and the
alarm. All of it is backward compatible with the running definition, proven by the full e2e suite. Commit B switched the state
machine and the flag in one apply.

### Trade-offs / alternatives considered
| Option | Why not (here) |
|---|---|
| **StopExecution** | Ends the execution immediately. No Catch runs, so no compensation: the stock stays reserved and a charge stays taken. A cancel must be a normal path through the saga. |
| Cancel at any time, then refund + restock | After picking starts, the goods are moving; unpicking is a return, a different process. Closing the window at FULFILLING keeps the saga honest. |
| A lock or a "cancel queue" | One conditional write on the order item already serializes the contenders; a lock adds a failure mode (who releases it?). |
| Webhook checks status first, then captures | Check-then-act: the cancel can land between the two. The condition must be inside the write. |
| Let the late charge happen and refund it | Correct, but the customer sees a debit and a credit for an order they cancelled. The void avoids it in the common case; the refund stays as the safety net for the real race. |
| Stamp `cancellable` at order creation | The order is created before its execution starts, so it can't know which definition will run it (see How). |

### Numbers
Live, 2026-10-30 (`docs/evidence/upgrade-2.4-cancellation.md`):
- **Race, 20 orders** (cancel API and DemoPay's charge fired at the same moment): 14 cancel won with nothing charged,
  4 cancel won and the losing webhook refunded the charge, 2 payment won and the cancel got 409. **0 with both.**
  Every order passed I1-I9.
- **Cancel -> CANCELLED:** 0.35 s while waiting for payment (zd), 0.52 s for an order from a checkout hold (zh),
  10.18 s after payment (ze: a paid order isn't waiting on a token, so the saga acts at BeginFulfillment, after the
  10 s demo Wait).
- **e2e 35/35** on commit B (29 earlier scenarios + 6 cancel scenarios), and 35/35 again on the B fix deploy;
  29/29 on commit A (nothing changed).
  **327 unit tests**, 93% coverage. UI suite 10/10.
- **Rollout:** 13 orders on the old definition asked to cancel during the Deploy, all 409 NOT_CANCELLABLE, all
  COMPLETED; 2 executions straddled the update and finished on the old definition.
- **Legacy cleanup:** 505 orders scanned, 233 legacy COMPLETED orders marked, 0 units moved (all reserved before the
  last re-seed); the stock check passed before and after.

### Likely interview questions
1. *Why SendTaskFailure and not StopExecution?* StopExecution aborts: no Catch, no compensation, so reserved stock and
   a captured payment would be left behind. SendTaskFailure fails just the payment wait with a named error,
   `OrderCancelled`, which the state machine catches like any other business error and turns into the cancel branch
   (refund, release, CANCELLED, email). The saga stays in charge of its own clean-up.
2. *How do you resolve cancel vs payment arriving together?* Both are conditional writes on the same DynamoDB item.
   Cancel requires the order to be in the window and not cancelled; capture requires "no cancelRequestedAt".
   DynamoDB applies one first; the other's condition fails. The loser never acts on the saga: a losing webhook doesn't
   call SendTaskSuccess, and a losing cancel returns 409.
3. *What if the payment is captured after the cancel?* The webhook's capture fails on the order condition, so the
   order isn't marked paid and the saga isn't resumed. The webhook refunds the charge through DemoPay's idempotent
   "refund what's left", so even if the saga's cancel branch refunds at the same moment, the money goes back once (I7).
   Before that, the cancel branch voids the intent, so in most cases DemoPay never charges at all.
4. *Why can't you cancel during fulfillment?* Once the warehouse starts picking, the goods are moving; undoing that
   is a return, not a cancellation. BeginFulfillment is the point of no return: one conditional write that the cancel
   API's write can't overtake. After it, cancel gets 409 TOO_LATE_TO_CANCEL and the order completes normally.
5. *How did you handle orders already running on the old definition?* A running Standard execution keeps the
   definition it started with. Those executions have no `OrderCancelled` Catch, so cancelling them would turn into a
   FAILED order. The new definition stamps `cancellable` on the order itself (in ReserveInventory), and the API answers
   409 NOT_CANCELLABLE for anything unstamped. The stamp records the definition the execution really runs.

### Debugging story
**A flaky DLQ test.** On commit A, which changed nothing on the poison path, scenario g failed: "message NOT in DLQ
within 5 min". The start_workflow logs showed the three failed receives, so the message had to be somewhere.
Receiving from the DLQ 30 times found 27 distinct messages, this one among them. The DLQ is never purged (it stays
for the demo), and the test peeked once per loop with `MaxNumberOfMessages=10`. A receive returns at most 10 messages, in
no particular order, and with `VisibilityTimeout=0` nothing it returned is hidden, so the next peek can return the
same 10 again: with 27 queued, the one you want can be missed every time. A fix with "peek more often"
still only lowers the odds as the queue grows. The deterministic version: (1) record the DLQ count before placing
the order and assert it rose by exactly 1; (2) sweep: receive with `VisibilityTimeout=30`, so each receive returns
only messages not seen yet, until the order's message is found or every message has been seen; then set every
received message's visibility back to 0. Nothing is deleted, and the queue looks exactly as before.

**What the rollout check found.** The in-flight check, running during commit B's Deploy, showed the cancel Lambda
switched on about 2 minutes before the state machine updated, in the same `terraform apply`. Terraform updates
independent resources in parallel, in no promised order, so for those 2 minutes the API accepted cancels while every
execution still ran the old definition (no `OrderCancelled` Catch: a cancel would have become a FAILED order). The
`cancellable` stamp, written by the new definition's ReserveInventory, is what kept them safe: all 13 old orders
asked were refused with 409 NOT_CANCELLABLE. Lesson: a feature flag and the code it guards can't be assumed to
switch together; the guard has to be a fact on the data itself.

## 14. Oversell race test

### What
`scripts/oversell_race.py` fires hundreds of real, signed requests at the LIVE API in the same instant, all trying to
claim the last units of a product, and proves that exactly the available units are claimed, every other buyer gets a
clean out-of-stock answer, nobody is charged for a unit they didn't get, and all the stock comes back afterwards. A
local negative control (`tests/race/test_oversell_negative_control.py`) proves the same race catches a broken
implementation.

### Why (the problem it solves)
"We use a conditional write, so we can't oversell" is a claim; a flash sale is where it gets tested. Concurrency bugs
don't show up in single-request tests or code review, and a race test that has never been seen failing proves nothing.

### How
- **Truly simultaneous:** every request is built and signed (Cognito access token fetched beforehand), its TCP + TLS
  connection opened, then a `threading.Barrier` releases all of them together: 200 requests left within ~50 ms.
- **Distinct buyers:** one ACTIVE hold per user is a product rule, so each hold attempt has its own Cognito test buyer
  (160 in all, made exactly like test users A/B: example.com address, password only in an SSM SecureString).
- **Two paths at once:** checkout holds (`POST /holds`, an instant 201 or 409) and direct orders (`POST /orders`; the
  stock answer comes later from the saga: RESERVED, or FAILED with OUT_OF_STOCK).
- **Classification:** CLAIMED | OUT_OF_STOCK | THROTTLED | ERROR. A 429 is retried with full-jitter backoff until a
  real answer arrives and is counted separately, never as out of stock.
- **Sampler:** consistent reads of the race products every 200 ms record the lowest `stock` and the highest claimed
  ever seen, and check I5 (stock + held + reserved + sold + writtenOff = seed) on every sample.
- **Recovery:** winners are cancelled (direct orders use `payment_manual`, so DemoPay never charges them) or left to
  expire on their EventBridge Scheduler schedules; then every product must be back at its seed with held = 0.
- **Test products off the shelf:** RACE-1 / RACE-X / RACE-Y carry `listed = false`, so `GET /products` hides them.
- **Negative control:** `BrokenReserve` (test-only) reads the stock, checks it, sleeps a few ms, then writes without a
  condition. The same 50-thread race on 5 units against moto must oversell with it and claim exactly 5 with the real
  `reserve_inventory` handler. Marker `race`, in `pytest.ini` testpaths, so every CI run includes it (~12 s).

### Trade-offs / alternatives considered
- **Conditional write vs a lock** (a lock row, Redis `SETNX`, a mutex): a lock needs acquire, release, a lease for
  crashed holders, and a second store; every buyer waits in line even when there is plenty of stock. The condition
  `stock >= :qty` is checked and applied atomically by DynamoDB in one request: no lock to leak, and losers learn at once.
- **Retrying TransactionConflict vs failing fast:** retries add up to ~5.6 s of worst-case latency for a few buyers;
  failing fast would send them away from stock that is still there. Retrying is safe because a cancelled transaction
  applied nothing and every transaction carries its own conditions.
- **503 vs 409 when conflicts never clear:** a consistent read decides. Answering "sold out" for a busy product loses
  a sale; answering "busy, retry" for a sold-out product only costs one more request.
- **Why that read can't cause an oversell (step 3.2 follow-up):** fix 2's direct stock read only CHOOSES THE ANSWER
  (409 vs 503) after the claim already failed; it never claims stock and writes nothing. Every unit is still claimed
  only by the conditional write (`stock >= :qty`). A stale or racing read can at worst pick the wrong one of two
  refusals ("sold out" vs "busy"): nobody gets a unit from it, so it can't oversell.
- **The storefront's side of a 503 (step 3.2):** `frontend/src/retry.ts` shows "The store is busy, retrying… (attempt n
  of 4)" and retries POST /holds and POST /orders with backoff (the server's Retry-After, else 0.5/1/2 s with jitter).
  An order keeps ONE Idempotency-Key across every try, so a retry can never create a second order. Only 503 is
  retried; 409 is a real answer. Vitest unit tests + a capture_ui scenario that fakes two 503s in the browser.
- **Hot item:** every buyer of one product writes the same DynamoDB item (~1,000 WCU/s per partition). Fine for 200
  buyers; a much bigger flash sale would split stock into N sub-counters (buckets) and pick one at random.
- **Live test vs only unit tests:** the live run costs ~$0.05 and 15 minutes (mostly hold expiry) but tests the real
  DynamoDB concurrency control, cold starts and API Gateway, which moto cannot.

### Numbers
- Final run `after-fix-2` (`docs/evidence/upgrade-3.1-oversell.md`): round 1, 200 attempts within 63 ms on 20 units ->
  **20 claimed, 180 clean out-of-stock, 0 errors, 0 throttled**; round 2, 100 two-item carts within 37 ms on 10 + 10 ->
  **10 carts claimed, 0 half carts, 0 errors**.
- Sampler: min stock 0, max claimed 20 / 10 / 10, I5 on every one of 108 samples.
- Hold latency p50 / p95 / max: 1375 / 2004 / 3040 ms (round 1, ~150 cold starts), 546 / 909 / 1571 ms (round 2).
- Server-side conflict retries: 3 holds (round 1) + 1 hold (round 2), 1 retry each.
- 90 losing direct orders: FAILED, out of stock, net ₹0; I1-I9 hold for all 90.
- Recovery: back to the seeded stock, held 0, 638 s after the last hold (holds last 600 s).
- Before the fix: 112 phantom out-of-stock answers (409 with 3-14 units left). After fix 1: 0, but 1 hold per round
  answered 503. After fix 2: 0 and 0.
- Negative control: BrokenReserve claimed 40-50 of 5 units (stock down to -45); the real code exactly 5.
- Peak Lambda concurrency 200 of 400; API stage burst 100 / 50 rps; 0 throttles observed.

### Likely interview questions
1. *How do you guarantee no overselling under concurrency?* Every claim of stock is one DynamoDB write whose condition
   (`stock >= :qty`) is evaluated atomically with the decrement; multi-item carts put all lines in one
   TransactWriteItems, so they all succeed or none do. There is no read-then-write window to race in. Proven live: 200
   simultaneous buyers on 20 units -> exactly 20, a sampler never saw stock below 0.
2. *Why a conditional write and not a lock?* A lock adds a second round trip, a lease or timeout for crashed holders,
   and serialises every buyer even when stock is plentiful. The condition is the lock, scoped to one item for one
   request, held by DynamoDB itself, so nothing can leak.
3. *What is a TransactionConflict and how do you handle it?* DynamoDB transactions are optimistic: if two touch the
   same item at the same moment, one is cancelled with reason `TransactionConflict`. Nothing was written and no
   condition failed. We retry with full-jitter backoff (10 tries, 50 ms to 1 s); only `ConditionalCheckFailed` means out
   of stock. If conflicts never clear, a consistent read decides between 409 (really short) and 503 + Retry-After.
4. *How did you prove the test can fail?* A negative control: a deliberately broken reserve (read, check, write without
   a condition) in the same thread race oversells (40-50 of 5), and the real code claims exactly 5. And the live test
   did fail for real the first time: it caught 112 false out-of-stock answers.
5. *What did throttling look like and how did you separate it from stock rejections?* The harness classifies by
   response: 429 / TooManyRequests is THROTTLED and retried with jittered backoff until a real 201/409 arrives, and is
   reported in its own column; only a 409 (or a saga FAILED with OUT_OF_STOCK) counts as out of stock. In practice 0
   requests were throttled (stage burst 100, Lambda peak 200 of 400), so the throttle path stayed ready but unused.
   Since step 3.2 a unit test (`tests/unit/test_race_harness.py`) feeds the real `send()` fake 429s: they are retried,
   counted as THROTTLED, and only the answer after them (201, or a 409 out of stock) becomes the outcome; a request
   throttled on every try ends as ERROR, never OUT_OF_STOCK.

### Debugging story
The first live run (`docs/evidence/upgrade-3.1/before-fix.md`) passed the headline check, exactly 20 of 20 claimed
and never more, but the harness also asks every 409 how much stock was left: **112 holds were refused "not enough
stock" with 3-14 units still available**, and 5 direct orders failed "Insufficient stock for: one or more items". The
cause: DynamoDB cancels one of two transactions that touch the same item at the same moment with the reason
`TransactionConflict`; nothing was written and no condition failed, but the code read every cancelled transaction as
"out of stock". Nobody was oversold or charged, but real buyers were turned away from a product that still had stock.

The fix (`src/common/transact.py`, a separate commit): `transact_write` retries a transaction while any cancellation
reason is `TransactionConflict` (10 tries, full-jitter backoff from 50 ms, capped at 1 s: at most ~5.6 s). Retrying is
safe because a cancelled transaction applied nothing and every one of these transactions is guarded by conditions. Only
a `ConditionalCheckFailed` on a stock item is out of stock now. If conflicts never clear, a hold does a consistent read:
stock really short -> a clean 409; stock still there -> **503 + Retry-After** (busy is never reported as sold out). A
reservation raises a Lambda error, not OutOfStock. The first version (8 tries, 20-400 ms) still let 1 of ~150 holds
per round run out of tries with a 503 in run `after-fix-1`; the wider budget plus the read is the second fix. Used on every
stock path: create / release / expire / consume a hold, reserve, release (fulfill_item and write_off_lines already had
their own conflict loops). 8 unit tests in `tests/unit/test_transact.py`.

## 15. Known gaps (and where they get fixed)

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
- ~~ID token used as the API credential~~ **fixed in step 2.0**: access tokens only, with a pre-token-generation
  trigger (section 9).
- **A charge whose callback never arrives** (webhook down for longer than DemoPay's 5 retries) leaves a debit for a
  FAILED order until someone redrives `order-saga-psp-dlq` (the alarm says so). Since step 3.2 the hourly invariant
  auditor DETECTS it (I2: a FAILED order with net charge > 0 -> alarm `order-saga-invariant-violation`, section 16);
  it does not repair it. Remaining fix: an automatic refund for charges the auditor finds on failed orders.
- Compensation failures are recorded in the execution (`refundError`/`releaseError`). Since step 2.3, refund and
  write-off Lambda errors raise the alarm `order-saga-refund-or-write-off-errors`; since step 2.4, ReleaseInventory,
  BeginFulfillment and cancel-API errors raise `order-saga-cancellation-errors`.
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

## 16. Chaos testing and reconciliation

### What
Two things, built together in step 3.2:
- **An invariant auditor**, a reconciliation job (Lambda `order-saga-invariant-auditor`, hourly via EventBridge
  Scheduler, also `scripts/audit_invariants.py`). It re-checks I1-I9 over everything stored: orders, payment intents,
  DemoPay's own charge/refund records, the customers' wallet ledger, the five stock counters per product, holds and
  write-off records. Findings are VIOLATION (money or stock doesn't add up: always a bug) or STUCK (an order not
  terminal 30+ minutes after creation, with its execution status). Metrics `OrderSaga/Audit`, alarms
  `order-saga-invariant-violation` and `order-saga-stuck-orders`.
- **Chaos experiments** that break things on purpose while traffic flows: injected Lambda faults (E1 errors, E2 delays,
  E5 refund outage; designed for AWS FIS, built ourselves when FIS turned out to be unavailable, see below),
  test-only crash-after-write switches (E3), duplicate deliveries (E4), with the auditor watching.

### Why (the problem it solves)
Every saga step is designed to be idempotent and every money movement exactly-once. Those are claims; failures in
production are partial (a Lambda dies after its write but before it returns), duplicated (SQS, webhooks and users all
retry) and slow (a provider answers after the timeout). The auditor is the independent check: it doesn't trust the
code that wrote the data, it re-derives the books, like a finance team reconciling bank statements against orders.

### How
- **Auditor, read-only:** paginated, strongly consistent scans of 7 tables. Per order: I1/I2/I6 (net charge = what was
  delivered), I3 (at most one DEBIT, each refund once, and every ledger entry matched 1:1 with a DemoPay record), I4,
  I7, I8, I9, and "a terminal order holds no reservation". Per product (I5): the five counters add up to `seededStock`
  (exact: every stock move is one transaction on one item), and each counter is explained by the records (held =
  ACTIVE holds, reserved = open reservations, sold = fulfilled lines, writtenOff = audit records).
- **Live data, not a snapshot:** in-flight orders (< 30 min) are skipped; anything changed in the last 2 minutes is
  "settling"; and a violation must appear in two audits 10 s apart to count, so a refund landing between two scans
  can't raise a false alarm.
- **Legacy shapes:** pre-DemoPay orders (no money), pre-2.1 direct debits (no intent), pre-2.3 refunds (no running
  `refundedAmount`), pre-2.3 COMPLETED orders (no per-line state; reservations before the last seed are ignored), poison
  orders parked in the DLQ by design (PARKED, not STUCK).
- **Fault injection (E1/E2/E5), FIS's contract built in-house:** the plan was AWS FIS (extension layer on the 9 saga
  Lambdas, 3 experiment templates). The first deploy failed: the account is on the **AWS Free plan**, and every FIS
  call (even `ListActions` with the admin user) answers `SubscriptionRequiredException`. Rather than upgrade the
  account plan, `src/common/chaos.py` gained an injector that mirrors FIS's Lambda actions:
  - *configuration*: one S3 object, `faults/active.json` in a private SSE-S3 bucket (`run`, `functions`,
    `action` = error | delay, `percent`, `delayMs`, `startsAt`, `expiresAt`), written by `scripts/chaos_run.py`;
  - *rate*: each target invocation rolls against `percent` (FIS: `invocationPercentage`); *error* fails before any
    write (FIS: `invocation-error` with `preventExecution`), *delay* sleeps first (FIS: `invocation-add-delay`);
  - *duration*: a configuration longer than 15 minutes, or past `expiresAt`, is ignored by the Lambdas themselves,
    so faults switch off even if the harness dies (FIS: the action's `duration`);
  - *stop condition*: the harness polls `order-saga-invariant-violation` every 15 s and deletes the configuration
    when it fires (FIS: a stop-condition alarm on the template); Lambdas re-read it every 30 s (FIS extension: 60 s);
  - *blast radius, narrower than FIS*: only orders created by that harness run (`chaosRun` = the run id) are
    affected; FIS would hit a percentage of ALL invocations, storefront orders included;
  - *idle cost*: gated by `CHAOS_ENABLED`; while it is false the hook returns without reading S3 or the order.
  The FIS layer, wrapper variables, role and templates were removed in the same fix commit (nothing half-applied);
  the bucket stayed for the injector.
- **Crash-after-write switches:** `src/common/chaos.py`. Only when `CHAOS_ENABLED=true` (Terraform variable, default
  false) AND the order carries `chaos = "crash_after:<point>"` (refused by POST /orders while disabled). The handler
  commits its write, then raises before returning; it fires only in the invocation that did the write.

### Trade-offs / alternatives considered
- **Full scan hourly vs streams:** at this size (~1,000 orders) a full scan is seconds and cents, and it is the
  simplest correct reconciliation. At scale: incremental, stream-based reconciliation (DynamoDB Streams of orders,
  intents and ledger into per-order running balances; only orders that changed are re-checked).
- **Detect vs repair:** the auditor never repairs. A job that "fixes" money on its own can turn one bug into two;
  findings page a human with a runbook (redrive for parked executions).
- **FIS vs in-house injector vs code switches:** FIS needs no code change and is the honest "real platform" fault,
  but hits a percentage of ALL invocations and wasn't available on the Free plan. The injector is ~100 lines that
  ship in every saga Lambda (inert unless `CHAOS_ENABLED`), with a narrower blast radius than FIS; the cost is that
  it injects at the top of my handler, not in the Lambda runtime, so it can't simulate an init/runtime crash.
  Crash-after-write switches hit one chosen order at one chosen point INSIDE a handler, which neither FIS nor the
  injector can.
- **Upgrade the account vs build it:** upgrading to the Paid plan would have made FIS work in minutes, but is
  irreversible and removes the Free plan's spending cap. A course project keeps the cap.

### Numbers
Filled in after the experiment runs (docs/evidence/upgrade-3.2-chaos.md).
- Baseline before any chaos (2026-10-31): 1,016 orders, 360 charges, 19 products audited: **0 violations, 0 stuck**,
  34 parked (poison orders in the DLQ by design + the outbox probe), after fixing 2 checker bugs (legacy shapes) and
  1 real data inconsistency (below).

### Likely interview questions
Answers are completed with measured numbers in the step's final commit.

### Debugging story
The first baseline run reported 9 violations before any chaos. Seven were the checker not understanding history:
an order created 1 s after my guessed DemoPay cutoff (no money ever moved), and five 2026-10-29 refunds made before
the CHARGE record had a running `refundedAmount`. Two were real: `ORD-20261030-399cf6c3` said COMPLETED, but L2 had
been written off and refunded. It was step 2.3's own test probe, which invoked the per-line Lambdas directly on an
order already completed by the old definition. Money and stock were consistent; only the status lied. Fixed with a
one-off conditional correction (`scripts/fix_probe_order.py`, status PARTIALLY_FULFILLED plus a history entry).
Lesson: a test harness that bypasses the orchestrator can leave states the orchestrator could never produce.

