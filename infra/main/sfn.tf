# The "/aws/vendedlogs/" prefix is the AWS-recommended path for Step Functions logs (it avoids
# hitting the CloudWatch Logs resource-policy size limit).
resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.state_machine_name}"
  retention_in_days = local.log_retention_days
}

resource "aws_sfn_state_machine" "order_saga" {
  name     = local.state_machine_name
  type     = "STANDARD" # exactly-once steps, up to 1 year duration, full visual history in the console
  role_arn = aws_iam_role.sfn.arn

  definition = templatefile("${path.module}/../../statemachine/order_saga.asl.json", {
    reserve_inventory_function_arn = aws_lambda_function.fn["reserve_inventory"].arn
    request_payment_function_arn   = aws_lambda_function.fn["request_payment"].arn
    release_inventory_function_arn = aws_lambda_function.fn["release_inventory"].arn
    refund_payment_function_arn    = aws_lambda_function.fn["refund_payment"].arn
    orders_table_name              = aws_dynamodb_table.orders.name
    payments_table_name            = aws_dynamodb_table.payments.name
    notifications_topic_arn        = aws_sns_topic.notifications.arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true # X-Ray
  }

  tags = {
    Name        = local.state_machine_name
    Description = "Order saga - reserve inventory - request payment and wait for the signed webhook (120 s timeout) - complete or compensate - notify customer"
  }

  depends_on = [aws_iam_role_policy.sfn]
}
