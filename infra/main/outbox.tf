# =============================================================================
# Transactional outbox: the order row IS the outbox.
#
#   create_order --(one DynamoDB transaction)--> order-saga-orders (status PENDING)
#        order-saga-orders stream (NEW_IMAGE) --> pipe order-saga-orders-outbox --> order-saga-orders-queue
#
# Before this, create_order wrote the order and THEN called SQS SendMessage. A crash between the two
# left the order PENDING forever (the "dual write" problem). Now the only write the API makes is the
# DynamoDB transaction. If it commits, the stream has the INSERT and the pipe delivers it, at least once.
# Duplicate deliveries are harmless: start_workflow names the execution after the orderId.
# =============================================================================

locals {
  outbox_pipe_name = "${var.project_prefix}-orders-outbox"
  outbox_pipe_arn  = "arn:aws:pipes:${var.region}:${local.account_id}:pipe/${local.outbox_pipe_name}"
}

# Records the pipe gave up on (retries exhausted or older than the max record age).
resource "aws_sqs_queue" "outbox_dlq" {
  name                      = "${var.project_prefix}-outbox-dlq"
  message_retention_seconds = 14 * 24 * 60 * 60 # 14 days, the SQS maximum
  sqs_managed_sse_enabled   = true

  tags = {
    Name        = "${var.project_prefix}-outbox-dlq"
    Description = module.tags.description["outbox_dlq"]
  }
}

# -----------------------------------------------------------------------------
# Pipe execution role: read THIS stream, send to the orders queue and the outbox DLQ. Nothing else.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "outbox_pipe_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["pipes.amazonaws.com"]
    }
    # Only this pipe in this account may use the role (confused-deputy protection).
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.outbox_pipe_arn]
    }
  }
}

data "aws_iam_policy_document" "outbox_pipe" {
  statement {
    sid       = "ReadOrdersStream"
    actions   = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"]
    resources = [aws_dynamodb_table.orders.stream_arn]
  }
  statement {
    sid       = "DeliverToOrdersQueueAndOutboxDlq"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.orders.arn, aws_sqs_queue.outbox_dlq.arn]
  }
}

resource "aws_iam_role" "outbox_pipe" {
  name               = "${local.outbox_pipe_name}-role"
  description        = "Execution role of pipe ${local.outbox_pipe_name}: reads the orders table stream, sends to the orders queue and the outbox DLQ"
  assume_role_policy = data.aws_iam_policy_document.outbox_pipe_assume.json
}

resource "aws_iam_role_policy" "outbox_pipe" {
  name   = "${local.outbox_pipe_name}-policy"
  role   = aws_iam_role.outbox_pipe.id
  policy = data.aws_iam_policy_document.outbox_pipe.json
}

# -----------------------------------------------------------------------------
# The pipe
# -----------------------------------------------------------------------------
resource "aws_pipes_pipe" "outbox" {
  name        = local.outbox_pipe_name
  description = "Transactional outbox: every NEW order row (stream INSERT, status PENDING) becomes one {orderId} message on ${aws_sqs_queue.orders.name}"
  role_arn    = aws_iam_role.outbox_pipe.arn

  source = aws_dynamodb_table.orders.stream_arn
  target = aws_sqs_queue.orders.arn

  desired_state = "RUNNING"

  source_parameters {
    dynamodb_stream_parameters {
      # TRIM_HORIZON, not LATEST: AWS warns a pipe can miss events for several minutes after it is
      # created or its polling settings change when it starts at LATEST. The stream only keeps 24 h,
      # and any record read twice is a harmless duplicate (see the header comment).
      starting_position = "TRIM_HORIZON"

      # One record per invocation = exactly one SQS message per new order.
      batch_size = 1

      # Bounded retries: give up after 5 failed deliveries or once a record is 1 h old, then send the
      # record's details to the outbox DLQ. 1 h is far below the stream's 24 h retention, which leaves
      # ~23 h to inspect the record in the stream after it is dead-lettered.
      maximum_retry_attempts        = 5
      maximum_record_age_in_seconds = 3600

      dead_letter_config {
        arn = aws_sqs_queue.outbox_dlq.arn
      }
    }

    # Only brand-new orders. Every saga step writes a MODIFY to the same row; those must never re-enter
    # the queue. status = PENDING is a second guard (a new row is always PENDING).
    filter_criteria {
      filter {
        pattern = jsonencode({
          eventName = ["INSERT"]
          dynamodb  = { NewImage = { status = { S = ["PENDING"] } } }
        })
      }
    }
  }

  target_parameters {
    # Exactly the body create_order's json.dumps({"orderId": ...}) produced, so start_workflow is unchanged.
    input_template = "{\"orderId\": \"<$.dynamodb.NewImage.orderId.S>\"}"
  }

  tags = {
    Name        = local.outbox_pipe_name
    Description = module.tags.description["outbox_pipe"]
  }

  depends_on = [aws_iam_role_policy.outbox_pipe]
}
