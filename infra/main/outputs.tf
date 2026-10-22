output "region" {
  value = var.region
}

output "api_url" {
  description = "Base URL of the HTTP API (POST /orders, GET /orders/{id})."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "orders_table" {
  value = aws_dynamodb_table.orders.name
}

output "inventory_table" {
  value = aws_dynamodb_table.inventory.name
}

output "queue_url" {
  value = aws_sqs_queue.orders.url
}

output "dlq_url" {
  value = aws_sqs_queue.orders_dlq.url
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.order_saga.arn
}

output "notifications_topic_arn" {
  value = aws_sns_topic.notifications.arn
}

output "ops_alerts_topic_arn" {
  value = aws_sns_topic.ops_alerts.arn
}

output "console_links" {
  description = "AWS Console pages to open during the demo."
  value = {
    state_machine   = "${local.console}/states/home?region=${var.region}#/statemachines/view/${aws_sfn_state_machine.order_saga.arn}"
    orders_queue    = "${local.console}/sqs/v3/home?region=${var.region}#/queues/${urlencode(aws_sqs_queue.orders.url)}"
    orders_dlq      = "${local.console}/sqs/v3/home?region=${var.region}#/queues/${urlencode(aws_sqs_queue.orders_dlq.url)}"
    orders_table    = "${local.console}/dynamodbv2/home?region=${var.region}#table?name=${aws_dynamodb_table.orders.name}"
    inventory_table = "${local.console}/dynamodbv2/home?region=${var.region}#table?name=${aws_dynamodb_table.inventory.name}"
    api             = "${local.console}/apigateway/main/api-detail?api=${aws_apigatewayv2_api.orders.id}&region=${var.region}"
    lambdas         = "${local.console}/lambda/home?region=${var.region}#/functions?fo=and&o0=%3A&v0=${var.project_prefix}-"
    sns_topics      = "${local.console}/sns/v3/home?region=${var.region}#/topics"
  }
}
