# Every Description tag value in this stack, validated at PLAN time by ../modules/tag_values (letters, digits,
# spaces and _ . : = + - @ only, max 256). A value AWS would reject fails `terraform plan`, before any resource is
# changed, instead of failing half-way through an apply. Resources use module.tags.description["<key>"];
# tests/unit/test_tag_values.py fails CI if a Description tag is written inline instead.
module "tags" {
  source = "../modules/tag_values"

  descriptions = {
    orders_table           = "Customer orders with current status and full statusHistory timeline"
    idempotency_table      = "Idempotency-Key to orderId map that prevents duplicate orders - expires after 24h via TTL"
    inventory_table        = "Product catalogue with price and stock counters - available - held - reserved - sold - writtenOff"
    wallets_table          = "DemoPay wallet balances - one per customer email - demo money only"
    wallet_txns_table      = "DemoPay ledger - DEBIT for payments - CREDIT for refunds - ADJUST for demo balance changes"
    frontend_bucket        = "Storefront static files - React build - served only through CloudFront"
    cdn                    = "CDN for the order-saga storefront - HTTPS only - OAC to a private S3 bucket"
    outbox_dlq             = "Stream records the outbox pipe could not deliver to the orders queue - their orders are stuck in PENDING"
    outbox_pipe            = "Transactional outbox - orders table stream to orders queue"
    payments_table         = "Payment intents - one per order - id PI-orderId - REQUESTED then SUCCEEDED or FAILED or TIMED_OUT then maybe REFUNDED"
    psp_transactions_table = "Mock provider DemoPay - one CHARGE per payment intent - REFUND records per intent or per order line - refunds capped at the charge"
    psp_dlq                = "Payment requests DemoPay gave up on - webhook unreachable or rejecting - money may have moved - investigate"
    psp_requests_queue     = "Payment requests to the mock provider DemoPay - DLQ after 5 receives"
    orders_dlq             = "Dead-letter queue for orders that failed to start the workflow 3 times"
    orders_queue           = "New orders waiting for the saga workflow to start - DLQ after 3 receives"
    state_machine          = "Order saga - reserve inventory - request payment and wait up to 120 s for the signed webhook - begin fulfillment then fulfil each line - refund and write off unavailable lines - customer cancel until fulfillment - complete or compensate - notify customer"
    notifications_topic    = "Customer order status emails published by the saga workflow"
    ops_alerts_topic       = "Operational alarms for the order saga - DLQ depth - errors - failed executions"
    holds_table            = "Checkout holds - stock set aside for one user for 10 minutes - ACTIVE then CONSUMED or RELEASED or EXPIRED - plus one USER pointer per user"
    holds_schedule_group   = "One-time schedules that expire checkout holds at their exact expiry time - created and deleted by order-saga-holds-api"
    client_ids_parameter   = "Cognito app client ids for the hold duration rule - storefront 600 s - automation client may ask for 30 to 600 s"
    write_offs_table       = "Audit of written-off order lines - damaged or missing after payment - one item per orderId and lineId - units never back on sale"
    audit_schedule_group   = "Schedules of the invariant auditor - hourly reconciliation of orders - payments - DemoPay ledger and stock - I1 to I9"
    fis_config_bucket      = "AWS FIS fault configurations for the order-saga Lambdas - written by running experiments only - expired after 1 day"
    fis_e1_errors          = "Chaos E1 - 30 percent invocation errors on the saga Lambdas for 10 min - stop condition order-saga-invariant-violation"
    fis_e2_delays          = "Chaos E2 - 25 s delay on half the DemoPay and webhook invocations for 10 min - pushes payments past the 120 s timeout"
    fis_e5_refund_outage   = "Chaos E5 - refund outage - all refund-payment invocations fail for 6 min - parked executions are redriven afterwards"
  }
}
