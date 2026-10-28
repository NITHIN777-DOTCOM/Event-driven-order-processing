"""refund_payment (idempotent compensation) and the wallet API."""

import json
from decimal import Decimal

import pytest

from conftest import EMAIL_B, USER_A, USER_B, api_event, jwt_claims, seed_order, wallet_of

AS_B = jwt_claims(USER_B, EMAIL_B)


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
    assert wallet_of(aws, USER_A) == (Decimal("1000000"), ["DEBIT", "CREDIT"])  # back to the start, refunded ONCE
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["refunded"] is True
    assert saved["statusHistory"][-1]["detail"] == "₹5,097 refunded to DemoPay · balance ₹10,00,000"


def test_refund_is_a_no_op_when_nothing_was_charged(aws, refund):
    order = seed_order(aws.orders)

    result = refund.lambda_handler({"orderId": order["orderId"]}, None)

    assert result["refunded"] is False and result["reason"] == "nothing charged"
    assert wallet_of(aws, USER_A) == (None, [])


def test_wallet_view_creates_wallet_with_ten_lakh(aws, api):
    result = api.lambda_handler(api_event(route_key="GET /wallet"), None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["walletId"] == USER_A and body["balance"] == 1000000 and body["transactions"] == []


def test_wallet_ignores_an_email_parameter(aws, api):
    """GET /wallet?email=<someone else> still returns the CALLER's wallet."""
    result = api.lambda_handler(api_event(route_key="GET /wallet", query={"email": "victim@example.com"}), None)

    assert json.loads(result["body"])["walletId"] == USER_A
    assert aws.wallets.get_item(Key={"walletId": "victim@example.com"}).get("Item") is None


def test_reset_changes_only_the_callers_wallet(aws, api):
    api.lambda_handler(api_event(route_key="GET /wallet", claims=AS_B), None)  # B's wallet: ₹10,00,000

    # A resets "B" by every means a client controls: none of them reach B's wallet.
    body = {"balance": 1000, "email": EMAIL_B, "userId": USER_B, "walletId": USER_B}
    result = api.lambda_handler(api_event(body, route_key="POST /wallet/reset"), None)

    assert json.loads(result["body"])["walletId"] == USER_A
    assert wallet_of(aws, USER_A) == (Decimal("1000"), ["ADJUST"])
    assert wallet_of(aws, USER_B) == (Decimal("1000000"), [])


def test_wallet_without_identity_is_401(aws, api):
    assert api.lambda_handler(api_event(route_key="GET /wallet", claims=None), None)["statusCode"] == 401


def test_wallet_view_lists_transactions_newest_first(aws, api, payment, refund):
    order = paid_order(aws, payment)
    refund.lambda_handler({"orderId": order["orderId"]}, None)

    body = json.loads(api.lambda_handler(api_event(route_key="GET /wallet"), None)["body"])

    assert [t["type"] for t in body["transactions"]] == ["CREDIT", "DEBIT"]
    assert body["transactions"][1]["orderId"] == order["orderId"]
    assert body["transactions"][1]["balanceAfter"] == 994903


def test_set_custom_balance_then_reset(aws, api):
    low = api.lambda_handler(api_event({"balance": 1000}, route_key="POST /wallet/reset"), None)
    reset = api.lambda_handler(api_event(route_key="POST /wallet/reset"), None)

    assert json.loads(low["body"])["balance"] == 1000
    body = json.loads(reset["body"])
    assert body["balance"] == 1000000
    assert [t["type"] for t in body["transactions"]] == ["ADJUST", "ADJUST"]
    assert body["transactions"][1]["amount"] == -999000  # 10,00,000 -> 1,000


@pytest.mark.parametrize(
    "event",
    [
        api_event({"balance": -5}, route_key="POST /wallet/reset"),
        api_event({"balance": "lots"}, route_key="POST /wallet/reset"),
        api_event({"balance": 99_000_000}, route_key="POST /wallet/reset"),
        api_event("not json", route_key="POST /wallet/reset"),
    ],
)
def test_bad_wallet_requests_return_400(aws, api, event):
    assert api.lambda_handler(event, None)["statusCode"] == 400


def test_unknown_route_returns_404(aws, api):
    assert api.lambda_handler(api_event(route_key="DELETE /wallet"), None)["statusCode"] == 404
