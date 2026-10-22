output "region" {
  value = var.region
}

output "api_url" {
  description = "Base URL of the HTTP API (POST /orders, GET /orders/{id})."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "frontend_url" {
  description = "The storefront (CloudFront, HTTPS)."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "frontend_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}

output "orders_table" {
  value = aws_dynamodb_table.orders.name
}

output "inventory_table" {
  value = aws_dynamodb_table.inventory.name
}

output "idempotency_table" {
  value = aws_dynamodb_table.idempotency.name
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
    idempotency     = "${local.console}/dynamodbv2/home?region=${var.region}#table?name=${aws_dynamodb_table.idempotency.name}"
    api             = "${local.console}/apigateway/main/api-detail?api=${aws_apigatewayv2_api.orders.id}&region=${var.region}"
    lambdas         = "${local.console}/lambda/home?region=${var.region}#/functions?fo=and&o0=%3A&v0=${var.project_prefix}-"
    sns_topics      = "${local.console}/sns/v3/home?region=${var.region}#/topics"
    dashboard       = "${local.console}/cloudwatch/home?region=${var.region}#dashboards/dashboard/${aws_cloudwatch_dashboard.main.dashboard_name}"
    alarms          = "${local.console}/cloudwatch/home?region=${var.region}#alarmsV2:?search=${var.project_prefix}"
    xray_map        = "${local.console}/cloudwatch/home?region=${var.region}#xray:service-map/map"
    xray_traces     = "${local.console}/cloudwatch/home?region=${var.region}#xray:traces/query"
    saved_queries   = "${local.console}/cloudwatch/home?region=${var.region}#logsV2:logs-insights"
  }
}
