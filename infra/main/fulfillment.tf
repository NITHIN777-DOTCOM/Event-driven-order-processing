# Per-item fulfillment (step 2.3): after the payment succeeds, the saga's inline Map "FulfillItems" picks each order
# line on its own (Lambda order-saga-fulfill-item). A line that can't be fulfilled is refunded on its own (DemoPay
# line refund, capped at the amount charged) and written off (Lambda order-saga-write-off-lines); the rest ships.
#
# Stock per product: stock (available) + held (checkout holds) + reserved (in flight) + sold (fulfilled lines)
# + writtenOff (unavailable lines) = what was seeded (invariant I5). A written-off unit never goes back on sale.

# Audit trail of every write-off: one item per (orderId, lineId). The write-off Lambda puts it with
# attribute_not_exists in the same transaction as the stock move, so it is also the idempotency record.
resource "aws_dynamodb_table" "write_offs" {
  name         = "${var.project_prefix}-write-offs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "orderId"
  range_key    = "lineId"

  deletion_protection_enabled = false

  attribute {
    name = "orderId"
    type = "S"
  }
  attribute {
    name = "lineId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-write-offs"
    Description = module.tags.description["write_offs_table"]
  }
}
