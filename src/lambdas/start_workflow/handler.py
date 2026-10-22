"""SQS consumer: start one Step Functions saga execution per queued order.

The function is triggered by order-saga-orders-queue with batches of up to 10 messages. It uses
ReportBatchItemFailures, so only the messages that failed are retried, never the whole batch.
After 3 failed receives, SQS moves a message to the dead-letter queue.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from common.logger import get_logger
from common.orders import PROCESSING, status_update

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
sfn = boto3.client("stepfunctions")
logger = get_logger("start_workflow")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            start_saga(record)
        except Exception:
            logger.bind(messageId=record.get("messageId")).exception(
                "Could not start workflow; message will be retried"
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def execution_arn_for(order_id: str) -> str:
    """The execution is named after the order, so its ARN is known before it starts."""
    return f"{STATE_MACHINE_ARN.replace(':stateMachine:', ':execution:')}:{order_id}"


def start_saga(record: dict[str, Any]) -> None:
    order_id = json.loads(record["body"])["orderId"]
    log = logger.bind(orderId=order_id, messageId=record["messageId"])

    # Phase 2: the "poison" simulation hook goes here (it raises, so the message ends up in the DLQ).

    execution_arn = execution_arn_for(order_id)

    # Mark PROCESSING *before* starting the execution. That way the first saga step can never
    # write its status ahead of this one, and the statusHistory timeline always stays in order.
    orders_table.update_item(
        Key={"orderId": order_id},
        **status_update(PROCESSING, "Saga workflow started", {"executionArn": execution_arn}),
    )

    try:
        sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=order_id,  # unique per state machine, so this is also an idempotency guard
            input=json.dumps({"orderId": order_id}),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        # SQS is at-least-once: a redelivered message must not start a second saga.
        log.info("Execution already exists; duplicate delivery ignored", executionArn=execution_arn)
        return

    log.info("Saga execution started", executionArn=execution_arn)
