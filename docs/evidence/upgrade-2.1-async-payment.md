# Upgrade step 2.1: asynchronous payment with webhooks (waitForTaskToken + HMAC + timeout)

Date: 2026-10-29 · Region: ap-south-1 · Commits: A `b2cdc15` (+ fixes `59bcbaa`, `2d926ed`), B `47fac57` (+ fix `108e8a9`)

## What changed
- The saga no longer charges the wallet itself. `RequestPayment` (`lambda:invoke.waitForTaskToken`, `TimeoutSeconds: 120`)
  creates payment intent `PI-<orderId>` in `order-saga-payments`, stores the task token **on the intent**, marks the
  order `PAYMENT_PENDING` and sends the request (without the token) to SQS `order-saga-psp-requests`.
- **DemoPay** (`order-saga-payment-provider`, a mock PSP) charges once per intent and POSTs an HMAC-signed callback to
  `POST /webhooks/payment` (no JWT). `order-saga-payment-webhook` verifies it and calls `SendTaskSuccess` /
  `SendTaskFailure("PaymentDeclined")`.
- No callback in 120 s → `States.Timeout` → `MarkPaymentTimedOut` (direct conditional DynamoDB update) → compensation →
  FAILED "payment timeout". A payment arriving later is refunded by the webhook.
- `order-saga-process-payment` removed; its log group is kept (`retired_log_groups`) so no logs were deleted.

## Money invariants (checked by `scripts/e2e_test.py` for every order, from the ledger and the payments table)
| | Invariant |
|---|---|
| I1 | COMPLETED ⇒ exactly one DEBIT of the order total, no CREDIT |
| I2 | FAILED (or never started) ⇒ net charge 0 |
| I3 | never more than one DEBIT or one CREDIT per order |
| I4 | the intent, if any, ends SUCCEEDED, FAILED, TIMED_OUT or REFUNDED (and the expected one) |

## Live e2e: 19/19 passed (2026-10-29 10:29–10:33 UTC, 212 s)
Full output: [`e2e-failure-tests.md`](e2e-failure-tests.md).

| # | Scenario | orderId | Intent (`PI-<orderId>`) | Ledger (DEBIT / CREDIT, net) | Result |
|---|---|---|---|---|---|
| a | none | `ORD-20261029-7e755bfa` | SUCCEEDED | 1 / 0, ₹3,499 | COMPLETED, PASS |
| b | payment_declined | `ORD-20261029-0f08dad5` | FAILED | 0 / 0, ₹0 | FAILED, PASS |
| c | payment_flaky | `ORD-20261029-01e415e1` | SUCCEEDED | 1 / 0, ₹26,990 | COMPLETED after 2 retries, PASS |
| d | out_of_stock | `ORD-20261029-a97e3f9b` | none (never requested) | 0 / 0, ₹0 | FAILED, PASS |
| e | same Idempotency-Key ×3 | `ORD-20261029-91f2ac59` | SUCCEEDED | 1 / 0, ₹24,999 | COMPLETED, PASS |
| f | same orderId ×3 via SQS | `ORD-20261029-4ed0dd64` | SUCCEEDED | 1 / 0, ₹799 | COMPLETED, PASS |
| g | poison | `ORD-20261029-7086bb49` | none | 0 / 0, ₹0 | PENDING in DLQ, PASS |
| h | low balance (real decline, user B) | `ORD-20261029-db3dbb07` | FAILED | 0 / 0, ₹0 | FAILED, PASS |
| i | crash simulation (outbox) | `ORD-20261029-c3ecb63b` | SUCCEEDED | 1 / 0, ₹2,299 | COMPLETED, PASS |
| n | per-user idempotency (user B) | `ORD-20261029-94885029` | SUCCEEDED | 1 / 0, ₹1,799 | COMPLETED, PASS |
| o | webhook security | none | none created | n/a | 401 ×5, 404 ×1, PASS |
| **p** | **payment_timeout** | `ORD-20261029-183e06ba` | **TIMED_OUT** | 0 / 0, ₹0 | FAILED "payment timeout" after **120.0 s**, PASS |
| **q** | **payment_late** | `ORD-20261029-05f213e9` | **REFUNDED** | **1 / 1, ₹0** | FAILED at 120 s, refunded at 151 s, PASS |
| **r** | **webhook_duplicate** | `ORD-20261029-c26394e5` | SUCCEEDED | 1 / 0, ₹6,499 | COMPLETED, 2nd callback "duplicate", PASS |
| **s** | **webhook_bad_signature** | `ORD-20261029-ffc1f856` | SUCCEEDED | 1 / 0, ₹4,999 | forged callback 401, genuine one COMPLETED, PASS |

(j, k, l, m re-check earlier steps; all PASS.)

### Scenario q, the late payment, step by step (statusHistory)
```
10:29:26.406Z  PENDING             Order received via API
10:29:27.580Z  PROCESSING          Saga workflow started
10:29:27.823Z  RESERVED            Reserved stock for 1 product(s)
10:29:27.983Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹18,999 · intent PI-ORD-20261029-05f213e9
10:31:28.195Z  INVENTORY_RELEASED  Compensation: released stock for 1 product(s)
10:31:28.238Z  FAILED              PaymentTimeout: payment timeout - DemoPay did not confirm the payment within 120 s
10:31:59.251Z  PAYMENT_REFUNDED    ₹18,999 refunded to DemoPay (late payment PAY-6d52164f8a1c, the order had already failed)
```

### Scenario a, the normal path (statusHistory)
```
10:29:26.827Z  PENDING             Order received via API
10:29:27.132Z  PROCESSING          Saga workflow started
10:29:27.267Z  RESERVED            Reserved stock for 1 product(s)
10:29:27.428Z  PAYMENT_PENDING     Awaiting payment confirmation from DemoPay · ₹3,499 · intent PI-ORD-20261029-7e755bfa
10:29:32.786Z  PAYMENT_CAPTURED    ₹3,499 captured by DemoPay · PAY-51745c88911f (confirmed by webhook)
10:29:32.947Z  COMPLETED           Order fulfilled - payment PAY-51745c88911f captured
```

## Numbers
- Request → webhook callback (`callbackDelayMs`, Logs Insights, last hour): **15 resumed payments, p50 5.2 s,
  max 11.5 s** (includes DemoPay's simulated 2–5 s processing delay). Duplicate: 4.3 s. Late: **150.2 s**.
- Timeout: `RequestPayment` entered → `TaskTimedOut` **120.0 s** (execution history, scenario p).
- Normal order end to end: **6.1 s** (PENDING → COMPLETED, scenario a), up from 0.56 s with the synchronous charge (step 2.0 e2e run, same scenario):
  the saga now waits for the provider, as a real gateway requires.
- `OrderSaga/WebhookSignatureFailures` during the run: **6** (5 from scenario o, 1 from scenario s).
- Unit tests: **166 passed, 94% coverage** (new: test_signing, test_payment_provider, test_payment_webhook,
  test_request_payment, test_refund_payment).

## Commit A live check (before anything depended on the webhook)
Scenario o against commit A: no signature, wrong secret, 10-minute-old and 10-minute-future timestamps → **401**; valid
signature for unknown intent `PI-ORD-20261029-e2ec57ff` → **404**, no item written; a user's JWT instead of a
signature → **401**. Secret: `/order-saga/psp/webhook-secret`, SecureString, key `alias/aws/ssm` (AWS-managed).

## Rollout: in-flight executions during commit B's deploy
A probe placed an order every few seconds while Deploy applied commit B, then read each execution's definition with
`DescribeStateMachineForExecution`.

- Commit B's first apply (`40856722473`) **failed** on the state machine's Description tag (Step Functions forbids
  parentheses in tag values). Terraform had already deleted `process_payment` and updated the state machine role,
  but the definition was still the old one.
- 32 orders were placed in that window (11 by the first probe, 21 by the second). **Every one ran the old
  definition** (ProcessPayment), including those still running after the switch: executions keep the definition they
  started with. Their ProcessPayment call failed (`Lambda.ResourceNotFoundException`, or `AccessDenied` once the role
  had no permission for the old function). `States.ALL` caught it, compensation ran, and **all 32 ended FAILED with 0
  ledger entries** (net ₹0) and their stock released.
- The fix (`108e8a9`, Deploy `40857370694`) switched the definition; the 2 orders placed after it ran
  **RequestPayment** and **COMPLETED** with one DEBIT each.
- Lesson recorded in `docs/interview-prep.md` §10: removing the old function belongs in a commit *after* the switch is
  live, so a half-applied deploy can't leave the old definition without its function.

## UI evidence
`scripts/capture_ui.py` adds a late-payment order: the tracker shows **"Awaiting payment confirmation"**, then the
failure at 120 s and the automatic refund row. See [`ui/README.md`](ui/README.md).
