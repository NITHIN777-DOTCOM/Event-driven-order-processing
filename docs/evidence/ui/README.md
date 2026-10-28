# Storefront UI evidence (Phase 4.1)

Every scenario was run through the deployed storefront (https://dg38gx94mao9n.cloudfront.net) by `scripts/capture_ui.py`
(Playwright + Chromium): browse -> product -> cart -> checkout -> DemoPay payment -> live tracker.
After each order the DemoPay ledger was checked through `GET /wallet`.

| Scenario | orderId | Tracker result | Wallet DEBITs (expected) |
|---|---|---|---|
| Normal | `ORD-20261028-e7b319fa` | Order completed; balance 1,000,000 -> 996,501 | 1 (1) ✓ |
| Payment glitch (retries) | `ORD-20261028-c765f7db` | Order completed | 1 (1) ✓ |
| Payment declined | `ORD-20261028-27f51557` | Order failed | 0 (0) ✓ |
| Low balance (real decline) | `ORD-20261028-b4d56f34` | Order failed | 0 (0) ✓ |
| Duplicate test (3 requests) | `ORD-20261028-cb8df6a3` | Order completed · 1 order | 1 (1) ✓ |
| Poison message (to DLQ) | `ORD-20261028-67d9704f` | Stuck in the dead-letter queue | 0 (0) ✓ |

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

### desktop-08-tracker-completed

![desktop-08-tracker-completed](desktop-08-tracker-completed.png)

### desktop-09-tracker-payment-glitch

![desktop-09-tracker-payment-glitch](desktop-09-tracker-payment-glitch.png)

### desktop-10-tracker-payment-declined

![desktop-10-tracker-payment-declined](desktop-10-tracker-payment-declined.png)

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

