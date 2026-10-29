### UPGRADE STEP 2.1 REPORT

**1. Summary**
Payment now works like a real gateway. The saga *requests* a payment and pauses on a Step Functions task token
(`waitForTaskToken`, 120 s timeout). The mock provider **DemoPay** charges once per intent and confirms through an
**HMAC-signed webhook**, which resumes the saga with `SendTaskSuccess` / `SendTaskFailure`. If no callback arrives in
120 s, the order fails with "payment timeout" and is compensated; a payment that arrives later is **refunded
automatically**. Four money invariants (I1–I4) are designed in, unit-tested and asserted for every live e2e scenario.
It shipped in two commits (A: provider and webhook beside the old path, verified live; B: switch and remove
`process_payment`).

**2. Resources created/changed** (ap-south-1)

| Service | Exact name | Purpose | Console |
|---|---|---|---|
| DynamoDB | `order-saga-payments` | Payment intents `PI-<orderId>` (status, task token, amount) | https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#table?name=order-saga-payments |
| DynamoDB | `order-saga-psp-transactions` | DemoPay's own records: `CHARGE#` / `REFUND#<intent>` (idempotency) | https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#table?name=order-saga-psp-transactions |
| SQS | `order-saga-psp-requests` | Payment requests to DemoPay (DelaySeconds 2–5, or 150 for payment_late) | https://ap-south-1.console.aws.amazon.com/sqs/v3/home?region=ap-south-1#/queues |
| SQS | `order-saga-psp-dlq` | Requests DemoPay failed 5 times (e.g. webhook down) | same |
| Lambda | `order-saga-request-payment` | waitForTaskToken step: intent + token, PAYMENT_PENDING, send request | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-request-payment |
| Lambda | `order-saga-payment-provider` | DemoPay: idempotent charge, signed callback, idempotent refund API | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-payment-provider |
| Lambda | `order-saga-payment-webhook` | Verifies HMAC, updates intent and order, resumes the saga, late refunds | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-payment-webhook |
| Lambda | `order-saga-refund-payment` (changed) | Compensation now refunds through DemoPay; abandons REQUESTED intents | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-refund-payment |
| Lambda | `order-saga-process-payment` (removed) | Replaced by request_payment; log group kept until retention expires | n/a |
| API Gateway | route `POST /webhooks/payment` (no authorizer) | DemoPay's callback endpoint | https://ap-south-1.console.aws.amazon.com/apigateway/main/apis?region=ap-south-1 |
| Step Functions | `order-saga-workflow` (changed) | RequestPayment (waitForTaskToken, 120 s) + MarkPaymentTimedOut | https://ap-south-1.console.aws.amazon.com/states/home?region=ap-south-1#/statemachines |
| SSM | `/order-saga/psp/webhook-secret` (SecureString, AWS-managed key) | HMAC secret; created by `scripts/create_webhook_secret.py` in Deploy, not in TF state | https://ap-south-1.console.aws.amazon.com/systems-manager/parameters?region=ap-south-1 |
| CloudWatch | alarms `order-saga-psp-dlq-not-empty`, `order-saga-webhook-signature-failures` | Provider failures; forged/stale callbacks | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#alarmsV2: |
| CloudWatch | metric filters `WebhookSignatureFailures`, `WebhookCallbackDelay` (ns OrderSaga); dashboard row 8 | Payments row: intents by status, webhook latency, timeouts, signature failures + PSP DLQ | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#dashboards |
| IAM | `order-saga-request-payment-role`, `-payment-provider-role`, `-payment-webhook-role` (+ refund, SFN updated) | Least privilege; SendTask* scoped to the state machine ARN | https://console.aws.amazon.com/iam/home#/roles |

**3. Key configuration values worth showing**
- `RequestPayment`: `arn:aws:states:::lambda:invoke.waitForTaskToken`, `TimeoutSeconds: 120`, payload
  `taskToken.$: $$.Task.Token`. Retry `PaymentTransientError` 2 s ×3, backoff 2. Catch `States.Timeout` →
  `MarkPaymentTimedOut`; `PaymentDeclined` / `States.ALL` → `RefundPayment`.
- `MarkPaymentTimedOut`: direct `dynamodb:updateItem`, `ConditionExpression #s = :requested` (loses cleanly to a
  capture that just happened).
- Webhook signature: `X-Signature = hex(HMAC_SHA256(secret, "<X-Timestamp>.<raw body>"))`, ±300 s window,
  `hmac.compare_digest`; failure → 401 + `event = webhook_signature_rejected`.
- `order-saga-psp-requests`: visibility 120 s (6× the provider's 20 s timeout), redrive maxReceiveCount 5 →
  `order-saga-psp-dlq`; event source mapping batch 5, ReportBatchItemFailures, max concurrency 2.
- Idempotency keys: intent `PI-<orderId>`; provider `CHARGE#<intent>` / `REFUND#<intent>` written in the same
  transaction as the wallet change (`attribute_not_exists`).
- Alarm `order-saga-webhook-signature-failures`: Sum ≥ 1 over 300 s.

**4. Commands run and key outputs**
- `terraform fmt -check -recursive infra` OK; `terraform validate` OK (only the existing `hash_key` deprecation warning).
- Plan for B (after keeping the retired log group): `4 to add, 29 to change, 3 to destroy` (process_payment function,
  role, policy).
- `pytest --cov=src`: 166 passed, total coverage 94%.
- `python scripts/e2e_test.py`: `19/19 scenarios passed in 212s`.
- `python scripts/capture_ui.py`: 7 scenarios OK, 0 browser console errors.
- Logs Insights on the webhook (`callbackDelayMs`): resumed n=15, p50 5,159 ms, max 11,499 ms; late-refunded 150,177 ms.
- New terraform outputs: `payments_table = order-saga-payments`, `psp_transactions_table = order-saga-psp-transactions`,
  `psp_requests_queue_url`, `psp_dlq_url`, `webhook_url = https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com/webhooks/payment`,
  `webhook_secret_parameter = /order-saga/psp/webhook-secret`.
- App stack: 133 managed resources (+13 bootstrap).

**5. Tests/verification**
- Commit A live (scenario o): no signature / wrong secret / 10 min old / 10 min future → 401 ×4; valid signature for
  unknown `PI-ORD-20261029-e2ec57ff` → 404, no item; a user JWT instead of a signature → 401. PASS.
- Live e2e after B: 19/19 PASS, I1–I4 for every order. New ones:
  p payment_timeout `ORD-20261029-183e06ba` (TIMED_OUT, 0/0, waited 120.0 s);
  q payment_late `ORD-20261029-05f213e9` (REFUNDED, DEBIT+CREDIT, net ₹0, refund at +151 s);
  r webhook_duplicate `ORD-20261029-c26394e5` (1 DEBIT, 2nd callback "duplicate");
  s webhook_bad_signature `ORD-20261029-ffc1f856` (401 then COMPLETED; metric = 6 for the run).
  Example execution: arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-05f213e9
- Verified live: PaymentTransientError raised by a waitForTaskToken Lambda is retried by name (scenario c:
  2 × PAYMENT_RETRY, then COMPLETED, 1 DEBIT); SendTaskSuccess/Failure scoped to the state machine ARN works (15
  resumes).
- Rollout probe: 32 orders placed during the deploys all ran the old definition (`DescribeStateMachineForExecution`)
  and ended FAILED with net ₹0 and stock released; 2 orders after the switch COMPLETED on RequestPayment.
- UI: "Awaiting payment confirmation" stage and the late-payment refund row captured
  (`docs/evidence/ui/desktop-07a…`, `desktop-07b…`).

**6. Files added/changed**
Added: `src/common/signing.py`, `src/common/secrets.py`, `src/common/payments.py`,
`src/lambdas/payment_provider/handler.py`, `src/lambdas/payment_webhook/handler.py`,
`src/lambdas/request_payment/handler.py`, `infra/main/payments.tf`, `scripts/create_webhook_secret.py`,
`tests/unit/test_signing.py`, `tests/unit/test_payment_provider.py`, `tests/unit/test_payment_webhook.py`,
`tests/unit/test_request_payment.py`, `tests/unit/test_refund_payment.py`,
`docs/evidence/upgrade-2.1-async-payment.md`, `docs/evidence/upgrade-2.1-report.md`,
`docs/evidence/ui/desktop-07a-tracker-awaiting-payment.png`, `docs/evidence/ui/desktop-07b-tracker-late-payment-refunded.png`.
Changed: `statemachine/order_saga.asl.json`, `infra/main/{api,iam,lambda,monitoring,outputs,sfn}.tf`,
`src/common/{orders,wallet,feed,logger}.py`, `src/lambdas/{create_order,refund_payment}/handler.py`,
`frontend/src/{types,format,tracker}.ts`, `frontend/src/pages/Checkout.tsx`, `scripts/{e2e_test,place_order,capture_ui}.py`,
`.github/workflows/deploy.yml`, `tests/unit/{conftest,test_feed,test_wallet}.py`, `README.md`,
`docs/{interview-prep,progress}.md`, `docs/evidence/e2e-failure-tests.md`, `docs/evidence/ui/*`.
Removed: `src/lambdas/process_payment/handler.py`, `tests/unit/test_process_payment.py`.

**7. Problems hit and how they were fixed**
- Commit A Deploy failed: `ValidationException: The Tag Value provided is invalid` on `order-saga-payments`, because
  the Description tag had parentheses. Removed them (`59bcbaa`); that left a comment inside `tags = {}`, which broke
  CI's `terraform fmt -check`; moved it (`2d926ed`).
- Commit B Deploy failed the same way on the state machine (Step Functions forbids parentheses too). By then Terraform
  had already deleted `process_payment`, but the definition was still the old one. For about 5 minutes the 32 orders
  placed (by the probe) failed safely through compensation, with zero charge. Fixed in `108e8a9`. Lesson: check tag
  characters for every service; put "remove the old function" in a later commit than "switch to the new one".
- The plan would have destroyed `process_payment`'s log group (log data). Kept it under Terraform via
  `retired_log_groups` so it ages out with the 7-day retention instead of being deleted.

**8. Cost notes**
- Step Functions waits for free (Standard bills per transition; a payment adds ~3 transitions per order).
- 2 new alarms: 10 alarms / 12 metrics in total, about $0.20/month beyond the free 10.
- New SQS queue with a Lambda event source mapping: idle long-polling requests, estimated within or close to the 1M
  free SQS requests (not measured). DynamoDB on-demand, SSM standard SecureString: $0 at this volume.
- Estimated total for this step: well under $1/month; nothing near the $10 guardrail.

**9. Manual actions for you**
None required. The orders DLQ holds 2 more poison orders from today's e2e and UI runs (by design; not purged).
Ops-alert emails you may see from today (all expected): `order-saga-webhook-signature-failures` (the security
tests; back to OK after 5 quiet minutes), `order-saga-high-order-failure-rate` (the 32 rollout-window orders plus the
deliberate failure scenarios; clears on its own), and `order-saga-dlq-not-empty` (poison orders, kept by design).

**10. Git**
A `b2cdc15` + `59bcbaa` + `2d926ed` (CI 40854315062 ✓, Deploy 40854487219 ✓) ·
B `47fac57` (CI 40856577267 ✓, Deploy 40856722473 ✗ tag) + `108e8a9` (CI 40857206915 ✓, Deploy 40857370694 ✓) ·
docs commit: see `git log` (the commit containing this file); pushed to origin main, CI and Deploy watched to completion.
