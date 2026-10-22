locals {
  src_dir   = "${path.module}/../../src"
  build_dir = "${path.module}/../../build"

  default_lambda_timeout = 30

  # One entry per function. The key is the folder under src/lambdas/.
  # `timeout` is optional (default 30 s).
  lambda_functions = {
    create_order = {
      description = "POST /orders - idempotent (Idempotency-Key): validates and prices the order, saves it as PENDING and enqueues it on SQS"
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        INVENTORY_TABLE   = aws_dynamodb_table.inventory.name
        IDEMPOTENCY_TABLE = aws_dynamodb_table.idempotency.name
        ORDERS_QUEUE_URL  = aws_sqs_queue.orders.url
      }
    }
    get_order = {
      description = "GET /orders/{id} - returns an order and its statusHistory timeline"
      environment = {
        ORDERS_TABLE = aws_dynamodb_table.orders.name
      }
    }
    start_workflow = {
      description = "SQS consumer - starts exactly one saga execution per order (execution name = orderId); duplicates ignored and poison messages go to the DLQ"
      # Short timeout so the queue visibility timeout (6x) can be 60 s: a poison message reaches the DLQ in about 3 min.
      timeout = 10
      environment = {
        ORDERS_TABLE      = aws_dynamodb_table.orders.name
        STATE_MACHINE_ARN = local.state_machine_arn
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
      description = "Saga step - simulated payment (none / payment_declined / payment_flaky); never charges an order twice"
      environment = {
        ORDERS_TABLE = aws_dynamodb_table.orders.name
      }
    }
    release_inventory = {
      description = "Saga COMPENSATION - idempotently returns the stock an order reserved when a later step fails"
      environment = {
        ORDERS_TABLE    = aws_dynamodb_table.orders.name
        INVENTORY_TABLE = aws_dynamodb_table.inventory.name
      }
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
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  timeout          = try(each.value.timeout, local.default_lambda_timeout)
  memory_size      = 256

  environment {
    variables = each.value.environment
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
