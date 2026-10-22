"""Shared pytest fixtures. Every AWS call is served by moto in memory, so no real AWS is touched."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import boto3
import pytest
from moto import mock_aws

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))  # makes `import common...` work just like it does inside the Lambda zip

REGION = "ap-south-1"

# Fake credentials and the env vars the handlers read at import time.
os.environ.update(
    AWS_DEFAULT_REGION=REGION,
    AWS_ACCESS_KEY_ID="testing",
    AWS_SECRET_ACCESS_KEY="testing",
    AWS_SESSION_TOKEN="testing",
    ORDERS_TABLE="test-orders",
    INVENTORY_TABLE="test-inventory",
    STATE_MACHINE_ARN=f"arn:aws:states:{REGION}:123456789012:stateMachine:test-workflow",
)

PRODUCTS = [
    {"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "price": Decimal("799.00"), "stock": 100, "reserved": 0},
    {"productId": "MECH-KEYBOARD", "name": "Mechanical Keyboard", "price": Decimal("3499.00"), "stock": 2, "reserved": 0},
]


@pytest.fixture
def aws():
    """Mocked DynamoDB tables (inventory seeded) and an SQS queue."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        orders = ddb.create_table(
            TableName="test-orders",
            KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "orderId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        inventory = ddb.create_table(
            TableName="test-inventory",
            KeySchema=[{"AttributeName": "productId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "productId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        for product in PRODUCTS:
            inventory.put_item(Item=product)

        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="test-orders-queue")["QueueUrl"]
        os.environ["ORDERS_QUEUE_URL"] = queue_url

        yield SimpleNamespace(orders=orders, inventory=inventory, sqs=sqs, queue_url=queue_url)


@pytest.fixture
def load_handler(aws):
    """Import a Lambda's handler.py inside the moto context (handlers create clients at import)."""

    def _load(name: str) -> ModuleType:
        path = SRC / "lambdas" / name / "handler.py"
        spec = importlib.util.spec_from_file_location(f"{name}_handler", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return _load


def api_event(body=None, path_parameters=None) -> dict:
    """Return a minimal API Gateway HTTP API (payload v2.0) event."""
    return {
        "body": json.dumps(body) if isinstance(body, (dict, list)) else body,
        "isBase64Encoded": False,
        "pathParameters": path_parameters,
        "requestContext": {"requestId": "test-request"},
    }


def seed_order(orders_table, **overrides) -> dict:
    """Write a PENDING order (2 mice + 1 keyboard) straight into the orders table."""
    order = {
        "orderId": "ORD-20261022-abcdef12",
        "customerName": "Asha Rao",
        "customerEmail": "asha@example.com",
        "items": [
            {"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "quantity": 2, "unitPrice": Decimal("799.00")},
            {"productId": "MECH-KEYBOARD", "name": "Mechanical Keyboard", "quantity": 1, "unitPrice": Decimal("3499.00")},
        ],
        "totalAmount": Decimal("5097.00"),
        "currency": "INR",
        "status": "PENDING",
        "statusHistory": [{"status": "PENDING", "timestamp": "2026-10-22T10:00:00.000Z", "detail": "test"}],
        "simulate": "none",
        "createdAt": "2026-10-22T10:00:00.000Z",
        "updatedAt": "2026-10-22T10:00:00.000Z",
        **overrides,
    }
    orders_table.put_item(Item=order)
    return order
