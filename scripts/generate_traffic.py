"""Send a realistic mix of orders so the CloudWatch dashboard has real data to show.

    python scripts/generate_traffic.py                    # 40 orders over 4 minutes
    python scripts/generate_traffic.py --orders 20 --minutes 1 --no-seed

The mix is 70% none, 10% payment_declined, 10% payment_flaky and 10% out_of_stock, shuffled.
Poison orders are never sent, so the DLQ isn't polluted. Inventory is re-seeded first unless
--no-seed is given. After sending, the script waits for every order to finish and prints a summary.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import time
import urllib.error
import urllib.request
import uuid

import seed_inventory
from auth_tokens import LABELS, auth_header, test_user
from tf_outputs import load_outputs

MIX = {"none": 0.7, "payment_declined": 0.1, "payment_flaky": 0.1, "out_of_stock": 0.1}
EXPECTED_STATUS = {"none": "COMPLETED", "payment_flaky": "COMPLETED", "payment_declined": "FAILED", "out_of_stock": "FAILED"}
# Only well-stocked products, so a "none" order never fails by running out of stock.
PRODUCTS = [p["productId"] for p in seed_inventory.PRODUCTS if p["stock"] >= 20]
CUSTOMERS = ["Asha Rao", "Rahul Mehta", "Priya Sharma", "Vikram Iyer", "Neha Gupta", "Arjun Nair"]


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def build_plan(total: int, rng: random.Random) -> list[str]:
    """Exactly round(total * share) orders per mode (the remainder goes to 'none'), shuffled."""
    plan = [mode for mode, share in MIX.items() if mode != "none" for _ in range(round(total * share))]
    plan += ["none"] * (total - len(plan))
    rng.shuffle(plan)
    return plan


def random_order(simulate: str, rng: random.Random, user: str) -> dict:
    customer = rng.choice(CUSTOMERS)  # the display name only; the account is the signed-in test user
    products = rng.sample(PRODUCTS, k=rng.randint(1, 2))
    return {
        "customerName": customer,
        "customerEmail": test_user(user)["email"],
        "items": [{"productId": p, "quantity": rng.randint(1, 2)} for p in products],
        "simulate": simulate,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--orders", type=int, default=40)
    parser.add_argument("--minutes", type=float, default=4.0)
    parser.add_argument("--seed", type=int, default=None, help="random seed for a repeatable mix")
    parser.add_argument("--no-seed", action="store_true", help="don't reset inventory first")
    args = parser.parse_args()

    if not args.no_seed:
        seed_inventory.main()
    api = load_outputs()["api_url"].rstrip("/")
    rng = random.Random(args.seed)
    plan = build_plan(args.orders, rng)
    interval = args.minutes * 60 / args.orders

    print(f"\nSending {args.orders} orders over {args.minutes:g} min (one every {interval:.1f}s): {dict(collections.Counter(plan))}")
    placed: list[tuple[str, str, str]] = []  # (orderId, simulate, test user)
    started = time.monotonic()
    for index, simulate in enumerate(plan, start=1):
        user = LABELS[index % len(LABELS)]  # alternate between the test users
        headers = {"Idempotency-Key": str(uuid.uuid4()), **auth_header(user)}
        code, body = http_json("POST", f"{api}/orders", random_order(simulate, rng, user), headers)
        if code == 202:
            placed.append((body["orderId"], simulate, user))
            print(f"  [{index:>3}/{args.orders}] {body['orderId']}  {simulate}")
        else:
            print(f"  [{index:>3}/{args.orders}] HTTP {code} {body}  {simulate}")
        # Keep an even pace regardless of how long each request took.
        time.sleep(max(0.0, started + index * interval - time.monotonic()))

    print("\nWaiting for all sagas to finish...")
    final: dict[str, str] = {}
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and len(final) < len(placed):
        for order_id, _, user in placed:
            if order_id not in final:
                status = http_json("GET", f"{api}/orders/{order_id}", headers=auth_header(user))[1].get("status")
                if status in ("COMPLETED", "FAILED"):
                    final[order_id] = status
        if len(final) < len(placed):
            time.sleep(3)

    summary = collections.Counter((simulate, final.get(order_id, "UNFINISHED")) for order_id, simulate, _ in placed)
    unexpected = [(o, s, final.get(o)) for o, s, _ in placed if final.get(o) != EXPECTED_STATUS[s]]
    print("\nSummary (simulate -> final status: count)")
    for (simulate, status), count in sorted(summary.items()):
        print(f"  {simulate:<17} -> {status:<10} {count}")
    completed = sum(1 for s in final.values() if s == "COMPLETED")
    print(f"\n{len(placed)} orders placed, {completed} COMPLETED, {len(placed) - completed} FAILED/unfinished, "
          f"{len(unexpected)} unexpected outcomes, in {time.monotonic() - started:.0f}s")
    for order_id, simulate, status in unexpected:
        print(f"  UNEXPECTED: {order_id} simulate={simulate} final={status}")
    return 0 if not unexpected and len(placed) == args.orders else 1


if __name__ == "__main__":
    sys.exit(main())
