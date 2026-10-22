resource "aws_apigatewayv2_api" "orders" {
  name          = "${var.project_prefix}-api"
  description   = "Order Saga public API - POST /orders to place an order and GET /orders/{id} to track it"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"] # tightened to the CloudFront domain in Phase 4
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type", "idempotency-key"]
    max_age       = 300
  }
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.project_prefix}-api"
  retention_in_days = local.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.orders.id
  name        = "$default"
  auto_deploy = true

  # Cost/abuse guard: caps the request rate across all routes.
  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      sourceIp         = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      path             = "$context.path"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      latencyMs        = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

locals {
  api_routes = {
    create_order = "POST /orders"
    get_order    = "GET /orders/{id}"
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = local.api_routes

  api_id                 = aws_apigatewayv2_api.orders.id
  description            = "${each.value} -> Lambda ${local.lambda_names[each.key]}"
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn[each.key].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "orders" {
  for_each = local.api_routes

  api_id    = aws_apigatewayv2_api.orders.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.key].id}"
}

# Allow only this API to invoke the two API Lambdas.
resource "aws_lambda_permission" "api" {
  for_each = local.api_routes

  statement_id  = "AllowInvokeFromOrderSagaApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.orders.execution_arn}/*/*"
}
