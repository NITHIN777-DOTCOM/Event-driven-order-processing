# Upgrade step 2.2: checkout holds (evidence)

Run on 2026-10-29 against the deployed stack in ap-south-1 (Mumbai). Design and interview notes:
[`docs/interview-prep.md` §11](../interview-prep.md#11-checkout-holds-10-minute-reservation-with-precise-expiry).

## Rollout

| Commit | What | CI | Deploy (terraform apply) |
|---|---|---|---|
| `b6ed9e3` part 0 | 2.1 postmortem, plan-time tag validation (`infra/modules/tag_values` + `terraform test`), expand → migrate → contract rule | green | green, no changes |
| (local, after "APPLY") | bootstrap: deploy role may manage `schedule-group/order-saga-*`; state-bucket tag without "/" | - | 2 changed, re-plan no changes |
| `08e8460` A | holds table, API (`POST /holds`, `GET /holds/current`, `DELETE /holds/{holdId}`), Scheduler group + role, expiry Lambda, alarm, dashboard row. Saga and storefront untouched | 40864783835 green | 40864924694: 22 added, 17 changed, 0 destroyed |
| `e2a90b8` B | orders carry `holdId`; ReserveInventory consumes the hold or falls back; storefront countdown | 40866782079 green | 40866957986: 1 added, 5 changed, 0 destroyed |

Commit A added a new path that nothing used yet; B switched the saga and the storefront onto it. Nothing was removed,
so there is no contract step.

## Live e2e: 26/26 (`scripts/e2e_test.py`, full output in [`e2e-failure-tests.md`](e2e-failure-tests.md))

Scenarios a–s (orders, failures, auth, payments) all still pass. New in 2.2:

| # | Scenario | Key evidence |
|---|---|---|
| t | hold lifecycle | COMPACT-KEYBOARD (stock, held, reserved) (14, 0, 0) → (12, 2, 0); the 2nd hold RELEASED the 1st and deleted its schedule; qty 6 → 400; 10 s duration → 400; WEBCAM-1080P → **409 naming the product**; DELETE → (14, 0, 0) |
| u | 30 s hold expired by its schedule | `HOLD-20261029-79cb7f26e9` EXPIRED, `expiredBy: schedule`, **20.1 s** after `expiresAt`; schedule deleted itself; units back in the pool |
| v | two users race for the last VERTICAL-MOUSE | HTTP codes **[201, 409]**; the 409 names VERTICAL-MOUSE; (stock, held) (0, 1); restored to (9, 0, 0) |
| w | ownership | B's DELETE of A's hold → **404** (same as a missing hold); B never sees it; A's stays ACTIVE |
| x | I5 stock conservation | seeded = stock + held + reserved, and held = units in ACTIVE holds, **for all 16 products** |
| y | order consumes its hold | `ORD-20261029-e5331e73` COMPLETED; B posting A's `holdId` → **400**; RESERVED "from checkout hold HOLD-20261029-c0177385c9"; hold CONSUMED by this order; LAPTOP-STAND (98, 0, 2) → (97, 0, 3): **stock taken once**, at hold time; schedule deleted; I1/I3/I4 hold |
| z | order after its 30 s hold expired | `ORD-20261029-1599e6c9` COMPLETED; RESERVED "(checkout hold HOLD-20261029-9f0f6c3fe2 had ended, so reserved afresh)"; COMPACT-KEYBOARD (14, 0, 0) → (13, 0, 1); hold stays EXPIRED |

The "OutOfStock after expiry" branch (someone else took the units after your hold expired) is covered by the unit
test `test_after_expiry_someone_else_can_take_the_stock_and_the_order_is_out_of_stock`.

Commit A's first live run was 23/24. Scenario u failed on `DESK-MAT (99, 0, 1), expected (100, 0, 0)`: scenario l
ordered a desk mat during u's 30 s window, so an exact before/after comparison of a shared counter was wrong
**in the test**. I5 (x) passed in that same run. u now checks what the hold controls (held back to its earlier
value; stock + reserved unchanged).

## Expiry precision (EventBridge Scheduler, `at()`, FlexibleTimeWindow OFF)

| Hold | expiresAt | Released (by the schedule) | Lag |
|---|---|---|---|
| HOLD-20261029-94be85f1a0 (run A, u) | 11:29:09.000Z | 11:29:54.911Z | 45.9 s |
| HOLD-20261029-79cb7f26e9 (run B, u) | 11:42:43.000Z | 11:43:03.136Z | 20.1 s |
| HOLD-20261029-9f0f6c3fe2 (run B, z) | 11:42:43.000Z | 11:42:54.798Z | 11.8 s |

n = 3, median 20.1 s, max 45.9 s. All three fired within about a minute but not at the exact second, so a
`HH:MM:SS` `at()` time is not second-precise in practice. This is why expiry is also enforced logically:
- after `expiresAt` the hold can't be consumed (`expiresAtEpoch > now` in the transaction);
- reading it (`GET /holds/current`, ReserveInventory) expires it on the spot;
- the storefront shows "Your hold expired" at 0:00, from server time.

The lag only delays when other shoppers get the units back. Three samples are not a distribution; the dashboard widget
"Expiry lag: schedule fired after expiresAt (ms)" (p50/max of `OrderSaga/HoldExpiryLag`) keeps measuring.

## Unit tests

217 passed, coverage **94%** (gate 85%). Hold-specific: `tests/unit/test_holds.py` (28: atomic create, per-user
limit, ownership 404, races, idempotent expiry, client_id duration rules, stale pointer repair) and
`tests/unit/test_hold_orders.py` (13: holdId validation, consume, fallback, overdue expiry at reserve time, lost
race → fallback, compensation after consume, I5).

## UI

`scripts/capture_ui.py` (Playwright + Chromium, deployed storefront, Cognito sign-in): **8/8**, 0 browser console
errors ([`ui/README.md`](ui/README.md)).
- Every checkout waits for the countdown (10:00 or 9:5x) before going on.
- The Normal order `ORD-20261029-2f17d17b` consumed its hold (RESERVED detail "from checkout hold"), and was
  debited once.
- In its own browser context with Playwright's fake clock, the run jumped 9:01 ahead to show the red last minute
  ([`desktop-07c`](ui/desktop-07c-checkout-hold-last-minute.png)), then past 10:00 to show "Your hold expired" +
  "Hold again" ([`desktop-07d`](ui/desktop-07d-checkout-hold-expired.png)).
- "Hold again" created `HOLD-20261029-0b69b40bc8`, which replaced `HOLD-20261029-2f5d6591e4`. Leaving checkout
  released it (`GET /holds/current` → null).
- Entering checkout: [`desktop-07-checkout-details`](ui/desktop-07-checkout-details.png) (10:00 banner).

## Resources (ap-south-1)

| Service | Name | Purpose |
|---|---|---|
| DynamoDB | `order-saga-holds` | holds + `USER#<sub>` pointer items; TTL `purgeAt` (clean-up only) |
| EventBridge Scheduler | schedule group `order-saga-holds` | one `at()` schedule per hold, deletes itself after firing |
| IAM | `order-saga-holds-scheduler-role` | Scheduler may invoke `order-saga-hold-expiry` only (`aws:SourceAccount` condition) |
| Lambda | `order-saga-holds-api`, `order-saga-hold-expiry` | the hold API; the expiry target |
| SSM | `/order-saga/auth/client-ids` (String) | spa / automation client ids for the duration rule |
| CloudWatch | alarm `order-saga-hold-expiry-errors`; metric filters → `OrderSaga/HoldEvents`, `OrderSaga/HoldExpiryLag`; dashboard row 9 (active holds, transitions, expiry lag, expiry Lambda) | |

App stack: 156 resources (was 133); bootstrap 13.

## Cost

Scheduler: 14 M invocations/month free, then $1 per million. One extra on-demand table, two Lambdas, one free
standard SSM parameter. Idle cost added: $0.
