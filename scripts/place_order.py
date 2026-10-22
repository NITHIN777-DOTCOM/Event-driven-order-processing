"""Place an order through the public API and follow it until it finishes.

Examples:
    python scripts/place_order.py --simulate none
    python scripts/place_order.py --item USBC-HUB:1 --item 4K-MONITOR:1

It POSTs to {api_url}/orders, polls GET /orders/{id} every 2 s until the order reaches a terminal
status (or the timeout passes), then prints the statusHistory timeline and a link to the
Step Functions execution in the console.
Exit code: 0 if the order reached a terminal status, 1 on an API error or timeout.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from tf_outputs import load_outputs

TERMINAL_STATUSES = {"COMPLETED", "FAILED"}
SIMULATE_MODES = ["none", "payment_declined", "payment_flaky", "out_of_stock", "poison"]
DEFAULT_ITEMS = ["WIRELESS-MOUSE:2", "MECH-KEYBOARD:1"]


def http_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    """Send a JSON request and return (status code, parsed body), including for 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def parse_item(spec: str) -> dict:
    product_id, _, quantity = spec.partition(":")
    return {"productId": product_id, "quantity": int(quantity or 1)}


def print_timeline(order: dict) -> None:
    print("\nStatus timeline:")
    for entry in order.get("statusHistory", []):
        print(f"  {entry['timestamp']}  {entry['status']:<17} {entry['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--simulate", choices=SIMULATE_MODES, default="none")
    parser.add_argument("--item", action="append", help="PRODUCT_ID:QTY (repeatable)")
    parser.add_argument("--name", default="Asha Rao")
    parser.add_argument("--email", default="asha.rao@example.com")
    parser.add_argument("--timeout", type=int, default=60, help="seconds to wait for a terminal status")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between polls")
    args = parser.parse_args()

    outputs = load_outputs()
    api_url = outputs["api_url"].rstrip("/")
    payload = {
        "customerName": args.name,
        "customerEmail": args.email,
        "items": [parse_item(spec) for spec in (args.item or DEFAULT_ITEMS)],
        "simulate": args.simulate,
    }

    print(f"POST {api_url}/orders  simulate={args.simulate}")
    status_code, body = http_json("POST", f"{api_url}/orders", payload)
    print(f"  -> HTTP {status_code} {json.dumps(body)}")
    if status_code not in (200, 202):
        return 1
    order_id = body["orderId"]

    # Poll until the saga finishes, printing each new status as it appears.
    deadline = time.monotonic() + args.timeout
    last_status, order = None, {}
    while time.monotonic() < deadline:
        _, order = http_json("GET", f"{api_url}/orders/{order_id}")
        if order.get("status") != last_status:
            last_status = order.get("status")
            print(f"  [{time.strftime('%H:%M:%S')}] {order_id} is {last_status}")
        if last_status in TERMINAL_STATUSES:
            break
        time.sleep(args.interval)

    print_timeline(order)
    print(f"\nOrder:     {order_id}")
    print(f"Status:    {order.get('status')}")
    print(f"Total:     {order.get('currency')} {float(order.get('totalAmount', 0)):.2f}")
    if order.get("executionArn"):
        region = outputs["region"]
        print(f"Execution: {order['executionArn']}")
        print(
            f"Console:   https://{region}.console.aws.amazon.com/states/home?region={region}"
            f"#/v2/executions/details/{order['executionArn']}"
        )

    if last_status not in TERMINAL_STATUSES:
        print(f"\nTimed out after {args.timeout}s waiting for a terminal status.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
