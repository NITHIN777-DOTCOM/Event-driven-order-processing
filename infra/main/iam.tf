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
    sid       = "ReadPricesKeysAndReplayedOrders"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.inventory.arn, aws_dynamodb_table.idempotency.arn, aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "CheckTheOrdersCheckoutHold"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.holds.arn]
  }
  # TransactWriteItems is authorised per item: PutItem on the idempotency table and on the orders table.
  statement {
    sid       = "WriteOrderAndIdempotencyKey"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.orders.arn, aws_dynamodb_table.idempotency.arn]
  }
  # Deliberately NO SQS permission: new orders reach the queue through the outbox pipe (outbox.tf).
  # The precondition on aws_iam_role_policy.lambda below fails the plan if one is ever added back.
}

data "aws_iam_policy_document" "get_order" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["get_order"].json]

  statement {
    sid       = "ReadOrders"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
}

data "aws_iam_policy_document" "list_orders" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["list_orders"].json]

  # Query on the index only: this function can't read the base table or scan it.
  statement {
    sid       = "QueryRecentOrdersIndex"
    actions   = ["dynamodb:Query"]
    resources = ["${aws_dynamodb_table.orders.arn}/index/gsi1"]
  }
}

data "aws_iam_policy_document" "list_products" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["list_products"].json]

  statement {
    sid       = "ReadCatalogue"
    actions   = ["dynamodb:Scan"]
    resources = [aws_dynamodb_table.inventory.arn]
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
    sid       = "ReadAndMarkOrderProcessing"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "StartSagaExecution"
    actions   = ["states:StartExecution"]
    resources = [local.state_machine_arn]
  }
  # Used to tell a duplicate delivery apart from a retry after a failed StartExecution.
  statement {
    sid       = "CheckExistingExecution"
    actions   = ["states:DescribeExecution"]
    resources = ["${replace(local.state_machine_arn, ":stateMachine:", ":execution:")}:*"]
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
  # Step 2.2: consume the order's checkout hold (hold -> CONSUMED, pointer deleted) or expire an overdue one.
  statement {
    sid       = "ConsumeCheckoutHold"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.holds.arn]
  }
  statement {
    sid       = "DeleteTheConsumedHoldsSchedule"
    actions   = ["scheduler:DeleteSchedule"]
    resources = [local.holds_schedules_arn]
  }
}

# Compensation no longer touches wallets: money moves only inside the provider (DemoPay), via its refund API.
data "aws_iam_policy_document" "refund_payment" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["refund_payment"].json]

  statement {
    sid       = "ReadAndFinishPaymentIntent"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.payments.arn]
  }
  statement {
    sid       = "RecordRefundOnOrder"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "CallDemoPayRefundApi"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.payment_provider_arn]
  }
}

# Starts a payment: intent + task token, order PAYMENT_PENDING, request to DemoPay. No wallet access at all.
data "aws_iam_policy_document" "request_payment" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["request_payment"].json]

  statement {
    sid       = "ReadOrderAndMarkPaymentPending"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "CreatePaymentIntent"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.payments.arn]
  }
  statement {
    sid       = "SendPaymentRequestToDemoPay"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.psp_requests.arn]
  }
  # Only used when a re-run finds the payment already finished and answers the new token itself.
  statement {
    sid       = "AnswerOwnTaskToken"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = [local.state_machine_arn]
  }
}

# DemoPay (mock PSP): its own records, the wallets it debits/credits, the queue it consumes, the webhook secret.
data "aws_iam_policy_document" "payment_provider" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["payment_provider"].json]

  statement {
    sid       = "OwnChargeAndRefundRecords"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.psp_transactions.arn]
  }
  statement {
    sid       = "DebitAndCreditWallets"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.wallets.arn]
  }
  statement {
    sid       = "WriteLedgerEntries"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.wallet_txns.arn]
  }
  statement {
    sid       = "ConsumePaymentRequests"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.psp_requests.arn]
  }
  # The AWS-managed key aws/ssm decrypts it; its key policy already allows SSM use within the account.
  statement {
    sid       = "ReadWebhookSecret"
    actions   = ["ssm:GetParameter"]
    resources = [local.webhook_secret_arn]
  }
}

# The webhook: verify (secret), record the outcome (payments + orders), resume the saga, refund late payments.
data "aws_iam_policy_document" "payment_webhook" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["payment_webhook"].json]

  statement {
    sid       = "ReadWebhookSecret"
    actions   = ["ssm:GetParameter"]
    resources = [local.webhook_secret_arn]
  }
  statement {
    sid       = "ReadAndUpdatePaymentIntents"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.payments.arn]
  }
  statement {
    sid       = "RecordPaymentOnOrder"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  # Task tokens are scoped to their state machine; this role can only answer tasks of the order saga.
  statement {
    sid       = "ResumeOrderSaga"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = [local.state_machine_arn]
  }
  statement {
    sid       = "CallDemoPayRefundApi"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.payment_provider_arn]
  }
}

data "aws_iam_policy_document" "wallet_api" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["wallet_api"].json]

  statement {
    sid       = "ReadAndSetWallet"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.wallets.arn]
  }
  statement {
    sid       = "ReadAndWriteLedger"
    actions   = ["dynamodb:Query", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.wallet_txns.arn]
  }
}

data "aws_iam_policy_document" "release_inventory" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["release_inventory"].json]

  statement {
    sid       = "ReadOrder"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
  statement {
    sid       = "ReturnStockAndMarkReleased"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.inventory.arn, aws_dynamodb_table.orders.arn]
  }
}

# Checkout holds (step 2.2). TransactWriteItems is authorised per item: Put/Update/Delete on holds (hold + pointer),
# Update on inventory.
data "aws_iam_policy_document" "holds_api" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["holds_api"].json]

  statement {
    sid       = "HoldsAndPrices"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.holds.arn]
  }
  statement {
    sid       = "MoveStockBetweenAvailableAndHeld"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.inventory.arn]
  }
  statement {
    sid       = "OneTimeExpirySchedulesInTheHoldsGroupOnly"
    actions   = ["scheduler:CreateSchedule", "scheduler:DeleteSchedule"]
    resources = [local.holds_schedules_arn]
  }
  # CreateSchedule hands the scheduler role to EventBridge Scheduler: only that role, only to that service.
  statement {
    sid       = "PassOnlyTheSchedulerRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.scheduler.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["scheduler.amazonaws.com"]
    }
  }
  statement {
    sid       = "ReadAppClientIds"
    actions   = ["ssm:GetParameter"]
    resources = [local.client_ids_parameter_arn] # a string: the parameter's value depends on Cognito -> cycle
  }
}

data "aws_iam_policy_document" "hold_expiry" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base["hold_expiry"].json]

  statement {
    sid       = "ExpireHoldAndDropPointer"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.holds.arn]
  }
  statement {
    sid       = "ReturnHeldStock"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.inventory.arn]
  }
}

locals {
  lambda_policies = {
    create_order      = data.aws_iam_policy_document.create_order.json
    get_order         = data.aws_iam_policy_document.get_order.json
    start_workflow    = data.aws_iam_policy_document.start_workflow.json
    reserve_inventory = data.aws_iam_policy_document.reserve_inventory.json
    request_payment   = data.aws_iam_policy_document.request_payment.json
    release_inventory = data.aws_iam_policy_document.release_inventory.json
    list_orders       = data.aws_iam_policy_document.list_orders.json
    list_products     = data.aws_iam_policy_document.list_products.json
    refund_payment    = data.aws_iam_policy_document.refund_payment.json
    wallet_api        = data.aws_iam_policy_document.wallet_api.json
    payment_provider  = data.aws_iam_policy_document.payment_provider.json
    payment_webhook   = data.aws_iam_policy_document.payment_webhook.json
    holds_api         = data.aws_iam_policy_document.holds_api.json
    hold_expiry       = data.aws_iam_policy_document.hold_expiry.json
    # The Cognito trigger touches no AWS resource: own logs + X-Ray only.
    pre_token = data.aws_iam_policy_document.lambda_base["pre_token"].json
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

  lifecycle {
    # Transactional-outbox guard: create_order must never be able to publish to SQS again (that was the
    # dual write). Checked on every plan, in CI and locally, before anything is changed.
    precondition {
      condition     = each.key != "create_order" || !strcontains(local.lambda_policies["create_order"], "sqs:")
      error_message = "create_order's role must not have any sqs:* permission: new orders are delivered by the outbox pipe (outbox.tf)."
    }
  }
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
      for key in ["reserve_inventory", "request_payment", "refund_payment", "release_inventory"] : [
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
    sid       = "MarkPaymentTimedOut"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.payments.arn]
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
