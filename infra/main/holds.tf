# Checkout holds (step 2.2): a signed-in user's cart is held for 10 minutes at checkout.
# Model, transitions and invariant I5: src/common/holds.py. API: src/lambdas/holds_api. Expiry: src/lambdas/hold_expiry.
#
# Release is PRECISE: each hold gets a one-time EventBridge Scheduler schedule at(expiresAt) in the group below,
# created by the holds Lambda at run time (not by Terraform), which invokes order-saga-hold-expiry. DynamoDB TTL on
# this table only cleans up old records (purgeAt = expiry + 7 days): TTL deletion can lag by days, so it never
# releases stock.

locals {
  holds_schedule_group = "${var.project_prefix}-holds"
  # Strings, not references: the Lambdas live in one for_each resource, and referencing aws_lambda_function.fn here
  # would make the holds_api function depend on itself (its env vars carry these values).
  hold_expiry_function_name = "${var.project_prefix}-hold-expiry"
  hold_expiry_function_arn  = "arn:aws:lambda:${var.region}:${local.account_id}:function:${local.hold_expiry_function_name}"
  holds_schedules_arn       = "arn:aws:scheduler:${var.region}:${local.account_id}:schedule/${local.holds_schedule_group}/*"
  client_ids_parameter      = "/${var.project_prefix}/auth/client-ids"
  client_ids_parameter_arn  = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${local.client_ids_parameter}"
  hold_log_groups           = [for key in ["holds_api", "hold_expiry"] : aws_cloudwatch_log_group.lambda[key].name]
}

resource "aws_dynamodb_table" "holds" {
  name         = "${var.project_prefix}-holds"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "holdId" # HOLD-<date>-<random> for holds; USER#<sub> for each user's "current hold" pointer

  deletion_protection_enabled = false

  attribute {
    name = "holdId"
    type = "S"
  }

  # Clean-up only (finished holds, 7 days after expiry). Never the release mechanism: see the comment at the top.
  ttl {
    attribute_name = "purgeAt"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name        = "${var.project_prefix}-holds"
    Description = module.tags.description["holds_table"]
  }
}

resource "aws_scheduler_schedule_group" "holds" {
  name = local.holds_schedule_group

  tags = {
    Name        = local.holds_schedule_group
    Description = module.tags.description["holds_schedule_group"]
  }
}

# The app client ids, for holds_api's "only the automation client may shorten a hold" rule. A parameter rather than
# Lambda env vars: the env vars would make every function depend on the Cognito clients, and the user pool already
# depends on the functions (its pre-token trigger), which is a cycle.
resource "aws_ssm_parameter" "client_ids" {
  name        = local.client_ids_parameter
  description = "Cognito app client ids (spa = storefront, automation = scripts and e2e tests) read by order-saga-holds-api"
  type        = "String" # ids are not secrets: they appear in every token
  value       = jsonencode({ spa = aws_cognito_user_pool_client.spa.id, automation = aws_cognito_user_pool_client.automation.id })

  tags = {
    Description = module.tags.description["client_ids_parameter"]
  }
}

# EventBridge Scheduler's execution role: it may invoke the expiry Lambda and nothing else.
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    # Confused-deputy protection: only schedules in this account may assume the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeHoldExpiryOnly"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.hold_expiry_function_arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project_prefix}-holds-scheduler-role"
  description        = "Assumed by EventBridge Scheduler (group ${local.holds_schedule_group}) to invoke ${local.hold_expiry_function_name} - nothing else"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.project_prefix}-holds-scheduler-policy"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
