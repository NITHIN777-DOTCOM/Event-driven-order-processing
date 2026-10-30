# Step 2.4: customer cancellation mid-saga (evidence)

Live, ap-south-1, 2026-10-30. `POST /orders/{id}/cancel` (Cognito, owner only, idempotent) cancels an order while it
waits for payment or is paid but not yet being fulfilled. One conditional write on the order item decides every race:
the cancel, the payment webhook's capture and `BeginFulfillment` each require that the others haven't happened.
The cancel answers the paused payment task with `SendTaskFailure("OrderCancelled")` (never `StopExecution`), and the
saga's cancel branch voids or refunds what was charged, releases the stock and marks the order **CANCELLED**.

New invariants, checked for every e2e order:
- **I8** a CANCELLED order has net charge ₹0, its stock released (INVENTORY_RELEASED) and no line fulfilled.
- **I9** cancel and payment never both win: an order with `cancelRequestedAt` is CANCELLED and never reached FULFILLING.

## Rollout (expand -> migrate -> switch, nothing removed)

| Commit | What | Deploy (terraform apply) | Live check |
|---|---|---|---|
| A `eb9a4ab` | cancel_order + begin_fulfillment Lambdas, `POST /orders/{id}/cancel` route, DemoPay void, conditional webhook/request_payment writes, alarm + metric filters + dashboard row, legacy migration script. **Switched off:** `CANCEL_ENABLED=false` (503), the state machine unchanged. CI 41043851030, Deploy 41044113358 | 16 added, 22 changed, 0 destroyed | full e2e 28/29 (g: test flaw, below), then **29/29**; UI **9/9**; legacy migration |
| B `48e7d8e` | the state machine's cancel branch, `cancellable` stamp, BeginFulfillment, the cancel check before MarkOrderFailed; `CANCEL_ENABLED=true`; storefront, feed, notification; SFN role may `dynamodb:GetItem` the orders table. CI 41060910418, Deploy 41061113800 | 0 added, 21 changed, 0 destroyed | in-flight check **PASS**; e2e **35/35**; UI 10/10 after the fix |
| B fix `fd8709a` | the CANCEL_REQUESTED entry names the reason once; UI capture waits for the tracker; UTF-8 output. CI 41064702078, Deploy 41065249876 | 0 added, 19 changed, 0 destroyed | UI **10/10** |

Evidence files: `upgrade-2.4/e2e-commit-A.md` (29/29 on A), `upgrade-2.4/e2e-commit-B.md` (35/35 on B),
`upgrade-2.4/inflight-definition.md`, `upgrade-2.4/legacy-migration-{apply,check,dry-run-after-apply}.md`,
`e2e-failure-tests.md` (latest), `ui/README.md`.

## Commit A: nothing changed

With the new Lambdas deployed but switched off, the full existing suite passed **29/29** and the UI suite **9/9**.
The first e2e run was 28/29: scenario g did not find the poison message in the orders DLQ within 5 min. It *was*
there: a sweep found 27 distinct messages, this one among them. The DLQ is never purged, so it held 27 messages,
and the test peeked once per loop with `MaxNumberOfMessages=10` and `VisibilityTimeout=0`: at most 10 messages,
none hidden afterwards, so every peek could return the same 10. See "Debugging story" in
`docs/interview-prep.md` section 13 for the deterministic version now in place.

## Legacy cleanup (`scripts/migrate_legacy_sold.py`)

Orders that completed on the pre-2.3 definition never moved their units from `reserved` to `sold`.

| | Value |
|---|---|
| Orders scanned | 505 |
| Legacy COMPLETED orders, not yet migrated | **233** |
| ... with units still in `reserved` (reserved after the last seed) | **0 orders, 0 units** |
| ... reserved before the last seed (counters already reset, only marked) | 233 |
| Applied | 233 of 233 marked (`legacyStockMigratedAt`, `legacyUnitsMoved = 0`), one transaction per order |
| Stock check BEFORE / AFTER | **PASS / PASS** for all 16 products (I5, and reserved = in flight + legacy) |
| Re-run (dry-run) | 0 orders left: idempotent |

## Commit B: running executions keep the old definition (`scripts/inflight_check.py`)

`payment_slow` orders every 10 s while the Deploy ran; every 2 s the cancel API was asked to cancel each running
order WITHOUT the `cancellable` stamp (old definition).

| Result | Value |
|---|---|
| Executions that straddled the update | 2 (`ORD-20261030-37aca7af`, `ORD-20261030-8d3a3daf`), both COMPLETED on the **old** definition |
| Old-definition orders asked to cancel after the flag flipped | **13, all 409 NOT_CANCELLABLE**, none cancelled, all COMPLETED |
| Before the flag flipped | 503 CANCEL_DISABLED (14 orders; 2 of them were asked again after the flip and got 409) |
| First order after the update | `ORD-20261030-7dbed2c2`: new definition, entered BeginFulfillment |

**Finding:** the cancel Lambda (`CANCEL_ENABLED=true`) was updated about 2 minutes **before** the state machine
(13:12 vs 13:14:27 UTC) in the same `terraform apply`. For those 2 minutes, cancellation was on while every
execution still ran the old definition, which has no `OrderCancelled` Catch. The `cancellable` stamp, written only by
the new definition's ReserveInventory, is what kept those orders safe: every one was refused with 409.

## Commit B: live e2e (35/35, `scripts/e2e_test.py`)

All 29 previous scenarios still pass (scenario a's history now has FULFILLING before ITEM_FULFILLED), plus:

| # | Scenario | Order | Result |
|---|---|---|---|
| zd | cancel while waiting for payment (`payment_slow`) | `ORD-20261030-7726b40c` | 202; B's cancel 404; repeat = same `cancelRequestedAt`; CANCELLED "nothing was charged" **0.35 s** after the request; DemoPay's delayed charge found the intent **VOIDED**; ledger empty; a cancel after the end -> 200, refundedAmount 0 |
| ze | cancel after payment (`fulfillment_slow`) | `ORD-20261030-4cd495b4` | CANCELLED **10.18 s** after the request (the saga acts on it at BeginFulfillment, after the 10 s demo Wait); one DEBIT + one CREDIT of the total, note "Refund for ... (order cancelled)"; intent REFUNDED; cancel twice -> 200, same amount |
| zf | cancel during fulfillment | `ORD-20261030-94055573` | 409 `{"error": "TOO_LATE_TO_CANCEL", "status": "FULFILLING"}` twice; COMPLETED; exactly one CANCEL_REJECTED entry |
| zg | cancel a COMPLETED order (a's) | `ORD-20261030-b94dfc11` | 409 TOO_LATE_TO_CANCEL; status unchanged |
| zh | cancel an order placed from a checkout hold | `ORD-20261030-16044a76` | CANCELLED 0.52 s after the request; hold CONSUMED by the order; (stock, held, reserved, sold, writtenOff) exactly as before the hold |
| zi | race x20 | `ORD-20261030-eb4de5fb` + 19 | below |

### The race (zi)

20 `payment_manual` orders, each paused on its payment token. For each one, two threads met at a barrier and fired
at once: `POST /orders/{id}/cancel` (delayed 0-950 ms, 50 ms more per order, so both orders of arrival happen) and
DemoPay's charge (the payment provider Lambda invoked directly, which debits the wallet and calls the webhook).

| Outcome | Orders | Ledger | Final |
|---|---|---|---|
| cancel won, nothing charged (the void beat the charge) | **14** | none | CANCELLED, intent FAILED |
| cancel won, the charge landed anyway; the losing webhook refunded it | **4** | 1 DEBIT + 1 CREDIT | CANCELLED, intent REFUNDED |
| payment won, BeginFulfillment ran, the cancel was refused (409) | **2** | 1 DEBIT | COMPLETED |
| both won | **0** | | |

Every order passed I1-I9. WIRELESS-EARBUDS moved by exactly the 2 COMPLETED units (stock -2, sold +2, reserved
unchanged), and I5 held for all 16 products at the end of the run.

## Observability (last 3 h, after the runs)

Metric `OrderSaga/CancelEvents` (dimension `Event`, from the metric filters on cancel_order, refund_payment,
payment_webhook and begin_fulfillment):

| Event | Count |
|---|---|
| accepted | 22 |
| nothing_charged | 16 |
| refunded | 6 |
| late_charge_refunded | 2 |
| repeated | 3 |
| rejected_too_late | 7 |
| not_cancellable | 88 (the in-flight probe asked every 2 s) |
| fulfillment_started | 23 |

Alarm `order-saga-cancellation-errors` (cancel_order + begin_fulfillment + release_inventory errors): **OK**.

## UI (`scripts/capture_ui.py`, 10/10)

"Cancel after payment" (`Slow warehouse` scenario) from the tracker: `desktop-10d-tracker-cancel-button`,
`desktop-10e-tracker-cancel-confirm`, `desktop-10f-tracker-cancelled` ("Order cancelled", "Cancelled — refunded
₹1,299", Cancelled badge, cancellation email), `desktop-10g-wallet-cancel-refund` (the CREDIT "order cancelled").
Two defects found in the first B run and fixed in `fd8709a`: the feed row repeated the default reason
("...: Cancelled by the customer"), and the confirm screenshot was taken before the tracker's 1.5 s poll had shown
the payment (the capture checked the API instead of the page).
