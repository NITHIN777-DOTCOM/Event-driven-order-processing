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
      description = "Saga step - reserves stock for all items in one DynamoDB transaction and raises OutOfStock if any item is short"
      environment = {
        ORDERS_TABLE    = aws_dynamodb_table.orders.name
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
      }
    }
    process_payment = {
      description = "Saga step - debits the DemoPay wallet atomically with the order (never twice); declines on low balance"
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        WALLETS_TABLE     = aws_dynamodb_table.wallets.name
        WALLET_TXNS_TABLE = aws_dynamodb_table.wallet_txns.name
      }
    }
    refund_payment = {
      description = "Saga COMPENSATION - idempotently refunds a wallet debit when a later step fails"
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        WALLETS_TABLE     = aws_dynamodb_table.wallets.name
        WALLET_TXNS_TABLE = aws_dynamodb_table.wallet_txns.name
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
    pre_token = {
      description = "Cognito pre-token-generation trigger (V2_0) for order-saga-users - adds email + email_verified to ACCESS tokens"
      # Cognito waits at most 5 s for a trigger; the function makes no AWS calls and finishes in milliseconds.
      timeout     = 5
      environment = {} # no tables, no topics: it only reads the event Cognito sends
    }
  }

  # order-saga-create-order, order-saga-get-order, ...
  lambda_names = { for key in keys(local.lambda_functions) : key => "${var.project_prefix}-${replace(key, "_", "-")}" }
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
  for_each = local.lambda_functions

  name              = "/aws/lambda/${local.lambda_names[each.key]}"
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
  layers           = [local.powertools_layer_arn]
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  timeout          = try(each.value.timeout, local.default_lambda_timeout)
  memory_size      = 256

  # Omitted when a function needs no variables (an empty block shows up as a change on every plan).
  dynamic "environment" {
    for_each = length(each.value.environment) > 0 ? [each.value.environment] : []
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

  tags = {
    Name = local.lambda_names[each.key]
  }

  depends_on = [aws_iam_role_policy.lambda]
}
