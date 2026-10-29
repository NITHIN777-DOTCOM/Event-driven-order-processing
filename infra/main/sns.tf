# Customer-facing order emails. Published directly by the state machine (no Lambda).
resource "aws_sns_topic" "notifications" {
  name         = "${var.project_prefix}-notifications"
  display_name = "Order Saga"

  tags = {
    Name        = "${var.project_prefix}-notifications"
    Description = module.tags.description["notifications_topic"]
  }
}

# Operations alerts. CloudWatch alarms publish here (Phase 3).
resource "aws_sns_topic" "ops_alerts" {
  name         = "${var.project_prefix}-ops-alerts"
  display_name = "Order Saga"

  tags = {
    Name        = "${var.project_prefix}-ops-alerts"
    Description = module.tags.description["ops_alerts_topic"]
  }
}

# Email subscriptions stay "PendingConfirmation" until the link in the AWS email is clicked.
resource "aws_sns_topic_subscription" "notifications_email" {
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_sns_topic_subscription" "ops_alerts_email" {
  topic_arn = aws_sns_topic.ops_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
