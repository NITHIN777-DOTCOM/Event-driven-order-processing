# Orders: one item per order. Only the key is declared; DynamoDB is schemaless otherwise.
# Stored attributes: orderId, customerName, customerEmail, items[{productId, name, quantity, unitPrice}],
# totalAmount, currency (INR), status, statusHistory[{status, timestamp, detail}], simulate,
# createdAt, updatedAt, executionArn, paymentId.
resource "aws_dynamodb_table" "orders" {
  name         = "${var.project_prefix}-orders"
  billing_mode = "PAY_PER_REQUEST" # on-demand: $0 when idle
  hash_key     = "orderId"

  deletion_protection_enabled = false

  attribute {
    name = "orderId"
    type = "S"
  }

  # Off to keep cost at zero for a course project; encryption at rest uses the AWS-owned key (default).
  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-orders"
    Description = "Customer orders with current status and full statusHistory timeline"
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
    Description = "Product catalogue with price - available stock - reserved quantity"
  }
}
