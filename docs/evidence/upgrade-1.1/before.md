# Outbox timing: before

Run: 2026-10-28 16:06:20 UTC · `python scripts/outbox_check.py timing --label before --dual` · 10 orders, one at a time, product DESK-MAT, simulate=none

| orderId | status | executions | DEBITs | starts / duplicates logged | client POST→COMPLETED (ms) | PENDING→PROCESSING (ms) | PENDING→COMPLETED (ms) |
|---|---|---|---|---|---|---|---|
| `ORD-20261028-7570015d` | COMPLETED | 1 | 1 | 1 / 1 | 1281 | 229 | 1007 |
| `ORD-20261028-b8bd68d7` | COMPLETED | 1 | 1 | 1 / 1 | 672 | 80 | 368 |
| `ORD-20261028-bd1f35d9` | COMPLETED | 1 | 1 | 1 / 1 | 703 | 60 | 366 |
| `ORD-20261028-8575182d` | COMPLETED | 1 | 1 | 1 / 1 | 687 | 69 | 408 |
| `ORD-20261028-844d7e60` | COMPLETED | 1 | 1 | 1 / 1 | 719 | 67 | 351 |
| `ORD-20261028-c60f2ec1` | COMPLETED | 1 | 1 | 1 / 1 | 672 | 78 | 365 |
| `ORD-20261028-25739bd6` | COMPLETED | 1 | 1 | 1 / 1 | 703 | 93 | 354 |
| `ORD-20261028-df5faa99` | COMPLETED | 1 | 1 | 1 / 1 | 656 | 62 | 377 |
| `ORD-20261028-76be9256` | COMPLETED | 1 | 1 | 1 / 1 | 671 | 66 | 354 |
| `ORD-20261028-f6f33f50` | COMPLETED | 1 | 1 | 1 / 1 | 688 | 74 | 329 |

- client POST→COMPLETED (ms): min 656 · median 688 · p95 1281 · max 1281
- PENDING→PROCESSING (ms): min 60 · median 72 · p95 229 · max 229
- PENDING→COMPLETED (ms): min 329 · median 366 · p95 1007 · max 1007

**Result: PASS**
