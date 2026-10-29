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
    PAYMENTS_TABLE="test-payments",
    PSP_TABLE="test-psp-transactions",
    WEBHOOK_SECRET_PARAMETER="/test/psp/webhook-secret",
    WEBHOOK_URL="https://example.invalid/webhooks/payment",
    PROVIDER_FUNCTION="test-payment-provider",
    PSP_QUEUE_URL="https://sqs.ap-south-1.amazonaws.com/123456789012/test-psp-requests",
)
WEBHOOK_SECRET = "test-webhook-secret-0123456789abcdef"

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
        payments = ddb.create_table(
            TableName="test-payments",
            KeySchema=[{"AttributeName": "paymentIntentId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "paymentIntentId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        psp = ddb.create_table(
            TableName="test-psp-transactions",
            KeySchema=[{"AttributeName": "pspTxnId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pspTxnId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        for product in PRODUCTS:
            inventory.put_item(Item=product)

        boto3.client("ssm", region_name=REGION).put_parameter(
            Name="/test/psp/webhook-secret", Value=WEBHOOK_SECRET, Type="SecureString"
        )
        from common import secrets as secret_cache  # a fresh cache per test (it lives in the module)

        secret_cache.clear_cache()

        # create_order no longer uses SQS (transactional outbox), so its env var is NOT set. The queue
        # exists only so tests can assert that nothing was ever sent to it.
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="test-orders-queue")["QueueUrl"]
        psp_queue_url = sqs.create_queue(QueueName="test-psp-requests")["QueueUrl"]

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
            payments=payments,
            psp=psp,
            sqs=sqs,
            queue_url=queue_url,
            psp_queue_url=psp_queue_url,
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


# --- Async payments (step 2.1) ---------------------------------------------------------------------
class FakeSfn:
    """Stands in for the Step Functions client: records SendTaskSuccess/Failure, optionally fails with `error`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.error: str | None = None

    def send_task_success(self, **kwargs):
        return self._call("success", kwargs)

    def send_task_failure(self, **kwargs):
        return self._call("failure", kwargs)

    def _call(self, kind, kwargs):
        self.calls.append((kind, kwargs))
        if self.error:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": self.error, "Message": "simulated"}}, f"SendTask{kind.title()}")
        return {}


def seed_intent(aws, order, status="REQUESTED", token="task-token-1", **extra) -> dict:
    """A payment intent for `order` (as request_payment would have written it)."""
    intent = {
        "paymentIntentId": f"PI-{order['orderId']}",
        "orderId": order["orderId"],
        "userId": order["userId"],
        "walletId": order["walletId"],
        "amount": order["totalAmount"],
        "currency": "INR",
        "status": status,
        "taskToken": token,
        "requestAttempts": 1,
        "requestedAt": "2026-10-29T10:00:00.000Z",
        "createdAt": "2026-10-29T10:00:00.000Z",
        "updatedAt": "2026-10-29T10:00:00.000Z",
        **extra,
    }
    aws.payments.put_item(Item=intent)
    return intent


def webhook_event(body, secret=WEBHOOK_SECRET, timestamp=None, headers=None, base64_body=False) -> dict:
    """An API Gateway (payload v2) event for POST /webhooks/payment, signed with `secret` unless headers given."""
    import base64

    from common.signing import signed_headers

    raw = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
    if headers is None:
        headers = signed_headers(secret, raw) if timestamp is None else signed_headers(secret, raw, now=timestamp)
        headers = {k.lower(): v for k, v in headers.items()}  # HTTP APIs lower-case header names
    return {
        "headers": {"content-type": "application/json", **headers},
        "body": base64.b64encode(raw).decode() if base64_body else raw.decode(),
        "isBase64Encoded": base64_body,
        "requestContext": {"requestId": "test-request", "http": {"sourceIp": "203.0.113.7"}},
    }


@pytest.fixture
def payments(aws, load_handler, monkeypatch):
    """provider + webhook wired together in-process: DemoPay's callbacks call the webhook handler directly,
    and the webhook's refund calls go straight to DemoPay's refund function (no HTTP, no Lambda invoke)."""
    provider = load_handler("payment_provider")
    webhook = load_handler("payment_webhook")
    fake_sfn = FakeSfn()
    monkeypatch.setattr(webhook, "sfn", fake_sfn)
    monkeypatch.setattr(webhook, "invoke_provider_refund", lambda _client, _fn, intent_id: provider.refund(intent_id))

    sent: list[dict] = []

    def deliver(body: bytes, secret: str) -> int:
        from common.signing import signed_headers

        headers = {k.lower(): v for k, v in signed_headers(secret, body).items()}
        result = webhook.lambda_handler(webhook_event(body, headers=headers), None)
        sent.append({"body": json.loads(body), "status": result["statusCode"], "result": json.loads(result["body"])})
        return result["statusCode"]

    monkeypatch.setattr(provider, "post_callback", deliver)
    return SimpleNamespace(provider=provider, webhook=webhook, sfn=fake_sfn, callbacks=sent)


def psp_request(order, simulate="none", **overrides) -> dict:
    return {
        "paymentIntentId": f"PI-{order['orderId']}",
        "orderId": order["orderId"],
        "walletId": order["walletId"],
        "amount": str(order["totalAmount"]),
        "currency": "INR",
        "simulate": simulate,
        **overrides,
    }


def sqs_event(*requests, receive_count=1) -> dict:
    return {
        "Records": [
            {"messageId": f"m-{i}", "body": json.dumps(r), "attributes": {"ApproximateReceiveCount": str(receive_count)}}
            for i, r in enumerate(requests)
        ]
    }


def ledger(aws, wallet_id=USER_A) -> list[tuple[str, Decimal]]:
    """[(type, amount)] of a wallet's ledger, oldest first."""
    items = aws.wallet_txns.query(KeyConditionExpression="walletId = :w", ExpressionAttributeValues={":w": wallet_id})["Items"]
    return [(t["type"], t["amount"]) for t in items]
