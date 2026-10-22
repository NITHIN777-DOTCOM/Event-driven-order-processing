"""process_payment: real DemoPay debits, natural declines, simulate modes, never charging twice."""

from decimal import Decimal

import pytest

from conftest import seed_order, wallet_of

EMAIL = "asha@example.com"  # seed_order's customerEmail


@pytest.fixture
def handler(load_handler):
    return load_handler("process_payment")


def pay(handler, order, simulate="none"):
    return handler.lambda_handler({"orderId": order["orderId"], "amount": "5097.00", "currency": "INR", "simulate": simulate}, None)


def load(aws, order_id):
    return aws.orders.get_item(Key={"orderId": order_id})["Item"]


def test_debits_wallet_records_ledger_and_marks_order_paid(aws, handler):
    order = seed_order(aws.orders)

    result = pay(handler, order)

    assert result["status"] == "CAPTURED" and result["paymentId"].startswith("PAY-")
    balance, ledger = wallet_of(aws, EMAIL)
    assert balance == Decimal("1000000") - Decimal("5097.00")  # wallet created lazily with ₹10,00,000
    assert ledger == ["DEBIT"]
    saved = load(aws, order["orderId"])
    assert saved["status"] == "PAYMENT_CAPTURED"
    assert saved["paymentId"] == result["paymentId"] and saved["paidAmount"] == Decimal("5097")
    assert saved["statusHistory"][-1]["detail"] == "₹5,097 debited from DemoPay · balance ₹9,94,903 (attempt 1)"


def test_insufficient_balance_is_a_natural_decline_with_no_debit(aws, handler):
    aws.wallets.put_item(Item={"walletId": EMAIL, "balance": Decimal("1000"), "currency": "INR"})
    order = seed_order(aws.orders)

    with pytest.raises(handler.PaymentDeclined, match="Insufficient wallet balance"):
        pay(handler, order)

    assert wallet_of(aws, EMAIL) == (Decimal("1000"), [])  # untouched, no ledger entry
    saved = load(aws, order["orderId"])
    assert saved["status"] == "PAYMENT_DECLINED" and "paymentId" not in saved
    assert "₹1,000 available, ₹5,097 needed" in saved["statusHistory"][-1]["detail"]


def test_simulated_card_decline_moves_no_money(aws, handler):
    order = seed_order(aws.orders, simulate="payment_declined")

    with pytest.raises(handler.PaymentDeclined, match="declined"):
        pay(handler, order, "payment_declined")

    assert wallet_of(aws, EMAIL) == (None, [])  # the wallet was never even touched
    assert load(aws, order["orderId"])["statusHistory"][-1]["detail"] == "Attempt 1: Card declined by issuer (simulated)"


def test_flaky_payment_retries_and_debits_exactly_once(aws, handler):
    order = seed_order(aws.orders, simulate="payment_flaky")

    for _ in range(2):  # Step Functions would retry; here we call the handler by hand
        with pytest.raises(handler.PaymentTransientError):
            pay(handler, order, "payment_flaky")
    pay(handler, order, "payment_flaky")

    saved = load(aws, order["orderId"])
    assert saved["paymentAttempts"] == 3
    assert [h["status"] for h in saved["statusHistory"]] == ["PENDING", "PAYMENT_RETRY", "PAYMENT_RETRY", "PAYMENT_CAPTURED"]
    assert wallet_of(aws, EMAIL)[1] == ["DEBIT"]


def test_already_paid_order_is_never_debited_again(aws, handler):
    order = seed_order(aws.orders)
    first = pay(handler, order)

    second = pay(handler, order)  # e.g. a Lambda retry after a lost response

    assert second == first
    balance, ledger = wallet_of(aws, EMAIL)
    assert ledger == ["DEBIT"] and balance == Decimal("994903")


def test_concurrent_attempt_that_paid_first_wins(aws, handler):
    """Two attempts read 'unpaid' at the same time: the order condition in the transaction lets only one debit."""
    order = seed_order(aws.orders)
    first = pay(handler, order)
    stale_copy = {**order}  # what the second attempt read before the first one committed

    result = handler.debit_wallet(stale_copy, 2, handler.logger)

    assert result["paymentId"] == first["paymentId"]
    assert wallet_of(aws, EMAIL)[1] == ["DEBIT"]  # still exactly one debit
