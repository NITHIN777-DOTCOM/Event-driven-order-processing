# Outbox timing: after

Run: 2026-10-28 16:12:26 UTC · `python scripts/outbox_check.py timing --label after` · 10 orders, one at a time, product DESK-MAT, simulate=none

| orderId | status | executions | DEBITs | client POST→COMPLETED (ms) | PENDING→PROCESSING (ms) | PENDING→COMPLETED (ms) |
|---|---|---|---|---|---|---|
| `ORD-20261028-a122182f` | COMPLETED | 1 | 1 | 1110 | 110 | 486 |
| `ORD-20261028-a6ddebf7` | COMPLETED | 1 | 1 | 1078 | 527 | 819 |
| `ORD-20261028-757ae894` | COMPLETED | 1 | 1 | 1047 | 435 | 737 |
| `ORD-20261028-289dddc6` | COMPLETED | 1 | 1 | 765 | 104 | 393 |
| `ORD-20261028-c1ee11d9` | COMPLETED | 1 | 1 | 1141 | 353 | 674 |
| `ORD-20261028-6a5c5d1b` | COMPLETED | 1 | 1 | 1172 | 434 | 752 |
| `ORD-20261028-92adc13f` | COMPLETED | 1 | 1 | 1500 | 542 | 1038 |
| `ORD-20261028-14d52cd7` | COMPLETED | 1 | 1 | 1157 | 266 | 519 |
| `ORD-20261028-30ab4897` | COMPLETED | 1 | 1 | 1171 | 340 | 616 |
| `ORD-20261028-0d8706e3` | COMPLETED | 1 | 1 | 750 | 202 | 476 |

- client POST→COMPLETED (ms): min 750 · median 1125 · p95 1500 · max 1500
- PENDING→PROCESSING (ms): min 104 · median 346 · p95 542 · max 542
- PENDING→COMPLETED (ms): min 393 · median 645 · p95 1038 · max 1038

**Result: PASS**
