# Upgrade step 1.2 evidence: Cognito sign-in + user-keyed orders and wallets

Date: 2026-10-28 · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com` ·
Storefront: https://dg38gx94mao9n.cloudfront.net

Before: no authentication. DemoPay wallets were keyed by an email the client typed (anyone could view or reset any
wallet), `GET /orders` listed everyone's orders, and `GET /orders/{id}` returned any order to anyone. After: Cognito
sign-in, an API Gateway JWT authorizer, identity taken only from verified token claims, and every order and wallet
owned by a Cognito `sub`.

## Resources

| Resource | Name / ID | Console |
|---|---|---|
| Cognito user pool | `order-saga-users` (`ap-south-1_Griah4PD3`), Essentials plan, deletion protection on | [User pool](https://ap-south-1.console.aws.amazon.com/cognito/v2/idp/user-pools/ap-south-1_Griah4PD3/overview?region=ap-south-1) |
| App client (storefront) | `spa` (`43mp31anuep6dffo56k08sjj9u`) | [App clients](https://ap-south-1.console.aws.amazon.com/cognito/v2/idp/user-pools/ap-south-1_Griah4PD3/applications/app-clients?region=ap-south-1) |
| App client (scripts/CI) | `automation` (`1v5m07eueaokak5ivnuvk7c3me`) | (same page) |
| Managed login domain | `https://order-saga-876889172858.auth.ap-south-1.amazoncognito.com` (v2) | [Domain](https://ap-south-1.console.aws.amazon.com/cognito/v2/idp/user-pools/ap-south-1_Griah4PD3/branding/domain?region=ap-south-1) |
| Managed login style | default Cognito look, for the `spa` client | [Managed login](https://ap-south-1.console.aws.amazon.com/cognito/v2/idp/user-pools/ap-south-1_Griah4PD3/branding/managed-login?region=ap-south-1) |
| JWT authorizer | `order-saga-cognito-jwt` (`fw4xvp`) on API `order-saga-api` | [Authorizers](https://ap-south-1.console.aws.amazon.com/apigateway/main/develop/authorizers?api=8kyxed1rec&region=ap-south-1) |
| SSM SecureStrings | `/order-saga/test-users/a`, `/order-saga/test-users/b` (key `alias/aws/ssm`) | [Parameter Store](https://ap-south-1.console.aws.amazon.com/systems-manager/parameters?region=ap-south-1) |

Sign-up page (opens straight on "Create an account"):
`https://order-saga-876889172858.auth.ap-south-1.amazoncognito.com/signup?client_id=43mp31anuep6dffo56k08sjj9u&response_type=code&scope=openid+email+profile&redirect_uri=https%3A%2F%2Fdg38gx94mao9n.cloudfront.net%2Fauth%2Fcallback`
(HTTP 200, page title "Sign up"). The simplest path for a demo is the storefront's **Sign in** → *Create an account*.

### Live configuration (from `describe-*` calls)

- Pool: `UserPoolTier = ESSENTIALS`, `MfaConfiguration = OFF`, `EmailSendingAccount = COGNITO_DEFAULT`,
  `DeletionProtection = ACTIVE`, username = email, auto-verified email, password ≥ 10 with upper/lower/digit.
- `spa`: `AllowedOAuthFlows = [code]`, scopes `email openid profile`, no secret, callbacks
  `https://dg38gx94mao9n.cloudfront.net/auth/callback` + `http://localhost:5173/auth/callback`,
  `RefreshTokenRotation = {Feature: ENABLED, RetryGracePeriodSeconds: 10}`, `PreventUserExistenceErrors = ENABLED`,
  `ExplicitAuthFlows = [ALLOW_CUSTOM_AUTH]` (inert: the pool has no custom-auth triggers), tokens 60 min, refresh 7 days.
- `automation`: `ExplicitAuthFlows = [ALLOW_ADMIN_USER_PASSWORD_AUTH, ALLOW_REFRESH_TOKEN_AUTH]`, no OAuth flows.
- Authorizer: `JWT`, identity source `$request.header.Authorization`, issuer
  `https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Griah4PD3`, audience = both client IDs.
- Routes: `GET /products` → `NONE`; `POST /orders`, `GET /orders`, `GET /orders/{id}`, `GET /wallet`,
  `POST /wallet/reset` → `JWT`.

## Rollout

| Commit | What | CI | Deploy |
|---|---|---|---|
| `15c2101` | AWS provider 5.x → `~> 6.68.0` (own commit) | [40730548204](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40730548204) ✅ | [40730665565](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40730665565) ✅ "No changes", apply 0/0/0; smoke `ORD-20261028-5090c62a` COMPLETED 4.5 s, 1 DEBIT |
| (bootstrap, local) | deploy role + `cognito-idp:AdminInitiateAuth` (after "APPLY") | | apply 1 changed; re-plan no changes |
| `ceebe0e` (A) | Cognito pool/domain/clients/branding, test users, token helper, scripts + frontend send tokens; **no authorizer, backend unchanged** | [40733526672](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40733526672) ✅ | [40733629307](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40733629307) ✅ apply 5 added, 2 changed; test users A/B **created** by the deploy role; smoke `ORD-20261028-fca46e40` COMPLETED 4.4 s, 1 DEBIT |
| `e48fbf6` (A fix) | `spa` client: `explicit_auth_flows = ["ALLOW_CUSTOM_AUTH"]` | [40734363298](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40734363298) ✅ | [40734477999](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40734477999) ❌ `AccessDenied` on `cognito-idp:ListUserPoolClients` (nothing changed) |
| (bootstrap, local) | deploy role + `cognito-idp:ListUserPoolClients` (after "APPLY") | | apply 1 changed; re-plan no changes |
| `bcff9c8` (A fix 2) | commits that bootstrap change; re-runs the A fix | [40735504142](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40735504142) ✅ | [40735614526](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40735614526) ✅ apply 1 changed; smoke `ORD-20261028-7c68eae4` COMPLETED 4.1 s, 1 DEBIT |
| `2c1444b` (B) | JWT authorizer, identity from claims, user-keyed orders/wallets/GSI, per-user idempotency | [40736799126](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40736799126) ✅ | [40736924726](https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/40736924726) ✅ apply 1 added, 15 changed; smoke: no-token `GET /wallet` → 401, `ORD-20261028-49328769` COMPLETED 4.2 s, 1 DEBIT |

## The `spa` client accepts no password API flow

`aws cognito-idp initiate-auth --client-id 43mp31anuep6dffo56k08sjj9u ...` with test user A's email (and a fake password):

| Flow | Before the fix (`explicit_auth_flows = []`) | After `bcff9c8` |
|---|---|---|
| `USER_PASSWORD_AUTH` | refused: "USER_PASSWORD_AUTH flow not enabled for this client" | refused: same |
| `USER_SRP_AUTH` | **answered with a `PASSWORD_VERIFIER` challenge** (SRP open) | refused: "USER_SRP_AUTH is not enabled for the client." |
| `CUSTOM_AUTH` | (not tried) | refused: "Custom auth lambda trigger is not configured for the user pool." |

Browser sign-in through managed login worked both before and after the fix (see below).

## Browser sign-in (Playwright, Chromium, live CloudFront)

Opening the protected `/wallet` page signed out:
1. redirected to `https://order-saga-876889172858.auth.ap-south-1.amazoncognito.com/login` with
   `code_challenge=...&code_challenge_method=S256` in the URL (PKCE);
2. the managed login form (`username` type email, `password`, button "Sign in"), filled with test user A;
3. back at `https://dg38gx94mao9n.cloudfront.net/wallet`, signed in ("Sign out" in the header, balance shown);
4. `sessionStorage` holds one key, `oidc.user:https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Griah4PD3:43mp31anuep6dffo56k08sjj9u`;
   `localStorage` holds no token; `/orders` loads; 0 browser console errors.

### Full UI suite: 6/6 (`python scripts/capture_ui.py`, [screenshots](ui/README.md))

Signs in through the real managed login page as test user A (`desktop-00-managed-login.png`, taken before the form is
filled, so no credentials appear in it), then runs every scenario through the storefront with ledger checks:

| Scenario | orderId | Result | DEBITs (expected) |
|---|---|---|---|
| Normal | `ORD-20261028-e7b319fa` | Order completed; balance 10,00,000 → 9,96,501 | 1 (1) |
| Payment glitch (retries) | `ORD-20261028-c765f7db` | Order completed | 1 (1) |
| Payment declined | `ORD-20261028-27f51557` | Order failed | 0 (0) |
| Low balance (real decline) | `ORD-20261028-b4d56f34` | Order failed | 0 (0) |
| Duplicate test (3 requests) | `ORD-20261028-cb8df6a3` | Order completed · 1 order | 1 (1) |
| Poison message (to DLQ) | `ORD-20261028-67d9704f` | Stuck in the dead-letter queue | 0 (0) |

Browser console errors during the run: 0. The mobile pass (360 px) signs in separately and covers shop, product,
checkout, tracker and wallet.

## End-to-end suite after commit B: 14/14 PASS

`python scripts/seed_inventory.py && python scripts/e2e_test.py` (226 s, [full output](e2e-failure-tests.md)). Every
request is signed in as test user A or B; no request sends an email or user id.

| # | Scenario | orderId |
|---|---|---|
| a | none → COMPLETED, 1 DEBIT | `ORD-20261028-fd7f2ff3` |
| b | payment_declined → FAILED, compensation | `ORD-20261028-5b827a2b` |
| c | payment_flaky → 2 retries → COMPLETED, 1 DEBIT | `ORD-20261028-ea2f10d0` |
| d | out_of_stock → FAILED, no release | `ORD-20261028-bf27518c` |
| e | same Idempotency-Key ×3 → 1 order (user-scoped key), 1 stream INSERT, 1 execution | `ORD-20261028-f5bd29d7` |
| f | same {orderId} sent 3× to SQS → 1 execution | `ORD-20261028-f20b357e` |
| g | poison → orders DLQ, outbox DLQ 0 | `ORD-20261028-4d66d9c4` |
| h | user B's wallet at ₹1,000 → real decline | `ORD-20261028-a8fa4e9c` |
| i | crash simulation (row written directly, user-keyed shape) → COMPLETED via the outbox | `ORD-20261028-d705754d` |
| j | MODIFY back to PENDING → not re-delivered | `ORD-20261028-d705754d` |
| **k** | **auth gate**: `GET /products` without a token → 200; `POST /orders`, `GET /orders`, `GET /orders/{id}`, `GET /wallet`, `POST /wallet/reset` without a token → **401**; tampered signature → **401**; payload forged with user B's `sub` → **401**; a valid **access** token (no email claim) → **403** "Send the ID token: it must carry a verified email" | none |
| **l** | **order isolation**: B's order read by A → **404**, worded exactly like a missing order; A's list (18 orders) has no B order, B's list (5) has it, no overlap, every order in A's list has A's `sub` | `ORD-20261028-007c022f` (B's) |
| **m** | **wallet isolation**: A's `POST /wallet/reset?email=<B>` with body `{balance: 4321, email: <B>, walletId: <B's sub>}` → A's wallet = 4321; **B's wallet unchanged** (₹9,98,701, 7 → 7 ledger entries) | none |
| **n** | **per-user idempotency**: A → 202 (`ORD-20261028-418dd2b7`); B with the **same key** → 202, a **different** order owned by B; A again → 200 duplicate of its original; A reading B's order → 404; both COMPLETED | `ORD-20261028-660da4c0` (B's) |

The step 1.1 outbox checks (e, g, i, j) all pass on the user-keyed data. All simulate flags (a–d, g) work with auth.

### First run: 13/14, and why

The first run after commit B failed scenario e on two checks, while the system behaved correctly (HTTP 202/200/200,
1 orderId, 1 execution, 1 DEBIT for `ORD-20261028-f17ab359`):
1. *"orders with this key in DynamoDB: 0"*: the script scanned for the raw key, but the order row now stores the
   user-scoped key `<sub>#<key>`. The test was updated to look for the scoped key.
2. *"INSERT records for this order in the orders stream: 0"*: the stream now has 4 open shards, and the reader stopped
   a shard after 2 empty pages. An open DynamoDB stream shard can return empty pages before its end. Re-reading with
   a patient reader found **1** INSERT for that order. The helper now stops after 10 empty pages in a row.

## Unit tests

`pytest --cov=src`: **81 passed, 94% coverage** (CI gate 85%). New tests: identity fields in the body are ignored;
no `sub` → 401, access token / unverified email → 403; another user's order → 404 with the same wording as a missing
one; a legacy order without `userId` → 404; `GET /orders` lists only the caller's; `GET /wallet?email=<other>` returns
the caller's wallet; a reset with someone else's ids changes only the caller's; same key from two users → two orders
and two scoped records; payment charges `order.walletId` and leaves an email-keyed legacy wallet untouched; an order
with no `walletId` is declined.

## Legacy data

Not deleted or migrated. Email-keyed wallet rows and orders with `gsi1pk = "ORDER"` (no `userId`) stay in the tables;
the API can no longer reach them (`GET /orders/{id}` → 404, not listed).

## Problems hit

1. **An empty `explicit_auth_flows` left SRP password auth open** on the public client (Cognito applies its defaults
   when the list is unset). Found with a live `InitiateAuth USER_SRP_AUTH` call; fixed with `["ALLOW_CUSTOM_AUTH"]`.
   `ALLOW_REFRESH_TOKEN_AUTH` can't be listed because refresh-token rotation forbids it.
2. **Deploy role `AccessDenied` on `cognito-idp:ListUserPoolClients`** (CloudTrail, run 40734477999, 17:19:30Z): the
   provider lists a pool's clients before updating one; creating them never needed it. Added to the bootstrap policy.
3. **E2E scenario e false failures** (raw vs scoped key; stream reader quitting early on an open shard): see above.
4. **AWS provider 5.x has no `aws_cognito_managed_login_branding`**, which managed login v2 needs per app client:
   upgraded to 6.68.x first, in its own commit, with a no-changes plan.

## Cost

- Cognito Essentials: 10,000 monthly active users free (not a 12-month trial). This demo has 2 test users plus any
  demo sign-ups. Default email sender: free (limited to a few dozen emails per day per account).
- JWT authorizer: no extra charge. SSM standard SecureStrings with the AWS-managed key: free.
- No M2M tokens, no Plus-plan threat protection, no SMS. Expected cost of this step: $0.

## DLQ state after this step

- `order-saga-outbox-dlq`: 0 messages; outbox alarms OK.
- `order-saga-orders-dlq`: 11 messages when this was written (9 before this step + the poison orders of the two e2e
  runs, `ORD-20261028-a6ebc2df` and `ORD-20261028-4d66d9c4`). The UI run's poison order `ORD-20261028-67d9704f` was
  still in flight on the orders queue (1 not visible) and moves to the DLQ on its next receive, making 12.
  Not purged or redriven. `order-saga-dlq-not-empty` stays in ALARM by design.
