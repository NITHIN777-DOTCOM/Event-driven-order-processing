"""Place an order through the public API and follow it until it finishes.

Examples:
    python scripts/place_order.py --simulate none
    python scripts/place_order.py --simulate payment_declined
    python scripts/place_order.py --item USBC-HUB:1 --item 4K-MONITOR:1
    python scripts/place_order.py --repeat 3                       # same Idempotency-Key 3x -> 1 order
    python scripts/place_order.py --idempotency-key checkout-123   # set the key yourself

It POSTs to {api_url}/orders (sending the same Idempotency-Key on every repeat), polls
GET /orders/{id} every 2 s until the order reaches a terminal status (or the timeout passes),
then prints the statusHistory timeline and a link to the Step Functions execution in the console.
Exit code: 0 if the order behaved as expected, 1 on an API error or timeout.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

from auth_tokens import LABELS, auth_header
from tf_outputs import load_outputs

TERMINAL_STATUSES = {"COMPLETED", "PARTIALLY_FULFILLED", "FAILED", "CANCELLED"}
SIMULATE_MODES = [
    "none", "payment_declined", "payment_flaky", "out_of_stock", "poison",
    "payment_timeout", "payment_late", "webhook_duplicate", "webhook_bad_signature",
]
DEFAULT_ITEMS = ["WIRELESS-MOUSE:2", "MECH-KEYBOARD:1"]


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict, dict]:
    """Send a JSON request and return (status code, parsed body, response headers), including for 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}"), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}"), dict(err.headers)


def parse_item(spec: str) -> dict:
    product_id, _, quantity = spec.partition(":")
    return {"productId": product_id, "quantity": int(quantity or 1)}


def execution_console_link(region: str, execution_arn: str) -> str:
    return f"https://{region}.console.aws.amazon.com/states/home?region={region}#/v2/executions/details/{execution_arn}"


def print_timeline(order: dict) -> None:
    print("\nStatus timeline:")
    for entry in order.get("statusHistory", []):
        print(f"  {entry['timestamp']}  {entry['status']:<19} {entry['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--simulate", choices=SIMULATE_MODES, default="none")
    parser.add_argument("--item", action="append", help="PRODUCT_ID:QTY (repeatable)")
    parser.add_argument("--name", default="Asha Rao")
    parser.add_argument("--user", choices=LABELS, default="a", help="Cognito test user to sign in as (create_test_users.py)")
    parser.add_argument("--idempotency-key", help="Idempotency-Key header (default: a new UUID)")
    parser.add_argument("--repeat", type=int, default=1, help="send the same request N times with the same key")
    parser.add_argument("--timeout", type=int, default=60, help="seconds to wait for a terminal status")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between polls")
    args = parser.parse_args()

    outputs = load_outputs()
    api_url = outputs["api_url"].rstrip("/")
    key = args.idempotency_key or str(uuid.uuid4())
    payload = {
        "customerName": args.name,
        "items": [parse_item(spec) for spec in (args.item or DEFAULT_ITEMS)],
        "simulate": args.simulate,
    }

    order_ids = set()
    for attempt in range(1, args.repeat + 1):
        print(f"POST {api_url}/orders  simulate={args.simulate}  Idempotency-Key={key}  (send {attempt}/{args.repeat})")
        status_code, body, _ = http_json("POST", f"{api_url}/orders", payload, {"Idempotency-Key": key, **auth_header(args.user)})
        print(f"  -> HTTP {status_code} {json.dumps(body)}")
        if status_code not in (200, 202):
            return 1
        order_ids.add(body["orderId"])
    if args.repeat > 1:
        print(f"\n{args.repeat} requests with one Idempotency-Key -> {len(order_ids)} distinct order(s): {sorted(order_ids)}")
    order_id = body["orderId"]

    if args.simulate == "poison":
        print(
            f"\n{order_id} will stay PENDING: start_workflow rejects its message, SQS retries it 3 times "
            "(60 s visibility timeout) and then moves it to order-saga-orders-dlq in about 3 minutes."
        )
        return 0

    # Poll until the saga finishes, printing each new status as it appears.
    deadline = time.monotonic() + args.timeout
    last_status, order = None, {}
    while time.monotonic() < deadline:
        _, order, _ = http_json("GET", f"{api_url}/orders/{order_id}", headers=auth_header(args.user))
        if order.get("status") != last_status:
            last_status = order.get("status")
            print(f"  [{time.strftime('%H:%M:%S')}] {order_id} is {last_status}")
        if last_status in TERMINAL_STATUSES:
            break
        time.sleep(args.interval)

    print_timeline(order)
    print(f"\nOrder:     {order_id}")
    print(f"Status:    {order.get('status')}")
    if order.get("failureReason"):
        print(f"Reason:    {order['failureReason']}")
    print(f"Total:     {order.get('currency')} {float(order.get('totalAmount', 0)):.2f}")
    if order.get("executionArn"):
        print(f"Execution: {order['executionArn']}")
        print(f"Console:   {execution_console_link(outputs['region'], order['executionArn'])}")

    if last_status not in TERMINAL_STATUSES:
        print(f"\nTimed out after {args.timeout}s waiting for a terminal status.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
