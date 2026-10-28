# PROJECT: Event-Driven E-Commerce Order Processing on AWS
Repo: event-driven-order-processing (github.com/NITHIN777-DOTCOM/event-driven-order-processing)

This is my AWS course project (Topic #18: event-driven order processing with SQS, SNS, Step Functions).
It must be (1) a working deployed system that I demo LIVE tomorrow in the AWS Console + a frontend to my
professor, and (2) a strong resume project. We build it PHASE BY PHASE: I give you one phase at a time.
Do ONLY the phase I give you, then stop and output the PHASE REPORT (format below).

FIRST: save everything from "# PROJECT" down to the end of "## PHASE REPORT FORMAT" as CLAUDE.md in
the repo root. Then do Phase 0.

## Environment & fixed decisions
- Windows 10 + PowerShell, Claude Code running locally. All scripts are Python (no bash), so they run on
  Windows and Linux. Use `python`: local Python 3.11, Lambda runtime 3.12 (keep all code
  compatible with 3.11 so local tests run). Put dev deps in requirements-dev.txt.
- Region: ap-south-1 (Mumbai). Lambdas: Python 3.12 + boto3. IaC: Terraform only (>= 1.10).
  Never create or modify AWS resources by hand or with ad-hoc CLI; the CLI is only for testing/inspection.
- AWS credentials: the default AWS CLI profile on this machine (IAM user order-saga-admin).
  NEVER print, read out, or commit credentials.
- ALERT_EMAIL = nithinthegreat06@gmail.com, kept in terraform.tfvars (gitignored), with a
  terraform.tfvars.example committed.
- Package Lambdas with Terraform archive_file (no Docker).
- Every AWS resource is named with the prefix `order-saga-`, tagged Project=aws-order-saga +
  ManagedBy=terraform (use provider default_tags), and gets a Description wherever AWS allows.
  My professor evaluates in the AWS Console, so names and descriptions must be clear.
- COST GUARDRAILS: everything stays serverless and pay-per-use. Do NOT use: NAT Gateway, VPC/subnets,
  EC2, RDS, ElastiCache, OpenSearch, customer-managed KMS keys, Secrets Manager, provisioned
  concurrency. Use AWS-managed/default encryption. Warn me and wait before anything that could
  cost more than $1.
- NEVER run `terraform destroy`, or delete data or buckets, unless I reply exactly "DESTROY".
- .gitignore: .terraform/, *.tfstate, *.tfstate.*, .terraform.lock.hcl is COMMITTED (not ignored),
  *.tfvars (but keep *.tfvars.example), .env, build/, dist/, *.zip, __pycache__/, .venv/, node_modules/
- Least-privilege IAM: each Lambda gets its own role scoped to exactly the resources it uses.
- Code must be clean and commented. Interviewers will read it.
- If something fails, debug it yourself (terraform errors, CloudWatch logs) before asking me.
- Commit with clear messages at the end of each phase and push to origin main.
- Keep docs/progress.md updated (phase, done, next, blockers) so any new session can resume.
- Every feature added or changed must also update docs/interview-prep.md in the same commit.

## Architecture (final target, built across phases)
API Gateway HTTP API (CORS enabled): POST /orders → Lambda create_order; GET /orders/{id} → Lambda get_order.
create_order: validate input, use an Idempotency-Key header, conditional-put to DynamoDB
  order-saga-orders (status PENDING, statusHistory list; duplicate key → return the existing order, 200),
  then send to SQS.
SQS order-saga-orders-queue (DLQ order-saga-orders-dlq, maxReceiveCount 3, visibility timeout ≥ 6x the
  Lambda timeout) → Lambda start_workflow (batch 10, ReportBatchItemFailures) → StartExecution of the
  state machine with execution name = orderId (ExecutionAlreadyExists = success, as an idempotency guard).
Step Functions STANDARD order-saga-workflow:
  ReserveInventory (Lambda; conditional decrement on DynamoDB order-saga-inventory; OutOfStock error)
  → ProcessPayment (Lambda, simulated; Retry PaymentTransientError 3x, interval 2s, backoff 2;
     Catch PaymentDeclined/States.ALL → compensation)
  → mark COMPLETED (direct DynamoDB SDK integration) → notify (direct SNS Publish integration).
  Compensation: ReleaseInventory → mark FAILED with reason → notify. OutOfStock → FAILED + notify.
  Every status change appends {status, timestamp, detail} to statusHistory.
Demo control: the order body may include "simulate": "none" | "payment_declined" | "payment_flaky"
  (fails twice, then succeeds) | "out_of_stock" | "poison" (start_workflow raises → message goes to the DLQ).
SNS topics: order-saga-notifications (customer emails) and order-saga-ops-alerts (alarms),
  both with an email subscription to ALERT_EMAIL.
Observability: X-Ray on Lambdas, API Gateway and Step Functions; structured JSON logs including orderId;
  log retention 7 days; CloudWatch dashboard + alarms.
Extras: frontend (S3 + CloudFront), GitHub Actions CI/CD with OIDC, k6 load test.

## Repo layout
infra/bootstrap/   Terraform state bucket + budget alert (local state)
infra/main/        all app resources, one file per concern (api.tf, queue.tf, sfn.tf, lambda.tf,
                   dynamodb.tf, sns.tf, monitoring.tf, iam.tf, frontend.tf); S3 remote backend
src/lambdas/<name>/handler.py, src/common/ (shared helpers)
statemachine/order_saga.asl.json (rendered with templatefile())
tests/unit/ (pytest + moto), scripts/ (Python: seed_inventory, e2e_test, demo, collect_evidence)
frontend/, loadtest/, docs/ (architecture.md, progress.md, evidence/, demo-script.md, viva-prep.md)
.github/workflows/

## Phase plan
P0 Foundation & bootstrap | P1 Core workflow | P2 Failure engineering + tests | P3 Monitoring |
P4 Frontend | P5 CI/CD | P6 Load test | P7 Docs, demo script, viva prep

Upgrade plan (after P5; supersedes P6/P7 above):
- Phase 1 Foundation: 1.0 prep (deploy-role permissions, CLI check, interview-prep doc) |
  1.1 transactional outbox (DynamoDB Streams -> EventBridge Pipes -> SQS) | 1.2 Cognito + user-keyed wallets/orders
- Phase 2 Saga features: 2.1 async payment (waitForTaskToken + HMAC webhook + timeout) |
  2.2 reservation holds with TTL | 2.3 multi-item orders with partial compensation | 2.4 mid-saga cancellation
- Phase 3 Proof + presentation: 3.1 oversell race test | 3.2 invariant/chaos checker | 3.3 k6 load test |
  3.4 Standard vs Express comparison + cost per 1,000 orders | 3.5 README rewrite + demo video

## PHASE REPORT FORMAT (end EVERY phase with this, in one block, nothing secret)
### PHASE <n> REPORT
1. Summary: 3–5 lines of what was built and why.
2. Resources created/changed: a table of AWS service | exact resource name | purpose | console link
   (ap-south-1).
3. Key configuration values worth showing in the console (e.g. retry settings, redrive policy).
4. Commands run and key outputs (trimmed), plus terraform output values.
5. Tests/verification run and results (pass/fail, with IDs such as orderIds or execution ARNs).
6. Files added/changed (paths only).
7. Problems hit and how they were fixed.
8. Cost notes for this phase.
9. Anything I must do manually (e.g. confirm an email).
10. Git: commit hash(es) and push status.
