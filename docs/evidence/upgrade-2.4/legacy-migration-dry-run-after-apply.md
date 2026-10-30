# Legacy stock cleanup: dry-run (2026-10-30T12:58:56.438Z)

## Stock check BEFORE

| Product | stock | held | reserved | sold | writtenOff | I5 (sum = seed) | reserved = in flight + legacy |
|---|---|---|---|---|---|---|---|
| 4K-MONITOR | 99 | 0 | 0 | 1 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |
| ANC-HEADPHONES | 96 | 0 | 0 | 2 | 2 | 100 = 100 OK | 0 = 0 + 0 OK |
| COMPACT-KEYBOARD | 13 | 0 | 0 | 1 | 0 | 14 = 14 OK | 0 = 0 + 0 OK |
| CURVED-MONITOR | 100 | 0 | 0 | 0 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |
| DESK-MAT | 99 | 0 | 0 | 1 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |
| ERGO-MOUSE | 98 | 0 | 0 | 1 | 1 | 100 = 100 OK | 0 = 0 + 0 OK |
| LAPTOP-STAND | 95 | 0 | 0 | 4 | 1 | 100 = 100 OK | 0 = 0 + 0 OK |
| LOWPRO-KEYBOARD | 96 | 0 | 0 | 4 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |
| MECH-KEYBOARD | 98 | 0 | 0 | 2 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |
| PODCAST-MIC | 100 | 0 | 0 | 0 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |
| USB-MIC | 18 | 0 | 0 | 0 | 0 | 18 = 18 OK | 0 = 0 + 0 OK |
| USBC-HUB | 99 | 0 | 0 | 0 | 1 | 100 = 100 OK | 0 = 0 + 0 OK |
| VERTICAL-MOUSE | 9 | 0 | 0 | 0 | 0 | 9 = 9 OK | 0 = 0 + 0 OK |
| WEBCAM-1080P | 0 | 0 | 0 | 0 | 0 | 0 = 0 OK | 0 = 0 + 0 OK |
| WIRELESS-EARBUDS | 97 | 0 | 0 | 1 | 2 | 100 = 100 OK | 0 = 0 + 0 OK |
| WIRELESS-MOUSE | 95 | 0 | 0 | 5 | 0 | 100 = 100 OK | 0 = 0 + 0 OK |

Result: PASS

## Plan

- Orders scanned: 505; legacy COMPLETED orders not yet migrated: **0**
- With units still in `reserved` (reserved after the last seed): **0** orders, **0** units
- Reserved before the last seed (counters already reset, only marked): 0 orders

| Product | units reserved -> sold |
|---|---|
| (none) | 0 |

| orderId | RESERVED at | moves | reset by the seed |
|---|---|---|---|

DRY RUN: nothing was written. Run with --apply to migrate.
