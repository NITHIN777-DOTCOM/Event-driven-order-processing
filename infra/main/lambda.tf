locals {
  src_dir   = "${path.module}/../../src"
  build_dir = "${path.module}/../../build"

  default_lambda_timeout = 30

  # AWS-published "Powertools for AWS Lambda (Python)" layer. We use it only for the aws-xray-sdk it
  # bundles (see src/common/tracing.py). It's pinned so deploys are reproducible. To upgrade, look up:
  #   aws ssm get-parameter --name /aws/service/powertools/python/arm64/python3.12/latest
  powertools_layer_arn = "arn:aws:lambda:${var.region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-arm64:40"

  # One entry per function. The key is the folder under src/lambdas/.
  # `timeout` is optional (default 30 s).
  lambda_functions = {
    create_order = {
      description = "POST /orders (JWT) - idempotent per user (Idempotency-Key): prices the order and saves it as PENDING; the outbox pipe enqueues it"
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        INVENTORY_TABLE   = aws_dynamodb_table.inventory.name
        IDEMPOTENCY_TABLE = aws_dynamodb_table.idempotency.name
        HOLDS_TABLE       = aws_dynamodb_table.holds.name
      }
    }
    get_order = {
      description = "GET /orders/{id} (JWT) - the caller's own order (404 for anyone else's), its statusHistory, a live feed and AWS Console links"
      environment = {
        ORDERS_TABLE       = aws_dynamodb_table.orders.name
        WORKFLOW_LOG_GROUP = "/aws/vendedlogs/states/${local.state_machine_name}"
      }
    }
    list_orders = {
      description = "GET /orders?limit=N (JWT) - the caller's newest orders via gsi1, partition USER#<sub> (Query, no scan)"
      environment = {
        ORDERS_TABLE = aws_dynamodb_table.orders.name
        ORDERS_INDEX = "gsi1"
      }
    }
    list_products = {
      description = "GET /products - storefront catalogue with live stock"
      environment = {
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
      }
    }
    start_workflow = {
      description = "SQS consumer - starts exactly one saga execution per order (execution name = orderId); duplicates ignored and poison messages go to the DLQ"
      # Short timeout so the queue visibility timeout (6x) can be 60 s: a poison message reaches the DLQ in about 3 min.
      timeout = 10
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        STATE_MACHINE_ARN = local.state_machine_arn
        MAX_RECEIVE_COUNT = tostring(local.max_receive_count)
      }
    }
    reserve_inventory = {
      description = "Saga step - consumes the order's checkout hold, or reserves stock for all items in one DynamoDB transaction - raises OutOfStock if any item is short"
      environment = {
        ORDERS_TABLE    = aws_dynamodb_table.orders.name
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
        HOLDS_TABLE     = aws_dynamodb_table.holds.name
        SCHEDULE_GROUP  = aws_scheduler_schedule_group.holds.name
      }
    }
    request_payment = {
      description = "Saga step (waitForTaskToken) - stores the task token on payment intent PI-orderId and asks DemoPay to charge via SQS - the webhook resumes the saga"
      environment = {
        ORDERS_TABLE   = aws_dynamodb_table.orders.name
        PAYMENTS_TABLE = aws_dynamodb_table.payments.name
        PSP_QUEUE_URL  = aws_sqs_queue.psp_requests.url
      }
    }
    refund_payment = {
      description = "Saga COMPENSATION - refunds what is left of a charge, or single order lines, through DemoPay's idempotent refund API"
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        PAYMENTS_TABLE    = aws_dynamodb_table.payments.name
        PROVIDER_FUNCTION = local.payment_provider_name
      }
    }
    wallet_api = {
      description = "GET /wallet and POST /wallet/reset (JWT) - the caller's own DemoPay wallet (keyed by Cognito sub)"
      environment = {
        WALLETS_TABLE     = aws_dynamodb_table.wallets.name
        WALLET_TXNS_TABLE = aws_dynamodb_table.wallet_txns.name
      }
    }
    release_inventory = {
      description = "Saga COMPENSATION - idempotently returns the stock an order reserved when a later step fails"
      environment = {
        ORDERS_TABLE    = aws_dynamodb_table.orders.name
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
      }
    }
    payment_provider = {
      description = "Mock payment provider DemoPay (SQS order-saga-psp-requests) - debits once per payment intent then calls our webhook with an HMAC signature - also its idempotent refund API"
      timeout     = local.payment_provider_timeout
      environment = {
        PSP_TABLE                = aws_dynamodb_table.psp_transactions.name
        WALLETS_TABLE            = aws_dynamodb_table.wallets.name
        WALLET_TXNS_TABLE        = aws_dynamodb_table.wallet_txns.name
        WEBHOOK_URL              = local.webhook_url
        WEBHOOK_SECRET_PARAMETER = local.webhook_secret_parameter
      }
    }
    payment_webhook = {
      description = "POST /webhooks/payment (no JWT - HMAC-SHA256 signed) - idempotently records the payment outcome and resumes the saga (SendTaskSuccess/Failure) - refunds late payments"
      environment = {
        PAYMENTS_TABLE           = aws_dynamodb_table.payments.name
        ORDERS_TABLE             = aws_dynamodb_table.orders.name
        PROVIDER_FUNCTION        = local.payment_provider_name
        WEBHOOK_SECRET_PARAMETER = local.webhook_secret_parameter
      }
    }
    holds_api = {
      description = "POST /holds - GET /holds/current - DELETE /holds/{holdId} (JWT) - holds the caller's cart for 10 min in one transaction and schedules its exact expiry"
      environment = {
        HOLDS_TABLE          = aws_dynamodb_table.holds.name
        INVENTORY_TABLE      = aws_dynamodb_table.inventory.name
        SCHEDULE_GROUP       = aws_scheduler_schedule_group.holds.name
        EXPIRY_FUNCTION_ARN  = local.hold_expiry_function_arn
        SCHEDULER_ROLE_ARN   = aws_iam_role.scheduler.arn
        CLIENT_IDS_PARAMETER = local.client_ids_parameter
      }
    }
    hold_expiry = {
      description = "Invoked by EventBridge Scheduler at a hold's expiresAt - ACTIVE to EXPIRED and its stock back in one transaction - idempotent"
      environment = {
        HOLDS_TABLE     = aws_dynamodb_table.holds.name
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
      }
    }
    fulfill_item = {
      description = "Saga step (one Map iteration per order line) - picks one line after payment - reserved to sold - raises ItemUnavailable for a damaged line"
      environment = {
        ORDERS_TABLE    = aws_dynamodb_table.orders.name
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
      }
    }
    write_off_lines = {
      description = "Saga step - writes off the units of lines that could not be fulfilled - reserved to writtenOff plus an audit record - idempotent per line"
      environment = {
        ORDERS_TABLE     = aws_dynamodb_table.orders.name
        INVENTORY_TABLE  = aws_dynamodb_table.inventory.name
        WRITE_OFFS_TABLE = aws_dynamodb_table.write_offs.name
      }
    }
    cancel_order = {
      description = "POST /orders/{id}/cancel (JWT, owner only) - one conditional write decides cancel vs payment vs fulfillment - SendTaskFailure OrderCancelled on the payment token"
      environment = {
        ORDERS_TABLE   = aws_dynamodb_table.orders.name
        PAYMENTS_TABLE = aws_dynamodb_table.payments.name
        # Switched on in step 2.4 commit B, in the same apply as the state machine's cancel branch. Orders whose
        # execution runs an older definition are still refused (no `cancellable` stamp: 409 NOT_CANCELLABLE).
        CANCEL_ENABLED = "true"
      }
    }
    begin_fulfillment = {
      description = "Saga step - PAYMENT_CAPTURED to FULFILLING unless the customer cancelled first - after this the order can no longer be cancelled"
      environment = {
        ORDERS_TABLE = aws_dynamodb_table.orders.name
      }
    }
    invariant_auditor = {
      description = "Reconciliation job - audits invariants I1-I9 over orders - payments - DemoPay ledger and stock - hourly via EventBridge Scheduler - metrics OrderSaga/Audit - read-only"
      timeout     = 180 # two full audits (a few seconds each at this size) with a 10 s pause between them
      memory_size = 512 # holds every order and ledger entry in memory while reconciling
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        PAYMENTS_TABLE    = aws_dynamodb_table.payments.name
        PSP_TABLE         = aws_dynamodb_table.psp_transactions.name
        WALLET_TXNS_TABLE = aws_dynamodb_table.wallet_txns.name
        INVENTORY_TABLE   = aws_dynamodb_table.inventory.name
        WRITE_OFFS_TABLE  = aws_dynamodb_table.write_offs.name
        HOLDS_TABLE       = aws_dynamodb_table.holds.name
      }
    }
    pre_token = {
      description = "Cognito pre-token-generation trigger (V2_0) for order-saga-users - adds email + email_verified to ACCESS tokens"
      # Cognito waits at most 5 s for a trigger; the function makes no AWS calls and finishes in milliseconds.
      timeout     = 5
      environment = {} # no tables, no topics: it only reads the event Cognito sends
    }
  }

  # Step 3.2 chaos experiments (chaos.tf, src/common/chaos.py).
  # FIS targets: the saga Lambdas get the AWS FIS extension layer and its two variables. With no experiment running,
  # the extension only polls the S3 config prefix (every 60 s while the function is active) and changes nothing.
  fis_target_functions = toset([
    "reserve_inventory", "request_payment", "payment_provider", "payment_webhook", "fulfill_item",
    "refund_payment", "release_inventory", "write_off_lines", "begin_fulfillment",
  ])
  fis_environment = {
    AWS_LAMBDA_EXEC_WRAPPER        = "/opt/aws-fis/bootstrap"
    AWS_FIS_CONFIGURATION_LOCATION = "${aws_s3_bucket.fis_config.arn}/${local.fis_config_prefix}/"
  }
  # Functions with a crash-after-write switch (E3) or that pass the chaos field on. CHAOS_ENABLED is the Terraform
  # variable chaos_enabled: "false" unless a chaos run flips it for E3, and flipped back right after.
  chaos_switch_functions = toset([
    "create_order", "reserve_inventory", "request_payment", "payment_provider", "payment_webhook",
    "refund_payment", "fulfill_item", "write_off_lines", "release_inventory",
  ])
  lambda_environment = {
    for key, fn in local.lambda_functions : key => merge(
      fn.environment,
      contains(local.fis_target_functions, key) ? local.fis_environment : {},
      contains(local.chaos_switch_functions, key) ? { CHAOS_ENABLED = tostring(var.chaos_enabled) } : {},
    )
  }

  # order-saga-create-order, order-saga-get-order, ...
  lambda_names = { for key in keys(local.lambda_functions) : key => "${var.project_prefix}-${replace(key, "_", "-")}" }

  # Log groups of removed functions (step 2.1: process_payment was replaced by request_payment). Kept under
  # Terraform so removing a function never deletes its logs; the 7-day retention still ages them out.
  retired_log_groups = toset(["process_payment"])
}

# Each zip = the function's handler.py + the shared src/common package.
data "archive_file" "lambda" {
  for_each = local.lambda_functions

  type        = "zip"
  output_path = "${local.build_dir}/${each.key}.zip"

  source {
    content  = file("${local.src_dir}/lambdas/${each.key}/handler.py")
    filename = "handler.py"
  }

  dynamic "source" {
    for_each = fileset("${local.src_dir}/common", "*.py")
    content {
      content  = file("${local.src_dir}/common/${source.value}")
      filename = "common/${source.value}"
    }
  }
}

# Created by Terraform (not by Lambda on first run), so retention is enforced and the role
# doesn't need logs:CreateLogGroup.
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = setunion(keys(local.lambda_functions), local.retired_log_groups)

  name              = "/aws/lambda/${var.project_prefix}-${replace(each.key, "_", "-")}"
  retention_in_days = local.log_retention_days
}

resource "aws_lambda_function" "fn" {
  for_each = local.lambda_functions

  function_name    = local.lambda_names[each.key]
  description      = each.value.description
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = "python3.12"
  architectures    = ["arm64"] # Graviton: about 20% cheaper per GB-second than x86
  handler          = "handler.lambda_handler"
  layers           = contains(local.fis_target_functions, each.key) ? [local.powertools_layer_arn, local.fis_extension_layer_arn] : [local.powertools_layer_arn]
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  timeout          = try(each.value.timeout, local.default_lambda_timeout)
  memory_size      = try(each.value.memory_size, 256)

  # Omitted when a function needs no variables (an empty block shows up as a change on every plan).
  dynamic "environment" {
    for_each = length(local.lambda_environment[each.key]) > 0 ? [local.lambda_environment[each.key]] : []
    content {
      variables = environment.value
    }
  }

  tracing_config {
    mode = "Active" # X-Ray
  }

  logging_config {
    log_format = "Text" # the handlers already write their own JSON lines
    log_group  = aws_cloudwatch_log_group.lambda[each.key].name
  }

  # ChaosTarget = saga marks the FIS targets (chaos.tf): experiment E1 selects all of them by this tag.
  tags = merge({ Name = local.lambda_names[each.key] }, contains(local.fis_target_functions, each.key) ? { ChaosTarget = "saga" } : {})

  depends_on = [aws_iam_role_policy.lambda]
}
