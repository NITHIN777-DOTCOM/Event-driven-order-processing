# Upgrade step 1.1 evidence: transactional outbox (DynamoDB Streams → EventBridge Pipes → SQS)

Date: 2026-10-28 · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`

Before: `create_order` wrote the order to DynamoDB, **then** called `sqs.send_message`. A crash in between
left the order PENDING forever. After: `create_order` makes one write (the DynamoDB transaction). The order
row's stream INSERT is delivered to `order-saga-orders-queue` by the pipe `order-saga-orders-outbox`.

## Resources

| Resource | Name | Console |
|---|---|---|
| DynamoDB stream | `order-saga-orders` stream `2026-10-28T16:00:51.383` (NEW_IMAGE) | [Exports and streams](https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#table?name=order-saga-orders&tab=streams) |
| EventBridge Pipe | `order-saga-orders-outbox` | [Pipe](https://ap-south-1.console.aws.amazon.com/events/home?region=ap-south-1#/pipes/order-saga-orders-outbox) |
| IAM role | `order-saga-orders-outbox-role` | [Role](https://us-east-1.console.aws.amazon.com/iam/home#/roles/details/order-saga-orders-outbox-role) |
| SQS DLQ | `order-saga-outbox-dlq` | [Queue](https://ap-south-1.console.aws.amazon.com/sqs/v3/home?region=ap-south-1#/queues/https%3A%2F%2Fsqs.ap-south-1.amazonaws.com%2F876889172858%2Forder-saga-outbox-dlq) |
| Alarm | `order-saga-outbox-dlq-not-empty` | [Alarm](https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#alarmsV2:alarm/order-saga-outbox-dlq-not-empty) |
| Alarm | `order-saga-outbox-pipe-failures` | [Alarm](https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#alarmsV2:alarm/order-saga-outbox-pipe-failures) |

Pipe settings: filter `{"eventName":["INSERT"],"dynamodb":{"NewImage":{"status":{"S":["PENDING"]}}}}` ·
input template `{"orderId": "<$.dynamodb.NewImage.orderId.S>"}` · batch size 1 · starting position TRIM_HORIZON ·
max retry attempts 5 · max record age 3600 s · DLQ `order-saga-outbox-dlq`.

## Rollout

| Commit | What | CI | Deploy |
|---|---|---|---|
| `4814f7d` (A) | stream + pipe + outbox DLQ + alarms added; direct SQS send **kept** | [40721453959](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40721453959) ✅ | [40721554193](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40721554193) ✅ apply 6 added, 2 changed; smoke `ORD-20261028-784a3816` COMPLETED 4.6 s, 1 DEBIT |
| `a6c2848` (B) | `enqueue_order`, SQS client, `ORDERS_QUEUE_URL` and `sqs:SendMessage` **removed** from create_order | [40722986095](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40722986095) ✅ | [40723106944](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40723106944) ✅ apply 3 changed; smoke `ORD-20261028-bee264ed` COMPLETED 3.5 s, 1 DEBIT (pipe-only path) |

## Commit A: every order delivered twice, still exactly once in effect

`python scripts/outbox_check.py timing --label before --dual` ([full table](upgrade-1.1/before.md)):
10/10 orders COMPLETED. Each had **2 deliveries** (start_workflow logged 1 "Saga execution started" + 1 "Duplicate
message ignored", from two different SQS message IDs), **1 execution** and **1 DEBIT**. That's the idempotent
consumer (conditional PENDING→PROCESSING + execution name = orderId) working on live traffic.

Example (`ORD-20261028-2b404026`, from the first run):
```
16:03:46.138Z  Saga execution started                         messageId c146923d...
16:03:46.167Z  Duplicate message ignored: saga already started messageId f28ceacc...
```
The first run reported this order as 0/0 because of local-clock skew in the log query window. The script was fixed
and re-run; see "Problems" below.

## Timing: before (direct send) vs after (pipe only), 10 orders each, one at a time

| Median (ms) | Before (commit A) | After (commit B) | Δ |
|---|---|---|---|
| PENDING → PROCESSING (write → start_workflow picked it up) | 72 | 346 | +274 |
| PENDING → COMPLETED (server timestamps) | 366 | 645 | +279 |
| Client POST → COMPLETED seen (polled every 0.25 s) | 688 | 1125 | +437 |

p95 PENDING→PROCESSING: 229 ms before, 542 ms after. Full tables: [before](upgrade-1.1/before.md), [after](upgrade-1.1/after.md).
The extra ~0.3 s is the pipe's stream polling (4 polls/s per shard) plus the pipe invocation. That's what one extra
hop costs, in exchange for no lost orders.

## End-to-end suite after commit B: 10/10 PASS

`python scripts/e2e_test.py` ([full output](e2e-failure-tests.md)), all through the pipe-only path:

| # | Scenario | orderId | Execution ARN |
|---|---|---|---|
| a | simulate=none → COMPLETED, wallet debited once | `ORD-20261028-5ec707d8` | `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261028-5ec707d8` |
| b | payment_declined → FAILED, compensation | `ORD-20261028-9034d4d7` | `...:order-saga-workflow:ORD-20261028-9034d4d7` |
| c | payment_flaky → 2 retries → COMPLETED, 1 DEBIT | `ORD-20261028-8a30a839` | `...:order-saga-workflow:ORD-20261028-8a30a839` |
| d | out_of_stock → FAILED, no release | `ORD-20261028-8ae80c14` | `...:order-saga-workflow:ORD-20261028-8ae80c14` |
| e | same Idempotency-Key ×3 → 1 order, **1 stream INSERT**, 1 execution | `ORD-20261028-69b825e6` | `...:order-saga-workflow:ORD-20261028-69b825e6` |
| f | same {orderId} sent 3× to SQS → 1 execution | `ORD-20261028-0e20bb65` | `...:order-saga-workflow:ORD-20261028-0e20bb65` |
| g | poison → **orders** DLQ after 191 s, outbox DLQ 0 | `ORD-20261028-b859a61f` | none (by design) |
| h | low balance → real decline | `ORD-20261028-8cf69754` | `...:order-saga-workflow:ORD-20261028-8cf69754` |
| i | **crash simulation**: row written straight into DynamoDB (no API, no SQS send) → COMPLETED, 1 execution, 1 DEBIT, 1 stream INSERT | `ORD-20261028-74eb8439` | `...:order-saga-workflow:ORD-20261028-74eb8439` |
| j | **MODIFY** (status flipped back to PENDING) → status stayed PENDING for 45 s, 0 new start_workflow log lines, executions still 1; status then restored | `ORD-20261028-74eb8439` | (same, unchanged) |

## create_order can no longer publish to SQS

- Live config: `aws lambda get-function-configuration --function-name order-saga-create-order` → env vars
  `ORDERS_TABLE`, `INVENTORY_TABLE`, `IDEMPOTENCY_TABLE` only (no `ORDERS_QUEUE_URL`).
- Live IAM: `aws iam simulate-principal-policy --policy-source-arn .../order-saga-create-order-role` on
  `order-saga-orders-queue`: `sqs:SendMessage`, `sqs:SendMessageBatch`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`,
  `sqs:GetQueueAttributes` → **implicitDeny**; `dynamodb:PutItem` on `order-saga-orders` → allowed.
- Guardrail: a Terraform `precondition` on `aws_iam_role_policy.lambda` (`infra/main/iam.tf`). Tested by temporarily
  adding an `sqs:SendMessage` statement and running `terraform plan`: **"Error: Resource precondition failed"**, then
  the file was restored with `git checkout`. It runs on every CI plan, so the dual write can't come back unnoticed.
- Unit tests: `test_create_order_never_sends_to_sqs`, `test_handler_needs_no_queue_configuration` (67 passed, 95% coverage).

## What the outbox DLQ receives (stream source)

**Not observed.** AWS documents that a stream-source pipe can use an SQS or SNS DLQ, and that records older than
`MaximumRecordAgeInSeconds` go to it without processing. It does not document the message body.

Probe attempted: a labelled test row (`orderId` = `OUTBOX-DLQ-TEST-68c7af7e` + U+0001, a character SQS rejects
in message bodies) to make the SQS send fail. Result: the pipe **JSON-escaped** the character, SQS accepted the message,
and `start_workflow` then failed with `InvalidName` from StartExecution. So it went to the **orders** DLQ after 3
receives, not the outbox DLQ. The test row is left in the table (status PROCESSING, customerName
"OUTBOX DLQ TEST (not a real order)", no `gsi1` keys, so it never appears in the storefront list). Forcing a real
pipe target failure would mean breaking the live pipe's permissions or target, so it wasn't done.

Recovery works either way, because the order row is the source of truth:
1. Read the DLQ message. If it carries the record, take `orderId`. If it only carries batch metadata (shard ID +
   sequence numbers, which is how Lambda's stream event sources report failures), read that range from the stream
   with `GetShardIterator AT_SEQUENCE_NUMBER`. The 1 h max record age leaves ~23 h before the stream trims it.
2. Fix the cause (the pipe's `StateReason` and the `order-saga-outbox-pipe-failures` alarm say what failed).
3. Send `{"orderId": ...}` to `order-saga-orders-queue`. start_workflow is idempotent, so a re-send is always safe.
4. Fallback with no stream data: query PENDING orders older than a few minutes (`gsi1` projects `status`). That's the
   sweeper listed as a known gap.

## Cost at idle: ESTIMATE, not measured

- **Estimate ≈ $1.57/month** (rounded to ~$1.6): AWS documents the pipe polling each stream shard about 4 times/s.
  4 × 2,592,000 s in 30 days ≈ 10.4M `GetRecords` calls; minus the 2.5M/month DynamoDB Streams free tier ≈ 7.9M billable;
  at $0.02 per 100,000 (the DynamoDB pricing page's example rate; the Mumbai rate isn't listed) ≈ $1.57.
- Basis: the DynamoDB pricing page lists only Lambda triggers and global tables as free stream readers; Pipes isn't
  listed, so its reads are assumed billed.
- Pipe requests: $0.40 per million, counted after filtering. ≈ $0 at demo volume (1,000 orders ≈ $0.0004).
- **Not measured.** A one-hour CloudWatch measurement was planned and then skipped. To measure it later:
  `python scripts/outbox_check.py cost --minutes 60` (it sums `SuccessfulRequestLatency` SampleCount for
  Operation=GetRecords on the orders stream and projects a month). The dashboard's outbox row has the same graph.
- Accepted by the owner (2026-10-28); within the $5 budget alert.

## Problems hit

1. **Clock skew in the log check.** The first commit-A timing run reported 1/10 orders as not double-delivered. CloudWatch
   showed both deliveries; the query's start time came from the local clock, which runs ahead of AWS (a log line at
   16:06:55.503Z for a row the script wrote at a local 16:06:56.253Z). Fix: 2 min of slack for unique orderIds, and a
   before/after count with no time window for the MODIFY test.
2. **`print` of "→" crashed on the Windows console (cp1252)**. The evidence file had already been written. Fix:
   `sys.stdout.reconfigure(encoding="utf-8")`.
3. **`simulate-principal-policy` rejects mixing `sqs:SendMessageBatch` with other actions** ("require different
   authorization information"). Ran it as separate calls.

## DLQ state after this step

- `order-saga-outbox-dlq`: 0 messages; both outbox alarms OK.
- `order-saga-orders-dlq`: 9 messages (7 from earlier demo/e2e runs + this step's e2e poison order + the DLQ-probe
  test row). Not purged or redriven.
