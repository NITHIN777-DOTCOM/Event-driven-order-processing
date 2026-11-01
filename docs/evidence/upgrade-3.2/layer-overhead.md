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

### FIS extension layer attached, idle (partial deploy of commit A): 2026-10-31 15:41 to 2026-10-31 16:43 UTC

| Function | Invocations | p50 ms | p95 ms | Cold starts | Init p50 ms | Init p95 ms |
|---|---|---|---|---|---|---|
| reserve-inventory | 46 | 35 | 163 | 3 | 558 | 603 |
| request-payment | 47 | 54 | 236 | 3 | 437 | 443 |
| payment-provider | 122 | 27 | 402 | 9 | 558 | 755 |
| payment-webhook | 33 | 58 | 564 | 3 | 586 | 603 |
| fulfill-item | 24 | 42 | 181 | 3 | 556 | 699 |
| refund-payment | 31 | 228 | 911 | 14 | 459 | 629 |
| release-inventory | 27 | 31 | 140 | 2 | 425 | 575 |
| write-off-lines | 4 | 164 | 190 | 2 | 438 | 577 |
| begin-fulfillment | 19 | 16 | 132 | 2 | 455 | 545 |

### after: no FIS layer, in-house injector hook idle (CHAOS_ENABLED=false), Deploy 41221265475: 2026-10-31 16:52 to 2026-10-31 17:03 UTC

| Function | Invocations | p50 ms | p95 ms | Cold starts | Init p50 ms | Init p95 ms |
|---|---|---|---|---|---|---|
| reserve-inventory | 53 | 25 | 130 | 1 | 319 | 319 |
| request-payment | 56 | 51 | 189 | 1 | 573 | 573 |
| payment-provider | 132 | 14 | 257 | 2 | 308 | 312 |
| payment-webhook | 37 | 65 | 322 | 0 | 0 | 0 |
| fulfill-item | 26 | 36 | 147 | 1 | 316 | 316 |
| refund-payment | 35 | 70 | 284 | 4 | 408 | 595 |
| release-inventory | 31 | 34 | 121 | 2 | 278 | 417 |
| write-off-lines | 4 | 130 | 162 | 1 | 409 | 409 |
| begin-fulfillment | 23 | 21 | 95 | 0 | 0 | 0 |

