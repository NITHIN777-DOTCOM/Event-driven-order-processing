# Oversell race test, run `before-fix`

Run: 2026-10-31T07:55:36.063Z · Region: ap-south-1 · API: `https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com` · Command: `python scripts/oversell_race.py --label before-fix` · Duration: 834 s

**Result: FAIL**

## Pre-flight

- Lambda account concurrency limit **400**, unreserved **400** (no function has reserved concurrency).
- API Gateway stage `$default`: burst **100**, rate **50.0/s**, per-route overrides: 0.
- Buyers: 10 order buyers + 150 hold buyers (one ACTIVE hold per user), tokens fetched before the race.

## Round 1: 200 simultaneous attempts on RACE-1 (20 units)

Fired 2026-10-31T07:55:36.063Z; all 200 requests left within **51 ms**.

| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |
|---|---|---|---|---|---|---|
| checkout holds | 150 | 20 | 130 | 0 | 0 | 0 |
| direct orders | 50 | 0 | 50 | 0 | 0 | 0 |
| **total** | 200 | 20 | 180 | 0 | 0 | 0 |

Latency in ms, p50 / p95 / max:

| Measure | p50 / p95 / max |
|---|---|
| answering request, holds (the real stock answer) | 911 / 1228 / 1257 |
| first send -> real answer, holds (throttled retries included) | 911 / 1228 / 1257 |
| POST /orders accepted (202) | 806 / 1094 / 1114 |
| order accepted -> stock answer in the saga | 1536 / 2577 / 2695 |

Sampler (consistent reads every ~200 ms during the round):

| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |
|---|---|---|---|---|
| RACE-1 | 49 | 0 | 20 | (0, 20, 0, 0, 0) |

Checks:

- PASS: exactly 20 carts claimed: 20 (holds 20, orders 0)
- PASS: 0 ERROR answers: 0
- PASS: every throttled request was eventually answered (0 throttled at least once)
- PASS: RACE-1 at settle: stock 0, held 20, reserved 0 (claimed 20 = 20)
- PASS: RACE-1 sampler (49 samples): min stock 0, max claimed 20 (<= 20)
- PASS: I5 on every sample: stock + claimed = seeded
- **FAIL**: no out-of-stock answer while stock was left (409 with available > 0): 58
- PASS: cancelled the 0 winning orders: HTTP []

<details><summary>Every attempt</summary>

| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 107 | hold | race-118 | RACE-1 | 409 | OUT_OF_STOCK | 1072 | 1072 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 62 | hold | race-073 | RACE-1 | 409 | OUT_OF_STOCK | 1052 | 1052 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 42 | hold | race-053 | RACE-1 | 409 | OUT_OF_STOCK | 1021 | 1021 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 64 | hold | race-075 | RACE-1 | 409 | OUT_OF_STOCK | 1079 | 1079 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 33 | hold | race-044 | RACE-1 | 409 | OUT_OF_STOCK | 850 | 850 | - | 409 Not enough stock to hold RACE-1 (available: 5) |
| 183 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 1084 | 1084 | ORD-20261031-b1b69718 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 39 | hold | race-050 | RACE-1 | 409 | OUT_OF_STOCK | 903 | 903 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 152 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 743 | 743 | ORD-20261031-59e6bb2d | Insufficient stock for: one or more items / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 102 | hold | race-113 | RACE-1 | 409 | OUT_OF_STOCK | 829 | 829 | - | 409 Not enough stock to hold RACE-1 (available: 8) |
| 185 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 863 | 863 | ORD-20261031-e1193e05 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 144 | hold | race-155 | RACE-1 | 409 | OUT_OF_STOCK | 1106 | 1106 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 178 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 692 | 692 | ORD-20261031-f706bf75 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 165 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 901 | 901 | ORD-20261031-e312be27 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 2 | hold | race-013 | RACE-1 | 409 | OUT_OF_STOCK | 919 | 919 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 194 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 754 | 754 | ORD-20261031-5482d360 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 97 | hold | race-108 | RACE-1 | 409 | OUT_OF_STOCK | 1156 | 1156 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 123 | hold | race-134 | RACE-1 | 201 | CLAIMED | 814 | 814 | HOLD-20261031-d0d971f45e |  |
| 142 | hold | race-153 | RACE-1 | 409 | OUT_OF_STOCK | 878 | 878 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 106 | hold | race-117 | RACE-1 | 409 | OUT_OF_STOCK | 1046 | 1047 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 171 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 1094 | 1094 | ORD-20261031-b56e3b28 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 0 | hold | race-011 | RACE-1 | 409 | OUT_OF_STOCK | 1058 | 1058 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 131 | hold | race-142 | RACE-1 | 409 | OUT_OF_STOCK | 840 | 840 | - | 409 Not enough stock to hold RACE-1 (available: 11) |
| 156 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 776 | 776 | ORD-20261031-73e9c5a7 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 137 | hold | race-148 | RACE-1 | 409 | OUT_OF_STOCK | 844 | 844 | - | 409 Not enough stock to hold RACE-1 (available: 10) |
| 187 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 779 | 779 | ORD-20261031-2e024564 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 70 | hold | race-081 | RACE-1 | 409 | OUT_OF_STOCK | 1060 | 1060 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 136 | hold | race-147 | RACE-1 | 409 | OUT_OF_STOCK | 874 | 874 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 49 | hold | race-060 | RACE-1 | 201 | CLAIMED | 790 | 790 | HOLD-20261031-5c9a9af2ac |  |
| 55 | hold | race-066 | RACE-1 | 409 | OUT_OF_STOCK | 1065 | 1065 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 63 | hold | race-074 | RACE-1 | 409 | OUT_OF_STOCK | 951 | 951 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 32 | hold | race-043 | RACE-1 | 409 | OUT_OF_STOCK | 828 | 828 | - | 409 Not enough stock to hold RACE-1 (available: 8) |
| 96 | hold | race-107 | RACE-1 | 409 | OUT_OF_STOCK | 819 | 819 | - | 409 Not enough stock to hold RACE-1 (available: 14) |
| 89 | hold | race-100 | RACE-1 | 409 | OUT_OF_STOCK | 867 | 867 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 162 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 699 | 699 | ORD-20261031-d29c6a6e | Insufficient stock for: one or more items / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 191 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 715 | 715 | ORD-20261031-97dce497 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 76 | hold | race-087 | RACE-1 | 409 | OUT_OF_STOCK | 924 | 924 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 113 | hold | race-124 | RACE-1 | 409 | OUT_OF_STOCK | 1087 | 1087 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 112 | hold | race-123 | RACE-1 | 409 | OUT_OF_STOCK | 1232 | 1232 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 145 | hold | race-156 | RACE-1 | 409 | OUT_OF_STOCK | 1230 | 1230 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 12 | hold | race-023 | RACE-1 | 409 | OUT_OF_STOCK | 1057 | 1057 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 197 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 737 | 737 | ORD-20261031-68d6c93b | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 73 | hold | race-084 | RACE-1 | 409 | OUT_OF_STOCK | 1066 | 1066 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 195 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 800 | 800 | ORD-20261031-1cf7dcea | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 35 | hold | race-046 | RACE-1 | 409 | OUT_OF_STOCK | 1109 | 1109 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 146 | hold | race-157 | RACE-1 | 409 | OUT_OF_STOCK | 854 | 854 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 40 | hold | race-051 | RACE-1 | 409 | OUT_OF_STOCK | 912 | 912 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 68 | hold | race-079 | RACE-1 | 409 | OUT_OF_STOCK | 827 | 827 | - | 409 Not enough stock to hold RACE-1 (available: 6) |
| 44 | hold | race-055 | RACE-1 | 409 | OUT_OF_STOCK | 1075 | 1075 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 22 | hold | race-033 | RACE-1 | 409 | OUT_OF_STOCK | 908 | 908 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 186 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 245 | 245 | ORD-20261031-8b61463c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 151 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 832 | 832 | ORD-20261031-232a3f2a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 158 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 898 | 898 | ORD-20261031-d723ad22 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 182 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 925 | 925 | ORD-20261031-6c5fefc0 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 17 | hold | race-028 | RACE-1 | 409 | OUT_OF_STOCK | 879 | 879 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 28 | hold | race-039 | RACE-1 | 409 | OUT_OF_STOCK | 1208 | 1208 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 100 | hold | race-111 | RACE-1 | 409 | OUT_OF_STOCK | 856 | 856 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 175 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 806 | 806 | ORD-20261031-89c0c94a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 168 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 786 | 786 | ORD-20261031-70925a64 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 92 | hold | race-103 | RACE-1 | 409 | OUT_OF_STOCK | 886 | 886 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 58 | hold | race-069 | RACE-1 | 409 | OUT_OF_STOCK | 878 | 878 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 105 | hold | race-116 | RACE-1 | 201 | CLAIMED | 790 | 790 | HOLD-20261031-f8180e69b6 |  |
| 1 | hold | race-012 | RACE-1 | 409 | OUT_OF_STOCK | 891 | 891 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 61 | hold | race-072 | RACE-1 | 409 | OUT_OF_STOCK | 890 | 890 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 21 | hold | race-032 | RACE-1 | 409 | OUT_OF_STOCK | 973 | 973 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 53 | hold | race-064 | RACE-1 | 409 | OUT_OF_STOCK | 1055 | 1055 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 108 | hold | race-119 | RACE-1 | 409 | OUT_OF_STOCK | 1051 | 1051 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 65 | hold | race-076 | RACE-1 | 409 | OUT_OF_STOCK | 1055 | 1055 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 19 | hold | race-030 | RACE-1 | 409 | OUT_OF_STOCK | 858 | 858 | - | 409 Not enough stock to hold RACE-1 (available: 6) |
| 125 | hold | race-136 | RACE-1 | 409 | OUT_OF_STOCK | 1239 | 1239 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 87 | hold | race-098 | RACE-1 | 409 | OUT_OF_STOCK | 896 | 896 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 134 | hold | race-145 | RACE-1 | 409 | OUT_OF_STOCK | 1212 | 1212 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 157 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 1096 | 1096 | ORD-20261031-097eaad1 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 176 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 802 | 802 | ORD-20261031-32a6e132 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 50 | hold | race-061 | RACE-1 | 409 | OUT_OF_STOCK | 1080 | 1081 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 117 | hold | race-128 | RACE-1 | 409 | OUT_OF_STOCK | 1008 | 1008 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 129 | hold | race-140 | RACE-1 | 409 | OUT_OF_STOCK | 991 | 991 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 109 | hold | race-120 | RACE-1 | 409 | OUT_OF_STOCK | 1022 | 1022 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 188 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 810 | 810 | ORD-20261031-1774055f | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 170 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 887 | 887 | ORD-20261031-932bb1f3 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 56 | hold | race-067 | RACE-1 | 409 | OUT_OF_STOCK | 999 | 999 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 38 | hold | race-049 | RACE-1 | 409 | OUT_OF_STOCK | 1033 | 1033 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 48 | hold | race-059 | RACE-1 | 409 | OUT_OF_STOCK | 1061 | 1061 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 177 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 721 | 721 | ORD-20261031-07ea5836 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 155 | order | race-006 | RACE-1 | 202 | OUT_OF_STOCK | 735 | 735 | ORD-20261031-7b4e5349 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 72 | hold | race-083 | RACE-1 | 201 | CLAIMED | 909 | 909 | HOLD-20261031-ace3745248 |  |
| 24 | hold | race-035 | RACE-1 | 409 | OUT_OF_STOCK | 836 | 836 | - | 409 Not enough stock to hold RACE-1 (available: 11) |
| 120 | hold | race-131 | RACE-1 | 201 | CLAIMED | 825 | 825 | HOLD-20261031-ed9125435d |  |
| 199 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 988 | 988 | ORD-20261031-a8fe45a3 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 47 | hold | race-058 | RACE-1 | 409 | OUT_OF_STOCK | 1088 | 1088 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 18 | hold | race-029 | RACE-1 | 409 | OUT_OF_STOCK | 1074 | 1074 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 128 | hold | race-139 | RACE-1 | 201 | CLAIMED | 821 | 821 | HOLD-20261031-b7ef75f201 |  |
| 83 | hold | race-094 | RACE-1 | 409 | OUT_OF_STOCK | 815 | 815 | - | 409 Not enough stock to hold RACE-1 (available: 14) |
| 16 | hold | race-027 | RACE-1 | 409 | OUT_OF_STOCK | 866 | 866 | - | 409 Not enough stock to hold RACE-1 (available: 5) |
| 7 | hold | race-018 | RACE-1 | 409 | OUT_OF_STOCK | 1050 | 1050 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 163 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 906 | 906 | ORD-20261031-19bfb26c | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 161 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 887 | 887 | ORD-20261031-699d5ba0 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 51 | hold | race-062 | RACE-1 | 201 | CLAIMED | 844 | 844 | HOLD-20261031-a8e83b9788 |  |
| 99 | hold | race-110 | RACE-1 | 409 | OUT_OF_STOCK | 896 | 896 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 57 | hold | race-068 | RACE-1 | 409 | OUT_OF_STOCK | 1091 | 1091 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 114 | hold | race-125 | RACE-1 | 201 | CLAIMED | 778 | 778 | HOLD-20261031-4fd1689fb6 |  |
| 169 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 229 | 229 | ORD-20261031-2ccb9fc8 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 196 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 1076 | 1076 | ORD-20261031-95c2a493 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 135 | hold | race-146 | RACE-1 | 409 | OUT_OF_STOCK | 911 | 911 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 26 | hold | race-037 | RACE-1 | 201 | CLAIMED | 830 | 830 | HOLD-20261031-4f8a918e42 |  |
| 11 | hold | race-022 | RACE-1 | 409 | OUT_OF_STOCK | 824 | 824 | - | 409 Not enough stock to hold RACE-1 (available: 12) |
| 130 | hold | race-141 | RACE-1 | 409 | OUT_OF_STOCK | 911 | 911 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 122 | hold | race-133 | RACE-1 | 409 | OUT_OF_STOCK | 1257 | 1257 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 23 | hold | race-034 | RACE-1 | 409 | OUT_OF_STOCK | 875 | 875 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 132 | hold | race-143 | RACE-1 | 409 | OUT_OF_STOCK | 1007 | 1007 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 159 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 731 | 731 | ORD-20261031-da36b1b8 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 93 | hold | race-104 | RACE-1 | 409 | OUT_OF_STOCK | 896 | 896 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 141 | hold | race-152 | RACE-1 | 409 | OUT_OF_STOCK | 1049 | 1049 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 121 | hold | race-132 | RACE-1 | 409 | OUT_OF_STOCK | 1044 | 1044 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 150 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 899 | 899 | ORD-20261031-605df985 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 166 | order | race-007 | RACE-1 | 202 | OUT_OF_STOCK | 771 | 771 | ORD-20261031-dfd56bdc | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 88 | hold | race-099 | RACE-1 | 201 | CLAIMED | 839 | 839 | HOLD-20261031-48bec366b0 |  |
| 139 | hold | race-150 | RACE-1 | 409 | OUT_OF_STOCK | 886 | 886 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 143 | hold | race-154 | RACE-1 | 409 | OUT_OF_STOCK | 1004 | 1004 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 110 | hold | race-121 | RACE-1 | 409 | OUT_OF_STOCK | 816 | 816 | - | 409 Not enough stock to hold RACE-1 (available: 14) |
| 5 | hold | race-016 | RACE-1 | 409 | OUT_OF_STOCK | 1216 | 1216 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 116 | hold | race-127 | RACE-1 | 409 | OUT_OF_STOCK | 1065 | 1065 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 184 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 1067 | 1067 | ORD-20261031-916a0a97 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 103 | hold | race-114 | RACE-1 | 409 | OUT_OF_STOCK | 865 | 865 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 118 | hold | race-129 | RACE-1 | 409 | OUT_OF_STOCK | 1023 | 1023 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 77 | hold | race-088 | RACE-1 | 409 | OUT_OF_STOCK | 1051 | 1051 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 34 | hold | race-045 | RACE-1 | 409 | OUT_OF_STOCK | 882 | 882 | - | 409 Not enough stock to hold RACE-1 (available: 6) |
| 85 | hold | race-096 | RACE-1 | 409 | OUT_OF_STOCK | 876 | 876 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 59 | hold | race-070 | RACE-1 | 201 | CLAIMED | 780 | 780 | HOLD-20261031-3010fb7076 |  |
| 104 | hold | race-115 | RACE-1 | 409 | OUT_OF_STOCK | 891 | 891 | - | 409 Not enough stock to hold RACE-1 (available: 5) |
| 101 | hold | race-112 | RACE-1 | 409 | OUT_OF_STOCK | 875 | 875 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 147 | hold | race-158 | RACE-1 | 409 | OUT_OF_STOCK | 854 | 854 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 81 | hold | race-092 | RACE-1 | 409 | OUT_OF_STOCK | 867 | 867 | - | 409 Not enough stock to hold RACE-1 (available: 5) |
| 15 | hold | race-026 | RACE-1 | 409 | OUT_OF_STOCK | 865 | 865 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 69 | hold | race-080 | RACE-1 | 409 | OUT_OF_STOCK | 812 | 812 | - | 409 Not enough stock to hold RACE-1 (available: 12) |
| 25 | hold | race-036 | RACE-1 | 409 | OUT_OF_STOCK | 1003 | 1003 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 127 | hold | race-138 | RACE-1 | 201 | CLAIMED | 880 | 880 | HOLD-20261031-7a4b019e70 |  |
| 3 | hold | race-014 | RACE-1 | 409 | OUT_OF_STOCK | 1201 | 1201 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 4 | hold | race-015 | RACE-1 | 409 | OUT_OF_STOCK | 806 | 806 | - | 409 Not enough stock to hold RACE-1 (available: 15) |
| 172 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 686 | 686 | ORD-20261031-a54c3a65 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 153 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 800 | 800 | ORD-20261031-c3901333 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 29 | hold | race-040 | RACE-1 | 201 | CLAIMED | 783 | 783 | HOLD-20261031-1200681584 |  |
| 31 | hold | race-042 | RACE-1 | 409 | OUT_OF_STOCK | 1035 | 1035 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 126 | hold | race-137 | RACE-1 | 409 | OUT_OF_STOCK | 892 | 892 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 10 | hold | race-021 | RACE-1 | 409 | OUT_OF_STOCK | 803 | 803 | - | 409 Not enough stock to hold RACE-1 (available: 10) |
| 148 | hold | race-159 | RACE-1 | 201 | CLAIMED | 810 | 810 | HOLD-20261031-a85106abbf |  |
| 78 | hold | race-089 | RACE-1 | 409 | OUT_OF_STOCK | 1086 | 1086 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 164 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 910 | 910 | ORD-20261031-a2dbd893 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 46 | hold | race-057 | RACE-1 | 409 | OUT_OF_STOCK | 1069 | 1070 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 74 | hold | race-085 | RACE-1 | 409 | OUT_OF_STOCK | 852 | 852 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 189 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 672 | 672 | ORD-20261031-66d5b921 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 71 | hold | race-082 | RACE-1 | 409 | OUT_OF_STOCK | 1075 | 1075 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 138 | hold | race-149 | RACE-1 | 409 | OUT_OF_STOCK | 841 | 841 | - | 409 Not enough stock to hold RACE-1 (available: 6) |
| 133 | hold | race-144 | RACE-1 | 409 | OUT_OF_STOCK | 1012 | 1012 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 36 | hold | race-047 | RACE-1 | 409 | OUT_OF_STOCK | 1007 | 1007 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 45 | hold | race-056 | RACE-1 | 409 | OUT_OF_STOCK | 1228 | 1228 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 41 | hold | race-052 | RACE-1 | 201 | CLAIMED | 808 | 808 | HOLD-20261031-9265899f9f |  |
| 193 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 910 | 910 | ORD-20261031-e6f2fcb7 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 140 | hold | race-151 | RACE-1 | 409 | OUT_OF_STOCK | 954 | 954 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 111 | hold | race-122 | RACE-1 | 409 | OUT_OF_STOCK | 911 | 911 | - | 409 Not enough stock to hold RACE-1 (available: 2) |
| 149 | hold | race-160 | RACE-1 | 409 | OUT_OF_STOCK | 855 | 855 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 37 | hold | race-048 | RACE-1 | 409 | OUT_OF_STOCK | 1045 | 1045 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 27 | hold | race-038 | RACE-1 | 409 | OUT_OF_STOCK | 861 | 861 | - | 409 Not enough stock to hold RACE-1 (available: 5) |
| 119 | hold | race-130 | RACE-1 | 409 | OUT_OF_STOCK | 1015 | 1015 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 67 | hold | race-078 | RACE-1 | 409 | OUT_OF_STOCK | 1017 | 1017 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 173 | order | race-004 | RACE-1 | 202 | OUT_OF_STOCK | 681 | 681 | ORD-20261031-f6179fec | Insufficient stock for: one or more items / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 86 | hold | race-097 | RACE-1 | 409 | OUT_OF_STOCK | 1071 | 1071 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 190 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 986 | 986 | ORD-20261031-22c086e2 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 181 | order | race-002 | RACE-1 | 202 | OUT_OF_STOCK | 806 | 806 | ORD-20261031-11d938a7 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 54 | hold | race-065 | RACE-1 | 201 | CLAIMED | 826 | 826 | HOLD-20261031-a7f523e316 |  |
| 84 | hold | race-095 | RACE-1 | 409 | OUT_OF_STOCK | 1079 | 1079 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 66 | hold | race-077 | RACE-1 | 409 | OUT_OF_STOCK | 1242 | 1242 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 124 | hold | race-135 | RACE-1 | 409 | OUT_OF_STOCK | 1037 | 1037 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 82 | hold | race-093 | RACE-1 | 409 | OUT_OF_STOCK | 830 | 830 | - | 409 Not enough stock to hold RACE-1 (available: 8) |
| 160 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 769 | 769 | ORD-20261031-1ceaf0bd | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 14 | hold | race-025 | RACE-1 | 409 | OUT_OF_STOCK | 958 | 958 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 75 | hold | race-086 | RACE-1 | 409 | OUT_OF_STOCK | 986 | 986 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 20 | hold | race-031 | RACE-1 | 409 | OUT_OF_STOCK | 994 | 994 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 179 | order | race-010 | RACE-1 | 202 | OUT_OF_STOCK | 837 | 837 | ORD-20261031-f70a338a | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 90 | hold | race-101 | RACE-1 | 409 | OUT_OF_STOCK | 903 | 903 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 52 | hold | race-063 | RACE-1 | 409 | OUT_OF_STOCK | 849 | 849 | - | 409 Not enough stock to hold RACE-1 (available: 4) |
| 60 | hold | race-071 | RACE-1 | 409 | OUT_OF_STOCK | 1232 | 1232 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 91 | hold | race-102 | RACE-1 | 201 | CLAIMED | 894 | 894 | HOLD-20261031-9f767daebe |  |
| 180 | order | race-001 | RACE-1 | 202 | OUT_OF_STOCK | 753 | 753 | ORD-20261031-ac18b647 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 6 | hold | race-017 | RACE-1 | 409 | OUT_OF_STOCK | 892 | 892 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 198 | order | race-009 | RACE-1 | 202 | OUT_OF_STOCK | 829 | 829 | ORD-20261031-25ea5b33 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 192 | order | race-003 | RACE-1 | 202 | OUT_OF_STOCK | 1114 | 1114 | ORD-20261031-076518b5 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 95 | hold | race-106 | RACE-1 | 409 | OUT_OF_STOCK | 1247 | 1247 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 30 | hold | race-041 | RACE-1 | 409 | OUT_OF_STOCK | 808 | 808 | - | 409 Not enough stock to hold RACE-1 (available: 14) |
| 13 | hold | race-024 | RACE-1 | 409 | OUT_OF_STOCK | 1033 | 1033 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 154 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 905 | 905 | ORD-20261031-b7090cb0 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 174 | order | race-005 | RACE-1 | 202 | OUT_OF_STOCK | 910 | 910 | ORD-20261031-f51f4da0 | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 43 | hold | race-054 | RACE-1 | 201 | CLAIMED | 845 | 845 | HOLD-20261031-161a685396 |  |
| 79 | hold | race-090 | RACE-1 | 201 | CLAIMED | 807 | 807 | HOLD-20261031-8bb47043d5 |  |
| 9 | hold | race-020 | RACE-1 | 409 | OUT_OF_STOCK | 970 | 970 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 94 | hold | race-105 | RACE-1 | 409 | OUT_OF_STOCK | 904 | 904 | - | 409 Not enough stock to hold RACE-1 (available: 3) |
| 80 | hold | race-091 | RACE-1 | 409 | OUT_OF_STOCK | 1001 | 1001 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 167 | order | race-008 | RACE-1 | 202 | OUT_OF_STOCK | 706 | 706 | ORD-20261031-f019000e | Insufficient stock for: RACE-1 / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 98 | hold | race-109 | RACE-1 | 409 | OUT_OF_STOCK | 1075 | 1075 | - | 409 Not enough stock to hold RACE-1 (available: 0) |
| 8 | hold | race-019 | RACE-1 | 201 | CLAIMED | 866 | 866 | HOLD-20261031-4f6fa7e422 |  |
| 115 | hold | race-126 | RACE-1 | 409 | OUT_OF_STOCK | 1209 | 1209 | - | 409 Not enough stock to hold RACE-1 (available: 0) |

</details>

## Round 2: 100 simultaneous carts {RACE-X: 1, RACE-Y: 1} (10 + 10 units), item order X,Y / Y,X

Fired 2026-10-31T07:55:56.634Z; all 100 requests left within **45 ms**.

| Path | Attempts | CLAIMED | OUT_OF_STOCK | ERROR | Throttled (requests) | Throttle retries |
|---|---|---|---|---|---|---|
| checkout holds | 60 | 6 | 54 | 0 | 0 | 0 |
| direct orders | 40 | 4 | 36 | 0 | 0 | 0 |
| **total** | 100 | 10 | 90 | 0 | 0 | 0 |

Latency in ms, p50 / p95 / max:

| Measure | p50 / p95 / max |
|---|---|
| answering request, holds (the real stock answer) | 338 / 440 / 464 |
| first send -> real answer, holds (throttled retries included) | 338 / 440 / 464 |
| POST /orders accepted (202) | 163 / 242 / 246 |
| order accepted -> stock answer in the saga | 588 / 1021 / 1205 |

Sampler (consistent reads every ~200 ms during the round):

| Product | Samples | Min stock seen | Max claimed seen | Counters at settle (stock, held, reserved, sold, writtenOff) |
|---|---|---|---|---|
| RACE-Y | 32 | 0 | 10 | (0, 6, 4, 0, 0) |
| RACE-X | 32 | 0 | 10 | (0, 6, 4, 0, 0) |

Checks:

- PASS: exactly 10 carts claimed: 10 (holds 6, orders 4)
- PASS: 0 ERROR answers: 0
- PASS: every throttled request was eventually answered (0 throttled at least once)
- PASS: RACE-Y at settle: stock 0, held 6, reserved 4 (claimed 10 = 10)
- PASS: RACE-Y sampler (32 samples): min stock 0, max claimed 10 (<= 10)
- PASS: RACE-X at settle: stock 0, held 6, reserved 4 (claimed 10 = 10)
- PASS: RACE-X sampler (32 samples): min stock 0, max claimed 10 (<= 10)
- PASS: I5 on every sample: stock + claimed = seeded
- **FAIL**: no out-of-stock answer while stock was left (409 with available > 0): 54
- PASS: all-or-nothing: no cart with only one item (0), units claimed per product {'RACE-Y': 10, 'RACE-X': 10}
- PASS: cancelled the 4 winning orders: HTTP [202]

<details><summary>Every attempt</summary>

| # | Path | Buyer | Cart | HTTP codes | Outcome | Final ms | Total ms | Id | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 49 | hold | race-061 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 279 | 279 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 94 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 149 | 149 | ORD-20261031-601bdfae | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 10 | hold | race-153 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 349 | 349 | - | 409 Not enough stock to hold RACE-X (available: 4) |
| 54 | hold | race-049 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 369 | 369 | - | 409 Not enough stock to hold RACE-X (available: 4) |
| 79 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 139 | 139 | ORD-20261031-38189bea | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 50 | hold | race-128 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 354 | 355 | - | 409 Not enough stock to hold RACE-X (available: 6) |
| 48 | hold | race-145 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 426 | 426 | - | 409 Not enough stock to hold RACE-X (available: 4) |
| 63 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 130 | 130 | ORD-20261031-07df88f2 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 91 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 236 | 236 | ORD-20261031-24b619c0 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 21 | hold | race-100 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 328 | 328 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 98 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 197 | 197 | ORD-20261031-6ff8b423 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 77 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 163 | 163 | ORD-20261031-b651d9b4 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 19 | hold | race-043 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 464 | 464 | - | 409 Not enough stock to hold RACE-Y (available: 5) |
| 61 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 153 | 153 | ORD-20261031-751dd3c5 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 1 | hold | race-073 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 332 | 332 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 11 | hold | race-117 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 272 | 272 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 80 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 156 | 156 | ORD-20261031-16fa6172 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 69 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 126 | 126 | ORD-20261031-c0f20bf8 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 46 | hold | race-136 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 350 | 350 | - | 409 Not enough stock to hold RACE-X (available: 5) |
| 39 | hold | race-012 | RACE-Y,RACE-X | 201 | CLAIMED | 314 | 314 | HOLD-20261031-b650353663 |  |
| 60 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 134 | 134 | ORD-20261031-aebecceb | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 74 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 178 | 178 | ORD-20261031-cae52103 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 14 | hold | race-148 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 275 | 275 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 12 | hold | race-011 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 449 | 450 | - | 409 Not enough stock to hold RACE-X (available: 5) |
| 38 | hold | race-069 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 298 | 298 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 44 | hold | race-076 | RACE-X,RACE-Y | 201 | CLAIMED | 423 | 423 | HOLD-20261031-d37b509a33 |  |
| 2 | hold | race-053 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 398 | 398 | - | 409 Not enough stock to hold RACE-X (available: 6) |
| 34 | hold | race-028 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 374 | 374 | - | 409 Not enough stock to hold RACE-X (available: 4) |
| 68 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 191 | 191 | ORD-20261031-2a8f62c8 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 65 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 142 | 142 | ORD-20261031-ddddeb45 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 88 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 245 | 245 | ORD-20261031-f26ec95a | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 0 | hold | race-118 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 388 | 388 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 9 | hold | race-108 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 393 | 393 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 73 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 160 | 160 | ORD-20261031-637caa02 | Insufficient stock for: one or more items / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 83 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 242 | 242 | ORD-20261031-4510f06a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 76 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 191 | 191 | ORD-20261031-4691a3df | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 53 | hold | race-067 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 307 | 307 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 42 | hold | race-064 | RACE-X,RACE-Y | 201 | CLAIMED | 327 | 327 | HOLD-20261031-71551aa631 |  |
| 27 | hold | race-084 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 282 | 282 | - | 409 Not enough stock to hold RACE-Y (available: 7) |
| 13 | hold | race-142 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 411 | 411 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 7 | hold | race-155 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 369 | 369 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 41 | hold | race-032 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 338 | 338 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 72 | order | race-003 | RACE-X,RACE-Y | 202 | CLAIMED | 114 | 114 | ORD-20261031-9b3b992a | Reserved stock for 2 product(s) / final CANCELLED, FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 82 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 246 | 246 | ORD-20261031-a9346adb | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 86 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 116 | 116 | ORD-20261031-5b41667e | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 75 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 127 | 127 | ORD-20261031-e29c751b | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 99 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 231 | 231 | ORD-20261031-ee4a8267 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 95 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 226 | 226 | ORD-20261031-cd62b601 | Insufficient stock for: one or more items / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 15 | hold | race-081 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 443 | 443 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 36 | hold | race-111 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 323 | 323 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 22 | hold | race-087 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 399 | 399 | - | 409 Not enough stock to hold RACE-X (available: 5) |
| 20 | hold | race-107 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 270 | 270 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 51 | hold | race-140 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 401 | 401 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 59 | hold | race-094 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 328 | 328 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 96 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 200 | 200 | ORD-20261031-88d8f370 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 43 | hold | race-119 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 298 | 298 | - | 409 Not enough stock to hold RACE-Y (available: 7) |
| 33 | hold | race-033 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 440 | 440 | - | 409 Not enough stock to hold RACE-Y (available: 7) |
| 78 | order | race-009 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 144 | 144 | ORD-20261031-adc8208b | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 45 | hold | race-030 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 353 | 354 | - | 409 Not enough stock to hold RACE-Y (available: 4) |
| 28 | hold | race-046 | RACE-X,RACE-Y | 201 | CLAIMED | 257 | 257 | HOLD-20261031-b061ea12e1 |  |
| 58 | hold | race-029 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 421 | 421 | - | 409 Not enough stock to hold RACE-X (available: 4) |
| 89 | order | race-010 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 172 | 172 | ORD-20261031-5d3aa8e0 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 29 | hold | race-157 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 399 | 399 | - | 409 Not enough stock to hold RACE-Y (available: 4) |
| 6 | hold | race-113 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 262 | 262 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 81 | order | race-002 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 92 | 92 | ORD-20261031-ea8d201a | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 8 | hold | race-013 | RACE-X,RACE-Y | 201 | CLAIMED | 251 | 251 | HOLD-20261031-24f8568834 |  |
| 92 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 200 | 200 | ORD-20261031-a994ba8f | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 47 | hold | race-098 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 291 | 291 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 4 | hold | race-044 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 285 | 285 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 67 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 169 | 169 | ORD-20261031-fa425845 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 85 | order | race-006 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 181 | 181 | ORD-20261031-e4e848eb | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 71 | order | race-002 | RACE-Y,RACE-X | 202 | CLAIMED | 223 | 223 | ORD-20261031-f1eeae33 | Reserved stock for 2 product(s) / final CANCELLED, FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 5 | hold | race-050 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 285 | 285 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 25 | hold | race-156 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 325 | 325 | - | 409 Not enough stock to hold RACE-Y (available: 5) |
| 30 | hold | race-051 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 386 | 386 | - | 409 Not enough stock to hold RACE-X (available: 5) |
| 56 | hold | race-035 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 431 | 431 | - | 409 Not enough stock to hold RACE-X (available: 4) |
| 32 | hold | race-055 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 327 | 327 | - | 409 Not enough stock to hold RACE-X (available: 5) |
| 97 | order | race-008 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 157 | 157 | ORD-20261031-4f391895 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 62 | order | race-003 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 215 | 215 | ORD-20261031-cda10f5e | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 3 | hold | race-075 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 397 | 397 | - | 409 Not enough stock to hold RACE-Y (available: 4) |
| 66 | order | race-007 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 108 | 108 | ORD-20261031-2caf3be9 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 93 | order | race-004 | RACE-Y,RACE-X | 202 | OUT_OF_STOCK | 165 | 165 | ORD-20261031-9b791cc8 | Insufficient stock for: RACE-Y, RACE-X / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 40 | hold | race-072 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 309 | 309 | - | 409 Not enough stock to hold RACE-X (available: 6) |
| 87 | order | race-008 | RACE-Y,RACE-X | 202 | CLAIMED | 150 | 150 | ORD-20261031-849384ca | Reserved stock for 2 product(s) / final CANCELLED, FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 55 | hold | race-059 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 428 | 428 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 57 | hold | race-058 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 331 | 331 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 37 | hold | race-103 | RACE-Y,RACE-X | 201 | CLAIMED | 259 | 259 | HOLD-20261031-3d58f58d3c |  |
| 90 | order | race-001 | RACE-X,RACE-Y | 202 | CLAIMED | 127 | 127 | ORD-20261031-22ac13b1 | Reserved stock for 2 product(s) / final CANCELLED, FAILED · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 18 | hold | race-074 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 404 | 404 | - | 409 Not enough stock to hold RACE-X (available: 6) |
| 31 | hold | race-079 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 287 | 287 | - | 409 Not enough stock to hold RACE-Y (available: 4) |
| 24 | hold | race-123 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 407 | 407 | - | 409 Not enough stock to hold RACE-X (available: 6) |
| 52 | hold | race-120 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 256 | 256 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 26 | hold | race-023 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 264 | 264 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 64 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 207 | 207 | ORD-20261031-63602e2a | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 35 | hold | race-039 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 360 | 360 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 17 | hold | race-066 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 374 | 374 | - | 409 Not enough stock to hold RACE-Y (available: 5) |
| 16 | hold | race-147 | RACE-X,RACE-Y | 409 | OUT_OF_STOCK | 319 | 319 | - | 409 Not enough stock to hold RACE-X (available: 7) |
| 23 | hold | race-124 | RACE-Y,RACE-X | 409 | OUT_OF_STOCK | 338 | 338 | - | 409 Not enough stock to hold RACE-Y (available: 6) |
| 84 | order | race-005 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 205 | 205 | ORD-20261031-c616e628 | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |
| 70 | order | race-001 | RACE-X,RACE-Y | 202 | OUT_OF_STOCK | 154 | 154 | ORD-20261031-38a123ef | Insufficient stock for: RACE-X, RACE-Y / final FAILED, - · ledger 0 DEBIT / 0 CREDIT, net ₹0 |

</details>

## Money invariants (I1-I4, I6-I9)

Checked 90 orders: **all pass**


## Recovery

- Counters after recovery (stock, held, reserved, sold, writtenOff): {'RACE-1': (20, 0, 0, 0, 0), 'RACE-X': (10, 0, 0, 0, 0), 'RACE-Y': (10, 0, 0, 0, 0)}
- Full recovery **652 s after the last winning hold was created** (holds last 600 s); waited 631 s.
- Winning holds: {'EXPIRED': 26}, expired by {'schedule': 26}; schedule lag after expiresAt (min / median / max s): (1.076, 24.066499999999998, 50.079)

## I5 stock conservation after recovery

- PASS: RACE-1 back to its seed: stock 20/20, held 0, reserved 0
- PASS: RACE-X back to its seed: stock 10/10, held 0, reserved 0
- PASS: RACE-Y back to its seed: stock 10/10, held 0, reserved 0
- PASS: no ACTIVE holds left on race products: none
- PASS: I5 holds for all 16 products
