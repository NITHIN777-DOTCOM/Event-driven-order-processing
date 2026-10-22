# Dead-letter queue: messages that failed processing 3 times end up here for inspection/redrive.
resource "aws_sqs_queue" "orders_dlq" {
  name                      = "${var.project_prefix}-orders-dlq"
  message_retention_seconds = 14 * 24 * 60 * 60 # 14 days, the SQS maximum
  sqs_managed_sse_enabled   = true

  tags = {
    Name        = "${var.project_prefix}-orders-dlq"
    Description = "Dead-letter queue for orders that failed to start the workflow 3 times"
  }
}

# Main queue between the API and the workflow. It buffers spikes and decouples the API from the saga.
resource "aws_sqs_queue" "orders" {
  name                       = "${var.project_prefix}-orders-queue"
  visibility_timeout_seconds = 180 # 6x the 30s Lambda timeout (AWS guidance for Lambda consumers)
  message_retention_seconds  = 4 * 24 * 60 * 60
  receive_wait_time_seconds  = 20 # long polling
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.orders_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "${var.project_prefix}-orders-queue"
    Description = "New orders waiting for the saga workflow to start - DLQ after 3 receives"
  }
}

# Only the orders queue may use the DLQ as its dead-letter target.
resource "aws_sqs_queue_redrive_allow_policy" "orders_dlq" {
  queue_url = aws_sqs_queue.orders_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.orders.arn]
  })
}

# SQS -> start_workflow Lambda.
resource "aws_lambda_event_source_mapping" "orders_queue" {
  event_source_arn = aws_sqs_queue.orders.arn
  function_name    = aws_lambda_function.fn["start_workflow"].arn
  batch_size       = 10

  # The handler reports which messages failed, so only those are retried.
  function_response_types = ["ReportBatchItemFailures"]

  # Caps parallel consumers (fits the default 10-concurrency limit on new accounts).
  scaling_config {
    maximum_concurrency = 5
  }
}
