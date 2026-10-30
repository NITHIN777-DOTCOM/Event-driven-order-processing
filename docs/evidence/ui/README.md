# Storefront UI evidence (Phase 4.1)

Every scenario was run through the deployed storefront (https://dg38gx94mao9n.cloudfront.net) by `scripts/capture_ui.py`
(Playwright + Chromium): browse -> product -> cart -> checkout -> DemoPay payment -> live tracker.
After each order the DemoPay ledger was checked through `GET /wallet`.

| Scenario | orderId | Tracker result | Wallet DEBITs (expected) |
|---|---|---|---|
| Normal | `ORD-20261030-fceed1dd` | Order completed; balance 1,000,000 -> 996,501; hold consumed: True | 1 (1) ✓ |
| Payment glitch (retries) | `ORD-20261030-8826857e` | Order completed | 1 (1) ✓ |
| Payment declined | `ORD-20261030-bd3afcbb` | Order failed | 0 (0) ✓ |
| Item damaged (partial refund) | `ORD-20261030-305562b3` | Order partially fulfilled; CREDITs [1799] (L2 = 1799) | 1 (1) ✓ |
| Cancel after payment | `ORD-20261030-5eb11ebb` | Order cancelled; Cancelled — refunded ₹1,299; CREDITs [1299] | 1 (1) ✓ |
| Low balance (real decline) | `ORD-20261030-034e71e4` | Order failed | 0 (0) ✓ |
| Duplicate test (3 requests) | `ORD-20261030-f9b6decd` | Order completed · 1 order | 1 (1) ✓ |
| Late payment (auto-refund) | `ORD-20261030-46b99269` | Order failed; refund row shown: True | 1 (1) ✓ |
| Poison message (to DLQ) | `ORD-20261030-57fb2f10` | Stuck in the dead-letter queue | 0 (0) ✓ |
| Checkout hold: expired, held again, released on leaving | `-` | HOLD-20261030-8463aab849 -> HOLD-20261030-407d7a122f; released: True | 0 (0) ✓ |

Browser console errors during the run: 0

## Screenshots

### desktop-00-managed-login

![desktop-00-managed-login](desktop-00-managed-login.png)

### desktop-01-shop

![desktop-01-shop](desktop-01-shop.png)

### desktop-02-category-keyboards

![desktop-02-category-keyboards](desktop-02-category-keyboards.png)

### desktop-03-search

![desktop-03-search](desktop-03-search.png)

### desktop-04-product

![desktop-04-product](desktop-04-product.png)

### desktop-05-cart-drawer

![desktop-05-cart-drawer](desktop-05-cart-drawer.png)

### desktop-06-cart

![desktop-06-cart](desktop-06-cart.png)

### desktop-07-checkout-details

![desktop-07-checkout-details](desktop-07-checkout-details.png)

### desktop-07-checkout-payment

![desktop-07-checkout-payment](desktop-07-checkout-payment.png)

### desktop-07a-tracker-awaiting-payment

![desktop-07a-tracker-awaiting-payment](desktop-07a-tracker-awaiting-payment.png)

### desktop-07b-tracker-late-payment-refunded

![desktop-07b-tracker-late-payment-refunded](desktop-07b-tracker-late-payment-refunded.png)

### desktop-07c-checkout-hold-last-minute

![desktop-07c-checkout-hold-last-minute](desktop-07c-checkout-hold-last-minute.png)

### desktop-07d-checkout-hold-expired

![desktop-07d-checkout-hold-expired](desktop-07d-checkout-hold-expired.png)

### desktop-08-tracker-completed

![desktop-08-tracker-completed](desktop-08-tracker-completed.png)

### desktop-09-tracker-payment-glitch

![desktop-09-tracker-payment-glitch](desktop-09-tracker-payment-glitch.png)

### desktop-10-tracker-payment-declined

![desktop-10-tracker-payment-declined](desktop-10-tracker-payment-declined.png)

### desktop-10b-tracker-partially-fulfilled

![desktop-10b-tracker-partially-fulfilled](desktop-10b-tracker-partially-fulfilled.png)

### desktop-10c-wallet-partial-credit

![desktop-10c-wallet-partial-credit](desktop-10c-wallet-partial-credit.png)

### desktop-10d-tracker-cancel-button

![desktop-10d-tracker-cancel-button](desktop-10d-tracker-cancel-button.png)

### desktop-10e-tracker-cancel-confirm

![desktop-10e-tracker-cancel-confirm](desktop-10e-tracker-cancel-confirm.png)

### desktop-10f-tracker-cancelled

![desktop-10f-tracker-cancelled](desktop-10f-tracker-cancelled.png)

### desktop-10g-wallet-cancel-refund

![desktop-10g-wallet-cancel-refund](desktop-10g-wallet-cancel-refund.png)

### desktop-11-checkout-insufficient-balance

![desktop-11-checkout-insufficient-balance](desktop-11-checkout-insufficient-balance.png)

### desktop-12-tracker-poison-retrying

![desktop-12-tracker-poison-retrying](desktop-12-tracker-poison-retrying.png)

### desktop-13-tracker-insufficient-balance

![desktop-13-tracker-insufficient-balance](desktop-13-tracker-insufficient-balance.png)

### desktop-14-checkout-duplicate-test

![desktop-14-checkout-duplicate-test](desktop-14-checkout-duplicate-test.png)

### desktop-15-wallet

![desktop-15-wallet](desktop-15-wallet.png)

### desktop-16-orders

![desktop-16-orders](desktop-16-orders.png)

### desktop-17-tracker-poison-dead-lettered

![desktop-17-tracker-poison-dead-lettered](desktop-17-tracker-poison-dead-lettered.png)

### mobile-01-shop

![mobile-01-shop](mobile-01-shop.png)

### mobile-02-product

![mobile-02-product](mobile-02-product.png)

### mobile-03-checkout-payment

![mobile-03-checkout-payment](mobile-03-checkout-payment.png)

### mobile-04-tracker-completed

![mobile-04-tracker-completed](mobile-04-tracker-completed.png)

### mobile-05-wallet

![mobile-05-wallet](mobile-05-wallet.png)

