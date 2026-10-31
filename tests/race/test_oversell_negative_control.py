"""Negative control for the oversell race test (step 3.1): proof that the race CAN catch an oversell bug.

A race test that always passes proves nothing unless it is shown to fail on broken code. So the same thread race
(50 buyers, 5 units, all released by one barrier) runs twice against moto:

  BrokenReserve  read stock -> check it in Python -> write WITHOUT a condition, with a small delay between the read
                 and the write (the window real traffic opens by chance). It must oversell: more than 5 claimed.
  real code      reserve_inventory's lambda_handler: one conditional transaction (stock >= qty). Exactly 5 claimed.

moto evaluates a request's condition and applies its write as separate Python steps, so under threads the GIL could
switch between them. Real DynamoDB evaluates a conditional write atomically per item. AtomicRequests restores that
guarantee by serialising whole requests, and nothing more: a read and a write in two separate requests (what
BrokenReserve does) can still interleave, exactly as they can in production.

BrokenReserve lives only here. It is never imported by src/ and never packaged into a Lambda.
"""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from conftest import aws, load_handler, seed_order  # noqa: E402,F401  (shared moto fixtures; aws/load_handler are used as fixtures)

pytestmark = pytest.mark.race

BUYERS = 50
UNITS = 5
PRODUCT = "RACE-NEG"
READ_WRITE_DELAY_S = 0.05  # BrokenReserve's window between reading the stock and writing it


class AtomicRequests:
    """Wraps a boto3 client or Table so each request runs alone, the way DynamoDB applies one request atomically."""

    _lock = threading.Lock()

    def __init__(self, target) -> None:
        self._target = target

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            with self._lock:
                return attr(*args, **kwargs)

        return call


class BrokenReserve:
    """TEST ONLY. The classic oversell bug: the stock check happens in application code, not in the write."""

    def __init__(self, client, table_name: str) -> None:
        self.client, self.table_name = client, table_name

    def reserve(self, product_id: str, quantity: int) -> bool:
        item = self.client.get_item(TableName=self.table_name, Key={"productId": product_id}, ConsistentRead=True)["Item"]
        if int(item["stock"]) < quantity:
            return False  # out of stock
        time.sleep(READ_WRITE_DELAY_S)  # everyone else can read the same, now stale, stock here
        self.client.update_item(
            TableName=self.table_name,
            Key={"productId": product_id},
            UpdateExpression="SET stock = stock - :q, reserved = reserved + :q",  # no ConditionExpression: the bug
            ExpressionAttributeValues={":q": quantity},
        )
        return True


def race(attempt) -> list[bool]:
    """Run `attempt(i)` in BUYERS threads released together; return who claimed a unit."""
    barrier = threading.Barrier(BUYERS, timeout=30)

    def buyer(index: int) -> bool:
        barrier.wait()
        return attempt(index)

    with ThreadPoolExecutor(max_workers=BUYERS) as pool:
        return list(pool.map(buyer, range(BUYERS)))


def counters(aws) -> tuple[int, int]:
    item = aws.inventory.get_item(Key={"productId": PRODUCT}, ConsistentRead=True)["Item"]
    return int(item["stock"]), int(item["reserved"])


@pytest.fixture
def scarce(aws):
    aws.inventory.put_item(Item={"productId": PRODUCT, "name": "Race negative control", "price": 100, "stock": UNITS, "reserved": 0})
    return aws


def test_broken_reserve_oversells(scarce):
    broken = BrokenReserve(AtomicRequests(scarce.inventory.meta.client), scarce.inventory.name)

    claimed = sum(race(lambda _: broken.reserve(PRODUCT, 1)))

    stock, reserved = counters(scarce)
    print(f"\nBrokenReserve: {BUYERS} buyers, {UNITS} units -> claimed {claimed}, stock {stock}, reserved {reserved}")
    assert claimed > UNITS  # the race test catches the bug: more sold than exists
    assert stock < 0 and reserved == claimed


def test_real_reserve_claims_exactly_the_stock(scarce, load_handler):
    reserve = load_handler("reserve_inventory")
    reserve.ddb_client = AtomicRequests(reserve.ddb_client)
    reserve.orders_table = AtomicRequests(reserve.orders_table)
    order_ids = [f"ORD-20261031-{index:08x}" for index in range(BUYERS)]
    for order_id in order_ids:
        seed_order(scarce.orders, orderId=order_id, status="PROCESSING", items=[{"productId": PRODUCT, "name": "Race", "quantity": 1, "unitPrice": 100}])

    def attempt(index: int) -> bool:
        try:
            reserve.lambda_handler({"orderId": order_ids[index]}, None)
            return True
        except reserve.OutOfStock:
            return False

    claimed = sum(race(attempt))

    stock, reserved = counters(scarce)
    out_of_stock = sum(1 for o in order_ids if scarce.orders.get_item(Key={"orderId": o})["Item"]["status"] == "OUT_OF_STOCK")
    print(f"\nreal reserve:  {BUYERS} buyers, {UNITS} units -> claimed {claimed}, stock {stock}, reserved {reserved}, out of stock {out_of_stock}")
    assert claimed == UNITS and (stock, reserved) == (0, UNITS)
    assert out_of_stock == BUYERS - UNITS  # every loser got a clean out-of-stock answer
