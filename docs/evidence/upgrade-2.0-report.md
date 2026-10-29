### UPGRADE STEP 2.0 REPORT

**1. Summary**
The API now follows standard OAuth practice: it accepts **access tokens only**. Before this, it required the ID token,
because Cognito access tokens carry no email. A new Cognito **pre-token-generation trigger (V2_0)**,
`order-saga-pre-token`, copies exactly `email` and `email_verified` into every access token. The rollout took two
commits. Commit A deployed the trigger, accepted both token types and switched the frontend, scripts and CI to the
access token. Commit B rejects ID tokens with 401, enforced by a `token_use` check, because API Gateway's JWT
authorizer lets both token types through.

**2. Resources created/changed**
| AWS service | Exact resource name | Purpose | Console link (ap-south-1) |
|---|---|---|---|
| Lambda | `order-saga-pre-token` (new) | Pre-token-generation trigger: email + email_verified → access token | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions/order-saga-pre-token |
| IAM role | `order-saga-pre-token-role` + `-policy` (new) | Own log group + X-Ray only | https://us-east-1.console.aws.amazon.com/iam/home#/roles/details/order-saga-pre-token-role |
| CloudWatch Logs | `/aws/lambda/order-saga-pre-token` (new, 7 days) | Trigger's JSON logs (no email) | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#logsV2:log-groups/log-group/$252Faws$252Flambda$252Forder-saga-pre-token |
| Lambda permission | `AllowInvokeFromOrderSagaUserPool` (new) | Only this pool's ARN may invoke the trigger | (Lambda → Configuration → Permissions) |
| Cognito | `order-saga-users` (changed) | Lambda trigger: Pre token generation, V2_0 | https://ap-south-1.console.aws.amazon.com/cognito/v2/idp/user-pools/ap-south-1_Griah4PD3/authentication/extensions?region=ap-south-1 |
| Lambda | all 10 app functions (code updated) | Shared `common/auth.py` checks `token_use` | https://ap-south-1.console.aws.amazon.com/lambda/home?region=ap-south-1#/functions |
| CloudWatch | dashboard + 2 Logs Insights queries (changed) | Now include the new function / log group | https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#dashboards |

**3. Key configuration values**
- User pool `order-saga-users`: tier **ESSENTIALS**. Lambda trigger **Pre token generation**, `LambdaVersion = V2_0`.
- `order-saga-pre-token`: python3.12, arm64, 256 MB, **timeout 5 s** (Cognito's limit), X-Ray Active, no environment
  variables, no AWS permissions apart from its logs and X-Ray.
- Claims added (access token only): `email` (string) and `email_verified` (boolean). Nothing else.
- JWT authorizer `order-saga-cognito-jwt`: unchanged (issuer = pool, audience = `spa` + `automation` client IDs, which
  it checks against `aud` or `client_id`).
- `caller_from`: `token_use == "access"`, otherwise 401 (an ID token gets a specific message). A missing or unverified
  email gets 403.

**4. Commands run and key outputs**
- `pytest --cov=src --cov-fail-under=85` → 101 passed (A), **105 passed, 94.51%** (B).
- `terraform plan` (local, before A) → `Plan: 5 to add, 25 to change, 0 to destroy`. Every function's zip changes
  because `common/` changed. The IAM policies show as "known after apply" only because they depend on the new log
  group, and their content is identical.
- Deploy A apply: `5 added, 14 changed, 0 destroyed`. Deploy B apply: `0 added, 11 changed, 0 destroyed`.
- `aws cognito-idp describe-user-pool` → `PreTokenGenerationConfig: {LambdaVersion: V2_0, LambdaArn: ...order-saga-pre-token}`.
- terraform outputs used: `user_pool_id = ap-south-1_Griah4PD3`, API `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com`,
  storefront `https://dg38gx94mao9n.cloudfront.net`.

**5. Tests/verification**
| Check | Result |
|---|---|
| Unit tests (B) | ✅ 105 passed, 94.5% |
| Decoded fresh access token | ✅ `token_use=access`, `client_id`, `email` (= user A), `email_verified=true`; ID token unchanged |
| Smoke test A / B | ✅ `ORD-20261029-32364eed` / `ORD-20261029-97279ad3` COMPLETED, 1 DEBIT each |
| Live e2e after A | ✅ 14/14 (ID token still 200 during the transition) |
| Live e2e after B | ✅ **14/14**. k: ID token on GET /wallet, GET /orders, POST /orders → **401**; access token → 200; tampered/forged → 401 |
| Browser UI (`capture_ui.py`, after B) | ✅ **6/6**, managed-login sign-in works, 0 console errors |
| Trigger runtime | ~2 ms warm, ~86 ms cold init, 33 MB |

Execution ARN example (B, a): `arn:aws:states:ap-south-1:876889172858:execution:order-saga-workflow:ORD-20261029-a886d6cc`.

**6. Files added/changed**
- Added: `src/lambdas/pre_token/handler.py`, `tests/unit/test_auth.py`, `docs/evidence/upgrade-2.0-access-tokens.md`,
  `docs/evidence/upgrade-2.0-report.md`
- Changed: `infra/main/auth.tf`, `infra/main/lambda.tf`, `infra/main/iam.tf`, `infra/main/api.tf`, `src/common/auth.py`,
  `tests/unit/conftest.py`, `tests/unit/test_create_order.py`, `scripts/auth_tokens.py`, `scripts/e2e_test.py`,
  `frontend/src/auth.tsx`, `frontend/src/api.ts`, `docs/interview-prep.md`, `docs/progress.md`, `README.md`,
  `docs/evidence/e2e-failure-tests.md`, `docs/evidence/ui/*`

**7. Problems hit and fixes**
- No deploy failures and no AccessDenied errors: the deploy role already covered `lambda:*` on `order-saga-*` and
  `cognito-idp:UpdateUserPool`, so infra/bootstrap is unchanged.
- The JWT authorizer accepts ID tokens as well as access tokens (it checks `aud` *or* `client_id`; shown by commit A's
  e2e). "Access tokens only" therefore can't be configured in API Gateway. It is enforced in `caller_from` via
  `token_use` and proven live on three routes.
- A function with no environment variables would get an empty `environment {}` block, which causes a diff on every
  plan. `lambda.tf` now makes the block dynamic, so it is omitted for such a function (no diff on the existing ones).
- Git Bash rewrote the `/aws/lambda/...` log group path in an AWS CLI call. Re-ran it with `MSYS_NO_PATHCONV=1`
  (tooling only).

**8. Cost notes**
The trigger runs once per sign-in or token refresh (not per API request), for about 2 ms at 256 MB. That is well
inside the Lambda free tier, effectively $0. Cognito Essentials charges nothing extra for triggers or for
access-token customization (MAU pricing is unchanged, and this pool has a handful of users). Logs are kept 7 days.
Expected cost for this step: **< $0.01**.

**9. Manual actions for you**
- None required. To see it yourself: Cognito → `order-saga-users` → Authentication → Extensions shows the Pre token
  generation trigger (V2_0). After signing in on the storefront, DevTools → Network shows `Authorization` carrying
  the access token.
- The orders DLQ gained one poison order per e2e/UI run (expected; don't purge).

**10. Git**
- Commit A `e1a8a3c`: pushed, CI 40847991518 ✅, Deploy 40848092637 ✅
- Commit B `59ad7cd`: pushed, CI 40849234155 ✅, Deploy 40849337652 ✅
- Evidence/docs commit (this report, evidence, UI screenshots, progress): pushed after B
