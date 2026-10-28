"""Post-deploy smoke test: one real order through the live system.

    python scripts/smoke_test.py

It signs in as Cognito test user A (auth_tokens.py; create_test_users.py runs first in the deploy job),
resets that user's wallet to ₹10,00,000, places one "none" order through the public API, waits up to
60 s for COMPLETED, and checks the DemoPay ledger holds exactly 1 DEBIT for that order. It also
checks that the storefront and its config.json are served. Inside GitHub Actions it writes a job
summary ($GITHUB_STEP_SUMMARY). Exit code 1 on any failure, which fails the deploy.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

from auth_tokens import auth_header
from tf_outputs import load_outputs

PRODUCT = "WIRELESS-MOUSE"
TIMEOUT_S = 60


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def main() -> int:
    out = load_outputs()
    api, site, region = out["api_url"].rstrip("/"), out["frontend_url"], out["region"]
    checks: list[tuple[bool, str]] = []

    with urllib.request.urlopen(site + "/", timeout=15) as resp:
        checks.append((resp.status == 200, f"storefront {site} -> HTTP {resp.status}"))
    status, config = http_json("GET", site + "/config.json")
    checks.append((config.get("apiUrl") == api, f"config.json apiUrl matches the API ({config.get('apiUrl')})"))

    checks.append((bool(config.get("auth", {}).get("clientId")), "config.json has the Cognito settings (auth.clientId)"))
    auth = auth_header("a")
    status, _ = http_json("GET", f"{api}/wallet")
    checks.append((status == 401, f"GET /wallet without a token -> HTTP {status} (expected 401: the JWT authorizer)"))

    http_json("POST", f"{api}/wallet/reset", {}, auth)
    status, body = http_json(
        "POST",
        f"{api}/orders",
        {"customerName": "CI Smoke Test", "items": [{"productId": PRODUCT, "quantity": 1}], "simulate": "none"},
        {"Idempotency-Key": f"ci-smoke-{uuid.uuid4()}", **auth},
    )
    checks.append((status == 202, f"POST /orders -> HTTP {status}"))
    order_id = body.get("orderId", "?")

    order: dict = {}
    deadline = time.monotonic() + TIMEOUT_S
    started = time.monotonic()
    while time.monotonic() < deadline:
        order = http_json("GET", f"{api}/orders/{order_id}", headers=auth)[1]
        if order.get("status") in ("COMPLETED", "FAILED"):
            break
        time.sleep(2)
    elapsed = time.monotonic() - started
    checks.append((order.get("status") == "COMPLETED", f"order {order_id} is {order.get('status')} after {elapsed:.1f}s (expected COMPLETED within {TIMEOUT_S}s)"))

    txns = http_json("GET", f"{api}/wallet", headers=auth)[1].get("transactions", [])
    debits = sum(1 for t in txns if t.get("orderId") == order_id and t["type"] == "DEBIT")
    checks.append((debits == 1, f"DemoPay ledger: {debits} DEBIT for the order (expected exactly 1)"))

    execution = order.get("executionArn", "")
    console = f"https://{region}.console.aws.amazon.com/states/home?region={region}#/v2/executions/details/{execution}"
    passed = all(ok for ok, _ in checks)
    for ok, text in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {text}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [
            f"## {'✅' if passed else '❌'} Deployed and smoke-tested",
            "",
            "| | |",
            "|---|---|",
            f"| Storefront | {site} |",
            f"| API | {api} |",
            f"| Commit | `{os.environ.get('GITHUB_SHA', '')[:7]}` |",
            f"| Smoke order | `{order_id}` ({order.get('status')}, {elapsed:.1f}s) |",
            f"| Step Functions execution | [open in console]({console}) |",
            "",
            "**Checks**",
            "",
            *[f"- {'✅' if ok else '❌'} {text}" for ok, text in checks],
        ]
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
