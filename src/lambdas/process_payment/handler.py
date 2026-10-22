"""Saga step 2: take the payment. It's simulated; no real payment provider is called.

The order's `simulate` field picks a behaviour, which lets every saga path be shown on demand.
Phase 1 implements "none" (the payment succeeds). Phase 2 adds:
  - "payment_declined": raise PaymentDeclined, a permanent error that triggers compensation
  - "payment_flaky":    raise PaymentTransientError twice, then succeed (shows SFN retries)
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Callable

import boto3

from common.logger import get_logger
from common.orders import PAYMENT_CAPTURED, status_update

ORDERS_TABLE = os.environ["ORDERS_TABLE"]

orders_table = boto3.resource("dynamodb").Table(ORDERS_TABLE)
logger = get_logger("process_payment")


def capture_payment(order_id: str, amount: str, currency: str) -> dict[str, str]:
    """Return a successful (fake) payment authorisation and capture."""
    return {"paymentId": f"PAY-{uuid.uuid4().hex[:12]}", "status": "CAPTURED"}


# Maps each simulate mode to its payment behaviour. Phase 2 registers the failure modes here.
SIMULATIONS: dict[str, Callable[[str, str, str], dict[str, str]]] = {
    "none": capture_payment,
}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    order_id = event["orderId"]
    amount, currency = event["amount"], event["currency"]
    simulate = event.get("simulate") or "none"
    log = logger.bind(orderId=order_id, simulate=simulate)

    behaviour = SIMULATIONS.get(simulate)
    if behaviour is None:
        log.warning("Simulation mode not implemented yet; capturing normally")
        behaviour = capture_payment

    payment = behaviour(order_id, amount, currency)

    orders_table.update_item(
        Key={"orderId": order_id},
        **status_update(
            PAYMENT_CAPTURED,
            f"Payment {payment['paymentId']} captured: {currency} {amount}",
            {"paymentId": payment["paymentId"]},
        ),
    )
    log.info("Payment captured", paymentId=payment["paymentId"], amount=amount, currency=currency)
    return payment
