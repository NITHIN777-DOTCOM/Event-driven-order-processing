### before (no FIS layer): 2026-10-30 00:00 to 2026-10-31 15:00 UTC

| Function | Invocations | p50 ms | p95 ms | Cold starts | Init p50 ms | Init p95 ms |
|---|---|---|---|---|---|---|
| reserve-inventory | 680 | 52 | 218 | 73 | 425 | 568 |
| request-payment | 404 | 59 | 243 | 21 | 426 | 565 |
| payment-provider | 541 | 128 | 894 | 54 | 330 | 581 |
| payment-webhook | 318 | 63 | 572 | 20 | 434 | 578 |
| fulfill-item | 212 | 33 | 135 | 20 | 313 | 531 |
| refund-payment | 123 | 119 | 858 | 25 | 334 | 561 |
| release-inventory | 96 | 35 | 171 | 13 | 419 | 1106 |
| write-off-lines | 27 | 114 | 172 | 8 | 317 | 424 |
| begin-fulfillment | 62 | 17 | 123 | 10 | 317 | 546 |

