"""SQS consumer: start exactly one Step Functions saga execution per order.

The function is triggered by order-saga-orders-queue with batches of up to 10 messages. It uses
ReportBatchItemFailures, so only the messages that failed are retried, never the whole batch.
After 3 failed receives, SQS moves a message to the dead-letter queue order-saga-orders-dlq.

SQS delivers at-least-once, so the same order can arrive more than once. Two guards stop that
from ever starting a second saga:
  1. The PENDING -> PROCESSING update is conditional on the order still being PENDING.
  2. The execution is named after the orderId, and Step Functions refuses a second execution
     with the same name (ExecutionAlreadyExists).
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logger import get_logger
from common.orders import PENDING, PROCESSING, status_update

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
sfn = boto3.client("stepfunctions")
logger = get_logger("start_workflow")


class PoisonMessage(Exception):
    """A message that can never be processed. It goes back to SQS and ends up in the DLQ."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            start_saga(record)
        except Exception as err:
            logger.bind(orderId=_order_id_of(record), messageId=record.get("messageId")).exception(
                "Could not start workflow; message returned to the queue for retry",
                errorType=type(err).__name__,
                receiveCount=record.get("attributes", {}).get("ApproximateReceiveCount"),
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def _order_id_of(record: dict[str, Any]) -> str | None:
    """Best-effort orderId for logging, even when the body is malformed."""
    try:
        return json.loads(record["body"])["orderId"]
    except (KeyError, TypeError, ValueError):
        return None


def execution_arn_for(order_id: str) -> str:
    """The execution is named after the order, so its ARN is known before it starts."""
    return f"{STATE_MACHINE_ARN.replace(':stateMachine:', ':execution:')}:{order_id}"


def start_saga(record: dict[str, Any]) -> None:
    order_id = json.loads(record["body"])["orderId"]
    log = logger.bind(orderId=order_id, messageId=record["messageId"])

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item")
    if order is None:
        raise PoisonMessage(f"Order {order_id} does not exist")

    # Demo: a message that always fails. SQS retries it 3 times, then moves it to the DLQ.
    # The order stays PENDING, because the saga is never started.
    if order.get("simulate") == "poison":
        raise PoisonMessage(f"Simulated poison message for order {order_id}")

    execution_arn = execution_arn_for(order_id)

    if order["status"] == PENDING:
        mark_processing(order_id, execution_arn)
    elif execution_exists(execution_arn):
        # The order was already picked up and its execution exists: a duplicate delivery.
        log.info("Duplicate message ignored: saga already started", executionArn=execution_arn)
        return
    # Otherwise the order is PROCESSING but StartExecution never succeeded (an earlier attempt
    # failed half-way), so fall through and start it now.

    try:
        sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=order_id,
            input=json.dumps({"orderId": order_id}),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        log.info("Duplicate message ignored: execution already exists", executionArn=execution_arn)
        return

    log.info("Saga execution started", executionArn=execution_arn)


def mark_processing(order_id: str, execution_arn: str) -> None:
    """Move PENDING -> PROCESSING *before* starting the execution, so the first saga step can't
    write its status ahead of this one and the statusHistory timeline always stays in order."""
    try:
        orders_table.update_item(
            Key={"orderId": order_id},
            **status_update(
                PROCESSING,
                "Saga workflow started",
                {"executionArn": execution_arn},
                condition="#status = :pending",
                condition_values={":pending": PENDING},
            ),
        )
    except ClientError as err:
        # A concurrent duplicate got here first. That's fine: StartExecution below is idempotent.
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def execution_exists(execution_arn: str) -> bool:
    try:
        sfn.describe_execution(executionArn=execution_arn)
        return True
    except sfn.exceptions.ExecutionDoesNotExist:
        return False
