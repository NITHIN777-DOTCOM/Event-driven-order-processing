### UPGRADE STEP 2.2 REPORT

1. **Summary.** Entering checkout now holds the cart for 10 minutes:
   - **Hold.** One DynamoDB transaction moves stock → held. The pointer item allows one ACTIVE hold per user, and a short product gets a 409 naming it.
   - **Expiry.** A one-time EventBridge Scheduler schedule per hold releases it.
   - **Paying.** Paying consumes the hold (held → reserved, stock taken once). An order whose hold has ended reserves afresh or fails OutOfStock. Orders without a hold work unchanged.
   - **Races.** Consume, expire and release race safely: each is one transaction led by `status = ACTIVE`, so exactly one wins.
   - **Logical expiry.** Expiry is also enforced in the data, because the schedule fired 11.8–45.9 s late (measured).
   - **Part 0.** Added plan-time validation of Description tags, so the 2.1 outage can't recur.

2. **Resources created/changed (ap-south-1)**

| AWS service | Exact resource name | Purpose | Console link |
|---|---|---|---|
| DynamoDB | `order-saga-holds` | holds + `USER#<sub>` pointers; TTL `purgeAt` for clean-up only | https://ap-south-1.console.aws.amazon.com/dynamodbv2/home?region=ap-south-1#table?name=order-saga-holds |
| EventBridge Scheduler | schedule group `order-saga-holds` | one `at(expiresAt)` schedule per hold, deletes itself | https://ap-south-1.console.aws.amazon.com/scheduler/home?region=ap-south-1#schedule-groups |
| IAM | `order-saga-holds-scheduler-role` | Scheduler → invoke `order-saga-hold-expiry` only | https://us-east-1.console.aws.amazon.com/iam/home#/roles/details/order-saga-holds-scheduler-role |
| Lambda | `order-saga-holds-api` | POST /holds, GET /holds/current, DELETE /holds/{holdId} | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-holds-api |
| Lambda | `order-saga-hold-expiry` | the schedule's target; idempotent expiry | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-hold-expiry |
| Lambda (changed) | `order-saga-create-order`, `order-saga-reserve-inventory` | holdId validation; consume or fall back | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-reserve-inventory |
| API Gateway | `order-saga-api` routes `POST /holds`, `GET /holds/current`, `DELETE /holds/{holdId}` (JWT) | hold API | https://ap-south-1.console.aws.amazon.com/apigateway/main/develop/routes?region=ap-south-1 |
| SSM Parameter Store | `/order-saga/auth/client-ids` (String) | spa / automation client ids (duration rule) | https://ap-south-1.console.aws.amazon.com/systems-manager/parameters/order-saga/auth/client-ids/description?region=ap-south-1 |
| CloudWatch | alarm `order-saga-hold-expiry-errors`; metric filters `OrderSaga/HoldEvents`, `OrderSaga/HoldExpiryLag`; dashboard row 9 | ops visibility | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#dashboards/dashboard/order-saga-dashboard |
| IAM (changed) | the create_order, reserve_inventory and holds_api roles | least privilege: holds table only; schedules in `order-saga-holds` only; PassRole of the scheduler role only to scheduler.amazonaws.com | |
| Bootstrap (changed) | `order-saga-github-deploy-role`, state bucket tag | Scheduler schedule-group permissions; tag value without "/" | |

3. **Key configuration values worth showing in the console**
   - **Holds:**
     - Duration 600 s for the storefront (spa client). Only the automation client may choose 30–600 s.
     - At most 5 units per product and 10 products per hold.
     - One ACTIVE hold per user.
   - **Schedule:** `at(<expiresAt>)`, FlexibleTimeWindow OFF, ActionAfterCompletion DELETE, retry policy, role condition `aws:SourceAccount`.
   - **Transitions:** each one is a `TransactWriteItems` whose item 0 is `#s = ACTIVE`.
     - Consume adds `expiresAtEpoch > now`.
     - Create puts the pointer with `attribute_not_exists` and requires `stock >= q`.
   - **TTL `purgeAt`:** expiry + 7 days (clean-up only, not the release mechanism).
   - **Alarm `order-saga-hold-expiry-errors`:** Lambda Errors ≥ 1 over 5 min. 11 alarms in total.

4. **Commands run and key outputs (trimmed)**
   - `terraform test` (tag_values): 5 runs pass. Bootstrap `terraform apply` (after "APPLY"): 2 changed; re-plan: no changes.
   - Commit A plan: 22 to add, 31 to change, 0 to destroy. Deploy 40864924694: **22 added, 17 changed, 0 destroyed**.
   - Commit B plan: 1 to add, 6 to change, 0 to destroy. Deploy 40866957986: **1 added, 5 changed, 0 destroyed**.
   - `python scripts/seed_inventory.py` (16 products, `held` = 0); `python scripts/e2e_test.py`; `python scripts/capture_ui.py`.
   - Terraform outputs added: `holds_table = order-saga-holds`, `holds_schedule_group = order-saga-holds`. App stack 156 resources, bootstrap 13.

5. **Tests and verification**
   - Unit: **217 passed, 94% coverage** (41 on holds: `test_holds.py` 28, `test_hold_orders.py` 13).
   - Live e2e: **26/26** (a–s unchanged, plus t–z):
     - t: 409 names WEBCAM-1080P.
     - u: `HOLD-20261029-79cb7f26e9` expired by its schedule 20.1 s late.
     - v: race codes [201, 409].
     - w: 404 for another user's hold.
     - x: I5 holds for all 16 products.
     - y: `ORD-20261029-e5331e73` consumed `HOLD-20261029-c0177385c9`; LAPTOP-STAND (98, 0, 2) → (97, 0, 3); B using A's holdId → 400.
     - z: `ORD-20261029-1599e6c9` reserved afresh after its hold expired.
     - Execution: `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-e5331e73`.
   - Commit A's first live run was 23/24. u compared a shared counter exactly; the fix was in the test (see 7).
   - UI: **8/8**, 0 console errors. The Normal order `ORD-20261029-2f17d17b` consumed its hold. The fake-clock run showed the last minute and "Your hold expired", "Hold again" replaced the hold, and leaving released it.
   - After the runs: the alarm is OK, `order-saga-hold-expiry` had 3 invocations and 0 errors, and no schedules were left in the group.
   - Expiry lag: 11.8 / 20.1 / 45.9 s (n = 3).

6. **Files added/changed**
   - **Part 0:** infra/modules/tag_values/main.tf, infra/modules/tag_values/tests/tag_values.tftest.hcl, infra/main/tags.tf, tests/unit/test_tag_values.py, .github/workflows/ci.yml, CLAUDE.md, docs/interview-prep.md, infra/bootstrap/main.tf, infra/bootstrap/github_oidc.tf
   - **A:** src/common/holds.py, src/common/auth.py, src/lambdas/holds_api/handler.py, src/lambdas/hold_expiry/handler.py, infra/main/holds.tf, infra/main/lambda.tf, infra/main/iam.tf, infra/main/api.tf, infra/main/outputs.tf, infra/main/monitoring.tf, scripts/seed_inventory.py, scripts/e2e_test.py, tests/unit/conftest.py, tests/unit/test_holds.py, docs/progress.md
   - **B:** src/lambdas/create_order/handler.py, src/lambdas/reserve_inventory/handler.py, frontend/src/hold.ts, frontend/src/api.ts, frontend/src/types.ts, frontend/src/pages/Checkout.tsx, scripts/capture_ui.py, tests/unit/test_hold_orders.py
   - **Docs:** docs/evidence/upgrade-2.2-holds.md, docs/evidence/upgrade-2.2-report.md, docs/evidence/e2e-failure-tests.md, docs/evidence/ui/*, README.md, docs/progress.md, docs/interview-prep.md

7. **Problems hit and how they were fixed**
   - **Bootstrap tag:** the state-bucket Description contained "infra/main" ("/" fails the new rule). Changed to "stack infra main" in the approved bootstrap diff.
   - **Terraform cycles (twice):**
     - Client ids in Lambda env vars created a cycle with the pool's pre-token trigger. Fixed by moving them to an SSM parameter.
     - The policy then referenced that parameter's ARN, creating another cycle. Fixed by building the ARN as a string local.
   - **Scenario u:** failed in A's first run because scenario l ordered a desk mat inside u's 30 s window. The test now checks held and stock + reserved. Every product is used by some scenario, so moving u to another product wasn't an option.
   - **Scheduler precision:** schedules fired 11.8–45.9 s after `expiresAt`, not at the second. No code change: the logical expiry (consume condition, lazy read, server-time countdown) already makes correctness independent of the timer. Documented in interview-prep §11 (Debugging story).
   - **Race test isolation:** the race test's setup could crash the whole e2e run. It now records a FAIL instead and always restores the parked stock.

8. **Cost notes.**
   - EventBridge Scheduler: 14 M invocations/month free, then $1 per million.
   - One on-demand table, two Lambdas, one standard (free) SSM parameter.
   - One more alarm: 11 alarms = 13 alarm metrics (some alarms use metric math). The free tier covers 10, so ~$0.30/month in total, of which this step adds $0.10.
   - Idle cost added: ≈ $0. This step's test runs cost cents.

9. **Anything you must do manually.** Nothing.
   - No new email subscriptions.
   - The orders DLQ gained 2 more poison orders (e2e + UI run). Leave them; do not purge or redrive.

10. **Git**
    - Part 0 `b6ed9e3`, A `08e8460`, B `e2a90b8`: all pushed, CI and Deploy green.
    - The docs commit (this report) is pushed after them; its CI/Deploy result is in progress.md.
