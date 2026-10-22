resource "aws_apigatewayv2_api" "orders" {
  name          = "${var.project_prefix}-api"
  description   = "Order Saga public API - POST /orders to place an order and GET /orders/{id} to track it"
  protocol_type = "HTTP"

  cors_configuration {
    # Only the storefront (CloudFront) and the local Vite dev server may call the API from a browser.
    allow_origins = ["https://${aws_cloudfront_distribution.frontend.domain_name}", "http://localhost:5173"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type", "idempotency-key"]
    # Lets browser JavaScript read the idempotency response headers.
    expose_headers = ["idempotency-key", "idempotent-replayed"]
    max_age        = 300
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
  # route name => { route key, Lambda (key in local.lambda_functions) }. Several routes may share one Lambda.
  api_routes = {
    create_order  = { route = "POST /orders", fn = "create_order" }
    get_order     = { route = "GET /orders/{id}", fn = "get_order" }
    list_orders   = { route = "GET /orders", fn = "list_orders" }
    list_products = { route = "GET /products", fn = "list_products" }
    wallet_get    = { route = "GET /wallet", fn = "wallet_api" }
    wallet_reset  = { route = "POST /wallet/reset", fn = "wallet_api" }
  }
  api_functions = toset([for r in local.api_routes : r.fn])
}

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = local.api_functions

  api_id                 = aws_apigatewayv2_api.orders.id
  description            = "Proxy to Lambda ${local.lambda_names[each.key]}"
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn[each.key].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "orders" {
  for_each = local.api_routes

  api_id    = aws_apigatewayv2_api.orders.id
  route_key = each.value.route
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.value.fn].id}"
}

# Allow only this API to invoke the API Lambdas.
resource "aws_lambda_permission" "api" {
  for_each = local.api_functions

  statement_id  = "AllowInvokeFromOrderSagaApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.orders.execution_arn}/*/*"
}
