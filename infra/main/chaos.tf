# =============================================================================
# Chaos experiments with AWS FIS (step 3.2): Lambda invocation errors and delays on the saga Lambdas.
#
# How FIS reaches a Lambda: the target functions carry the AWS FIS extension layer (lambda.tf). The extension polls
# an S3 prefix for a fault configuration; a running experiment (role order-saga-fis-experiment-role) writes one
# there, the extension applies it to that % of invocations, and the experiment deletes it when it ends.
#
# Blast radius: FIS faults hit a PERCENTAGE OF ALL INVOCATIONS of the targeted functions, not chosen orders. What
# keeps it safe here: short windows (max duration per template), no real users (a course project with test users),
# and a stop condition on every template: the order-saga-invariant-violation alarm. Never run one during a demo.
#
# These templates are definitions only: nothing happens until someone starts an experiment
# (scripts/chaos_run.py, or `aws fis start-experiment --experiment-template-id ...`).
# =============================================================================

locals {
  # Published by AWS as SSM parameter /aws/service/fis/lambda-extension/AWS-FIS-extension-arm64/1.x.x (ap-south-1:
  # version 422, read 2026-10-31). Pinned so deploys are reproducible.
  fis_extension_layer_arn = "arn:aws:lambda:${var.region}:058264376524:layer:aws-fis-extension-arm64:422"
  fis_config_prefix       = "FisConfigs"
  fis_target_arns         = { for key in local.fis_target_functions : key => "arn:aws:lambda:${var.region}:${local.account_id}:function:${local.lambda_names[key]}" }
  fis_stop_condition      = aws_cloudwatch_metric_alarm.invariant_violation.arn
}

# ---------------------------------------------------------------------------
# Config bucket: private, SSE-S3 (AWS-managed), TLS only, and old configs cleaned up by a lifecycle rule.
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "fis_config" {
  bucket        = "${var.project_prefix}-fis-config-${local.account_id}"
  force_destroy = false

  tags = {
    Name        = "${var.project_prefix}-fis-config-${local.account_id}"
    Description = module.tags.description["fis_config_bucket"]
  }
}

resource "aws_s3_bucket_public_access_block" "fis_config" {
  bucket                  = aws_s3_bucket.fis_config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "fis_config" {
  bucket = aws_s3_bucket.fis_config.id
  rule {
    object_ownership = "BucketOwnerEnforced" # ACLs off
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "fis_config" {
  bucket = aws_s3_bucket.fis_config.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3, no customer-managed key
    }
  }
}

# FIS deletes its configuration when an experiment ends; this catches anything left behind (e.g. an interrupted run).
resource "aws_s3_bucket_lifecycle_configuration" "fis_config" {
  bucket = aws_s3_bucket.fis_config.id
  rule {
    id     = "expire-old-fault-configs"
    status = "Enabled"
    filter {
      prefix = "${local.fis_config_prefix}/"
    }
    expiration {
      days = 1
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "fis_config_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.fis_config.arn, "${aws_s3_bucket.fis_config.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "fis_config" {
  bucket     = aws_s3_bucket.fis_config.id
  policy     = data.aws_iam_policy_document.fis_config_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.fis_config]
}

# ---------------------------------------------------------------------------
# Experiment role. AWS publishes no managed policy for the Lambda actions, so this is an inline policy with exactly
# what the FIS docs list: write on the config prefix, lambda:GetFunction and tag:GetResources (to resolve targets),
# plus cloudwatch:DescribeAlarms for the stop condition. GetFunction is scoped to the target functions.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "fis_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["fis.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:fis:${var.region}:${local.account_id}:experiment/*"]
    }
  }
}

data "aws_iam_policy_document" "fis" {
  statement {
    sid       = "WriteFaultConfigs"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.fis_config.arn}/${local.fis_config_prefix}/*"]
  }
  statement {
    sid       = "ResolveTargetFunctions"
    actions   = ["lambda:GetFunction"]
    resources = values(local.fis_target_arns)
  }
  # tag:GetResources supports no resource-level permissions.
  statement {
    sid       = "ResolveTargetsByTag"
    actions   = ["tag:GetResources"]
    resources = ["*"]
  }
  # DescribeAlarms supports no resource-level permissions either.
  statement {
    sid       = "ReadStopConditionAlarm"
    actions   = ["cloudwatch:DescribeAlarms"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "fis" {
  name               = "${var.project_prefix}-fis-experiment-role"
  description        = "AWS FIS experiments on the order-saga Lambdas - writes fault configs to the FIS config bucket prefix only"
  assume_role_policy = data.aws_iam_policy_document.fis_assume.json
}

resource "aws_iam_role_policy" "fis" {
  name   = "${var.project_prefix}-fis-experiment-policy"
  role   = aws_iam_role.fis.id
  policy = data.aws_iam_policy_document.fis.json
}

# ---------------------------------------------------------------------------
# Experiment templates
# ---------------------------------------------------------------------------
locals {
  fis_experiments = {
    # E1: ~30% of invocations of every saga Lambda fail for 10 minutes (preventExecution: the handler doesn't run,
    # like a crash at start-up). Crashes AFTER a write are E3 (code switches, src/common/chaos.py): FIS can't aim
    # at one order or at a point inside a handler.
    e1_errors = {
      description = "E1 - 30 percent invocation errors on the 9 saga Lambdas for 10 min - stop on invariant violation"
      action      = "aws:lambda:invocation-error"
      functions   = local.fis_target_functions # selected by tag: a FIS target lists at most 5 ARNs
      parameters  = { duration = "PT10M", invocationPercentage = "30", preventExecution = "true" }
    }
    # E2: half the DemoPay and webhook invocations start 25 s late. DemoPay's timeout is 20 s, so a delayed charge
    # times out and SQS redelivers it after the 120 s visibility timeout: past the saga's 120 s payment timeout.
    # The webhook (API Gateway's 30 s limit) answers late but within it.
    e2_delays = {
      description = "E2 - 25 s start-up delay on half the payment-provider and payment-webhook invocations for 10 min"
      action      = "aws:lambda:invocation-add-delay"
      functions   = toset(["payment_provider", "payment_webhook"])
      parameters  = { duration = "PT10M", invocationPercentage = "50", startupDelayMilliseconds = "25000" }
    }
    # E5: refund outage. Every refund-payment invocation fails for 6 minutes: orders that need a refund park
    # (their executions FAIL after the retries) until someone redrives them (docs/runbooks/redrive-stuck-order.md).
    e5_refund_outage = {
      description = "E5 - refund outage - 100 percent errors on refund-payment for 6 min - executions park for a redrive"
      action      = "aws:lambda:invocation-error"
      functions   = toset(["refund_payment"])
      parameters  = { duration = "PT6M", invocationPercentage = "100", preventExecution = "true" }
    }
  }
}

resource "aws_fis_experiment_template" "chaos" {
  for_each = local.fis_experiments

  description = each.value.description
  role_arn    = aws_iam_role.fis.arn

  stop_condition {
    source = "aws:cloudwatch:alarm"
    value  = local.fis_stop_condition
  }

  action {
    name        = replace(each.key, "_", "-")
    action_id   = each.value.action
    description = each.value.description
    target {
      key   = "Functions"
      value = "saga-functions"
    }
    dynamic "parameter" {
      for_each = each.value.parameters
      content {
        key   = parameter.key
        value = parameter.value
      }
    }
  }

  # Up to 5 functions: by ARN. More (E1, all 9): by the ChaosTarget = saga tag, which only the FIS targets carry.
  target {
    name           = "saga-functions"
    resource_type  = "aws:lambda:function"
    selection_mode = "ALL"
    resource_arns  = length(each.value.functions) <= 5 ? [for key in sort(tolist(each.value.functions)) : local.fis_target_arns[key]] : null
    dynamic "resource_tag" {
      for_each = length(each.value.functions) > 5 ? [1] : []
      content {
        key   = "ChaosTarget"
        value = "saga"
      }
    }
  }

  experiment_options {
    account_targeting            = "single-account"
    empty_target_resolution_mode = "fail"
  }

  tags = {
    Name        = "${var.project_prefix}-chaos-${replace(each.key, "_", "-")}"
    Description = module.tags.description["fis_${each.key}"]
  }
}
