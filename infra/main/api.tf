resource "aws_apigatewayv2_api" "orders" {
  name          = "${var.project_prefix}-api"
  description   = "Order Saga public API - POST /orders to place an order and GET /orders/{id} to track it"
  protocol_type = "HTTP"

  cors_configuration {
    # Only the storefront (CloudFront) and the local Vite dev server may call the API from a browser.
    allow_origins = ["https://${aws_cloudfront_distribution.frontend.domain_name}", "http://localhost:5173"]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]                 # DELETE: release a checkout hold
    allow_headers = ["authorization", "content-type", "idempotency-key"] # authorization: the Cognito access token
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
  # route name => { route key, Lambda (key in local.lambda_functions), needs a signed-in user? }.
  # Several routes may share one Lambda. No JWT on: the catalogue (public) and the payment webhook (HMAC-signed).
  api_routes = {
    create_order  = { route = "POST /orders", fn = "create_order", auth = true }
    get_order     = { route = "GET /orders/{id}", fn = "get_order", auth = true }
    list_orders   = { route = "GET /orders", fn = "list_orders", auth = true }
    list_products = { route = "GET /products", fn = "list_products", auth = false }
    wallet_get    = { route = "GET /wallet", fn = "wallet_api", auth = true }
    wallet_reset  = { route = "POST /wallet/reset", fn = "wallet_api", auth = true }
    hold_create   = { route = "POST /holds", fn = "holds_api", auth = true }
    hold_current  = { route = "GET /holds/current", fn = "holds_api", auth = true }
    hold_release  = { route = "DELETE /holds/{holdId}", fn = "holds_api", auth = true }
    # Server-to-server from the payment provider: no user, so no JWT. The HMAC signature is the authentication.
    payment_webhook = { route = "POST /webhooks/payment", fn = "payment_webhook", auth = false }
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

# Validates the Cognito JWT on protected routes BEFORE any Lambda runs (no Lambda authorizer to write or pay for):
# signature (the pool's public keys, fetched and cached by API Gateway), issuer = our user pool, audience = one of
# our two app clients, and expiry. A missing, tampered or expired token gets 401 from API Gateway itself.
# "Audience" works for both Cognito token types: an ID token names its app client in "aud", an access token
# in "client_id" (it has no "aud"), and HTTP API JWT authorizers check whichever is present against this list.
# The Lambdas then read the caller only from the verified claims (src/common/auth.py).
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.orders.id
  name             = "${var.project_prefix}-cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
    audience = [aws_cognito_user_pool_client.spa.id, aws_cognito_user_pool_client.automation.id]
  }
}

resource "aws_apigatewayv2_route" "orders" {
  for_each = local.api_routes

  api_id             = aws_apigatewayv2_api.orders.id
  route_key          = each.value.route
  target             = "integrations/${aws_apigatewayv2_integration.lambda[each.value.fn].id}"
  authorization_type = each.value.auth ? "JWT" : "NONE"
  authorizer_id      = each.value.auth ? aws_apigatewayv2_authorizer.cognito.id : null
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
