data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  console    = "https://${var.region}.console.aws.amazon.com"

  state_machine_name = "${var.project_prefix}-workflow"
  # Built from known parts instead of taken from the resource. The state machine depends on the
  # Lambdas, while start_workflow (a Lambda) needs this ARN, so using the resource would be a cycle.
  state_machine_arn = "arn:aws:states:${var.region}:${local.account_id}:stateMachine:${local.state_machine_name}"

  log_retention_days = 7
}
