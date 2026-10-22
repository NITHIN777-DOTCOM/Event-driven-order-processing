"""GET /products: the storefront catalogue (name, price, live stock, image).

The catalogue is small and bounded (one item per product), so a Scan is the right tool here.
Orders, which grow without limit, are never scanned: they're listed through a GSI query instead.
"""

from __future__ import annotations

import os
from typing import Any

import boto3

from common.http import response
from common.logger import get_logger
from common.tracing import instrument_aws_sdk

instrument_aws_sdk()  # X-Ray subsegments for every boto3 call (see common/tracing.py)

INVENTORY_TABLE = os.environ["INVENTORY_TABLE"]

inventory_table = boto3.resource("dynamodb").Table(INVENTORY_TABLE)
logger = get_logger("list_products")

FIELDS = (
    "productId", "name", "category", "price", "mrp", "rating", "ratingCount",
    "stock", "highlights", "description", "imageKey",
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {}
    while True:  # follow pagination, though the catalogue fits in one page
        page = inventory_table.scan(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    products = sorted(
        ({field: item.get(field) for field in FIELDS} for item in items),
        key=lambda product: product["price"],
    )
    logger.info("Products listed", count=len(products))
    return response(200, {"products": products})
