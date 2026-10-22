"""Saga step 2: take the payment. It's simulated; no real payment provider is called.

The order's `simulate` field picks a behaviour, which lets every saga path be shown on demand:
  - "none"             : the payment is captured
  - "payment_declined" : raises PaymentDeclined, a permanent error. Step Functions does NOT retry it;
                         it runs compensation (ReleaseInventory) instead.
  - "payment_flaky"    : raises PaymentTransientError on attempts 1 and 2 and succeeds on attempt 3.
                         Step Functions retries it with exponential backoff.

No double charge: if the order already has a paymentId, that payment is returned and nothing
is charged again. The capture itself is conditional on there being no paymentId yet.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Callable

import boto3
from botocore.exceptions import ClientError

from common.logger import StructuredLogger, get_logger
from common.orders import PAYMENT_CAPTURED, PAYMENT_RETRY, status_update
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

ORDERS_TABLE = os.environ["ORDERS_TABLE"]

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
logger = get_logger("process_payment")

FLAKY_FAILURES = 2  # payment_flaky fails this many times before succeeding


class PaymentDeclined(Exception):
    """Permanent failure: the card was declined. Caught by the state machine, which compensates."""


class PaymentTransientError(Exception):
    """Temporary failure (e.g. a gateway timeout). The state machine retries it."""


def capture_payment(order_id: str, attempt: int) -> dict[str, str]:
    """Return a successful (fake) payment authorisation and capture."""
    return {"paymentId": f"PAY-{uuid.uuid4().hex[:12]}", "status": "CAPTURED"}


def decline_payment(order_id: str, attempt: int) -> dict[str, str]:
    raise PaymentDeclined("Card declined by issuer (simulated)")


def flaky_payment(order_id: str, attempt: int) -> dict[str, str]:
    if attempt <= FLAKY_FAILURES:
        raise PaymentTransientError(f"Payment gateway timeout on attempt {attempt} (simulated)")
    return capture_payment(order_id, attempt)


# Maps each simulate mode to its payment behaviour.
SIMULATIONS: dict[str, Callable[[str, int], dict[str, str]]] = {
    "none": capture_payment,
    "payment_declined": decline_payment,
    "payment_flaky": flaky_payment,
}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    order_id = event["orderId"]
    amount, currency = event["amount"], event["currency"]
    simulate = event.get("simulate") or "none"
    log = logger.bind(orderId=order_id, simulate=simulate)

    order = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]
    if order.get("paymentId"):
        log.info("Order already paid; returning the existing payment (no second charge)", paymentId=order["paymentId"])
        return {"paymentId": order["paymentId"], "status": "CAPTURED"}

    attempt = record_attempt(order_id)
    log = log.bind(attempt=attempt)
    behaviour = SIMULATIONS.get(simulate, capture_payment)

    try:
        payment = behaviour(order_id, attempt)
    except PaymentTransientError as err:
        log.warning("Transient payment failure; Step Functions will retry", reason=str(err))
        orders_table.update_item(
            Key={"orderId": order_id},
            **status_update(PAYMENT_RETRY, f"Attempt {attempt} failed: {err} - retrying"),
        )
        raise
    except PaymentDeclined as err:
        log.warning("Payment declined; saga will compensate", reason=str(err))
        raise

    return save_capture(order_id, payment, amount, currency, attempt, log)


def record_attempt(order_id: str) -> int:
    """Atomically increment paymentAttempts and return the new value (1 on the first attempt)."""
    result = orders_table.update_item(
        Key={"orderId": order_id},
        UpdateExpression="ADD paymentAttempts :one",
        ConditionExpression="attribute_exists(orderId)",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"]["paymentAttempts"])


def save_capture(
    order_id: str,
    payment: dict[str, str],
    amount: str,
    currency: str,
    attempt: int,
    log: StructuredLogger,
) -> dict[str, str]:
    """Record the capture, but only if no other attempt has already recorded one."""
    try:
        orders_table.update_item(
            Key={"orderId": order_id},
            **status_update(
                PAYMENT_CAPTURED,
                f"Payment {payment['paymentId']} captured: {currency} {amount} (attempt {attempt})",
                {"paymentId": payment["paymentId"]},
                condition="attribute_not_exists(paymentId)",
            ),
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        existing = orders_table.get_item(Key={"orderId": order_id}, ConsistentRead=True)["Item"]["paymentId"]
        log.info("Concurrent attempt already captured payment; returning it", paymentId=existing)
        return {"paymentId": existing, "status": "CAPTURED"}

    log.info("Payment captured", paymentId=payment["paymentId"], amount=amount, currency=currency)
    return payment
