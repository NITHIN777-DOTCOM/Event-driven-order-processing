# Oversell race test, run `after-fix-1`

Run: 2026-10-31T08:17:41.210Z · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com` · Command: `python scripts/oversell_race.py --label after-fix` · Duration: 742 s

**Result: FAIL**

## Pre-flight

- Lambda account concurrency limit **400**, unreserved **400** (no function has reserved concurrency).
- API Gateway stage `$default`: burst **100**, rate **50.0/s**, per-route overrides: 0.
- Buyers: 10 order buyers + 150 hold buyers (one ACTIVE hold per user), tokens fetched before the race.

## Round 1: 200 simultaneous attempts on RACE-1 (20 units)

Fired 2026-10-31T08:17:41.210Z; all 200 requests left within **29 ms**.

| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |
|---|---|---|---|---|---|---|
| checkout holds | 150 | 20 | 129 | 1 | 0 | 0 |
| direct orders | 50 | 0 | 50 | 0 | 0 | 0 |
| **total** | 200 | 20 | 179 | 1 | 0 | 0 |

Latency in ms, p50 / p95 / max:

| Measure | p50 / p95 / max |
|---|---|
| answering request, holds (the real stock answer) | 1339 / 1865 / 2349 |
| first send -> real answer, holds (throttled retries included) | 1339 / 1865 / 2349 |
| POST /orders accepted (202) | 915 / 1120 / 1225 |
| order accepted -> stock answer in the saga | 1499 / 1906 / 2359 |

Sampler (consistent reads every ~200 ms during the round):

| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |
|---|---|---|---|---|
| RACE-1 | 36 | 0 | 20 | (0, 20, 0, 0, 0) |

Checks:

- PASS: exactly 20 carts claimed: 20 (holds 20, orders 0)
- **FAIL**: 0 ERROR answers: 1
      hold race-116: 503 {"error": "These products are in very high demand right now; please retry"}
- PASS: every throttled request was eventually answered (0 throttled at least once)
- PASS: RACE-1 at settle: stock 0, held 20, reserved 0 (claimed 20 = 20)
- PASS: RACE-1 sampler (36 samples): min stock 0, max claimed 20 (<= 20)
- PASS: I5 on every sample: stock + claimed = seeded
- PASS: no out-of-stock answer while stock was left (409 with available > 0): 0
- PASS: cancelled the 0 winning orders: HTTP []

<details><summary>Every attempt</summary>

| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 98 | hold | race-109 | RACE-1 | 409 | OUT_OF_STOCK | 1578 | 1578 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 56 | hold | race-067 | RACE-1 | 409 | OUT_OF_STOCK | 1135 | 1135 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 198 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 1120 | 1120 | ORD-20261031-52e1fd92 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 182 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 797 | 797 | ORD-20261031-7015ac34 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 170 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1055 | 1055 | ORD-20261031-139a9aae | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 191 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 811 | 811 | ORD-20261031-17a9c832 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 4 | hold | race-015 | RACE-1 | 409 | OUT_OF_STOCK | 1181 | 1181 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 13 | hold | race-024 | RACE-1 | 201 | CLAIMED | 1001 | 1001 | HOLD-20261031-5aadb5fc09 |  |
| 121 | hold | race-132 | RACE-1 | 409 | OUT_OF_STOCK | 1152 | 1152 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 111 | hold | race-122 | RACE-1 | 409 | OUT_OF_STOCK | 1326 | 1326 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 10 | hold | race-021 | RACE-1 | 201 | CLAIMED | 1037 | 1037 | HOLD-20261031-43cd655ddb |  |
| 86 | hold | race-097 | RACE-1 | 409 | OUT_OF_STOCK | 1264 | 1264 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 120 | hold | race-131 | RACE-1 | 409 | OUT_OF_STOCK | 1403 | 1403 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 78 | hold | race-089 | RACE-1 | 409 | OUT_OF_STOCK | 1346 | 1346 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 168 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 909 | 909 | ORD-20261031-df0e837b | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 76 | hold | race-087 | RACE-1 | 409 | OUT_OF_STOCK | 1706 | 1706 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 130 | hold | race-141 | RACE-1 | 409 | OUT_OF_STOCK | 1324 | 1324 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 3 | hold | race-014 | RACE-1 | 409 | OUT_OF_STOCK | 1209 | 1209 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 64 | hold | race-075 | RACE-1 | 201 | CLAIMED | 1039 | 1039 | HOLD-20261031-15c30f000e |  |
| 180 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 925 | 925 | ORD-20261031-29e6d8ab | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 57 | hold | race-068 | RACE-1 | 409 | OUT_OF_STOCK | 1391 | 1391 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 146 | hold | race-157 | RACE-1 | 409 | OUT_OF_STOCK | 1375 | 1375 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 195 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 930 | 930 | ORD-20261031-1dda1b0f | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 197 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 183 | 183 | ORD-20261031-77535d4c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 128 | hold | race-139 | RACE-1 | 409 | OUT_OF_STOCK | 1332 | 1332 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 125 | hold | race-136 | RACE-1 | 409 | OUT_OF_STOCK | 1565 | 1565 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 53 | hold | race-064 | RACE-1 | 409 | OUT_OF_STOCK | 1469 | 1469 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 28 | hold | race-039 | RACE-1 | 409 | OUT_OF_STOCK | 1678 | 1678 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 5 | hold | race-016 | RACE-1 | 409 | OUT_OF_STOCK | 1549 | 1549 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 83 | hold | race-094 | RACE-1 | 409 | OUT_OF_STOCK | 1205 | 1205 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 21 | hold | race-032 | RACE-1 | 409 | OUT_OF_STOCK | 1763 | 1763 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 157 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 922 | 922 | ORD-20261031-42fdc4d2 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 92 | hold | race-103 | RACE-1 | 409 | OUT_OF_STOCK | 1557 | 1557 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 63 | hold | race-074 | RACE-1 | 409 | OUT_OF_STOCK | 1178 | 1178 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 193 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 1094 | 1094 | ORD-20261031-405f4769 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 26 | hold | race-037 | RACE-1 | 409 | OUT_OF_STOCK | 1339 | 1339 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 185 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 896 | 896 | ORD-20261031-e1610401 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 175 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 928 | 928 | ORD-20261031-4118dbaa | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 38 | hold | race-049 | RACE-1 | 409 | OUT_OF_STOCK | 1683 | 1683 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 139 | hold | race-150 | RACE-1 | 409 | OUT_OF_STOCK | 1865 | 1865 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 46 | hold | race-057 | RACE-1 | 201 | CLAIMED | 1047 | 1047 | HOLD-20261031-2570ab34ca |  |
| 189 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 862 | 862 | ORD-20261031-054b36b3 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 194 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 915 | 915 | ORD-20261031-34c3c95e | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 165 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 1106 | 1106 | ORD-20261031-005bc8d9 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 25 | hold | race-036 | RACE-1 | 409 | OUT_OF_STOCK | 1766 | 1766 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 174 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 925 | 925 | ORD-20261031-bae0775b | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 27 | hold | race-038 | RACE-1 | 409 | OUT_OF_STOCK | 1528 | 1528 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 2 | hold | race-013 | RACE-1 | 409 | OUT_OF_STOCK | 1441 | 1441 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 18 | hold | race-029 | RACE-1 | 409 | OUT_OF_STOCK | 1133 | 1133 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 124 | hold | race-135 | RACE-1 | 409 | OUT_OF_STOCK | 1278 | 1278 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 9 | hold | race-020 | RACE-1 | 201 | CLAIMED | 971 | 971 | HOLD-20261031-b2c4cd5328 |  |
| 135 | hold | race-146 | RACE-1 | 409 | OUT_OF_STOCK | 1251 | 1251 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 54 | hold | race-065 | RACE-1 | 409 | OUT_OF_STOCK | 1444 | 1444 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 30 | hold | race-041 | RACE-1 | 409 | OUT_OF_STOCK | 1120 | 1120 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 75 | hold | race-086 | RACE-1 | 409 | OUT_OF_STOCK | 1359 | 1359 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 171 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 847 | 847 | ORD-20261031-36fbb559 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 49 | hold | race-060 | RACE-1 | 409 | OUT_OF_STOCK | 1614 | 1614 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 188 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 884 | 884 | ORD-20261031-e17ec27d | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 172 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 1225 | 1225 | ORD-20261031-507709de | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 6 | hold | race-017 | RACE-1 | 201 | CLAIMED | 997 | 997 | HOLD-20261031-d48776e4b6 |  |
| 39 | hold | race-050 | RACE-1 | 409 | OUT_OF_STOCK | 1411 | 1411 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 87 | hold | race-098 | RACE-1 | 409 | OUT_OF_STOCK | 1215 | 1215 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 82 | hold | race-093 | RACE-1 | 409 | OUT_OF_STOCK | 1397 | 1397 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 148 | hold | race-159 | RACE-1 | 409 | OUT_OF_STOCK | 1265 | 1265 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 43 | hold | race-054 | RACE-1 | 409 | OUT_OF_STOCK | 1299 | 1299 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 7 | hold | race-018 | RACE-1 | 409 | OUT_OF_STOCK | 1442 | 1442 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 184 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 896 | 896 | ORD-20261031-8a6e1add | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 142 | hold | race-153 | RACE-1 | 409 | OUT_OF_STOCK | 1614 | 1614 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 122 | hold | race-133 | RACE-1 | 409 | OUT_OF_STOCK | 1390 | 1390 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 181 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 905 | 905 | ORD-20261031-662ca2c5 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 156 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 1075 | 1075 | ORD-20261031-80a20a80 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 109 | hold | race-120 | RACE-1 | 409 | OUT_OF_STOCK | 1387 | 1387 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 103 | hold | race-114 | RACE-1 | 201 | CLAIMED | 999 | 999 | HOLD-20261031-bf73c02d2c |  |
| 36 | hold | race-047 | RACE-1 | 201 | CLAIMED | 939 | 939 | HOLD-20261031-15174c7bd5 |  |
| 31 | hold | race-042 | RACE-1 | 409 | OUT_OF_STOCK | 1482 | 1482 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 114 | hold | race-125 | RACE-1 | 409 | OUT_OF_STOCK | 1230 | 1230 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 134 | hold | race-145 | RACE-1 | 409 | OUT_OF_STOCK | 2088 | 2088 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 117 | hold | race-128 | RACE-1 | 409 | OUT_OF_STOCK | 1776 | 1776 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 74 | hold | race-085 | RACE-1 | 409 | OUT_OF_STOCK | 1424 | 1424 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 66 | hold | race-077 | RACE-1 | 409 | OUT_OF_STOCK | 1305 | 1305 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 137 | hold | race-148 | RACE-1 | 409 | OUT_OF_STOCK | 1309 | 1309 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 14 | hold | race-025 | RACE-1 | 409 | OUT_OF_STOCK | 1402 | 1402 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 50 | hold | race-061 | RACE-1 | 409 | OUT_OF_STOCK | 1339 | 1339 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 138 | hold | race-149 | RACE-1 | 409 | OUT_OF_STOCK | 1234 | 1234 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 160 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 914 | 914 | ORD-20261031-987bdaf5 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 169 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 1021 | 1021 | ORD-20261031-3b24a6bb | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 123 | hold | race-134 | RACE-1 | 409 | OUT_OF_STOCK | 1227 | 1227 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 91 | hold | race-102 | RACE-1 | 409 | OUT_OF_STOCK | 1886 | 1886 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 62 | hold | race-073 | RACE-1 | 409 | OUT_OF_STOCK | 1098 | 1098 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 89 | hold | race-100 | RACE-1 | 409 | OUT_OF_STOCK | 1294 | 1294 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 12 | hold | race-023 | RACE-1 | 409 | OUT_OF_STOCK | 1632 | 1632 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 33 | hold | race-044 | RACE-1 | 409 | OUT_OF_STOCK | 1971 | 1971 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 144 | hold | race-155 | RACE-1 | 409 | OUT_OF_STOCK | 1924 | 1924 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 183 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 847 | 847 | ORD-20261031-0a5e54b8 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 151 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1106 | 1106 | ORD-20261031-62cbb021 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 77 | hold | race-088 | RACE-1 | 409 | OUT_OF_STOCK | 1424 | 1424 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 71 | hold | race-082 | RACE-1 | 409 | OUT_OF_STOCK | 2349 | 2349 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 101 | hold | race-112 | RACE-1 | 409 | OUT_OF_STOCK | 1203 | 1203 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 119 | hold | race-130 | RACE-1 | 409 | OUT_OF_STOCK | 1389 | 1389 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 90 | hold | race-101 | RACE-1 | 409 | OUT_OF_STOCK | 1407 | 1407 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 23 | hold | race-034 | RACE-1 | 409 | OUT_OF_STOCK | 1271 | 1271 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 179 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 787 | 787 | ORD-20261031-26458317 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 152 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 775 | 775 | ORD-20261031-37eac978 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 32 | hold | race-043 | RACE-1 | 409 | OUT_OF_STOCK | 1510 | 1510 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 161 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1063 | 1063 | ORD-20261031-8e81e2dc | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 154 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 753 | 753 | ORD-20261031-22f7f794 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 186 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 759 | 759 | ORD-20261031-0f964234 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 37 | hold | race-048 | RACE-1 | 201 | CLAIMED | 912 | 912 | HOLD-20261031-13aa370860 |  |
| 58 | hold | race-069 | RACE-1 | 409 | OUT_OF_STOCK | 1171 | 1171 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 127 | hold | race-138 | RACE-1 | 409 | OUT_OF_STOCK | 1454 | 1454 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 72 | hold | race-083 | RACE-1 | 409 | OUT_OF_STOCK | 1386 | 1386 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 68 | hold | race-079 | RACE-1 | 201 | CLAIMED | 986 | 986 | HOLD-20261031-408c99815d |  |
| 159 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 915 | 915 | ORD-20261031-f4cce07b | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 95 | hold | race-106 | RACE-1 | 409 | OUT_OF_STOCK | 1123 | 1123 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 65 | hold | race-076 | RACE-1 | 409 | OUT_OF_STOCK | 1756 | 1756 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 129 | hold | race-140 | RACE-1 | 409 | OUT_OF_STOCK | 1279 | 1279 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 147 | hold | race-158 | RACE-1 | 201 | CLAIMED | 1032 | 1032 | HOLD-20261031-b55118b2ae |  |
| 126 | hold | race-137 | RACE-1 | 409 | OUT_OF_STOCK | 1710 | 1710 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 0 | hold | race-011 | RACE-1 | 409 | OUT_OF_STOCK | 1824 | 1824 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 40 | hold | race-051 | RACE-1 | 409 | OUT_OF_STOCK | 1192 | 1192 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 112 | hold | race-123 | RACE-1 | 409 | OUT_OF_STOCK | 1166 | 1166 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 190 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 1099 | 1099 | ORD-20261031-67e6ab70 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 199 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 952 | 952 | ORD-20261031-209b5994 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 166 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 954 | 954 | ORD-20261031-fca6b06a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 176 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 904 | 904 | ORD-20261031-d0d5d070 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 61 | hold | race-072 | RACE-1 | 409 | OUT_OF_STOCK | 1520 | 1520 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 145 | hold | race-156 | RACE-1 | 409 | OUT_OF_STOCK | 1458 | 1458 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 15 | hold | race-026 | RACE-1 | 409 | OUT_OF_STOCK | 1761 | 1761 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 96 | hold | race-107 | RACE-1 | 409 | OUT_OF_STOCK | 1332 | 1332 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 177 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 1085 | 1085 | ORD-20261031-7dcdbf07 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 60 | hold | race-071 | RACE-1 | 409 | OUT_OF_STOCK | 1131 | 1131 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 88 | hold | race-099 | RACE-1 | 201 | CLAIMED | 919 | 919 | HOLD-20261031-42218dacc3 |  |
| 1 | hold | race-012 | RACE-1 | 409 | OUT_OF_STOCK | 1364 | 1364 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 108 | hold | race-119 | RACE-1 | 409 | OUT_OF_STOCK | 1242 | 1242 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 136 | hold | race-147 | RACE-1 | 409 | OUT_OF_STOCK | 1111 | 1111 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 70 | hold | race-081 | RACE-1 | 409 | OUT_OF_STOCK | 1486 | 1486 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 48 | hold | race-059 | RACE-1 | 409 | OUT_OF_STOCK | 1511 | 1511 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 67 | hold | race-078 | RACE-1 | 201 | CLAIMED | 924 | 924 | HOLD-20261031-ea9a9237fa |  |
| 153 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 1135 | 1135 | ORD-20261031-11c1bc02 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 133 | hold | race-144 | RACE-1 | 409 | OUT_OF_STOCK | 1503 | 1503 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 132 | hold | race-143 | RACE-1 | 409 | OUT_OF_STOCK | 1170 | 1170 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 162 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 1005 | 1005 | ORD-20261031-af024869 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 167 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 873 | 873 | ORD-20261031-bde440a8 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 105 | hold | race-116 | RACE-1 | 503 | ERROR | 1707 | 1707 | - | 503 {"error": "These products are in very high demand right now; please retry"} |
| 93 | hold | race-104 | RACE-1 | 409 | OUT_OF_STOCK | 1211 | 1211 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 51 | hold | race-062 | RACE-1 | 409 | OUT_OF_STOCK | 1784 | 1784 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 140 | hold | race-151 | RACE-1 | 409 | OUT_OF_STOCK | 1446 | 1446 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 141 | hold | race-152 | RACE-1 | 409 | OUT_OF_STOCK | 1276 | 1276 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 107 | hold | race-118 | RACE-1 | 409 | OUT_OF_STOCK | 1481 | 1481 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 45 | hold | race-056 | RACE-1 | 201 | CLAIMED | 1008 | 1008 | HOLD-20261031-7f6744e207 |  |
| 17 | hold | race-028 | RACE-1 | 409 | OUT_OF_STOCK | 1692 | 1692 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 52 | hold | race-063 | RACE-1 | 409 | OUT_OF_STOCK | 1168 | 1168 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 131 | hold | race-142 | RACE-1 | 409 | OUT_OF_STOCK | 1187 | 1187 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 163 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 849 | 849 | ORD-20261031-e0234a3c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 19 | hold | race-030 | RACE-1 | 201 | CLAIMED | 1039 | 1039 | HOLD-20261031-4c57327947 |  |
| 102 | hold | race-113 | RACE-1 | 409 | OUT_OF_STOCK | 1190 | 1190 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 110 | hold | race-121 | RACE-1 | 201 | CLAIMED | 1014 | 1014 | HOLD-20261031-9f660125bf |  |
| 158 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 809 | 809 | ORD-20261031-06213eda | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 34 | hold | race-045 | RACE-1 | 409 | OUT_OF_STOCK | 1393 | 1393 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 24 | hold | race-035 | RACE-1 | 409 | OUT_OF_STOCK | 1494 | 1494 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 192 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 932 | 932 | ORD-20261031-c3b94954 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 187 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 786 | 786 | ORD-20261031-c36ceb1c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 55 | hold | race-066 | RACE-1 | 409 | OUT_OF_STOCK | 1958 | 1958 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 42 | hold | race-053 | RACE-1 | 409 | OUT_OF_STOCK | 1533 | 1533 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 118 | hold | race-129 | RACE-1 | 409 | OUT_OF_STOCK | 1527 | 1527 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 8 | hold | race-019 | RACE-1 | 409 | OUT_OF_STOCK | 1449 | 1449 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 178 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 1027 | 1027 | ORD-20261031-9cdf227c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 113 | hold | race-124 | RACE-1 | 409 | OUT_OF_STOCK | 1292 | 1292 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 106 | hold | race-117 | RACE-1 | 201 | CLAIMED | 1032 | 1032 | HOLD-20261031-dce3a759f9 |  |
| 149 | hold | race-160 | RACE-1 | 409 | OUT_OF_STOCK | 1114 | 1114 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 29 | hold | race-040 | RACE-1 | 409 | OUT_OF_STOCK | 1569 | 1569 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 22 | hold | race-033 | RACE-1 | 409 | OUT_OF_STOCK | 1814 | 1814 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 116 | hold | race-127 | RACE-1 | 409 | OUT_OF_STOCK | 1576 | 1576 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 81 | hold | race-092 | RACE-1 | 409 | OUT_OF_STOCK | 1264 | 1264 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 44 | hold | race-055 | RACE-1 | 409 | OUT_OF_STOCK | 1218 | 1218 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 97 | hold | race-108 | RACE-1 | 409 | OUT_OF_STOCK | 1229 | 1229 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 79 | hold | race-090 | RACE-1 | 409 | OUT_OF_STOCK | 1424 | 1424 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 115 | hold | race-126 | RACE-1 | 409 | OUT_OF_STOCK | 1281 | 1281 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 100 | hold | race-111 | RACE-1 | 409 | OUT_OF_STOCK | 1571 | 1571 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 20 | hold | race-031 | RACE-1 | 409 | OUT_OF_STOCK | 2189 | 2189 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 143 | hold | race-154 | RACE-1 | 409 | OUT_OF_STOCK | 1291 | 1291 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 155 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 1057 | 1057 | ORD-20261031-062bd630 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 73 | hold | race-084 | RACE-1 | 409 | OUT_OF_STOCK | 1653 | 1653 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 69 | hold | race-080 | RACE-1 | 409 | OUT_OF_STOCK | 1272 | 1272 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 85 | hold | race-096 | RACE-1 | 409 | OUT_OF_STOCK | 1748 | 1748 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 150 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 935 | 935 | ORD-20261031-4a723c40 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 196 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 249 | 249 | ORD-20261031-eb86269c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 35 | hold | race-046 | RACE-1 | 409 | OUT_OF_STOCK | 1251 | 1251 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 80 | hold | race-091 | RACE-1 | 409 | OUT_OF_STOCK | 1848 | 1848 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 41 | hold | race-052 | RACE-1 | 409 | OUT_OF_STOCK | 1117 | 1117 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 164 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 1055 | 1055 | ORD-20261031-5d1c7254 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 84 | hold | race-095 | RACE-1 | 409 | OUT_OF_STOCK | 1296 | 1296 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 94 | hold | race-105 | RACE-1 | 409 | OUT_OF_STOCK | 1479 | 1479 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 47 | hold | race-058 | RACE-1 | 201 | CLAIMED | 969 | 969 | HOLD-20261031-31dcc69291 |  |
| 59 | hold | race-070 | RACE-1 | 409 | OUT_OF_STOCK | 1249 | 1249 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 11 | hold | race-022 | RACE-1 | 201 | CLAIMED | 961 | 961 | HOLD-20261031-66dc8a80ab |  |
| 104 | hold | race-115 | RACE-1 | 409 | OUT_OF_STOCK | 1712 | 1712 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 173 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 900 | 900 | ORD-20261031-d101b2a1 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 16 | hold | race-027 | RACE-1 | 201 | CLAIMED | 901 | 901 | HOLD-20261031-1c93874c32 |  |
| 99 | hold | race-110 | RACE-1 | 409 | OUT_OF_STOCK | 1200 | 1201 | - | 409 Not enough stock to hold RACE-1 (available: 0) |

</details>

## Round 2: 100 simultaneous carts {RACE-X: 1, RACE-Y: 1} (10 + 10 units), item order X,Y / Y,X

Fired 2026-10-31T08:17:53.389Z; all 100 requests left within **17 ms**.

| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |
|---|---|---|---|---|---|---|
| checkout holds | 60 | 10 | 49 | 1 | 0 | 0 |
| direct orders | 40 | 0 | 40 | 0 | 0 | 0 |
| **total** | 100 | 10 | 89 | 1 | 0 | 0 |

Latency in ms, p50 / p95 / max:

| Measure | p50 / p95 / max |
|---|---|
| answering request, holds (the real stock answer) | 537 / 1012 / 1133 |
| first send -> real answer, holds (throttled retries included) | 537 / 1012 / 1133 |
| POST /orders accepted (202) | 136 / 156 / 159 |
| order accepted -> stock answer in the saga | 796 / 1275 / 1402 |

Sampler (consistent reads every ~200 ms during the round):

| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |
|---|---|---|---|---|
| RACE-Y | 24 | 0 | 10 | (0, 10, 0, 0, 0) |
| RACE-X | 24 | 0 | 10 | (0, 10, 0, 0, 0) |

Checks:

- PASS: exactly 10 carts claimed: 10 (holds 10, orders 0)
- **FAIL**: 0 ERROR answers: 1
      hold race-064: 503 {"error": "These products are in very high demand right now; please retry"}
- PASS: every throttled request was eventually answered (0 throttled at least once)
- PASS: RACE-Y at settle: stock 0, held 10, reserved 0 (claimed 10 = 10)
- PASS: RACE-Y sampler (24 samples): min stock 0, max claimed 10 (<= 10)
- PASS: RACE-X at settle: stock 0, held 10, reserved 0 (claimed 10 = 10)
- PASS: RACE-X sampler (24 samples): min stock 0, max claimed 10 (<= 10)
- PASS: I5 on every sample: stock + claimed = seeded
- PASS: no out-of-stock answer while stock was left (409 with available > 0): 0
- PASS: all-or-nothing: no cart with only one item (0), units claimed per product {'RACE-Y': 10, 'RACE-X': 10}
- PASS: cancelled the 0 winning orders: HTTP []

<details><summary>Every attempt</summary>

| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 65 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 108 | 108 | ORD-20261031-f9acaa96 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 77 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 137 | 137 | ORD-20261031-bc58c559 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 5 | hold | race-097 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 538 | 538 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 4 | hold | race-122 | RACE-X,RACE-Y | 201 | CLAIMED | 221 | 221 | HOLD-20261031-84fa9aceeb |  |
| 34 | hold | race-060 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 1069 | 1069 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 25 | hold | race-036 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 570 | 570 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 70 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 128 | 128 | ORD-20261031-50967384 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 66 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 138 | 138 | ORD-20261031-79458343 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 32 | hold | race-041 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 639 | 639 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 92 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 150 | 150 | ORD-20261031-756a60fa | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 26 | hold | race-038 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 537 | 537 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 29 | hold | race-135 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 535 | 535 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 19 | hold | race-032 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 850 | 850 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 6 | hold | race-131 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 442 | 442 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 73 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 119 | 119 | ORD-20261031-72445ca9 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 58 | hold | race-023 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 562 | 562 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 56 | hold | race-073 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 419 | 419 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 53 | hold | race-149 | RACE-Y,RACE-X | 201 | CLAIMED | 195 | 195 | HOLD-20261031-8231b5a380 |  |
| 16 | hold | race-039 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 472 | 472 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 28 | hold | race-029 | RACE-X,RACE-Y | 201 | CLAIMED | 217 | 217 | HOLD-20261031-80fecee41b |  |
| 38 | hold | race-159 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 1133 | 1133 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 27 | hold | race-013 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 459 | 459 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 49 | hold | race-077 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 1019 | 1019 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 96 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 142 | 142 | ORD-20261031-d64f68bb | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 93 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 119 | 119 | ORD-20261031-8900d59d | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 91 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 127 | 127 | ORD-20261031-7d30451d | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 40 | hold | race-018 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 719 | 719 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 98 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 125 | 125 | ORD-20261031-ddbd3184 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 44 | hold | race-042 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 641 | 641 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 87 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 146 | 146 | ORD-20261031-296b8b5b | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 97 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 139 | 139 | ORD-20261031-574b654d | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 41 | hold | race-153 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 578 | 578 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 30 | hold | race-146 | RACE-X,RACE-Y | 201 | CLAIMED | 250 | 250 | HOLD-20261031-eced35b1a3 |  |
| 10 | hold | race-014 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 881 | 881 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 17 | hold | race-016 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 539 | 539 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 55 | hold | race-102 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 428 | 428 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 63 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 117 | 117 | ORD-20261031-6c5d62d9 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 14 | hold | race-136 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 773 | 773 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 68 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 133 | 133 | ORD-20261031-76e16697 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 67 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 143 | 143 | ORD-20261031-1939009a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 15 | hold | race-064 | RACE-Y,RACE-X | 503 | ERROR | 1012 | 1012 | - | 503 {"error": "These products are in very high demand right now; please retry"} |
| 20 | hold | race-103 | RACE-X,RACE-Y | 201 | CLAIMED | 269 | 269 | HOLD-20261031-286615626f |  |
| 64 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 131 | 131 | ORD-20261031-f6622a01 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 36 | hold | race-098 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 385 | 385 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 51 | hold | race-025 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 992 | 992 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 71 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 125 | 125 | ORD-20261031-285e4dc9 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 18 | hold | race-094 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 661 | 661 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 88 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 102 | 102 | ORD-20261031-a7e559bf | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 82 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 143 | 143 | ORD-20261031-48641da5 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 76 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 136 | 136 | ORD-20261031-7efa2ea7 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 48 | hold | race-085 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 504 | 505 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 37 | hold | race-093 | RACE-Y,RACE-X | 201 | CLAIMED | 234 | 234 | HOLD-20261031-e84e4748a4 |  |
| 61 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 142 | 142 | ORD-20261031-5078f30f | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 89 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 156 | 156 | ORD-20261031-4804df29 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 50 | hold | race-148 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 710 | 711 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 79 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 137 | 137 | ORD-20261031-a39d7dae | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 74 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 101 | 101 | ORD-20261031-4060368d | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 78 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 152 | 152 | ORD-20261031-299e404b | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 99 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 132 | 132 | ORD-20261031-f14ebffb | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 24 | hold | race-150 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 372 | 372 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 54 | hold | race-134 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 398 | 398 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 83 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 140 | 140 | ORD-20261031-8f98e9f1 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 75 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 151 | 151 | ORD-20261031-6b83e1e9 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 94 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 120 | 120 | ORD-20261031-fcf5b346 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 39 | hold | race-054 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 502 | 502 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 12 | hold | race-157 | RACE-X,RACE-Y | 201 | CLAIMED | 223 | 223 | HOLD-20261031-ac1f54457c |  |
| 23 | hold | race-049 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 494 | 494 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 35 | hold | race-050 | RACE-Y,RACE-X | 201 | CLAIMED | 213 | 213 | HOLD-20261031-3ef0d1b4c8 |  |
| 57 | hold | race-100 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 608 | 608 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 13 | hold | race-139 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 609 | 610 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 69 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 128 | 128 | ORD-20261031-85a76fa9 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 11 | hold | race-068 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 375 | 375 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 7 | hold | race-089 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 868 | 868 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 1 | hold | race-067 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 566 | 566 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 86 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 159 | 159 | ORD-20261031-0e5b0cdc | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 42 | hold | race-133 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 593 | 593 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 46 | hold | race-145 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 520 | 520 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 62 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 134 | 134 | ORD-20261031-4f769e62 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 9 | hold | race-141 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 537 | 537 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 60 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 156 | 156 | ORD-20261031-1210303e | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 43 | hold | race-120 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 483 | 483 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 47 | hold | race-128 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 408 | 408 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 81 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 157 | 157 | ORD-20261031-54a87356 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 22 | hold | race-037 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 599 | 599 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 0 | hold | race-109 | RACE-X,RACE-Y | 201 | CLAIMED | 268 | 268 | HOLD-20261031-ad2b88e40b |  |
| 33 | hold | race-086 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 443 | 443 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 80 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 151 | 151 | ORD-20261031-b401d1f1 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 85 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 124 | 124 | ORD-20261031-d64ff236 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 52 | hold | race-061 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 449 | 449 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 84 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 138 | 138 | ORD-20261031-e7eff656 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 2 | hold | race-015 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 806 | 806 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 72 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 131 | 131 | ORD-20261031-f877e591 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 8 | hold | race-087 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 823 | 823 | - | 409 Not enough stock to hold RACE-X (available: 0) |
| 45 | hold | race-125 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 825 | 825 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 3 | hold | race-132 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 564 | 564 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 90 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 120 | 120 | ORD-20261031-c65102b5 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 59 | hold | race-044 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 378 | 378 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 31 | hold | race-065 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 550 | 550 | - | 409 Not enough stock to hold RACE-Y (available: 0) |
| 95 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 145 | 145 | ORD-20261031-b4cdbcbd | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 21 | hold | race-074 | RACE-Y,RACE-X | 201 | CLAIMED | 274 | 274 | HOLD-20261031-3fa35f3c27 |  |

</details>

## Money invariants (I1-I4, I6-I9)

Checked 90 orders: **all pass**


## Recovery

- Counters after recovery (stock, held, reserved, sold, writtenOff): {'RACE-1': (20, 0, 0, 0, 0), 'RACE-X': (10, 0, 0, 0, 0), 'RACE-Y': (10, 0, 0, 0, 0)}
- Full recovery **646 s after the last winning hold was created** (holds last 600 s); waited 629 s.
- Winning holds: {'EXPIRED': 30}, expired by {'schedule': 30}; schedule lag after expiresAt (min / median / max s): (0.8, 25.064500000000002, 49.075)

## I5 stock conservation after recovery

- PASS: RACE-1 back to its seed: stock 20/20, held 0, reserved 0
- PASS: RACE-X back to its seed: stock 10/10, held 0, reserved 0
- PASS: RACE-Y back to its seed: stock 10/10, held 0, reserved 0
- PASS: no ACTIVE holds left on race products: none
- PASS: I5 holds for all 16 products
