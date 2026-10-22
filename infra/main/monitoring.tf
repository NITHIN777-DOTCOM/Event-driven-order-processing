# =============================================================================
# Monitoring: one CloudWatch dashboard, alarms -> SNS ops-alerts, saved Logs Insights queries.
#
# Alarm design note: a compensated order (payment declined, out of stock) ends in a Fail state,
# and process_payment raises on declines. So "ExecutionsFailed > 0" and "process_payment Errors > 0"
# are normal BUSINESS outcomes, not system faults. We alarm on:
#   - system faults:   DLQ not empty, start_workflow crashes, API 5xx, executions timed out/aborted,
#                      queue backlog
#   - business health: the failure RATE (only with enough traffic to be meaningful)
# =============================================================================

locals {
  sfn_arn       = aws_sfn_state_machine.order_saga.arn
  api_id        = aws_apigatewayv2_api.orders.id
  orders_queue  = aws_sqs_queue.orders.name
  dlq           = aws_sqs_queue.orders_dlq.name
  dynamo_tables = [aws_dynamodb_table.orders.name, aws_dynamodb_table.inventory.name]

  # Log groups the saved queries search across.
  lambda_log_groups = [for group in aws_cloudwatch_log_group.lambda : group.name]
  all_log_groups    = concat(local.lambda_log_groups, [aws_cloudwatch_log_group.sfn.name])

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
}

# -----------------------------------------------------------------------------
# Alarms (6 alarms = 8 alarm metrics, inside the 10-metric free tier)
# -----------------------------------------------------------------------------
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
  ]
}

# -----------------------------------------------------------------------------
# Dashboard: 7 rows on a 24-column grid, top to bottom following the order's path
# -----------------------------------------------------------------------------
locals {
  # One Lambda graph per metric, with every function on it.
  lambda_widgets = [
    for index, spec in [
      { title = "Lambda invocations", metric = "Invocations", stat = "Sum" },
      { title = "Lambda errors (process_payment errors include simulated declines)", metric = "Errors", stat = "Sum" },
      { title = "Lambda duration p95 (ms)", metric = "Duration", stat = "p95" },
      { title = "Lambda throttles", metric = "Throttles", stat = "Sum" },
      ] : {
      type   = "metric"
      x      = index * 6
      y      = 23
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
      y      = 29
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
            "**API Gateway -> Lambda -> SQS (+DLQ) -> Step Functions saga** (reserve inventory -> payment with retries -> complete, or compensate) **-> SNS email**. Region `${var.region}`.",
            "",
            "[State machine](${local.console}/states/home?region=${var.region}#/statemachines/view/${local.sfn_arn}) · [Orders queue](${local.console}/sqs/v3/home?region=${var.region}#/queues/${urlencode(aws_sqs_queue.orders.url)}) · [DLQ](${local.console}/sqs/v3/home?region=${var.region}#/queues/${urlencode(aws_sqs_queue.orders_dlq.url)}) · [Orders table](${local.console}/dynamodbv2/home?region=${var.region}#table?name=${aws_dynamodb_table.orders.name}) · [X-Ray service map](${local.console}/cloudwatch/home?region=${var.region}#xray:service-map/map)",
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

      # ---- Row 3: queue ----
      {
        type   = "metric"
        x      = 0
        y      = 17
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
        y      = 17
        width  = 8
        height = 6
        properties = {
          title  = "Orders queue: messages sent / deleted (processed)"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", local.orders_queue, { label = "Sent (by create_order)" }],
            ["AWS/SQS", "NumberOfMessagesDeleted", "QueueName", local.orders_queue, { label = "Deleted (by start_workflow)" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 17
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

    # ---- Row 4: Lambdas ----
    local.lambda_widgets,

    # ---- Row 5: DynamoDB ----
    local.dynamodb_widgets,
    [
      {
        type   = "metric"
        x      = 16
        y      = 29
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

      # ---- Row 6: latest failed orders (Logs Insights) ----
      {
        type   = "log"
        x      = 0
        y      = 35
        width  = 24
        height = 6
        properties = {
          title  = "20 latest FAILED orders and their reason (Step Functions execution logs)"
          region = var.region
          view   = "table"
          query  = "SOURCE '${aws_cloudwatch_log_group.sfn.name}' | fields @timestamp, details.cause as reason | filter type = \"ExecutionFailed\" | parse execution_arn /:(?<orderId>ORD-[0-9]+-[0-9a-f]+)$/ | display @timestamp, orderId, reason | sort @timestamp desc | limit 20"
        }
      },
    ]
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
