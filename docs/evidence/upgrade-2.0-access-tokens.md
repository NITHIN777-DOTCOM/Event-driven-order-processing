# Upgrade step 2.0: access tokens for the API (evidence)

Date: 2026-10-29. Region: ap-south-1. Commits: A `e1a8a3c`, B `59ad7cd`.

## What changed
- New Lambda `order-saga-pre-token`: a Cognito **pre-token-generation trigger, event version V2_0**, attached to
  `order-saga-users` (Essentials plan, which supports access-token customization). It adds `email` and
  `email_verified` to the **access token** only. The ID token is unchanged.
- `aws_lambda_permission.cognito_pre_token`: principal `cognito-idp.amazonaws.com`, `source_arn` = the pool ARN.
- `src/common/auth.py`: commit A accepted `token_use` `access` or `id`; commit B accepts **`access` only**. An ID
  token gets **401** "ID tokens are not accepted: send the access token in the Authorization header".
- The frontend (`getAccessToken()`), `scripts/auth_tokens.py` (`auth_header()`), the smoke test and the e2e suite
  all send the access token.
- JWT authorizer `order-saga-cognito-jwt`: **unchanged**. HTTP API JWT authorizers match the audience list against
  `aud` (ID token) or `client_id` (access token).

## Live pool configuration
```
aws cognito-idp describe-user-pool --user-pool-id ap-south-1_Griah4PD3 --query "UserPool.{tier:UserPoolTier,lambda:LambdaConfig}"
{
  "tier": "ESSENTIALS",
  "lambda": {
    "PreTokenGeneration": "arn:aws:lambda:ap-south-1:876889172858:function:order-saga-pre-token",
    "PreTokenGenerationConfig": { "LambdaVersion": "V2_0",
      "LambdaArn": "arn:aws:lambda:ap-south-1:876889172858:function:order-saga-pre-token" }
  }
}
```

## A freshly issued access token, decoded (no signature, no email printed)
Test user A, signed in through the `automation` client (`AdminInitiateAuth`):
```
ACCESS: {"token_use": "access", "client_id": "1v5m07eueaokak5ivnuvk7c3me", "scope": "aws.cognito.signin.user.admin",
         "email_verified": true, "email": "<test user A email>", "has_sub": true}
ACCESS claim names: auth_time, client_id, email, email_verified, event_id, exp, iat, iss, jti, origin_jti, scope,
                    sub, token_use, username
ID     claim names: aud, auth_time, cognito:username, email, email_verified, event_id, exp, iat, iss, jti, name,
                    origin_jti, sub, token_use
```
Before step 2.0 the access token had no `email` and no `email_verified`. Those are the only two claims added.
`email_verified` is a JSON boolean, the same type as in the ID token. API Gateway passes it to the Lambda as `"true"`.

## Trigger logs (CloudWatch `/aws/lambda/order-saga-pre-token`, 7-day retention)
```
{"level": "INFO", "service": "pre_token", "message": "Access token claims set", "triggerSource": "TokenGeneration_Authentication",
 "clientId": "1v5m07eueaokak5ivnuvk7c3me", "userSub": "f1337d8a-...", "claimsAdded": ["email", "email_verified"], "emailVerified": true}
```
The email is never logged. Duration: about 2 ms warm, about 86 ms init on a cold start, 33 MB of 256 MB used
(Cognito's limit for triggers is 5 s).

## CI / Deploy
| Commit | CI | Deploy | Apply | Smoke test order |
|---|---|---|---|---|
| A `e1a8a3c` | 40847991518 ✅ | 40848092637 ✅ | 5 added, 14 changed, 0 destroyed | `ORD-20261029-32364eed` COMPLETED, 1 DEBIT |
| B `59ad7cd` | 40849234155 ✅ | 40849337652 ✅ | 0 added, 11 changed, 0 destroyed | `ORD-20261029-97279ad3` COMPLETED, 1 DEBIT |

No deploy-role (bootstrap) change was needed. The role already had `lambda:*` on `function:order-saga-*` (create,
AddPermission) and `cognito-idp:UpdateUserPool` on project-tagged pools.

## Live e2e (`scripts/e2e_test.py`)
- After commit A: **14/14** in 234 s. Scenario k: the access token carries the email claims → 200, and the ID token was
  still accepted → 200 (transition).
- After commit B: **14/14** in 288 s. Scenario k:
```
PASS: GET /products without a token -> 200
PASS: POST /orders, GET /orders, GET /orders/{id}, GET /wallet, POST /wallet/reset without a token -> 401
PASS: GET /wallet with a tampered signature -> 401
PASS: GET /wallet with a payload forged as user B -> 401
PASS: access token carries token_use=access, email (matches A: True), email_verified=True
PASS: GET /wallet with the ACCESS token -> 200 (A's wallet)
PASS: GET /wallet with the ID token -> 401 (ID tokens are not accepted: send the access token in the Authorization header)
PASS: GET /orders with the ID token -> 401 (same)
PASS: POST /orders with the ID token -> 401 (same)
```
  Orders (B run): a `ORD-20261029-a886d6cc`, b `-c95cd39b`, c `-05b7dd19`, d `-6c9af410`, e `-6621c5aa`, f `-a2a2a97e`,
  g `-12185014` (DLQ), h `-195dd54b`, i/j `-e71041f5`, l `-5f6d77c9`, n `-3f2bc669`. Full log: `e2e-failure-tests.md`.

## Browser (`scripts/capture_ui.py`, after commit B)
Chromium signs in through Cognito managed login (code + PKCE) as test user A, then runs every scenario through the
storefront, which now sends the access token. A storefront still sending ID tokens would fail every protected call
with 401. **6/6**, 0 console errors:
```
Normal                       ORD-20261029-756f2710  Order completed  DEBITs=1 OK
Payment glitch (retries)     ORD-20261029-dddd6be7  Order completed  DEBITs=1 OK
Payment declined             ORD-20261029-a41e1d12  Order failed     DEBITs=0 OK
Low balance (real decline)   ORD-20261029-6e23f4fa  Order failed     DEBITs=0 OK
Duplicate test (3 requests)  ORD-20261029-811bf7bf  Order completed, 1 order  DEBITs=1 OK
Poison message (to DLQ)      ORD-20261029-fa277eef  Stuck in the dead-letter queue  DEBITs=0 OK
```
Screenshots: `ui/`.

## Unit tests
`pytest --cov=src`: **105 passed, 94.5%** (gate 85%). New `tests/unit/test_auth.py`:
- an access token with a verified email is accepted; no email / `email_verified` false or missing → 403;
- an unknown `token_use` → 401; an ID token → 401 in `caller_from` and in all four API handlers (nothing written);
- identity ignores the body, headers and query;
- the trigger adds only `email` + `email_verified` (for sign-in and refresh), leaves the ID token alone, passes
  `false` through, adds nothing for a user without an email, its output is accepted by `caller_from`, and it never
  logs the email.
