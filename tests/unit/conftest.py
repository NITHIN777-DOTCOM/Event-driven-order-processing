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
    IDEMPOTENCY_TABLE="test-idempotency",
    WALLETS_TABLE="test-wallets",
    WALLET_TXNS_TABLE="test-wallet-txns",
    STATE_MACHINE_ARN=f"arn:aws:states:{REGION}:123456789012:stateMachine:test-workflow",
)

PRODUCTS = [
    {"productId": "WIRELESS-MOUSE", "name": "Wireless Mouse", "price": Decimal("799.00"), "stock": 100, "reserved": 0},
    {"productId": "MECH-KEYBOARD", "name": "Mechanical Keyboard", "price": Decimal("3499.00"), "stock": 2, "reserved": 0},
]


@pytest.fixture
def aws():
    """Mocked DynamoDB tables (inventory seeded), an SQS queue and a Step Functions state machine."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        orders = ddb.create_table(
            TableName="test-orders",
            KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "orderId", "AttributeType": "S"},
                {"AttributeName": "gsi1pk", "AttributeType": "S"},
                {"AttributeName": "gsi1sk", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        inventory = ddb.create_table(
            TableName="test-inventory",
            KeySchema=[{"AttributeName": "productId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "productId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        idempotency = ddb.create_table(
            TableName="test-idempotency",
            KeySchema=[{"AttributeName": "idempotencyKey", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "idempotencyKey", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        wallets = ddb.create_table(
            TableName="test-wallets",
            KeySchema=[{"AttributeName": "walletId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "walletId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        wallet_txns = ddb.create_table(
            TableName="test-wallet-txns",
            KeySchema=[
                {"AttributeName": "walletId", "KeyType": "HASH"},
                {"AttributeName": "txnId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "walletId", "AttributeType": "S"},
                {"AttributeName": "txnId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        for product in PRODUCTS:
            inventory.put_item(Item=product)

        # create_order no longer uses SQS (transactional outbox), so its env var is NOT set. The queue
        # exists only so tests can assert that nothing was ever sent to it.
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="test-orders-queue")["QueueUrl"]

        sfn = boto3.client("stepfunctions", region_name=REGION)
        state_machine_arn = sfn.create_state_machine(
            name="test-workflow",
            definition=json.dumps({"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}),
            roleArn="arn:aws:iam::123456789012:role/test-sfn-role",
        )["stateMachineArn"]

        yield SimpleNamespace(
            orders=orders,
            inventory=inventory,
            idempotency=idempotency,
            wallets=wallets,
            wallet_txns=wallet_txns,
            sqs=sqs,
            queue_url=queue_url,
            sfn=sfn,
            state_machine_arn=state_machine_arn,
        )


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


# Two signed-in users. In production the ids are Cognito "sub" values from the verified JWT.
USER_A, EMAIL_A = "11111111-aaaa-4aaa-8aaa-111111111111", "asha@example.com"
USER_B, EMAIL_B = "22222222-bbbb-4bbb-8bbb-222222222222", "bilal@example.com"


def jwt_claims(user_id=USER_A, email=EMAIL_A, verified="true", token_use="access") -> dict:
    """What API Gateway's JWT authorizer puts in the event after verifying a Cognito token (all values strings).
    Default: an access token, with the email + email_verified the pre-token trigger adds (step 2.0)."""
    claims = {"sub": user_id, "token_use": token_use}
    if token_use == "access":
        claims.update(client_id="test-client", scope="openid email profile")
    else:
        claims.update(aud="test-client")
    if email is not None:
        claims["email"] = email
    if verified is not None:
        claims["email_verified"] = verified
    return claims


def api_event(body=None, path_parameters=None, headers=None, claims="default", route_key=None, query=None) -> dict:
    """Return a minimal API Gateway HTTP API (payload v2.0) event, signed in as user A by default.
    claims=None builds an event with no authorizer context (a route deployed without the authorizer)."""
    context = {"requestId": "test-request"}
    if claims is not None:
        context["authorizer"] = {"jwt": {"claims": jwt_claims() if claims == "default" else claims}}
    event = {
        "headers": headers or {},
        "body": json.dumps(body) if isinstance(body, (dict, list)) else body,
        "isBase64Encoded": False,
        "pathParameters": path_parameters,
        "queryStringParameters": query,
        "requestContext": context,
    }
    if route_key:
        event["routeKey"] = route_key
    return event


def stock_of(aws, product_id) -> tuple[int, int]:
    """(stock, reserved) of a product."""
    item = aws.inventory.get_item(Key={"productId": product_id})["Item"]
    return int(item["stock"]), int(item["reserved"])


def wallet_of(aws, wallet_id=USER_A) -> tuple:
    """(balance, [ledger entry types, oldest first]) of a wallet; (None, []) if it doesn't exist."""
    wallet = aws.wallets.get_item(Key={"walletId": wallet_id}).get("Item")
    txns = aws.wallet_txns.query(KeyConditionExpression="walletId = :w", ExpressionAttributeValues={":w": wallet_id})["Items"]
    return (wallet["balance"] if wallet else None), [t["type"] for t in txns]


def seed_order(orders_table, **overrides) -> dict:
    """Write a PENDING order (2 mice + 1 keyboard) straight into the orders table."""
    order = {
        "orderId": "ORD-20261022-abcdef12",
        "userId": USER_A,
        "walletId": USER_A,
        "customerName": "Asha Rao",
        "customerEmail": EMAIL_A,
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
