# Least privilege: each Lambda has its OWN role, scoped to exactly the resources it touches.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Every function may write to its own log group and send X-Ray traces.
# (X-Ray trace APIs don't support resource-level permissions, so "*" is required.)
data "aws_iam_policy_document" "lambda_base" {
  for_each = local.lambda_functions

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"]
  }

  statement {
    sid       = "XRayTracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "create_order" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["create_order"].json]

  statement {
    sid       = "ReadProductPrices"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.inventory.arn]
  }
  statement {
    sid       = "WriteNewOrders"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "EnqueueOrders"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.orders.arn]
  }
}

data "aws_iam_policy_document" "get_order" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["get_order"].json]

  statement {
    sid       = "ReadOrders"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
}

data "aws_iam_policy_document" "start_workflow" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["start_workflow"].json]

  statement {
    sid       = "ConsumeOrdersQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.orders.arn]
  }
  statement {
    sid       = "MarkOrderProcessing"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "StartSagaExecution"
    actions   = ["states:StartExecution"]
    resources = [local.state_machine_arn]
  }
}

data "aws_iam_policy_document" "reserve_inventory" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["reserve_inventory"].json]

  statement {
    sid       = "ReadOrder"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  # TransactWriteItems is authorised per item, using the UpdateItem action on each table.
  statement {
    sid       = "ReserveStockAndMarkOrder"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.inventory.arn, aws_dynamodb_table.orders.arn]
  }
}

data "aws_iam_policy_document" "process_payment" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["process_payment"].json]

  statement {
    sid       = "MarkPaymentCaptured"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
}

locals {
  lambda_policies = {
    create_order      = data.aws_iam_policy_document.create_order.json
    get_order         = data.aws_iam_policy_document.get_order.json
    start_workflow    = data.aws_iam_policy_document.start_workflow.json
    reserve_inventory = data.aws_iam_policy_document.reserve_inventory.json
    process_payment   = data.aws_iam_policy_document.process_payment.json
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.lambda_functions

  name               = "${local.lambda_names[each.key]}-role"
  description        = "Execution role for Lambda ${local.lambda_names[each.key]} - least privilege"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.lambda_functions

  name   = "${local.lambda_names[each.key]}-policy"
  role   = aws_iam_role.lambda[each.key].id
  policy = local.lambda_policies[each.key]
}

# ---------------------------------------------------------------------------
# Step Functions execution role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    # Confused-deputy protection: only state machines in this account may assume the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid     = "InvokeSagaLambdas"
    actions = ["lambda:InvokeFunction"]
    resources = flatten([
      for key in ["reserve_inventory", "process_payment"] : [
        aws_lambda_function.fn[key].arn,
        "${aws_lambda_function.fn[key].arn}:*", # versions/aliases
      ]
    ])
  }
  statement {
    sid       = "MarkOrderCompleted"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "NotifyCustomer"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.notifications.arn]
  }
  statement {
    sid       = "XRayTracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }
  # Step Functions log delivery uses CloudWatch Logs "vended logs" APIs. AWS documents
  # that these need Resource "*".
  statement {
    sid = "DeliverExecutionLogs"
    actions = [
      "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.state_machine_name}-role"
  description        = "Execution role for the ${local.state_machine_name} state machine - invokes saga Lambdas and updates orders and publishes to SNS"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${local.state_machine_name}-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}
