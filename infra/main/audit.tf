# =============================================================================
# Invariant auditor (step 3.2): a reconciliation job that keeps checking I1-I9 for ever.
#
#   EventBridge Scheduler (hourly) -> Lambda order-saga-invariant-auditor (read-only, src/common/invariants.py)
#     -> metrics OrderSaga/Audit (Violations, Stuck, Parked, per-invariant Violations)
#     -> alarms order-saga-invariant-violation and order-saga-stuck-orders -> SNS order-saga-ops-alerts
#
# The violation alarm is also the stop condition of every chaos run (scripts/chaos_run.py): a run that breaks an
# invariant stops itself.
# =============================================================================

locals {
  auditor_name = local.lambda_names["invariant_auditor"]
}

resource "aws_scheduler_schedule_group" "audit" {
  name = "${var.project_prefix}-audit"

  tags = {
    Name        = "${var.project_prefix}-audit"
    Description = module.tags.description["audit_schedule_group"]
  }
}

data "aws_iam_policy_document" "audit_scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    # Confused-deputy protection: only schedules in this account's audit group may use the role. Scheduler sends the
    # schedule GROUP's ARN as aws:SourceArn (a schedule ARN here made CreateSchedule fail: "must allow AWS
    # EventBridge Scheduler to assume the role").
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_scheduler_schedule_group.audit.arn]
    }
  }
}

resource "aws_iam_role" "audit_scheduler" {
  name               = "${var.project_prefix}-audit-scheduler-role"
  description        = "EventBridge Scheduler role for the hourly invariant audit - may only invoke ${local.auditor_name}"
  assume_role_policy = data.aws_iam_policy_document.audit_scheduler_assume.json
}

resource "aws_iam_role_policy" "audit_scheduler" {
  name = "${var.project_prefix}-audit-scheduler-policy"
  role = aws_iam_role.audit_scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeTheAuditorOnly"
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.fn["invariant_auditor"].arn
    }]
  })
}

resource "aws_scheduler_schedule" "audit_hourly" {
  name        = "${var.project_prefix}-invariant-audit-hourly"
  group_name  = aws_scheduler_schedule_group.audit.name
  description = "Runs the invariant auditor every hour - reconciles orders - payments - ledger and stock - I1 to I9"

  schedule_expression = "rate(1 hour)"
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.fn["invariant_auditor"].arn
    role_arn = aws_iam_role.audit_scheduler.arn
    input    = jsonencode({ source = "schedule" })
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}

# Each audit run publishes one datapoint (0 included). Period 60 s + treat_missing_data = "ignore": the alarm keeps
# the verdict of the LAST audit until the next one (hourly, or every minute during a chaos run).
resource "aws_cloudwatch_metric_alarm" "invariant_violation" {
  alarm_name          = "${var.project_prefix}-invariant-violation"
  alarm_description   = "The invariant auditor found money or stock that does not add up (I1-I9). Always a bug. Its log group /aws/lambda/${local.auditor_name} lists each finding (auditFinding = violation, orderId, invariant, detail). Also the stop condition of every chaos run: scripts/chaos_run.py removes its fault configuration when this fires."
  namespace           = "OrderSaga/Audit"
  metric_name         = "Violations"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "ignore"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "stuck_orders" {
  alarm_name          = "${var.project_prefix}-stuck-orders"
  alarm_description   = "An order is still not COMPLETED / PARTIALLY_FULFILLED / FAILED / CANCELLED 30+ minutes after it was created. The auditor log (auditFinding = stuck) names it with its execution status. FAILED execution = parked: fix the cause, then follow docs/runbooks/redrive-stuck-order.md (aws stepfunctions redrive-execution)."
  namespace           = "OrderSaga/Audit"
  metric_name         = "Stuck"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "ignore"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}
