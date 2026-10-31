# Oversell race test, run `after-fix-2`

Run: 2026-10-31T11:38:02.177Z · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com` · Command: `python scripts/oversell_race.py --label after-fix-2` · Duration: 847 s

**Result: PASS**

## Pre-flight

- Lambda account concurrency limit **400**, unreserved **400** (no function has reserved concurrency).
- API Gateway stage `$default`: burst **100**, rate **50.0/s**, per-route overrides: 0.
- Buyers: 10 order buyers + 150 hold buyers (one ACTIVE hold per user), tokens fetched before the race.

## Round 1: 200 simultaneous attempts on RACE-1 (20 units)

Fired 2026-10-31T11:38:02.177Z; all 200 requests left within **63 ms**.

> Note (added after the run): the "Fired" stamps in this file were taken before the threads pre-connected (TCP +
> TLS), not at the barrier release. CloudWatch shows the real release: `order-saga-holds-api` ran 150 invocations at
> 11:38:30-31 (round 1) and 60 at 11:38:48 (round 2). Latencies and the send spread are measured from each thread's
> own send and are unaffected. The harness now stamps the release in the barrier's action.
> Server-side conflict retries (Logs Insights, `"Transaction committed after conflicts"`): round 1: 3 holds committed
> after 1 retry each; round 2: 1 hold after 1 retry. 0 ERROR log lines, 0 Lambda timeouts in the window.

| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |
|---|---|---|---|---|---|---|
| checkout holds | 150 | 20 | 130 | 0 | 0 | 0 |
| direct orders | 50 | 0 | 50 | 0 | 0 | 0 |
| **total** | 200 | 20 | 180 | 0 | 0 | 0 |

Latency in ms, p50 / p95 / max:

| Measure | p50 / p95 / max |
|---|---|
| answering request, holds (the real stock answer) | 1375 / 2004 / 3040 |
| first send -> real answer, holds (throttled retries included) | 1375 / 2004 / 3040 |
| POST /orders accepted (202) | 1096 / 1291 / 1345 |
| order accepted -> stock answer in the saga | 2019 / 2541 / 2600 |

Sampler (consistent reads every ~200 ms during the round):

| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |
|---|---|---|---|---|
| RACE-1 | 50 | 0 | 20 | (0, 20, 0, 0, 0) |

Checks:

- PASS: exactly 20 carts claimed: 20 (holds 20, orders 0)
- PASS: 0 ERROR answers: 0
- PASS: every throttled request was eventually answered (0 throttled at least once)
- PASS: RACE-1 at settle: stock 0, held 20, reserved 0 (claimed 20 = 20)
- PASS: RACE-1 sampler (50 samples): min stock 0, max claimed 20 (<= 20)
- PASS: I5 on every sample: stock + claimed = seeded
- PASS: no out-of-stock answer while stock was left (409 with available > 0): 0
- PASS: cancelled the 0 winning orders: HTTP []

<details><summary>Every attempt</summary>

| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 35 | hold | race-046 | RACE-1 | 409 | OUT_OF_STOCK | 1181 | 1181 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 178 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 1187 | 1187 | ORD-20261031-53c822be | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 17 | hold | race-028 | RACE-1 | 201 | CLAIMED | 1059 | 1059 | HOLD-20261031-0b29791226 |  |
| 131 | hold | race-142 | RACE-1 | 409 | OUT_OF_STOCK | 1581 | 1581 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 99 | hold | race-110 | RACE-1 | 409 | OUT_OF_STOCK | 1185 | 1185 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 44 | hold | race-055 | RACE-1 | 409 | OUT_OF_STOCK | 1850 | 1850 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 30 | hold | race-041 | RACE-1 | 409 | OUT_OF_STOCK | 1826 | 1826 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 51 | hold | race-062 | RACE-1 | 409 | OUT_OF_STOCK | 1477 | 1477 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 188 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 963 | 963 | ORD-20261031-f332991f | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 135 | hold | race-146 | RACE-1 | 201 | CLAIMED | 949 | 949 | HOLD-20261031-b83153d89e |  |
| 118 | hold | race-129 | RACE-1 | 409 | OUT_OF_STOCK | 1478 | 1478 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 22 | hold | race-033 | RACE-1 | 201 | CLAIMED | 913 | 913 | HOLD-20261031-6d6dee903a |  |
| 105 | hold | race-116 | RACE-1 | 409 | OUT_OF_STOCK | 2231 | 2231 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 77 | hold | race-088 | RACE-1 | 409 | OUT_OF_STOCK | 1160 | 1160 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 46 | hold | race-057 | RACE-1 | 409 | OUT_OF_STOCK | 1199 | 1199 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 19 | hold | race-030 | RACE-1 | 409 | OUT_OF_STOCK | 1260 | 1260 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 138 | hold | race-149 | RACE-1 | 409 | OUT_OF_STOCK | 1689 | 1689 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 191 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1261 | 1261 | ORD-20261031-d9b1bedf | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 122 | hold | race-133 | RACE-1 | 409 | OUT_OF_STOCK | 2068 | 2068 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 6 | hold | race-017 | RACE-1 | 409 | OUT_OF_STOCK | 1158 | 1158 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 179 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 1096 | 1096 | ORD-20261031-15e134e5 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 80 | hold | race-091 | RACE-1 | 409 | OUT_OF_STOCK | 1415 | 1415 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 116 | hold | race-127 | RACE-1 | 409 | OUT_OF_STOCK | 1335 | 1336 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 84 | hold | race-095 | RACE-1 | 409 | OUT_OF_STOCK | 1466 | 1466 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 39 | hold | race-050 | RACE-1 | 409 | OUT_OF_STOCK | 1376 | 1376 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 121 | hold | race-132 | RACE-1 | 409 | OUT_OF_STOCK | 1374 | 1374 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 4 | hold | race-015 | RACE-1 | 409 | OUT_OF_STOCK | 1188 | 1188 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 15 | hold | race-026 | RACE-1 | 409 | OUT_OF_STOCK | 1124 | 1124 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 171 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1048 | 1048 | ORD-20261031-410d6a95 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 162 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 1294 | 1294 | ORD-20261031-c5640696 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 2 | hold | race-013 | RACE-1 | 409 | OUT_OF_STOCK | 1728 | 1729 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 81 | hold | race-092 | RACE-1 | 409 | OUT_OF_STOCK | 1369 | 1369 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 190 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1220 | 1220 | ORD-20261031-cd8158f1 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 184 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 1200 | 1200 | ORD-20261031-b8b3bcf5 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 9 | hold | race-020 | RACE-1 | 409 | OUT_OF_STOCK | 1431 | 1432 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 100 | hold | race-111 | RACE-1 | 201 | CLAIMED | 1046 | 1046 | HOLD-20261031-31219b2998 |  |
| 120 | hold | race-131 | RACE-1 | 409 | OUT_OF_STOCK | 1336 | 1336 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 37 | hold | race-048 | RACE-1 | 409 | OUT_OF_STOCK | 1819 | 1819 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 98 | hold | race-109 | RACE-1 | 409 | OUT_OF_STOCK | 1375 | 1375 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 74 | hold | race-085 | RACE-1 | 409 | OUT_OF_STOCK | 1629 | 1629 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 192 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 976 | 976 | ORD-20261031-b7a8e743 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 55 | hold | race-066 | RACE-1 | 409 | OUT_OF_STOCK | 1450 | 1450 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 21 | hold | race-032 | RACE-1 | 409 | OUT_OF_STOCK | 1985 | 1985 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 182 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 1101 | 1101 | ORD-20261031-009ae6b8 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 71 | hold | race-082 | RACE-1 | 409 | OUT_OF_STOCK | 1315 | 1315 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 198 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 1031 | 1031 | ORD-20261031-e3cf540a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 102 | hold | race-113 | RACE-1 | 409 | OUT_OF_STOCK | 1367 | 1367 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 187 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 953 | 953 | ORD-20261031-8e9d97ab | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 150 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1285 | 1285 | ORD-20261031-14dd40f3 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 126 | hold | race-137 | RACE-1 | 409 | OUT_OF_STOCK | 1765 | 1765 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 8 | hold | race-019 | RACE-1 | 409 | OUT_OF_STOCK | 1374 | 1374 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 36 | hold | race-047 | RACE-1 | 201 | CLAIMED | 996 | 996 | HOLD-20261031-be1c2bb24f |  |
| 110 | hold | race-121 | RACE-1 | 409 | OUT_OF_STOCK | 1384 | 1384 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 197 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 1291 | 1291 | ORD-20261031-fb9c2d9b | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 108 | hold | race-119 | RACE-1 | 201 | CLAIMED | 1083 | 1083 | HOLD-20261031-48b1896e17 |  |
| 160 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1079 | 1079 | ORD-20261031-f954237e | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 107 | hold | race-118 | RACE-1 | 201 | CLAIMED | 1071 | 1071 | HOLD-20261031-a6dc96dce1 |  |
| 96 | hold | race-107 | RACE-1 | 201 | CLAIMED | 937 | 937 | HOLD-20261031-bb02c8876d |  |
| 58 | hold | race-069 | RACE-1 | 409 | OUT_OF_STOCK | 1231 | 1231 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 75 | hold | race-086 | RACE-1 | 409 | OUT_OF_STOCK | 1510 | 1510 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 153 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 913 | 913 | ORD-20261031-153a9a3e | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 45 | hold | race-056 | RACE-1 | 409 | OUT_OF_STOCK | 1415 | 1415 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 145 | hold | race-156 | RACE-1 | 409 | OUT_OF_STOCK | 1466 | 1466 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 40 | hold | race-051 | RACE-1 | 409 | OUT_OF_STOCK | 1593 | 1593 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 104 | hold | race-115 | RACE-1 | 409 | OUT_OF_STOCK | 1588 | 1588 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 95 | hold | race-106 | RACE-1 | 409 | OUT_OF_STOCK | 1626 | 1626 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 119 | hold | race-130 | RACE-1 | 409 | OUT_OF_STOCK | 1130 | 1130 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 60 | hold | race-071 | RACE-1 | 409 | OUT_OF_STOCK | 1442 | 1442 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 54 | hold | race-065 | RACE-1 | 409 | OUT_OF_STOCK | 1572 | 1572 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 27 | hold | race-038 | RACE-1 | 409 | OUT_OF_STOCK | 1259 | 1259 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 11 | hold | race-022 | RACE-1 | 201 | CLAIMED | 1045 | 1045 | HOLD-20261031-0edef59d85 |  |
| 117 | hold | race-128 | RACE-1 | 409 | OUT_OF_STOCK | 3040 | 3040 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 91 | hold | race-102 | RACE-1 | 201 | CLAIMED | 1073 | 1073 | HOLD-20261031-58bcef8f66 |  |
| 50 | hold | race-061 | RACE-1 | 409 | OUT_OF_STOCK | 1555 | 1555 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 33 | hold | race-044 | RACE-1 | 409 | OUT_OF_STOCK | 1650 | 1650 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 34 | hold | race-045 | RACE-1 | 409 | OUT_OF_STOCK | 2272 | 2272 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 68 | hold | race-079 | RACE-1 | 409 | OUT_OF_STOCK | 1273 | 1273 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 14 | hold | race-025 | RACE-1 | 409 | OUT_OF_STOCK | 1788 | 1788 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 170 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1049 | 1049 | ORD-20261031-8a81c313 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 28 | hold | race-039 | RACE-1 | 409 | OUT_OF_STOCK | 1468 | 1468 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 86 | hold | race-097 | RACE-1 | 409 | OUT_OF_STOCK | 1678 | 1678 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 1 | hold | race-012 | RACE-1 | 409 | OUT_OF_STOCK | 1300 | 1300 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 25 | hold | race-036 | RACE-1 | 409 | OUT_OF_STOCK | 1332 | 1332 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 18 | hold | race-029 | RACE-1 | 409 | OUT_OF_STOCK | 1207 | 1207 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 43 | hold | race-054 | RACE-1 | 409 | OUT_OF_STOCK | 1365 | 1365 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 12 | hold | race-023 | RACE-1 | 409 | OUT_OF_STOCK | 1449 | 1449 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 26 | hold | race-037 | RACE-1 | 409 | OUT_OF_STOCK | 1848 | 1848 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 144 | hold | race-155 | RACE-1 | 409 | OUT_OF_STOCK | 1852 | 1852 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 156 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 1150 | 1150 | ORD-20261031-62da63f7 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 130 | hold | race-141 | RACE-1 | 409 | OUT_OF_STOCK | 1312 | 1312 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 185 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 1229 | 1229 | ORD-20261031-ecebb20c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 31 | hold | race-042 | RACE-1 | 409 | OUT_OF_STOCK | 1647 | 1647 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 149 | hold | race-160 | RACE-1 | 409 | OUT_OF_STOCK | 1278 | 1278 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 148 | hold | race-159 | RACE-1 | 409 | OUT_OF_STOCK | 1324 | 1324 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 79 | hold | race-090 | RACE-1 | 409 | OUT_OF_STOCK | 1145 | 1145 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 175 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 1345 | 1345 | ORD-20261031-5d5bd418 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 157 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 1256 | 1256 | ORD-20261031-4e9bfb95 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 92 | hold | race-103 | RACE-1 | 409 | OUT_OF_STOCK | 1297 | 1297 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 0 | hold | race-011 | RACE-1 | 201 | CLAIMED | 1080 | 1080 | HOLD-20261031-f2f8b5c420 |  |
| 70 | hold | race-081 | RACE-1 | 409 | OUT_OF_STOCK | 1575 | 1575 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 125 | hold | race-136 | RACE-1 | 409 | OUT_OF_STOCK | 1254 | 1254 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 173 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 1043 | 1043 | ORD-20261031-13c25208 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 123 | hold | race-134 | RACE-1 | 409 | OUT_OF_STOCK | 1285 | 1285 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 169 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 1037 | 1037 | ORD-20261031-27081a45 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 115 | hold | race-126 | RACE-1 | 409 | OUT_OF_STOCK | 1658 | 1658 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 90 | hold | race-101 | RACE-1 | 409 | OUT_OF_STOCK | 1593 | 1593 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 49 | hold | race-060 | RACE-1 | 409 | OUT_OF_STOCK | 1820 | 1820 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 64 | hold | race-075 | RACE-1 | 409 | OUT_OF_STOCK | 1743 | 1743 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 159 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 1224 | 1224 | ORD-20261031-38cfbf75 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 127 | hold | race-138 | RACE-1 | 409 | OUT_OF_STOCK | 1261 | 1261 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 183 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 976 | 976 | ORD-20261031-318f6587 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 88 | hold | race-099 | RACE-1 | 409 | OUT_OF_STOCK | 1133 | 1133 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 136 | hold | race-147 | RACE-1 | 201 | CLAIMED | 993 | 993 | HOLD-20261031-ccfdb8c50d |  |
| 146 | hold | race-157 | RACE-1 | 409 | OUT_OF_STOCK | 1342 | 1342 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 69 | hold | race-080 | RACE-1 | 409 | OUT_OF_STOCK | 1582 | 1583 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 113 | hold | race-124 | RACE-1 | 409 | OUT_OF_STOCK | 1555 | 1556 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 85 | hold | race-096 | RACE-1 | 409 | OUT_OF_STOCK | 1506 | 1506 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 73 | hold | race-084 | RACE-1 | 409 | OUT_OF_STOCK | 1304 | 1304 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 165 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 1251 | 1251 | ORD-20261031-342099ac | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 147 | hold | race-158 | RACE-1 | 201 | CLAIMED | 925 | 925 | HOLD-20261031-67c27e9eec |  |
| 62 | hold | race-073 | RACE-1 | 201 | CLAIMED | 971 | 971 | HOLD-20261031-293db36248 |  |
| 168 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 924 | 924 | ORD-20261031-852f21d8 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 32 | hold | race-043 | RACE-1 | 409 | OUT_OF_STOCK | 2004 | 2004 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 52 | hold | race-063 | RACE-1 | 201 | CLAIMED | 945 | 945 | HOLD-20261031-0a0ccd5203 |  |
| 158 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 1096 | 1096 | ORD-20261031-0da92828 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 101 | hold | race-112 | RACE-1 | 409 | OUT_OF_STOCK | 1312 | 1312 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 89 | hold | race-100 | RACE-1 | 409 | OUT_OF_STOCK | 1256 | 1256 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 174 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 878 | 878 | ORD-20261031-026f58ce | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 161 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1190 | 1190 | ORD-20261031-33559196 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 82 | hold | race-093 | RACE-1 | 409 | OUT_OF_STOCK | 1477 | 1477 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 57 | hold | race-068 | RACE-1 | 409 | OUT_OF_STOCK | 2262 | 2262 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 66 | hold | race-077 | RACE-1 | 409 | OUT_OF_STOCK | 1438 | 1438 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 42 | hold | race-053 | RACE-1 | 409 | OUT_OF_STOCK | 1507 | 1507 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 41 | hold | race-052 | RACE-1 | 409 | OUT_OF_STOCK | 1253 | 1253 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 189 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 1242 | 1242 | ORD-20261031-395b4a7c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 111 | hold | race-122 | RACE-1 | 409 | OUT_OF_STOCK | 1283 | 1283 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 93 | hold | race-104 | RACE-1 | 201 | CLAIMED | 1003 | 1003 | HOLD-20261031-e993899ff5 |  |
| 65 | hold | race-076 | RACE-1 | 409 | OUT_OF_STOCK | 1516 | 1516 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 7 | hold | race-018 | RACE-1 | 201 | CLAIMED | 963 | 963 | HOLD-20261031-f6d69dda04 |  |
| 97 | hold | race-108 | RACE-1 | 201 | CLAIMED | 979 | 979 | HOLD-20261031-fe33daadf2 |  |
| 142 | hold | race-153 | RACE-1 | 409 | OUT_OF_STOCK | 1490 | 1490 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 87 | hold | race-098 | RACE-1 | 409 | OUT_OF_STOCK | 1651 | 1652 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 20 | hold | race-031 | RACE-1 | 201 | CLAIMED | 1060 | 1060 | HOLD-20261031-9a4dcf68ad |  |
| 23 | hold | race-034 | RACE-1 | 409 | OUT_OF_STOCK | 1553 | 1553 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 172 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 1113 | 1113 | ORD-20261031-18a5b884 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 103 | hold | race-114 | RACE-1 | 201 | CLAIMED | 1008 | 1008 | HOLD-20261031-97fc4e6e9e |  |
| 16 | hold | race-027 | RACE-1 | 409 | OUT_OF_STOCK | 1607 | 1607 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 181 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1054 | 1054 | ORD-20261031-91ccec3c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 10 | hold | race-021 | RACE-1 | 409 | OUT_OF_STOCK | 1241 | 1241 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 199 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 1127 | 1127 | ORD-20261031-22d1510a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 141 | hold | race-152 | RACE-1 | 409 | OUT_OF_STOCK | 1620 | 1620 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 151 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 985 | 985 | ORD-20261031-1aa8872e | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 152 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 955 | 955 | ORD-20261031-a701728a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 72 | hold | race-083 | RACE-1 | 409 | OUT_OF_STOCK | 1140 | 1140 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 124 | hold | race-135 | RACE-1 | 409 | OUT_OF_STOCK | 1821 | 1821 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 155 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 877 | 877 | ORD-20261031-94d29dfb | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 163 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 1142 | 1142 | ORD-20261031-1d7d2f6b | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 133 | hold | race-144 | RACE-1 | 409 | OUT_OF_STOCK | 1263 | 1263 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 106 | hold | race-117 | RACE-1 | 409 | OUT_OF_STOCK | 2268 | 2268 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 154 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 1177 | 1177 | ORD-20261031-34230627 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 129 | hold | race-140 | RACE-1 | 409 | OUT_OF_STOCK | 1477 | 1477 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 29 | hold | race-040 | RACE-1 | 409 | OUT_OF_STOCK | 1227 | 1227 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 38 | hold | race-049 | RACE-1 | 409 | OUT_OF_STOCK | 1305 | 1305 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 48 | hold | race-059 | RACE-1 | 409 | OUT_OF_STOCK | 1212 | 1212 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 164 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 795 | 795 | ORD-20261031-55ede0fc | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 177 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 1185 | 1185 | ORD-20261031-91d3a564 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 47 | hold | race-058 | RACE-1 | 409 | OUT_OF_STOCK | 2535 | 2535 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 114 | hold | race-125 | RACE-1 | 409 | OUT_OF_STOCK | 1488 | 1488 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 24 | hold | race-035 | RACE-1 | 409 | OUT_OF_STOCK | 1653 | 1653 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 112 | hold | race-123 | RACE-1 | 409 | OUT_OF_STOCK | 1153 | 1153 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 180 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1043 | 1043 | ORD-20261031-05baaabe | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 78 | hold | race-089 | RACE-1 | 409 | OUT_OF_STOCK | 1636 | 1636 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 63 | hold | race-074 | RACE-1 | 409 | OUT_OF_STOCK | 1773 | 1773 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 56 | hold | race-067 | RACE-1 | 409 | OUT_OF_STOCK | 1591 | 1591 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 194 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 1186 | 1186 | ORD-20261031-dc05675e | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 5 | hold | race-016 | RACE-1 | 409 | OUT_OF_STOCK | 1696 | 1696 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 67 | hold | race-078 | RACE-1 | 409 | OUT_OF_STOCK | 1737 | 1737 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 13 | hold | race-024 | RACE-1 | 409 | OUT_OF_STOCK | 1347 | 1347 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 196 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 1053 | 1053 | ORD-20261031-1454e84d | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 61 | hold | race-072 | RACE-1 | 409 | OUT_OF_STOCK | 1265 | 1265 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 166 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 1185 | 1185 | ORD-20261031-ef5ce316 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 143 | hold | race-154 | RACE-1 | 409 | OUT_OF_STOCK | 1117 | 1117 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 109 | hold | race-120 | RACE-1 | 409 | OUT_OF_STOCK | 1276 | 1276 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 76 | hold | race-087 | RACE-1 | 409 | OUT_OF_STOCK | 1118 | 1118 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 167 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 897 | 897 | ORD-20261031-69520433 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 137 | hold | race-148 | RACE-1 | 409 | OUT_OF_STOCK | 1561 | 1561 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 186 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 970 | 970 | ORD-20261031-e9412116 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 83 | hold | race-094 | RACE-1 | 409 | OUT_OF_STOCK | 1291 | 1291 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 3 | hold | race-014 | RACE-1 | 409 | OUT_OF_STOCK | 1600 | 1600 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 134 | hold | race-145 | RACE-1 | 409 | OUT_OF_STOCK | 1215 | 1215 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 128 | hold | race-139 | RACE-1 | 409 | OUT_OF_STOCK | 1909 | 1909 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 139 | hold | race-150 | RACE-1 | 409 | OUT_OF_STOCK | 1761 | 1761 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 94 | hold | race-105 | RACE-1 | 409 | OUT_OF_STOCK | 1501 | 1502 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 140 | hold | race-151 | RACE-1 | 409 | OUT_OF_STOCK | 1140 | 1140 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 193 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 1050 | 1050 | ORD-20261031-d1b3ab3a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 176 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 1180 | 1180 | ORD-20261031-c9f534b2 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 195 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 1202 | 1202 | ORD-20261031-c312a531 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 132 | hold | race-143 | RACE-1 | 409 | OUT_OF_STOCK | 1854 | 1854 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 53 | hold | race-064 | RACE-1 | 409 | OUT_OF_STOCK | 1491 | 1491 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 59 | hold | race-070 | RACE-1 | 409 | OUT_OF_STOCK | 1116 | 1116 | - | 409 Not enough stock to hold RACE-1 (available: 0) |

</details>

## Round 2: 100 simultaneous carts {RACE-X: 1, RACE-Y: 1} (10 + 10 units), item order X,Y / Y,X

Fired 2026-10-31T11:38:35.381Z; all 100 requests left within **37 ms**.

| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |
|---|---|---|---|---|---|---|
| checkout holds | 60 | 10 | 50 | 0 | 0 | 0 |
| direct orders | 40 | 0 | 40 | 0 | 0 | 0 |
| **total** | 100 | 10 | 90 | 0 | 0 | 0 |

Latency in ms, p50 / p95 / max:

| Measure | p50 / p95 / max |
|---|---|
| answering request, holds (the real stock answer) | 546 / 909 / 1571 |
| first send -> real answer, holds (throttled retries included) | 546 / 909 / 1571 |
| POST /orders accepted (202) | 353 / 410 / 416 |
| order accepted -> stock answer in the saga | 797 / 1121 / 1210 |

Sampler (consistent reads every ~200 ms during the round):

| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |
|---|---|---|---|---|
| RACE-X | 29 | 0 | 10 | (0, 10, 0, 0, 0) |
| RACE-Y | 29 | 0 | 10 | (0, 10, 0, 0, 0) |

Checks:

- PASS: exactly 10 carts claimed: 10 (holds 10, orders 0)
- PASS: 0 ERROR answers: 0
- PASS: every throttled request was eventually answered (0 throttled at least once)
- PASS: RACE-X at settle: stock 0, held 10, reserved 0 (claimed 10 = 10)
- PASS: RACE-X sampler (29 samples): min stock 0, max claimed 10 (<= 10)
- PASS: RACE-Y at settle: stock 0, held 10, reserved 0 (claimed 10 = 10)
- PASS: RACE-Y sampler (29 samples): min stock 0, max claimed 10 (<= 10)
- PASS: I5 on every sample: stock + claimed = seeded
- PASS: no out-of-stock answer while stock was left (409 with available > 0): 0
- PASS: all-or-nothing: no cart with only one item (0), units claimed per product {'RACE-X': 10, 'RACE-Y': 10}
- PASS: cancelled the 0 winning orders: HTTP []

<details><summary>Every attempt</summary>

| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 52 | hold | race-039 | RACE-X,RACE-Y | 201 | CLAIMED | 263 | 263 | HOLD-20261031-e961a63bf5 |  |
| 25 | hold | race-048 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 784 | 784 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 14 | hold | race-091 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 538 | 538 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 63 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 389 | 389 | ORD-20261031-495946b6 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 88 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 366 | 366 | ORD-20261031-f732deaa | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 21 | hold | race-013 | RACE-Y,RACE-X | 201 | CLAIMED | 397 | 397 | HOLD-20261031-95169e92b5 |  |
| 86 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 254 | 254 | ORD-20261031-c37ec0ee | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 2 | hold | race-110 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 635 | 635 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 92 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 372 | 372 | ORD-20261031-b80ea49f | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 54 | hold | race-012 | RACE-X,RACE-Y | 201 | CLAIMED | 376 | 376 | HOLD-20261031-0b531f0cfc |  |
| 18 | hold | race-132 | RACE-X,RACE-Y | 201 | CLAIMED | 329 | 329 | HOLD-20261031-ecea3de5be |  |
| 30 | hold | race-082 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 591 | 591 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 75 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 268 | 268 | ORD-20261031-32035439 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 93 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 234 | 234 | ORD-20261031-7303e42a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 15 | hold | race-127 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 1041 | 1041 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 82 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 408 | 408 | ORD-20261031-158b8496 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 58 | hold | race-023 | RACE-X,RACE-Y | 201 | CLAIMED | 282 | 283 | HOLD-20261031-36709fc586 |  |
| 16 | hold | race-095 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 548 | 548 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 4 | hold | race-041 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 687 | 687 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 62 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 321 | 321 | ORD-20261031-fd21e9a5 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 47 | hold | race-061 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 548 | 548 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 68 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 340 | 340 | ORD-20261031-43987707 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 77 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 239 | 239 | ORD-20261031-42e3942a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 29 | hold | race-032 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 459 | 459 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 55 | hold | race-036 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 490 | 490 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 83 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 226 | 226 | ORD-20261031-05c0bbd4 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 65 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 298 | 298 | ORD-20261031-7c38e3b5 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 23 | hold | race-020 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 437 | 437 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 0 | hold | race-046 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 549 | 549 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 89 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 229 | 229 | ORD-20261031-67502658 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 1 | hold | race-142 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 1571 | 1571 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 78 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 280 | 281 | ORD-20261031-9e8dba19 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 56 | hold | race-029 | RACE-X,RACE-Y | 201 | CLAIMED | 426 | 426 | HOLD-20261031-f3ef071b12 |  |
| 20 | hold | race-026 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 588 | 588 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 76 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 354 | 354 | ORD-20261031-e6fee29a | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 94 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 366 | 366 | ORD-20261031-6d514826 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 42 | hold | race-130 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 864 | 864 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 73 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 256 | 256 | ORD-20261031-01306bf3 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 67 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 353 | 354 | ORD-20261031-05940091 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 36 | hold | race-086 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 614 | 614 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 97 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 330 | 330 | ORD-20261031-7125a19b | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 49 | hold | race-045 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 448 | 448 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 26 | hold | race-109 | RACE-X,RACE-Y | 201 | CLAIMED | 334 | 334 | HOLD-20261031-5a9bc6391d |  |
| 44 | hold | race-065 | RACE-X,RACE-Y | 201 | CLAIMED | 423 | 423 | HOLD-20261031-4aaf334ea9 |  |
| 34 | hold | race-121 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 1315 | 1315 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 19 | hold | race-015 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 435 | 435 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 48 | hold | race-044 | RACE-X,RACE-Y | 201 | CLAIMED | 408 | 408 | HOLD-20261031-e7515622b5 |  |
| 57 | hold | race-054 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 518 | 518 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 27 | hold | race-085 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 486 | 486 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 79 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 336 | 336 | ORD-20261031-fae8da00 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 53 | hold | race-097 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 453 | 453 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 61 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 232 | 232 | ORD-20261031-6478750a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 6 | hold | race-129 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 496 | 496 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 45 | hold | race-038 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 538 | 538 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 71 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 400 | 400 | ORD-20261031-f4983a8f | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 46 | hold | race-128 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 509 | 509 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 84 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 265 | 265 | ORD-20261031-bc30401f | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 59 | hold | race-037 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 784 | 784 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 87 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 388 | 388 | ORD-20261031-bdf32cde | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 24 | hold | race-131 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 473 | 473 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 37 | hold | race-056 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 537 | 537 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 8 | hold | race-088 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 909 | 909 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 64 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 379 | 379 | ORD-20261031-596ffa86 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 12 | hold | race-133 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 790 | 790 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 81 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 357 | 357 | ORD-20261031-9a87688d | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 74 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 360 | 360 | ORD-20261031-1a9775ab | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 72 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 399 | 399 | ORD-20261031-8434773a | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 10 | hold | race-030 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 558 | 558 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 33 | hold | race-019 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 576 | 576 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 13 | hold | race-017 | RACE-Y,RACE-X | 201 | CLAIMED | 352 | 352 | HOLD-20261031-70098f0ab8 |  |
| 40 | hold | race-115 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 667 | 667 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 91 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 410 | 411 | ORD-20261031-4cd0068a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 69 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 390 | 390 | ORD-20261031-e3e3fe2f | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 90 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 394 | 394 | ORD-20261031-f32d6bdd | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 51 | hold | race-025 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 555 | 555 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 9 | hold | race-057 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 779 | 779 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 35 | hold | race-069 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 481 | 481 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 80 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 416 | 416 | ORD-20261031-84474412 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 28 | hold | race-066 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 845 | 845 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 31 | hold | race-113 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 579 | 579 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 50 | hold | race-079 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 545 | 545 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 5 | hold | race-062 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 839 | 839 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 17 | hold | race-050 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 597 | 597 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 41 | hold | race-106 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 588 | 588 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 3 | hold | race-055 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 432 | 432 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 85 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 314 | 314 | ORD-20261031-cb2fb2e5 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 39 | hold | race-051 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 590 | 590 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 32 | hold | race-137 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 659 | 659 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 96 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 305 | 305 | ORD-20261031-29280a5e | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 43 | hold | race-071 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 578 | 578 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 66 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 360 | 360 | ORD-20261031-a62a8d31 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 22 | hold | race-092 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 546 | 546 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 11 | hold | race-149 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 459 | 459 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 98 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 392 | 392 | ORD-20261031-2d6935ce | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 99 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 412 | 412 | ORD-20261031-45c9dcc1 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 38 | hold | race-156 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 449 | 449 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 7 | hold | race-116 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 611 | 611 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 60 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 329 | 329 | ORD-20261031-b4950d91 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 70 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 368 | 369 | ORD-20261031-665f5f52 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 95 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 333 | 333 | ORD-20261031-9039b6bd | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |

</details>

## Money invariants (I1-I4, I6-I9)

Checked 90 orders: **all pass**


## Recovery

- Counters after recovery (stock, held, reserved, sold, writtenOff): {'RACE-1': (20, 0, 0, 0, 0), 'RACE-X': (10, 0, 0, 0, 0), 'RACE-Y': (10, 0, 0, 0, 0)}
- Full recovery **638 s after the last winning hold was created** (holds last 600 s); waited 608 s.
- Winning holds: {'EXPIRED': 30}, expired by {'schedule': 30}; schedule lag after expiresAt (min / median / max s): (1.048, 22.085, 50.078)

## I5 stock conservation after recovery

- PASS: RACE-1 back to its seed: stock 20/20, held 0, reserved 0
- PASS: RACE-X back to its seed: stock 10/10, held 0, reserved 0
- PASS: RACE-Y back to its seed: stock 10/10, held 0, reserved 0
- PASS: no ACTIVE holds left on race products: none
- PASS: I5 holds for all 16 products
