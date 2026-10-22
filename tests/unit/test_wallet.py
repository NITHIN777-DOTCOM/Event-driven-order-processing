"""refund_payment (idempotent compensation) and the wallet API."""

import json
from decimal import Decimal

import pytest

from conftest import seed_order, wallet_of

EMAIL = "asha@example.com"


@pytest.fixture
def payment(load_handler):
    return load_handler("process_payment")


@pytest.fixture
def refund(load_handler):
    return load_handler("refund_payment")


@pytest.fixture
def api(load_handler):
    return load_handler("wallet_api")


def paid_order(aws, payment):
    order = seed_order(aws.orders)
    payment.lambda_handler({"orderId": order["orderId"], "simulate": "none"}, None)
    return order


def test_refund_credits_wallet_once(aws, payment, refund):
    order = paid_order(aws, payment)

    first = refund.lambda_handler({"orderId": order["orderId"]}, None)
    second = refund.lambda_handler({"orderId": order["orderId"]}, None)

    assert first["refunded"] is True
    assert second == {"orderId": order["orderId"], "refunded": False, "reason": "already refunded"}
    assert wallet_of(aws, EMAIL) == (Decimal("1000000"), ["DEBIT", "CREDIT"])  # back to the start, refunded ONCE
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["refunded"] is True
    assert saved["statusHistory"][-1]["detail"] == "₹5,097 refunded to DemoPay · balance ₹10,00,000"


def test_refund_is_a_no_op_when_nothing_was_charged(aws, refund):
    order = seed_order(aws.orders)

    result = refund.lambda_handler({"orderId": order["orderId"]}, None)

    assert result["refunded"] is False and result["reason"] == "nothing charged"
    assert wallet_of(aws, EMAIL) == (None, [])


def test_wallet_view_creates_wallet_with_ten_lakh(aws, api):
    result = api.lambda_handler({"routeKey": "GET /wallet", "queryStringParameters": {"email": " Asha@Example.com "}}, None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["walletId"] == EMAIL and body["balance"] == 1000000 and body["transactions"] == []


def test_wallet_view_lists_transactions_newest_first(aws, api, payment, refund):
    order = paid_order(aws, payment)
    refund.lambda_handler({"orderId": order["orderId"]}, None)

    body = json.loads(api.lambda_handler({"routeKey": "GET /wallet", "queryStringParameters": {"email": EMAIL}}, None)["body"])

    assert [t["type"] for t in body["transactions"]] == ["CREDIT", "DEBIT"]
    assert body["transactions"][1]["orderId"] == order["orderId"]
    assert body["transactions"][1]["balanceAfter"] == 994903


def test_set_custom_balance_then_reset(aws, api):
    low = api.lambda_handler({"routeKey": "POST /wallet/reset", "body": json.dumps({"email": EMAIL, "balance": 1000})}, None)
    reset = api.lambda_handler({"routeKey": "POST /wallet/reset", "body": json.dumps({"email": EMAIL})}, None)

    assert json.loads(low["body"])["balance"] == 1000
    body = json.loads(reset["body"])
    assert body["balance"] == 1000000
    assert [t["type"] for t in body["transactions"]] == ["ADJUST", "ADJUST"]
    assert body["transactions"][1]["amount"] == -999000  # 10,00,000 -> 1,000


@pytest.mark.parametrize(
    "event",
    [
        {"routeKey": "GET /wallet", "queryStringParameters": {"email": "not-an-email"}},
        {"routeKey": "GET /wallet", "queryStringParameters": None},
        {"routeKey": "POST /wallet/reset", "body": json.dumps({"email": EMAIL, "balance": -5})},
        {"routeKey": "POST /wallet/reset", "body": json.dumps({"email": EMAIL, "balance": "lots"})},
        {"routeKey": "POST /wallet/reset", "body": json.dumps({"email": EMAIL, "balance": 99_000_000})},
    ],
)
def test_bad_wallet_requests_return_400(aws, api, event):
    assert api.lambda_handler(event, None)["statusCode"] == 400


def test_unknown_route_returns_404(aws, api):
    assert api.lambda_handler({"routeKey": "DELETE /wallet"}, None)["statusCode"] == 404
