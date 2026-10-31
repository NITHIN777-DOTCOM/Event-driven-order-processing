"""One-off data correction found by the step 3.2 invariant-auditor baseline: ORD-20261030-399cf6c3.

What happened: step 2.3's scripts/fulfillment_check.py tested the new per-line Lambdas by invoking them DIRECTLY on
an order that had already COMPLETED on the pre-2.3 definition: L1 and L3 fulfilled, L2 written off and refunded
(DemoPay line refund ₹26,990). The money and stock are consistent with that (net ₹15,395 = L1 + L3; the write-off
has its audit record), but the order still says COMPLETED. The auditor reports I1 (COMPLETED -> one DEBIT, no
CREDIT) and I6 (net = fulfilled lines). The saga itself never produced this: the probe bypassed it.

The fix: make the status say what really happened, PARTIALLY_FULFILLED, with a statusHistory entry explaining the
correction. Money and stock are not touched. Conditional on the order still being COMPLETED with exactly that line
state, so it can run once and only on this order.

    python scripts/fix_probe_order.py           # dry run (default): show the order and what would change
    python scripts/fix_probe_order.py --apply   # do it
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import boto3

from tf_outputs import load_outputs

ORDER_ID = "ORD-20261030-399cf6c3"
DETAIL = (
    "Status corrected by the step 3.2 invariant audit: this order was the step 2.3 direct-invoke probe "
    "(scripts/fulfillment_check.py). L1 and L3 were delivered, L2 was written off and refunded, so it is "
    "partially fulfilled. Money and stock unchanged."
)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = load_outputs()
    table = boto3.resource("dynamodb", region_name=out["region"]).Table(out["orders_table"])
    order = table.get_item(Key={"orderId": ORDER_ID}, ConsistentRead=True)["Item"]
    lines = [(i.get("lineId"), i.get("fulfillment")) for i in order["items"]]
    print(f"{ORDER_ID}: status {order['status']}, lines {lines}")
    expected = [("L1", "FULFILLED"), ("L2", "WRITTEN_OFF"), ("L3", "FULFILLED")]
    if order["status"] != "COMPLETED" or lines != expected:
        sys.exit("Not in the expected state; nothing to do.")
    print(f"Would set status PARTIALLY_FULFILLED and append: {DETAIL}")
    if "--apply" not in sys.argv:
        print("Dry run. Re-run with --apply.")
        return

    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    table.update_item(
        Key={"orderId": ORDER_ID},
        UpdateExpression="SET #s = :partial, updatedAt = :now, statusHistory = list_append(statusHistory, :entry)",
        ConditionExpression="#s = :completed AND #items[1].fulfillment = :wo",
        ExpressionAttributeNames={"#s": "status", "#items": "items"},
        ExpressionAttributeValues={
            ":partial": "PARTIALLY_FULFILLED",
            ":completed": "COMPLETED",
            ":wo": "WRITTEN_OFF",
            ":now": now,
            ":entry": [{"status": "PARTIALLY_FULFILLED", "timestamp": now, "detail": DETAIL}],
        },
    )
    print("Corrected.")


if __name__ == "__main__":
    main()
