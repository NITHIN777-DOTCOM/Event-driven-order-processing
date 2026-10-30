# Step 2.3: per-item fulfillment with partial refunds (evidence)

Live, ap-south-1, 2026-10-30. Reservation stays all-or-nothing. After the payment succeeds, the inline Map
`FulfillItems` fulfils each line on its own. A line found damaged is refunded (DemoPay line refund, at the price
stored on the order) and written off; the rest ships, and the order ends **PARTIALLY_FULFILLED**.

## Rollout (expand -> migrate, nothing removed)

| Commit | What | Deploy (terraform apply) | Live check |
|---|---|---|---|
| A `25a6b90` | fulfill-item + write-off-lines Lambdas, table `order-saga-write-offs`, DemoPay line refund + cap, refund_payment `lineIds`, per-line prices on new orders, alarm + metric filters + dashboard row. **Not wired into the saga.** | 15 added, 22 changed, 0 destroyed | `fulfillment_check.py` **19/19**; full e2e **26/26** (old path unchanged) |
| B `89f355f` | Map + SummarizeFulfillment + Choice + PARTIALLY_FULFILLED path + all-unavailable path, `item_unavailable` / `simulateLine`, line details in the order APIs, storefront | 0 added, 20 changed, 0 destroyed | e2e 28/29 (u: test flaw), then **29/29** after the fix |
| B fix `e464e66` | wallet shows the refund note; test fixes (u pool, in-flight probe product); Map comment | 0 added, 1 changed, 0 destroyed | in-flight check **PASS**; UI suite (below) |

Evidence files: `docs/evidence/upgrade-2.3/fulfillment-check.md` (commit A, direct invokes),
`upgrade-2.3/e2e-commit-A.md` (26/26 on A), `upgrade-2.3/e2e-commit-B-first-run.md` (28/29),
`e2e-failure-tests.md` (29/29, latest), `upgrade-2.3/inflight-definition.md`, `ui/README.md`.

## Commit A, tested in isolation (`scripts/fulfillment_check.py`, order `ORD-20261030-399cf6c3`)

A 3-line order (3 x Slim Wireless Mouse ₹2,397, 1 x Noise-Cancelling Headphones ₹26,990, 2 x Ergonomic Mouse
₹12,998; total ₹42,385 = the sum of the stored lines) completed on the OLD definition, with its units still in
`reserved`. The new Lambdas were then invoked directly:
- fulfill L1 and L3 **concurrently** (two lines of one order: the transaction-conflict path), then L1 again: each
  line's units moved reserved -> sold exactly once.
- write off L2 twice: 1 unit, then 0. One audit record; reserved -> writtenOff; not back on sale.
- refund L2 twice: ONE CREDIT of exactly ₹26,990. The intent stays SUCCEEDED with refundedAmount 26,990.
- **I7 probe:** a DemoPay line refund of the whole ₹42,385 on top of L2 -> `RefundRejected`; ledger unchanged.
- I6: net ₹15,395 = L1 + L3. I5 unchanged for all three products.

Then the **full existing e2e suite passed 26/26 on commit A**. Scenario a additionally asserted that an
old-definition COMPLETED order moves nothing to `sold` (MECH-KEYBOARD (sold, writtenOff) (0, 0) -> (0, 0)) and that
new orders store `L1` + `lineAmount`; x (I5) summed all five counters, including the fulfillment-check order.

## Commit B, live e2e (29/29)

| # | Scenario | orderId | Result |
|---|---|---|---|
| za | 3 lines (2 x Mouse ₹1,598 / 1 x Ergo Mouse ₹6,499 / 3 x Low-profile Keyboard ₹6,897), line 2 damaged | `ORD-20261030-6289f422` | PARTIALLY_FULFILLED; ledger 1 DEBIT ₹14,994 + 1 CREDIT ₹6,499 (L2); **net ₹8,495 = L1 + L3 (I6)**; L2 written off + audit record; L1/L3 reserved -> sold; execution SUCCEEDED at OrderPartiallyFulfilled |
| zb | every line damaged | `ORD-20261030-c689fb2c` | FAILED "AllItemsUnavailable: all items unavailable - INR 11997.00 refunded …"; 2 CREDITs (one per line), net ₹0, intent REFUNDED; everything written off; ReleaseInventory did not run |
| zc | checkout hold + last line damaged | `ORD-20261030-96692ac2` | hold CONSUMED once; LAPTOP-STAND (97,0,0,3,0) -> (96,0,0,4,0); ANC-HEADPHONES (99,0,0,1,0) -> (97,0,0,1,2) |
| a | single item, no flag | `ORD-20261030-af2706e5` | COMPLETED as before: one DEBIT; history gains ITEM_FULFILLED; the unit goes reserved -> sold |
| x | I5, all 16 products | - | seeded = stock + held + reserved + sold + writtenOff; writtenOff = write-off records since `seededAt` |

All the earlier scenarios (a–z: 2.1 payment flags, 2.2 holds, outbox, auth) still pass, and I1–I4, I6 and I7 were
checked for every order. I3 is now per line: at most one DEBIT, at most one CREDIT per line, and at most one
whole-remainder CREDIT.

**First B run: 28/29.** u failed: DESK-MAT (100, 0, 0) -> (99, 0, 0), "stock + reserved" 99 instead of 100.
Scenario l orders a desk mat during u's 30 s window, and since B that unit ends in `sold`, a counter u didn't add.
I5 (x) passed in the same run. The fix was in the test (u's pool = stock + reserved + sold + writtenOff). It's the same lesson as
2.2's u failure: a test may only compare what its own action controls.

## Timings (execution history)

| Order | Lines | FulfillItems (Map) | Whole execution |
|---|---|---|---|
| a `ORD-20261030-604d2a92` | 1 | 0.181 s | 4.9 s |
| za `ORD-20261030-ad9664a8` | 3 | 0.230 s | 5.8 s |
| zc `ORD-20261030-05694fd9` | 2 | 0.135 s | 6.2 s |
| zb `ORD-20261030-26e3307f` | 2 | 0.210 s | 3.2 s |

(First B run's orders; the payment webhook's 2–5 s dominates the total.)

## Running executions keep their definition

`scripts/inflight_check.py` places a `payment_flaky` order (~11 s execution) every 10 s while the Deploy job
updates the state machine, then reads each execution's definition with `DescribeStateMachineForExecution`.

| orderId | Window | Started (UTC) | Stopped (UTC) | Definition used |
|---|---|---|---|---|
| `ORD-20261030-22902131` | before | 09:41:07.608 | 09:41:18.609 | old |
| **`ORD-20261030-62b512cd`** | **straddled** | **09:41:17.873** | **09:41:28.823** | **old** |
| `ORD-20261030-d3064971` | after | 09:41:28.136 | 09:41:39.218 | new |

The definition was updated at **09:41:22 UTC**. The execution that was running at that moment finished on the
definition it started with. (The script prints local time, IST = UTC+5:30, so the raw output reads 15:11.)
Full table: `upgrade-2.3/inflight-definition.md`.

**During commit B itself the check was inconclusive.** That was a test bug: the probe product USB-MIC has only
18 units seeded and ran out ~1.5 min before the update. Every later execution failed at ReserveInventory in
0.3 s, so none was running at the update (`upgrade-2.3/inflight-definition-commit-B-attempt.md`). The fix-commit
deploy is a real definition update (a Comment change), with the same mechanism. The executions that ran on
the pre-B definition during B's deploy finished as before: COMPLETED with no ITEM_FULFILLED, units in `reserved`.

## Observability (after the runs, last 3 h)

- Alarm `order-saga-refund-or-write-off-errors`: **OK**. refund-payment 19 invocations / 0 errors, write-off-lines
  7 / 0.
- `OrderSaga/FulfillmentEvents`: fulfilled 33, unavailable 8, written_off 9, line_refunded 9, partially_fulfilled
  5, all_unavailable 2 (they include the commit A check's direct invokes).
- fulfill-item: 40 invocations, **8 errors = the 8 simulated `ItemUnavailable` raises**. Step Functions only
  catches a business error that the Lambda raises, so these count as Lambda errors. That's why there's no alarm on
  fulfill-item errors; the `unavailable` metric is the business signal.

## UI (`scripts/capture_ui.py`)

**9/9 scenarios OK, 0 browser console errors** (after the B fix deploy). New: "Item damaged (partial refund)",
`ORD-20261030-e9c97701` (1 x Slim Wireless Mouse ₹799 + 1 x Aluminium Laptop Stand ₹1,799, the stand damaged):
- `ui/desktop-10b-tracker-partially-fulfilled.png`: title "Order partially fulfilled", pill "Partially
  fulfilled", last step "Partly delivered · 1 of 2 refunded", the mouse "Delivered", the stand "Cancelled — refunded
  ₹1,799", "Refunded to wallet −₹1,799", feed rows for the pack, line refund, write-off and PARTIALLY_FULFILLED.
- `ui/desktop-10c-wallet-partial-credit.png`: the ledger's Refund row +₹1,799 with "Refund for ORD-20261030-e9c97701
  line L2 (1 x Aluminium Laptop Stand)" under the order id, and one Debit of ₹2,598.

The first UI run on B stopped at the wallet check. The CREDIT was correct (1 x ₹1,799), but the page showed only
the order id, not the ledger note the test looked for. The B fix shows the note on refund rows, so a partial
refund says which item it was for.

Known nit: the write-off feed row repeats the item name ("1 x Aluminium Laptop Stand (line L2) written off:
Aluminium Laptop Stand (line L2) was found damaged …"), because the write-off reason is fulfill_item's error
message. It's cosmetic; it'll be trimmed in a later step.
