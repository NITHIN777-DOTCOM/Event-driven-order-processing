# =============================================================================
# Monitoring: one CloudWatch dashboard, alarms -> SNS ops-alerts, saved Logs Insights queries.
#
# Alarm design note: a compensated order (payment declined, out of stock) ends in a Fail state,
# and request_payment raises PaymentTransientError for payment_flaky. So "ExecutionsFailed > 0" and those Lambda errors
# are normal BUSINESS outcomes, not system faults. We alarm on:
#   - system faults:   DLQ not empty, start_workflow crashes, API 5xx, executions timed out/aborted,
#                      queue backlog, outbox pipe failures / outbox DLQ not empty
#   - business health: the failure RATE (only with enough traffic to be meaningful)
# =============================================================================

locals {
  sfn_arn       = aws_sfn_state_machine.order_saga.arn
  api_id        = aws_apigatewayv2_api.orders.id
  orders_queue  = aws_sqs_queue.orders.name
  dlq           = aws_sqs_queue.orders_dlq.name
  outbox_dlq    = aws_sqs_queue.outbox_dlq.name
  outbox_pipe   = aws_pipes_pipe.outbox.name
  dynamo_tables = [aws_dynamodb_table.orders.name, aws_dynamodb_table.inventory.name]

  # Log groups the saved queries search across.
  lambda_log_groups = [for group in aws_cloudwatch_log_group.lambda : group.name]
  all_log_groups    = concat(local.lambda_log_groups, [aws_cloudwatch_log_group.sfn.name])

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
}

# -----------------------------------------------------------------------------
# Alarms (15 in all since step 3.2, the 2 audit alarms in audit.tf; standard alarms cost $0.10 per alarm metric per
# month beyond the 10 free: a few dollars at most)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "outbox_dlq_not_empty" {
  alarm_name        = "${var.project_prefix}-outbox-dlq-not-empty"
  alarm_description = "CRITICAL: the outbox pipe gave up on a new-order stream record (5 retries or 1 h old) and put its details in ${local.outbox_dlq}. That order is stuck in PENDING. Read the DLQ message, find the order(s), fix the cause, then send {\"orderId\": ...} to ${local.orders_queue} (start_workflow is idempotent)."

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = local.outbox_dlq }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "outbox_pipe_failures" {
  alarm_name        = "${var.project_prefix}-outbox-pipe-failures"
  alarm_description = "The outbox pipe ${local.outbox_pipe} failed to deliver new orders to ${local.orders_queue} (a permission, throttling or target error). It retries; persistent failures end in ${local.outbox_dlq}. Check the pipe's state and StateReason in the EventBridge Pipes console."

  namespace           = "AWS/EventBridge/Pipes"
  metric_name         = "ExecutionFailed"
  dimensions          = { PipeName = local.outbox_pipe }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name        = "${var.project_prefix}-dlq-not-empty"
  alarm_description = "CRITICAL: an order message is in ${local.dlq}. It failed 3 times and its order is stuck in PENDING. Inspect the message in the SQS console, fix the cause, then redrive it to ${local.orders_queue}."

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = local.dlq }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "start_workflow_errors" {
  alarm_name        = "${var.project_prefix}-start-workflow-errors"
  alarm_description = "The SQS consumer order-saga-start-workflow crashed (an unhandled error or timeout), so orders aren't reaching Step Functions. Poison messages are handled per message and are covered by the DLQ alarm instead. Check its CloudWatch logs."

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.fn["start_workflow"].function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name        = "${var.project_prefix}-api-5xx"
  alarm_description = "order-saga-api returned server errors (5xx): customers can't place or track orders. Check the API access logs and the create_order / get_order Lambda logs."

  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = local.api_id }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Business alarm: more than half of the orders failing is abnormal, even though each failure on
# its own is handled correctly by compensation. IF() suppresses it at low volume (< 5 orders in
# 15 min), where one or two declines would otherwise look like a 50%+ failure rate.
resource "aws_cloudwatch_metric_alarm" "high_order_failure_rate" {
  alarm_name        = "${var.project_prefix}-high-order-failure-rate"
  alarm_description = "BUSINESS: more than 50% of the orders started in the last 15 min failed (evaluated only when at least 5 orders started). Possible causes: payment provider outage, empty inventory. Run the 'Failed orders by reason' saved query."

  comparison_operator = "GreaterThanThreshold"
  threshold           = 0.5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "failure_rate"
    expression  = "IF(FILL(started, 0) >= 5, FILL(failed, 0) / FILL(started, 0), 0)"
    label       = "Order failure rate (0-1, only when >= 5 orders started)"
    return_data = true
  }

  metric_query {
    id = "failed"
    metric {
      namespace   = "AWS/States"
      metric_name = "ExecutionsFailed"
      dimensions  = { StateMachineArn = local.sfn_arn }
      stat        = "Sum"
      period      = 900
    }
  }

  metric_query {
    id = "started"
    metric {
      namespace   = "AWS/States"
      metric_name = "ExecutionsStarted"
      dimensions  = { StateMachineArn = local.sfn_arn }
      stat        = "Sum"
      period      = 900
    }
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "sfn_timeouts_aborts" {
  alarm_name        = "${var.project_prefix}-sfn-timeouts-aborts"
  alarm_description = "A saga execution timed out or was aborted, so the order may be stuck mid-saga, possibly with stock reserved. This is a SYSTEM fault: business failures end in the OrderFailed state instead. Check the execution in the Step Functions console."

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "stuck"
    expression  = "FILL(timed_out, 0) + FILL(aborted, 0)"
    label       = "Executions timed out + aborted"
    return_data = true
  }

  metric_query {
    id = "timed_out"
    metric {
      namespace   = "AWS/States"
      metric_name = "ExecutionsTimedOut"
      dimensions  = { StateMachineArn = local.sfn_arn }
      stat        = "Sum"
      period      = 300
    }
  }

  metric_query {
    id = "aborted"
    metric {
      namespace   = "AWS/States"
      metric_name = "ExecutionsAborted"
      dimensions  = { StateMachineArn = local.sfn_arn }
      stat        = "Sum"
      period      = 300
    }
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "queue_backlog" {
  alarm_name        = "${var.project_prefix}-queue-backlog"
  alarm_description = "The oldest message in ${local.orders_queue} has waited more than 5 min: orders aren't being picked up. Check whether the event source mapping is enabled and whether start_workflow is throttled or failing."

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = local.orders_queue }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 300
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

locals {
  all_alarm_arns = [
    aws_cloudwatch_metric_alarm.dlq_not_empty.arn,
    aws_cloudwatch_metric_alarm.start_workflow_errors.arn,
    aws_cloudwatch_metric_alarm.api_5xx.arn,
    aws_cloudwatch_metric_alarm.high_order_failure_rate.arn,
    aws_cloudwatch_metric_alarm.sfn_timeouts_aborts.arn,
    aws_cloudwatch_metric_alarm.queue_backlog.arn,
    aws_cloudwatch_metric_alarm.outbox_pipe_failures.arn,
    aws_cloudwatch_metric_alarm.outbox_dlq_not_empty.arn,
    aws_cloudwatch_metric_alarm.psp_dlq_not_empty.arn,
    aws_cloudwatch_metric_alarm.webhook_signature_failures.arn,
    aws_cloudwatch_metric_alarm.hold_expiry_errors.arn,
    aws_cloudwatch_metric_alarm.refund_or_write_off_errors.arn,
    aws_cloudwatch_metric_alarm.cancellation_errors.arn,
  ]
}

# -----------------------------------------------------------------------------
# Checkout holds (step 2.2)
# -----------------------------------------------------------------------------
# If expiry fails, held stock is not returned until the next read of that hold (lazy expiry) or a retry.
resource "aws_cloudwatch_metric_alarm" "hold_expiry_errors" {
  alarm_name        = "${var.project_prefix}-hold-expiry-errors"
  alarm_description = "Lambda ${local.hold_expiry_function_name} failed: a checkout hold may still be holding stock after its expiry. Check its logs (holdId on every line); Lambda retries twice and Scheduler retries delivery for up to 1 h. The hold is also expired lazily the next time it is read."

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = local.hold_expiry_function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# One count per hold transition (holdEvent = created / released / expired, and consumed from reserve_inventory),
# as metric OrderSaga/HoldEvents with the transition as its Event dimension.
resource "aws_cloudwatch_log_metric_filter" "hold_events" {
  for_each = toset(["holds_api", "hold_expiry", "reserve_inventory"])

  name           = "${var.project_prefix}-hold-events-${replace(each.key, "_", "-")}"
  log_group_name = aws_cloudwatch_log_group.lambda[each.key].name
  pattern        = "{ $.holdEvent = * }"

  metric_transformation {
    name       = "HoldEvents"
    namespace  = "OrderSaga"
    value      = "1"
    dimensions = { Event = "$.holdEvent" }
  }
}

# How late the schedule fired: now - expiresAt, in ms (EventBridge Scheduler's precision).
resource "aws_cloudwatch_log_metric_filter" "hold_expiry_lag" {
  name           = "${var.project_prefix}-hold-expiry-lag"
  log_group_name = aws_cloudwatch_log_group.lambda["hold_expiry"].name
  pattern        = "{ $.holdEvent = \"expired\" }"

  metric_transformation {
    name      = "HoldExpiryLag"
    namespace = "OrderSaga"
    value     = "$.expiryLagMs"
    unit      = "Milliseconds"
  }
}

# -----------------------------------------------------------------------------
# Per-item fulfillment and partial refunds (step 2.3)
# -----------------------------------------------------------------------------
# PartialRefund and WriteOffLines retry, then FAIL the execution on purpose (it can be redriven from that state,
# and both steps are idempotent per line). Without this alarm that failure would be silent: the customer is owed
# money (or the stock books are wrong) and the order stays at PAYMENT_CAPTURED. It also covers the full-refund
# compensation, whose Catch otherwise carries on quietly after its retries.
resource "aws_cloudwatch_metric_alarm" "refund_or_write_off_errors" {
  alarm_name          = "${var.project_prefix}-refund-or-write-off-errors"
  alarm_description   = "A refund (full or per line) or a write-off failed: a customer may be owed money, or written-off stock may be miscounted. Check the refund-payment and write-off-lines logs (orderId, lineId on every line), fix the cause, then REDRIVE the failed execution in Step Functions: both steps are idempotent per line."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "errors"
    expression  = "refund + writeoff"
    label       = "Refund and write-off Lambda errors"
    return_data = true
  }
  metric_query {
    id = "refund"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = local.lambda_names["refund_payment"] }
      stat        = "Sum"
      period      = 300
    }
  }
  metric_query {
    id = "writeoff"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = local.lambda_names["write_off_lines"] }
      stat        = "Sum"
      period      = 300
    }
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# One count per fulfillment event: fulfilled / unavailable (fulfill_item), written_off (write_off_lines),
# line_refunded / partially_fulfilled / all_unavailable (refund_payment). Metric OrderSaga/FulfillmentEvents.
resource "aws_cloudwatch_log_metric_filter" "fulfillment_events" {
  for_each = toset(["fulfill_item", "write_off_lines", "refund_payment"])

  name           = "${var.project_prefix}-fulfillment-events-${replace(each.key, "_", "-")}"
  log_group_name = aws_cloudwatch_log_group.lambda[each.key].name
  pattern        = "{ $.fulfillmentEvent = * }"

  metric_transformation {
    name       = "FulfillmentEvents"
    namespace  = "OrderSaga"
    value      = "1"
    dimensions = { Event = "$.fulfillmentEvent" }
  }
}

resource "aws_cloudwatch_log_metric_filter" "written_off_units" {
  name           = "${var.project_prefix}-written-off-units"
  log_group_name = aws_cloudwatch_log_group.lambda["write_off_lines"].name
  pattern        = "{ $.fulfillmentEvent = \"written_off\" }"

  metric_transformation {
    name      = "WrittenOffUnits"
    namespace = "OrderSaga"
    value     = "$.quantity"
  }
}

resource "aws_cloudwatch_log_metric_filter" "line_refund_amount" {
  name           = "${var.project_prefix}-line-refund-amount"
  log_group_name = aws_cloudwatch_log_group.lambda["refund_payment"].name
  pattern        = "{ $.fulfillmentEvent = \"line_refunded\" }"

  metric_transformation {
    name      = "LineRefundAmount"
    namespace = "OrderSaga"
    value     = "$.amount"
  }
}

# -----------------------------------------------------------------------------
# Customer cancellation (step 2.4)
# -----------------------------------------------------------------------------
# The cancel branch's steps retry and then FAIL the execution on purpose (redrive once fixed; every step is
# idempotent). A failure there leaves a cancelled order with its stock still reserved or its money not yet back,
# so it must never be silent. RefundWhatIsLeft is refund-payment, already covered by refund_or_write_off_errors.
resource "aws_cloudwatch_metric_alarm" "cancellation_errors" {
  alarm_name          = "${var.project_prefix}-cancellation-errors"
  alarm_description   = "The cancel API, BeginFulfillment or ReleaseInventory failed: a cancelled order may still hold reserved stock or be stuck in CANCEL_REQUESTED. Check the cancel-order, begin-fulfillment and release-inventory logs (orderId on every line), fix the cause, then REDRIVE the failed execution in Step Functions: every cancel step is idempotent."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "errors"
    expression  = "cancel + begin + release"
    label       = "Cancellation path Lambda errors"
    return_data = true
  }
  dynamic "metric_query" {
    for_each = { cancel = "cancel_order", begin = "begin_fulfillment", release = "release_inventory" }
    content {
      id = metric_query.key
      metric {
        namespace   = "AWS/Lambda"
        metric_name = "Errors"
        dimensions  = { FunctionName = local.lambda_names[metric_query.value] }
        stat        = "Sum"
        period      = 300
      }
    }
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# One count per cancel event, metric OrderSaga/CancelEvents with the event as its Event dimension:
#   cancel-order:       accepted / rejected_too_late / not_cancellable / not_cancellable_yet / repeated
#   refund-payment:     refunded / nothing_charged (the cancel branch's RefundWhatIsLeft)
#   payment-webhook:    late_charge_refunded (a charge that slipped past the cancel, given back)
#   begin-fulfillment:  fulfillment_started (the moment cancelling closes)
resource "aws_cloudwatch_log_metric_filter" "cancel_events" {
  for_each = toset(["cancel_order", "refund_payment", "payment_webhook", "begin_fulfillment"])

  name           = "${var.project_prefix}-cancel-events-${replace(each.key, "_", "-")}"
  log_group_name = aws_cloudwatch_log_group.lambda[each.key].name
  pattern        = "{ $.cancelEvent = * }"

  metric_transformation {
    name       = "CancelEvents"
    namespace  = "OrderSaga"
    value      = "1"
    dimensions = { Event = "$.cancelEvent" }
  }
}

# -----------------------------------------------------------------------------
# Async payments (step 2.1)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "psp_dlq_not_empty" {
  alarm_name        = "${var.project_prefix}-psp-dlq-not-empty"
  alarm_description = "CRITICAL: DemoPay gave up on a payment request (its callback to POST /webhooks/payment failed 5 times). Money may have moved without the saga knowing. Check the payment_webhook logs, fix the webhook, then redrive ${aws_sqs_queue.psp_dlq.name} to ${aws_sqs_queue.psp_requests.name}: the provider replays the same outcome and a late success is refunded automatically."

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.psp_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# One count per webhook request rejected for a missing, wrong or stale signature (the handler logs
# event = "webhook_signature_rejected", never the signature itself).
resource "aws_cloudwatch_log_metric_filter" "webhook_signature_failures" {
  name           = "${var.project_prefix}-webhook-signature-failures"
  log_group_name = aws_cloudwatch_log_group.lambda["payment_webhook"].name
  pattern        = "{ $.event = \"webhook_signature_rejected\" }"

  metric_transformation {
    name      = "WebhookSignatureFailures"
    namespace = "OrderSaga"
    value     = "1"
    unit      = "Count"
  }
}

# Time from our payment request to the provider's callback (DemoPay's "processing time"), per callback.
resource "aws_cloudwatch_log_metric_filter" "webhook_callback_delay" {
  name           = "${var.project_prefix}-webhook-callback-delay"
  log_group_name = aws_cloudwatch_log_group.lambda["payment_webhook"].name
  pattern        = "{ ($.message = \"Webhook processed\") && ($.callbackDelayMs >= 0) }"

  metric_transformation {
    name      = "WebhookCallbackDelay"
    namespace = "OrderSaga"
    value     = "$.callbackDelayMs"
    unit      = "Milliseconds"
  }
}

resource "aws_cloudwatch_metric_alarm" "webhook_signature_failures" {
  alarm_name        = "${var.project_prefix}-webhook-signature-failures"
  alarm_description = "SECURITY: POST /webhooks/payment rejected requests with a missing, forged or stale HMAC signature. A few during e2e runs are expected (they test exactly this); otherwise someone may be probing the endpoint. Check sourceIp in the payment_webhook logs."

  namespace           = "OrderSaga"
  metric_name         = "WebhookSignatureFailures"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions

  depends_on = [aws_cloudwatch_log_metric_filter.webhook_signature_failures]
}

# -----------------------------------------------------------------------------
# Dashboard: 9 rows on a 24-column grid, top to bottom following the order's path
# -----------------------------------------------------------------------------
locals {
  # One Lambda graph per metric, with every function on it.
  lambda_widgets = [
    for index, spec in [
      { title = "Lambda invocations", metric = "Invocations", stat = "Sum" },
      { title = "Lambda errors (request_payment errors include simulated payment_flaky retries)", metric = "Errors", stat = "Sum" },
      { title = "Lambda duration p95 (ms)", metric = "Duration", stat = "p95" },
      { title = "Lambda throttles", metric = "Throttles", stat = "Sum" },
      ] : {
      type   = "metric"
      x      = index * 6
      y      = 29
      width  = 6
      height = 6
      properties = {
        title   = spec.title
        region  = var.region
        view    = "timeSeries"
        stat    = spec.stat
        period  = 60
        metrics = [for key, name in local.lambda_names : ["AWS/Lambda", spec.metric, "FunctionName", name, { label = key }]]
      }
    }
  ]

  dynamodb_widgets = [
    for index, spec in [
      { title = "DynamoDB consumed read capacity units", metric = "ConsumedReadCapacityUnits" },
      { title = "DynamoDB consumed write capacity units", metric = "ConsumedWriteCapacityUnits" },
      ] : {
      type   = "metric"
      x      = index * 8
      y      = 35
      width  = 8
      height = 6
      properties = {
        title   = spec.title
        region  = var.region
        view    = "timeSeries"
        stat    = "Sum"
        period  = 60
        metrics = [for table in local.dynamo_tables : ["AWS/DynamoDB", spec.metric, "TableName", table, { label = table }]]
      }
    }
  ]

  # ---- Row 8: async payments (step 2.1) ----
  payment_log_sources = join(" | ", [for name in local.payment_log_groups : "SOURCE '${name}'"])
  payment_widgets = [
    {
      type   = "log"
      x      = 0
      y      = 47
      width  = 6
      height = 6
      properties = {
        title  = "Payment intents: transitions by status (selected time range)"
        region = var.region
        view   = "bar"
        query  = "${local.payment_log_sources} | filter ispresent(intentStatus) | stats count(*) as transitions by intentStatus"
      }
    },
    {
      type   = "metric"
      x      = 6
      y      = 47
      width  = 6
      height = 6
      properties = {
        title  = "Webhook latency: payment request -> provider callback (ms)"
        region = var.region
        view   = "timeSeries"
        period = 60
        metrics = [
          ["OrderSaga", "WebhookCallbackDelay", { stat = "p50", label = "p50" }],
          ["OrderSaga", "WebhookCallbackDelay", { stat = "p95", label = "p95" }],
          ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.fn["payment_webhook"].function_name, { stat = "p95", label = "webhook handler p95", yAxis = "right" }],
        ]
      }
    },
    {
      type   = "log"
      x      = 12
      y      = 47
      width  = 6
      height = 6
      properties = {
        title  = "Payment timeouts (no callback within 120 s)"
        region = var.region
        view   = "timeSeries"
        query  = "SOURCE '${aws_cloudwatch_log_group.sfn.name}' | filter type = \"TaskTimedOut\" | stats count(*) as timeouts by bin(5m)"
      }
    },
    {
      type   = "metric"
      x      = 18
      y      = 47
      width  = 6
      height = 6
      properties = {
        title  = "Webhook signature failures / DemoPay DLQ (both should be 0)"
        region = var.region
        view   = "timeSeries"
        period = 60
        metrics = [
          ["OrderSaga", "WebhookSignatureFailures", { stat = "Sum", label = "Signature failures", color = "#d62728" }],
          ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.psp_dlq.name, { stat = "Maximum", label = "Messages in psp DLQ", color = "#ff7f0e" }],
        ]
        yAxis = { left = { min = 0 } }
      }
    },
  ]

  # ---- Row 9: checkout holds (step 2.2) ----
  hold_log_sources = join(" | ", [for name in local.hold_log_groups : "SOURCE '${name}'"])
  hold_widgets = [
    {
      type   = "log"
      x      = 0
      y      = 53
      width  = 6
      height = 6
      properties = {
        title  = "Active holds now (latest status per hold, holds created in the time range)"
        region = var.region
        view   = "table"
        query  = "${local.hold_log_sources} | filter ispresent(holdStatus) | stats latest(holdStatus) as status by holdId | filter status = \"ACTIVE\" | stats count(*) as activeHolds"
      }
    },
    {
      type   = "metric"
      x      = 6
      y      = 53
      width  = 6
      height = 6
      properties = {
        title  = "Hold transitions per 5 min"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [for event in ["created", "consumed", "released", "expired"] :
          ["OrderSaga", "HoldEvents", "Event", event, { label = event }]
        ]
        yAxis = { left = { min = 0 } }
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 53
      width  = 6
      height = 6
      properties = {
        title  = "Expiry lag: schedule fired after expiresAt (ms)"
        region = var.region
        view   = "timeSeries"
        period = 300
        metrics = [
          ["OrderSaga", "HoldExpiryLag", { stat = "p50", label = "p50" }],
          ["OrderSaga", "HoldExpiryLag", { stat = "Maximum", label = "max" }],
        ]
        yAxis = { left = { min = 0 } }
      }
    },
    {
      type   = "metric"
      x      = 18
      y      = 53
      width  = 6
      height = 6
      properties = {
        title  = "hold-expiry Lambda: invocations / errors (errors should be 0)"
        region = var.region
        view   = "timeSeries"
        period = 300
        metrics = [
          ["AWS/Lambda", "Invocations", "FunctionName", local.hold_expiry_function_name, { stat = "Sum", label = "Invocations" }],
          ["AWS/Lambda", "Errors", "FunctionName", local.hold_expiry_function_name, { stat = "Sum", label = "Errors", color = "#d62728" }],
        ]
        yAxis = { left = { min = 0 } }
      }
    },
  ]

  fulfillment_widgets = [
    {
      type   = "metric"
      x      = 0
      y      = 59
      width  = 8
      height = 6
      properties = {
        title  = "Fulfillment per 5 min: lines fulfilled / unavailable / written off, orders partially fulfilled"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [for event in ["fulfilled", "unavailable", "written_off", "partially_fulfilled", "all_unavailable"] :
          ["OrderSaga", "FulfillmentEvents", "Event", event, { label = event }]
        ]
        yAxis = { left = { min = 0 } }
      }
    },
    {
      type   = "metric"
      x      = 8
      y      = 59
      width  = 8
      height = 6
      properties = {
        title  = "Partial refunds (INR) and written-off units per 5 min"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [
          ["OrderSaga", "LineRefundAmount", { label = "INR refunded per line", yAxis = "left" }],
          ["OrderSaga", "WrittenOffUnits", { label = "units written off", yAxis = "right" }],
        ]
        yAxis = { left = { min = 0 }, right = { min = 0 } }
      }
    },
    {
      type   = "metric"
      x      = 16
      y      = 59
      width  = 8
      height = 6
      properties = {
        title  = "Refund / write-off Lambda errors (should be 0; alarm at 1)"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [for key in ["refund_payment", "write_off_lines"] :
          ["AWS/Lambda", "Errors", "FunctionName", local.lambda_names[key], { label = local.lambda_names[key] }]
        ]
        yAxis = { left = { min = 0 } }
      }
    },
  ]

  # ---- Customer cancellation (step 2.4) ----
  cancel_widgets = [
    {
      type   = "metric"
      x      = 0
      y      = 65
      width  = 8
      height = 6
      properties = {
        title  = "Cancel requests per 5 min: accepted / rejected (too late) / not cancellable"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [for event in ["accepted", "rejected_too_late", "not_cancellable", "not_cancellable_yet", "repeated"] :
          ["OrderSaga", "CancelEvents", "Event", event, { label = event }]
        ]
        yAxis = { left = { min = 0 } }
      }
    },
    {
      type   = "metric"
      x      = 8
      y      = 65
      width  = 8
      height = 6
      properties = {
        title  = "Cancelled orders per 5 min: refunded / nothing charged / late charge refunded"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [for event in ["refunded", "nothing_charged", "late_charge_refunded"] :
          ["OrderSaga", "CancelEvents", "Event", event, { label = event }]
        ]
        yAxis = { left = { min = 0 } }
      }
    },
    {
      type   = "metric"
      x      = 16
      y      = 65
      width  = 8
      height = 6
      properties = {
        title  = "Cancellation path Lambda errors (should be 0; alarm at 1)"
        region = var.region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [for key in ["cancel_order", "begin_fulfillment", "release_inventory"] :
          ["AWS/Lambda", "Errors", "FunctionName", local.lambda_names[key], { label = local.lambda_names[key] }]
        ]
        yAxis = { left = { min = 0 } }
      }
    },
  ]

  # Row y=71 (step 3.2): the invariant auditor. Both lines must stay at 0; each point is one audit run.
  audit_widgets = [
    {
      type   = "metric"
      x      = 0
      y      = 71
      width  = 12
      height = 6
      properties = {
        title  = "Invariant audit: violations and stuck orders per run (must be 0; alarms at > 0)"
        region = var.region
        view   = "timeSeries"
        stat   = "Maximum"
        period = 60
        metrics = [
          ["OrderSaga/Audit", "Violations", { label = "Violations (I1-I9)", color = "#d62728" }],
          ["OrderSaga/Audit", "Stuck", { label = "Stuck orders (30+ min, not terminal)", color = "#ff7f0e" }],
          ["OrderSaga/Audit", "Parked", { label = "Parked by design (dead-lettered)", color = "#7f7f7f" }],
        ]
        yAxis = { left = { min = 0 } }
      }
    },
    {
      type   = "alarm"
      x      = 12
      y      = 71
      width  = 12
      height = 6
      properties = {
        title  = "Reconciliation alarms (also the stop condition of every chaos run)"
        alarms = [aws_cloudwatch_metric_alarm.invariant_violation.arn, aws_cloudwatch_metric_alarm.stuck_orders.arn]
      }
    },
  ]

  dashboard_widgets = concat(
    [
      # ---- Row 0: title + alarm status ----
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 12
        height = 5
        properties = {
          markdown = join("\n", [
            "# Event-Driven Order Processing — Live Dashboard",
            "**API Gateway -> Lambda -> DynamoDB (outbox) -> Stream -> EventBridge Pipe -> SQS (+DLQ) -> Step Functions saga** (reserve inventory -> request payment and WAIT for the signed DemoPay webhook, 120 s timeout -> complete, or compensate) **-> SNS email**. Region `${var.region}`.",
            "",
            "[State machine](${local.console}/states/home?region=${var.region}#/statemachines/view/${local.sfn_arn}) · [Outbox pipe](${local.console}/events/home?region=${var.region}#/pipes/${local.outbox_pipe}) · [Orders queue](${local.console}/sqs/v3/home?region=${var.region}#/queues/${urlencode(aws_sqs_queue.orders.url)}) · [DLQ](${local.console}/sqs/v3/home?region=${var.region}#/queues/${urlencode(aws_sqs_queue.orders_dlq.url)}) · [Orders table](${local.console}/dynamodbv2/home?region=${var.region}#table?name=${aws_dynamodb_table.orders.name}) · [X-Ray service map](${local.console}/cloudwatch/home?region=${var.region}#xray:service-map/map)",
          ])
        }
      },
      {
        type   = "alarm"
        x      = 12
        y      = 0
        width  = 12
        height = 5
        properties = {
          title  = "Alarm status (all alarms notify the order-saga-ops-alerts SNS topic)"
          alarms = local.all_alarm_arns
        }
      },

      # ---- Row 1: orders (Step Functions) ----
      {
        type   = "metric"
        x      = 0
        y      = 5
        width  = 10
        height = 6
        properties = {
          title  = "Orders: saga executions started / succeeded / failed (per minute)"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", local.sfn_arn, { label = "Started", color = "#1f77b4" }],
            ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", local.sfn_arn, { label = "Succeeded (COMPLETED)", color = "#2ca02c" }],
            ["AWS/States", "ExecutionsFailed", "StateMachineArn", local.sfn_arn, { label = "Failed (compensated, order FAILED)", color = "#d62728" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 10
        y      = 5
        width  = 4
        height = 6
        properties = {
          title                = "Order success rate (selected time range)"
          region               = var.region
          view                 = "singleValue"
          stat                 = "Sum"
          period               = 60
          setPeriodToTimeRange = true
          metrics = [
            [{ expression = "100 * FILL(succeeded, 0) / started", label = "Success rate %", id = "rate" }],
            ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", local.sfn_arn, { id = "succeeded", visible = false }],
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", local.sfn_arn, { id = "started", visible = false }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 14
        y      = 5
        width  = 10
        height = 6
        properties = {
          title  = "Saga execution time p50 / p95 (ms) - flaky payments add retry backoff"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/States", "ExecutionTime", "StateMachineArn", local.sfn_arn, { stat = "p50", label = "p50" }],
            ["AWS/States", "ExecutionTime", "StateMachineArn", local.sfn_arn, { stat = "p95", label = "p95" }],
          ]
        }
      },

      # ---- Row 2: API ----
      {
        type   = "metric"
        x      = 0
        y      = 11
        width  = 8
        height = 6
        properties = {
          title   = "API requests (order-saga-api)"
          region  = var.region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 60
          metrics = [["AWS/ApiGateway", "Count", "ApiId", local.api_id, { label = "Requests" }]]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 11
        width  = 8
        height = 6
        properties = {
          title  = "API errors: 4xx (client) / 5xx (server)"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/ApiGateway", "4xx", "ApiId", local.api_id, { label = "4xx", color = "#ff7f0e" }],
            ["AWS/ApiGateway", "5xx", "ApiId", local.api_id, { label = "5xx", color = "#d62728" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 11
        width  = 8
        height = 6
        properties = {
          title  = "API latency p50 / p95 (ms)"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_id, { stat = "p50", label = "p50" }],
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_id, { stat = "p95", label = "p95" }],
          ]
        }
      },

      # ---- Row 3: transactional outbox (orders stream -> pipe -> queue) ----
      {
        type   = "metric"
        x      = 0
        y      = 17
        width  = 6
        height = 6
        properties = {
          title  = "Outbox pipe: new orders delivered / failed"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/EventBridge/Pipes", "Invocations", "PipeName", local.outbox_pipe, { label = "Invocations (1 per new order)", color = "#2ca02c" }],
            ["AWS/EventBridge/Pipes", "ExecutionFailed", "PipeName", local.outbox_pipe, { label = "Failed (retried)", color = "#d62728" }],
            ["AWS/EventBridge/Pipes", "TargetStageFailed", "PipeName", local.outbox_pipe, { label = "SQS send failed", color = "#ff7f0e" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 17
        width  = 6
        height = 6
        properties = {
          title  = "Outbox pipe: execution duration p50 / p95 (ms)"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/EventBridge/Pipes", "Duration", "PipeName", local.outbox_pipe, { stat = "p50", label = "p50" }],
            ["AWS/EventBridge/Pipes", "Duration", "PipeName", local.outbox_pipe, { stat = "p95", label = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 17
        width  = 6
        height = 6
        properties = {
          title  = "Orders stream: GetRecords calls by the pipe (billed stream reads)"
          region = var.region
          view   = "timeSeries"
          period = 300
          # Stream metrics are published per (Operation, StreamLabel, TableName); SampleCount = number of calls.
          metrics = [[{
            expression = "SEARCH('{AWS/DynamoDB,Operation,StreamLabel,TableName} MetricName=\"SuccessfulRequestLatency\" Operation=\"GetRecords\" TableName=\"${aws_dynamodb_table.orders.name}\"', 'SampleCount', 300)"
            id         = "getrecords"
            label      = "GetRecords calls / 5 min"
          }]]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 17
        width  = 6
        height = 6
        properties = {
          title  = "OUTBOX DLQ: undeliverable new orders (should be 0)"
          region = var.region
          view   = "timeSeries"
          stat   = "Maximum"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.outbox_dlq, { label = "Messages in outbox DLQ", color = "#d62728" }],
          ]
          annotations = {
            horizontal = [{ value = 0, label = "Healthy = 0", color = "#d62728" }]
          }
          yAxis = { left = { min = 0 } }
        }
      },

      # ---- Row 4: queue ----
      {
        type   = "metric"
        x      = 0
        y      = 23
        width  = 8
        height = 6
        properties = {
          title  = "Orders queue: backlog and age of oldest message"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.orders_queue, { stat = "Maximum", label = "Messages waiting" }],
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", local.orders_queue, { stat = "Maximum", label = "Oldest message age (s)", yAxis = "right" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 23
        width  = 8
        height = 6
        properties = {
          title  = "Orders queue: messages sent / deleted (processed)"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", local.orders_queue, { label = "Sent (by the outbox pipe)" }],
            ["AWS/SQS", "NumberOfMessagesDeleted", "QueueName", local.orders_queue, { label = "Deleted (by start_workflow)" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 23
        width  = 8
        height = 6
        properties = {
          title  = "DEAD-LETTER QUEUE: messages (should be 0)"
          region = var.region
          view   = "timeSeries"
          stat   = "Maximum"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.dlq, { label = "Messages in DLQ", color = "#d62728" }],
          ]
          annotations = {
            horizontal = [{ value = 0, label = "Healthy = 0", color = "#d62728" }]
          }
          yAxis = { left = { min = 0 } }
        }
      },
    ],

    # ---- Row 5: Lambdas ----
    local.lambda_widgets,

    # ---- Row 6: DynamoDB ----
    local.dynamodb_widgets,
    [
      {
        type   = "metric"
        x      = 16
        y      = 35
        width  = 8
        height = 6
        properties = {
          title  = "DynamoDB throttled requests (orders, inventory)"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          # ThrottledRequests is published per (TableName, Operation), so SEARCH collects every operation.
          metrics = [for index, table in local.dynamo_tables : [{
            expression = "SEARCH('{AWS/DynamoDB,Operation,TableName} MetricName=\"ThrottledRequests\" TableName=\"${table}\"', 'Sum', 60)"
            id         = "throttled${index}"
            label      = table
          }]]
        }
      },

      # ---- Row 7: latest failed orders (Logs Insights) ----
      {
        type   = "log"
        x      = 0
        y      = 41
        width  = 24
        height = 6
        properties = {
          title  = "20 latest FAILED orders and their reason (Step Functions execution logs)"
          region = var.region
          view   = "table"
          query  = "SOURCE '${aws_cloudwatch_log_group.sfn.name}' | fields @timestamp, details.cause as reason | filter type = \"ExecutionFailed\" | parse execution_arn /:(?<orderId>ORD-[0-9]+-[0-9a-f]+)$/ | display @timestamp, orderId, reason | sort @timestamp desc | limit 20"
        }
      },
    ],
    local.payment_widgets,
    local.hold_widgets,
    local.fulfillment_widgets,
    local.cancel_widgets,
    local.audit_widgets,
  )
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_prefix}-dashboard"
  dashboard_body = jsonencode({ widgets = local.dashboard_widgets })
}

# -----------------------------------------------------------------------------
# Saved Logs Insights queries (CloudWatch -> Logs Insights -> Saved queries -> order-saga/)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_query_definition" "trace_order" {
  name            = "order-saga/Trace one order"
  log_group_names = local.all_log_groups
  query_string    = <<-EOT
    # Replace ORD-PASTE-ORDER-ID-HERE with an orderId, then Run. This shows every log line about that
    # order across the 6 Lambdas (JSON logs carry orderId) and the Step Functions execution log.
    # source = which Lambda (service) or which Step Functions event type; event = log message, state name or error.
    fields @timestamp, @log, coalesce(service, type) as source, level, coalesce(message, details.name, details.cause) as event
    | filter orderId = "ORD-PASTE-ORDER-ID-HERE" or execution_arn like "ORD-PASTE-ORDER-ID-HERE"
    | sort @timestamp asc
    | limit 200
  EOT
}

resource "aws_cloudwatch_query_definition" "failed_by_reason" {
  name            = "order-saga/Failed orders by reason"
  log_group_names = [aws_cloudwatch_log_group.sfn.name]
  query_string    = <<-EOT
    # Every order that ended in the OrderFailed state, grouped by its failure reason.
    filter type = "ExecutionFailed"
    | fields details.cause as reason
    | parse reason /^(?<errorType>[A-Za-z.]+):/
    | stats count(*) as orders by errorType, reason
    | sort orders desc
  EOT
}

resource "aws_cloudwatch_query_definition" "duplicates_ignored" {
  name            = "order-saga/Duplicate messages ignored"
  log_group_names = [aws_cloudwatch_log_group.lambda["start_workflow"].name]
  query_string    = <<-EOT
    # SQS delivers at least once: these are re-deliveries that start_workflow safely ignored.
    fields @timestamp, orderId, messageId, executionArn, message
    | filter message like /Duplicate message ignored/
    | sort @timestamp desc
    | limit 100
  EOT
}

resource "aws_cloudwatch_query_definition" "slowest_invocations" {
  name            = "order-saga/Slowest Lambda invocations"
  log_group_names = local.lambda_log_groups
  query_string    = <<-EOT
    # The REPORT line Lambda writes after every invocation (initDuration is set only on cold starts).
    filter @type = "REPORT"
    | fields @timestamp, @log, @duration, @billedDuration, @initDuration, @maxMemoryUsed / 1000000 as maxMemoryMB
    | sort @duration desc
    | limit 25
  EOT
}
