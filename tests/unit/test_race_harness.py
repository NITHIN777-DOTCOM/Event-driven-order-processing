"""The oversell race harness (scripts/oversell_race.py) must never score a throttled request as "out of stock".

API Gateway answers 429 when the burst limit is hit. That says nothing about the stock, so the harness retries it with
backoff and counts it as THROTTLED; only the answer after the retries is the attempt's outcome. If a 429 were ever
read as OUT_OF_STOCK, a throttled race would look like a correct "sold out" and could hide an oversell (step 3.1).

The harness imports live-system helpers (e2e_test reads `terraform output` at import time), so those modules are
replaced by stubs here; the code under test (classify, send) is the real one. HTTPS is faked: no network.
"""

from __future__ import annotations

import sys
import threading
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def race():
    stubs = {
        "e2e_test": types.SimpleNamespace(
            OUT={}, REGION="ap-south-1", API="https://api.example.test", inventory_table=None, orders_table=None, holds_table=None
        ),
        "auth_tokens": types.SimpleNamespace(auth_header=lambda user: {"Authorization": f"token-{user}"}, test_user=lambda user: {}),
        "create_test_users": types.SimpleNamespace(ensure_user=lambda *a, **k: None),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update({name: types.ModuleType(name) for name in stubs})
    for name, stub in stubs.items():
        sys.modules[name].__dict__.update(vars(stub))
    sys.path.insert(0, str(SCRIPTS))
    try:
        import oversell_race

        yield oversell_race
    finally:
        sys.path.remove(str(SCRIPTS))
        sys.modules.pop("oversell_race", None)
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class FakeConnection:
    """Stands in for http.client.HTTPSConnection: answers from a shared script of (status, body) responses."""

    script: list[tuple[int, bytes]] = []

    def __init__(self, *args, **kwargs):
        pass

    def connect(self):
        pass

    def request(self, *args, **kwargs):
        pass

    def getresponse(self):
        status, body = FakeConnection.script.pop(0)
        return types.SimpleNamespace(status=status, read=lambda: body)

    def close(self):
        pass


def run(race, monkeypatch, kind: str, responses: list[tuple[int, bytes]]):
    FakeConnection.script = list(responses)
    monkeypatch.setattr(race.http.client, "HTTPSConnection", FakeConnection)
    monkeypatch.setattr(race.time, "sleep", lambda s: None)  # backoff without waiting
    attempt = race.Attempt(0, kind, "race-011", ["RACE-1"])
    return race.send(attempt, threading.Barrier(1))


THROTTLED_BODY = b'{"message":"Too Many Requests"}'


def test_429_is_classified_throttled_never_out_of_stock(race):
    # Even a 429 whose body happens to name a product is a throttle, not a stock answer.
    attempt = race.Attempt(0, "hold", "race-011", ["RACE-1"])
    assert race.classify(attempt, 429, {"message": "Too Many Requests", "productId": "RACE-1"}) == race.THROTTLED
    assert race.classify(attempt, 409, {"error": "OUT_OF_STOCK", "productId": "RACE-1"}) == race.OUT_OF_STOCK


def test_throttled_hold_is_retried_and_counted(race, monkeypatch):
    attempt = run(race, monkeypatch, "hold", [(429, THROTTLED_BODY), (429, THROTTLED_BODY), (201, b'{"holdId":"HOLD-1"}')])
    assert attempt.throttles == 2  # counted as THROTTLED twice ...
    assert attempt.codes == [429, 429, 201]
    assert attempt.outcome == race.CLAIMED  # ... and the real answer after the retries is the outcome
    assert attempt.hold_id == "HOLD-1"


def test_throttled_then_really_out_of_stock(race, monkeypatch):
    attempt = run(race, monkeypatch, "hold", [(429, THROTTLED_BODY), (409, b'{"error":"OUT_OF_STOCK","productId":"RACE-1","available":0}')])
    assert attempt.throttles == 1
    assert attempt.outcome == race.OUT_OF_STOCK  # only the 409 after the retry says "out of stock"


def test_always_throttled_ends_as_error_not_out_of_stock(race, monkeypatch):
    attempt = run(race, monkeypatch, "order", [(429, THROTTLED_BODY)] * race.MAX_ATTEMPTS)
    assert attempt.throttles == race.MAX_ATTEMPTS
    assert attempt.outcome == race.ERROR
    assert "still throttled" in attempt.detail
    assert attempt.outcome != race.OUT_OF_STOCK
