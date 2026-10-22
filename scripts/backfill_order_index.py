"""One-off migration: add the gsi1 keys to orders created before the "recent orders" index existed.

    python scripts/backfill_order_index.py

It sets gsi1pk = "ORDER" and gsi1sk = createdAt on every order that lacks them, so those orders
appear in GET /orders. This maintenance job scans the table once, which is the only scan of the
orders table anywhere; the API itself only uses Query. It's idempotent: the condition skips
orders that already have the keys.
"""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from tf_outputs import load_outputs

ORDER_LIST_PARTITION = "ORDER"


def main() -> None:
    outputs = load_outputs()
    table = boto3.resource("dynamodb", region_name=outputs["region"]).Table(outputs["orders_table"])

    updated = skipped = 0
    kwargs = {"ProjectionExpression": "orderId, createdAt, gsi1pk"}
    while True:
        page = table.scan(**kwargs)
        for item in page["Items"]:
            if item.get("gsi1pk") or not item.get("createdAt"):
                skipped += 1
                continue
            try:
                table.update_item(
                    Key={"orderId": item["orderId"]},
                    UpdateExpression="SET gsi1pk = :pk, gsi1sk = :sk",
                    ConditionExpression="attribute_not_exists(gsi1pk)",
                    ExpressionAttributeValues={":pk": ORDER_LIST_PARTITION, ":sk": item["createdAt"]},
                )
                updated += 1
            except ClientError as err:
                if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                skipped += 1
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    print(f"Backfilled {updated} orders into the gsi1 index ({skipped} already had the keys).")


if __name__ == "__main__":
    main()
