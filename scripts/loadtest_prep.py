"""Step 3.3 load test, part 1 of 3: get everything ready so the k6 run itself only POSTs orders.

    python scripts/loadtest_prep.py          # then k6 and the report: see the header of loadtest/k6/orders.js

What it does:
  1. Seeds 20 hidden load products LOAD-01 .. LOAD-20 (listed = false: never in the storefront), 10,000 units each,
     prices ₹100-₹290. Spreading orders over 20 products keeps the per-item transaction rate low (each reservation
     is one DynamoDB transaction over its products; two in flight on the same item conflict and retry). A product
     that already exists from an earlier run is TOPPED UP instead (ADD stock and seededStock by the same amount), so
     the auditor's I5 sum "counters = seededStock" stays exact across runs.
  2. Buyers: the 160 race-test users from step 3.1 (race-001 .. race-160; created if missing, exactly like test users
     A and B). Orders are spread over all of them, so each DemoPay wallet sees ~0.3 debits/s at 50 orders/s and its
     conditional balance update rarely conflicts. Every wallet is reset to ₹10,00,000 (far above ~120 orders x ₹870).
  3. Fetches every buyer's ACCESS token now (they last 60 minutes; the run takes ~10) and writes them, with the run id
     and product list, to build/loadtest/run.json. build/ is gitignored: the tokens never reach git.
  4. Records the "before" facts the report compares against: DLQ depths and an auditor run.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.config import Config

import e2e_test as e2e
from auth_tokens import test_user
from create_test_users import ensure_user

OUT, REGION = e2e.OUT, e2e.REGION
RUN_FILE = Path(__file__).resolve().parents[1] / "build" / "loadtest" / "run.json"
PRODUCTS = {f"LOAD-{n:02d}": Decimal(90 + 10 * n) for n in range(1, 21)}  # productId -> price (₹100 .. ₹290)
UNITS = 10_000
BUYERS = [f"race-{n:03d}" for n in range(1, 161)]
DLQS = {"orders": OUT["dlq_url"], "outbox": OUT["outbox_dlq_url"], "psp": OUT["psp_dlq_url"]}

dynamodb = boto3.resource("dynamodb", region_name=REGION)
inventory = dynamodb.Table(OUT["inventory_table"])
sqs = boto3.client("sqs", region_name=REGION)
# The auditor scans every table and can run up to its 900 s timeout: wait longer than that, and never re-invoke on a
# client timeout (botocore's default 60 s read timeout + retries started duplicate audits).
lambda_client = boto3.client("lambda", region_name=REGION, config=Config(read_timeout=960, retries={"max_attempts": 1}))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_products() -> None:
    seeded_at = now_iso()
    for product, price in PRODUCTS.items():
        try:
            inventory.put_item(
                Item={
                    "productId": product, "name": f"Load test product {product}", "category": "Test",
                    "price": price, "mrp": price, "stock": UNITS, "held": 0, "reserved": 0, "sold": 0, "writtenOff": 0,
                    "listed": False, "seededAt": seeded_at, "seededStock": UNITS,
                    "description": "Test-only product for the step 3.3 k6 load test; never listed in the storefront.",
                },
                ConditionExpression="attribute_not_exists(productId)",
            )
        except inventory.meta.client.exceptions.ConditionalCheckFailedException:
            # Used by an earlier run: top up both sides of the I5 sum by the same amount (never reset counters).
            item = inventory.get_item(Key={"productId": product}, ConsistentRead=True)["Item"]
            top_up = max(UNITS - int(item["stock"]), 0)
            if top_up:
                inventory.update_item(Key={"productId": product}, UpdateExpression="ADD stock :n, seededStock :n",
                                      ExpressionAttributeValues={":n": top_up})
    print(f"Products: {len(PRODUCTS)} hidden LOAD-* products with {UNITS:,} units available each")


def prepare_buyers() -> list[dict]:
    patient = Config(retries={"mode": "adaptive", "max_attempts": 10})  # SSM PutParameter allows only a few per second
    cognito = boto3.client("cognito-idp", region_name=REGION, config=patient)
    ssm = boto3.client("ssm", region_name=REGION, config=patient)
    created = [s for s in (ensure_user(cognito, ssm, OUT["user_pool_id"], label) for label in BUYERS) if s != "exists"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        users = list(pool.map(test_user, BUYERS))
        list(pool.map(e2e.set_wallet, BUYERS))  # ₹10,00,000 each
    print(f"Buyers: {len(BUYERS)} ready ({len(created)} created now), tokens fetched, wallets reset to ₹10,00,000")
    return [{"label": label, "sub": u["sub"], "token": u["access_token"], "expiresAt": u["expires_at"]} for label, u in zip(BUYERS, users)]


def dlq_depths() -> dict[str, int]:
    depths = {}
    for name, url in DLQS.items():
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
        depths[name] = int(attrs["ApproximateNumberOfMessages"]) + int(attrs["ApproximateNumberOfMessagesNotVisible"])
    return depths


def run_auditor() -> dict:
    started = time.monotonic()
    resp = lambda_client.invoke(FunctionName=OUT["invariant_auditor_function_name"], Payload=b'{"source":"loadtest"}')
    payload = json.loads(resp["Payload"].read() or b"{}")
    return {"violations": payload.get("violations"), "stuck": payload.get("stuck"), "orders": payload.get("orders"),
            "seconds": round(time.monotonic() - started, 1), "error": resp.get("FunctionError")}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    seed_products()
    buyers = prepare_buyers()
    before = {"dlq": dlq_depths(), "auditor": run_auditor()}
    print(f"Before: DLQs {before['dlq']}, auditor {before['auditor']}")
    run = {"runId": f"LT-{uuid.uuid4().hex[:8]}", "preparedAt": now_iso(), "api": e2e.API,
           "products": {p: str(price) for p, price in PRODUCTS.items()}, "buyers": buyers, "before": before}
    RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUN_FILE.write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"Run {run['runId']} ready: {RUN_FILE} (gitignored; holds tokens). Tokens valid ~60 min: start k6 now.")


if __name__ == "__main__":
    main()
