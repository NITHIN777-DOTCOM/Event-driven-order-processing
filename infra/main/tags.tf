# Every Description tag value in this stack, validated at PLAN time by ../modules/tag_values (letters, digits,
# spaces and _ . : = + - @ only, max 256). A value AWS would reject fails `terraform plan`, before any resource is
# changed, instead of failing half-way through an apply. Resources use module.tags.description["<key>"];
# tests/unit/test_tag_values.py fails CI if a Description tag is written inline instead.
module "tags" {
  source = "../modules/tag_values"

  descriptions = {
    orders_table           = "Customer orders with current status and full statusHistory timeline"
    idempotency_table      = "Idempotency-Key to orderId map that prevents duplicate orders - expires after 24h via TTL"
    inventory_table        = "Product catalogue with price - available stock - reserved quantity"
    wallets_table          = "DemoPay wallet balances - one per customer email - demo money only"
    wallet_txns_table      = "DemoPay ledger - DEBIT for payments - CREDIT for refunds - ADJUST for demo balance changes"
    frontend_bucket        = "Storefront static files - React build - served only through CloudFront"
    cdn                    = "CDN for the order-saga storefront - HTTPS only - OAC to a private S3 bucket"
    outbox_dlq             = "Stream records the outbox pipe could not deliver to the orders queue - their orders are stuck in PENDING"
    outbox_pipe            = "Transactional outbox - orders table stream to orders queue"
    payments_table         = "Payment intents - one per order - id PI-orderId - REQUESTED then SUCCEEDED or FAILED or TIMED_OUT then maybe REFUNDED"
    psp_transactions_table = "Mock provider DemoPay - its charge and refund records - one CHARGE and at most one REFUND per payment intent"
    psp_dlq                = "Payment requests DemoPay gave up on - webhook unreachable or rejecting - money may have moved - investigate"
    psp_requests_queue     = "Payment requests to the mock provider DemoPay - DLQ after 5 receives"
    orders_dlq             = "Dead-letter queue for orders that failed to start the workflow 3 times"
    orders_queue           = "New orders waiting for the saga workflow to start - DLQ after 3 receives"
    state_machine          = "Order saga - reserve inventory - request payment and wait up to 120 s for the signed webhook - complete or compensate - notify customer"
    notifications_topic    = "Customer order status emails published by the saga workflow"
    ops_alerts_topic       = "Operational alarms for the order saga - DLQ depth - errors - failed executions"
  }
}
