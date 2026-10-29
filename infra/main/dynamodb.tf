# Orders: one item per order. Only the key is declared; DynamoDB is schemaless otherwise.
# Stored attributes: orderId, customerName, customerEmail, items[{productId, name, quantity, unitPrice}],
# totalAmount, currency (INR), status, statusHistory[{status, timestamp, detail}], simulate,
# createdAt, updatedAt, executionArn, paymentId, gsi1pk/gsi1sk (see below).
resource "aws_dynamodb_table" "orders" {
  name         = "${var.project_prefix}-orders"
  billing_mode = "PAY_PER_REQUEST" # on-demand: $0 when idle
  hash_key     = "orderId"

  deletion_protection_enabled = false

  # Transactional outbox source (see outbox.tf): every new order row reaches the queue via this stream.
  # NEW_IMAGE is enough: the pipe only needs the new row. Never disable it: a re-enabled stream gets a
  # new ARN, and the pipe would have to be re-created.
  stream_enabled   = true
  stream_view_type = "NEW_IMAGE"

  attribute {
    name = "orderId"
    type = "S"
  }
  attribute {
    name = "gsi1pk"
    type = "S"
  }
  attribute {
    name = "gsi1sk"
    type = "S"
  }

  # "Recent orders" index for GET /orders: gsi1pk = "ORDER" (constant), gsi1sk = createdAt.
  # One Query with ScanIndexForward=false returns the newest N orders without a table scan.
  # A single constant partition key is fine at demo scale; at high volume you'd shard it (e.g. ORDER#<day>).
  global_secondary_index {
    name               = "gsi1"
    hash_key           = "gsi1pk"
    range_key          = "gsi1sk"
    projection_type    = "INCLUDE"
    non_key_attributes = ["createdAt", "status", "simulate", "totalAmount", "currency", "customerName", "deadLettered"]
  }

  # Off to keep cost at zero for a course project; encryption at rest uses the AWS-owned key (default).
  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-orders"
    Description = module.tags.description["orders_table"]
  }
}

# Idempotency keys: one item per Idempotency-Key header -> the orderId it created.
# Written in the SAME transaction as the order. DynamoDB TTL deletes records after 24 h, at no cost.
resource "aws_dynamodb_table" "idempotency" {
  name         = "${var.project_prefix}-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotencyKey"

  deletion_protection_enabled = false

  attribute {
    name = "idempotencyKey"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt" # epoch seconds
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-idempotency"
    Description = module.tags.description["idempotency_table"]
  }
}

# Inventory: one item per product. Fields: productId, name, price, stock, reserved.
resource "aws_dynamodb_table" "inventory" {
  name         = "${var.project_prefix}-inventory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "productId"

  deletion_protection_enabled = false

  attribute {
    name = "productId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-inventory"
    Description = module.tags.description["inventory_table"]
  }
}

# DemoPay wallets: one item per customer email (walletId = lower-cased email). Created lazily
# with ₹10,00,000 on first use. Only the balance lives here; the history is in wallet_txns.
resource "aws_dynamodb_table" "wallets" {
  name         = "${var.project_prefix}-wallets"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "walletId"

  deletion_protection_enabled = false

  attribute {
    name = "walletId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-wallets"
    Description = module.tags.description["wallets_table"]
  }
}

# DemoPay ledger: one item per balance change. A separate table rather than a list on the wallet item,
# because history grows without limit (items cap at 400 KB) and "latest 20, newest first" is a single
# Query on (walletId, txnId DESC). txnId = "<ISO timestamp>#<random>", so it sorts by time.
resource "aws_dynamodb_table" "wallet_txns" {
  name         = "${var.project_prefix}-wallet-txns"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "walletId"
  range_key    = "txnId"

  deletion_protection_enabled = false

  attribute {
    name = "walletId"
    type = "S"
  }
  attribute {
    name = "txnId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-wallet-txns"
    Description = module.tags.description["wallet_txns_table"]
  }
}
