# =============================================================================
# Async payments (step 2.1): the saga asks a payment provider to charge, PAUSES, and resumes on its webhook.
#
#   Step Functions RequestPayment (lambda:invoke.waitForTaskToken, 120 s)
#     -> request_payment: intent in order-saga-payments (task token stored), message to order-saga-psp-requests
#   order-saga-psp-requests (2-5 s delay) -> payment_provider ("DemoPay", a mock external PSP)
#     -> debits the wallet once per intent (its own records: order-saga-psp-transactions)
#     -> POST /webhooks/payment, HMAC-signed with the secret in SSM /order-saga/psp/webhook-secret
#   payment_webhook -> verifies the signature -> SendTaskSuccess / SendTaskFailure -> the saga continues
#
# The task token never leaves our side: DemoPay only knows the payment intent id.
# =============================================================================

locals {
  # Created by scripts/create_webhook_secret.py (run by Deploy), so the value is never in Terraform state.
  webhook_secret_parameter = "/${var.project_prefix}/psp/webhook-secret"
  webhook_secret_arn       = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${local.webhook_secret_parameter}"
  webhook_url              = "${aws_apigatewayv2_api.orders.api_endpoint}/webhooks/payment"

  # Built as a string (not taken from aws_lambda_function.fn or local.lambda_names): functions in the same
  # for_each that call DemoPay's refund API would otherwise reference their own resource (a cycle).
  payment_provider_name = "${var.project_prefix}-payment-provider"
  payment_provider_arn  = "arn:aws:lambda:${var.region}:${local.account_id}:function:${local.payment_provider_name}"

  payment_provider_timeout = 20 # seconds: a debit plus at most two webhook calls of <= 8 s each (normally < 1 s in total)
  psp_max_receive_count    = 5  # DemoPay retries a callback our webhook didn't accept 4 more times, then gives up

  # Lambdas that log an intent's status changes (field intentStatus), for the dashboard's payments row.
  payment_log_groups = [for key in ["payment_webhook", "refund_payment"] : aws_cloudwatch_log_group.lambda[key].name]
}

# OUR record of each payment: one intent per order (paymentIntentId = PI-<orderId>), with its status and the
# Step Functions task token. No GSI on orderId: the id is derived from the orderId, so a GetItem finds it.
resource "aws_dynamodb_table" "payments" {
  name         = "${var.project_prefix}-payments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "paymentIntentId"

  deletion_protection_enabled = false

  attribute {
    name = "paymentIntentId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-payments"
    Description = "Payment intents - one per order (PI-orderId) - REQUESTED then SUCCEEDED or FAILED or TIMED_OUT then maybe REFUNDED"
  }
}

# DemoPay's OWN records (the provider's side, not ours): CHARGE#<intent> and REFUND#<intent>. Written in the same
# transaction as the wallet change, conditional on not existing, so each intent is charged and refunded at most once.
resource "aws_dynamodb_table" "psp_transactions" {
  name         = "${var.project_prefix}-psp-transactions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pspTxnId"

  deletion_protection_enabled = false

  attribute {
    name = "pspTxnId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-psp-transactions"
    Description = "Mock provider DemoPay - its charge and refund records - one CHARGE and at most one REFUND per payment intent"
  }
}

# Requests DemoPay could not complete: its callback to our webhook kept failing (5 receives).
resource "aws_sqs_queue" "psp_dlq" {
  name                      = "${var.project_prefix}-psp-dlq"
  message_retention_seconds = 14 * 24 * 60 * 60
  sqs_managed_sse_enabled   = true

  tags = {
    Name        = "${var.project_prefix}-psp-dlq"
    Description = "Payment requests DemoPay gave up on - webhook unreachable or rejecting - money may have moved - investigate"
  }
}

# Our payment requests to DemoPay. Each message is delayed 2-5 s by the sender (a provider's processing time).
resource "aws_sqs_queue" "psp_requests" {
  name                       = "${var.project_prefix}-psp-requests"
  visibility_timeout_seconds = 6 * local.payment_provider_timeout # AWS guidance for Lambda consumers: >= 6x timeout
  message_retention_seconds  = 4 * 24 * 60 * 60
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.psp_dlq.arn
    maxReceiveCount     = local.psp_max_receive_count
  })

  tags = {
    Name        = "${var.project_prefix}-psp-requests"
    Description = "Payment requests to the mock provider DemoPay - DLQ after 5 receives"
  }
}

resource "aws_sqs_queue_redrive_allow_policy" "psp_dlq" {
  queue_url = aws_sqs_queue.psp_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.psp_requests.arn]
  })
}

resource "aws_lambda_event_source_mapping" "psp_requests" {
  event_source_arn        = aws_sqs_queue.psp_requests.arn
  function_name           = aws_lambda_function.fn["payment_provider"].arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 2 # the SQS minimum; keeps the account's small concurrency pool free for the API
  }
}
