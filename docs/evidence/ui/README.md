# Storefront UI evidence (Phase 4)

Every scenario was run through the deployed storefront (https://dg38gx94mao9n.cloudfront.net) by `scripts/capture_ui.py`
(Playwright + Chromium): Shop -> Add -> Cart -> Checkout -> Place order -> live tracker.

| Scenario | orderId | Tracker result |
|---|---|---|
| Normal | `ORD-20261022-103f4ca5` | Order completed |
| Payment declined | `ORD-20261022-dea64a6e` | Order failed |
| Payment glitch (retries) | `ORD-20261022-faa0b08d` | Order completed |
| Out of stock | `ORD-20261022-c24789e1` | Order failed |
| Duplicate test (3 requests) | `ORD-20261022-f4cdf11b` | Order completed · 1 order |
| Poison message (to DLQ) | `ORD-20261022-ad12231d` | Stuck in the dead-letter queue |

Browser console errors during the run: 0

## Screenshots

### desktop-01-shop

![desktop-01-shop](desktop-01-shop.png)

### desktop-02-cart-drawer

![desktop-02-cart-drawer](desktop-02-cart-drawer.png)

### desktop-03-checkout

![desktop-03-checkout](desktop-03-checkout.png)

### desktop-04-tracker-completed

![desktop-04-tracker-completed](desktop-04-tracker-completed.png)

### desktop-05-tracker-payment-declined

![desktop-05-tracker-payment-declined](desktop-05-tracker-payment-declined.png)

### desktop-06-tracker-payment-glitch

![desktop-06-tracker-payment-glitch](desktop-06-tracker-payment-glitch.png)

### desktop-07-tracker-poison-retrying

![desktop-07-tracker-poison-retrying](desktop-07-tracker-poison-retrying.png)

### desktop-08-tracker-out-of-stock

![desktop-08-tracker-out-of-stock](desktop-08-tracker-out-of-stock.png)

### desktop-09-checkout-duplicate-test

![desktop-09-checkout-duplicate-test](desktop-09-checkout-duplicate-test.png)

### desktop-10-orders

![desktop-10-orders](desktop-10-orders.png)

### desktop-11-tracker-poison-dead-lettered

![desktop-11-tracker-poison-dead-lettered](desktop-11-tracker-poison-dead-lettered.png)

### mobile-01-shop

![mobile-01-shop](mobile-01-shop.png)

### mobile-02-checkout

![mobile-02-checkout](mobile-02-checkout.png)

### mobile-03-tracker-completed

![mobile-03-tracker-completed](mobile-03-tracker-completed.png)

### mobile-04-tracker-payment-declined

![mobile-04-tracker-payment-declined](mobile-04-tracker-payment-declined.png)

### mobile-05-orders

![mobile-05-orders](mobile-05-orders.png)

