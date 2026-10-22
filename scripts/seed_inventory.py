"""Seed the inventory table with the demo product catalogue.

Idempotent: re-running it overwrites each product, which resets stock to 100 and reserved to 0.
Usage: python scripts/seed_inventory.py
"""

from __future__ import annotations

from decimal import Decimal

import boto3

from tf_outputs import load_outputs

STOCK = 100

# productId, name, unit price (INR)
PRODUCTS = [
    ("WIRELESS-MOUSE", "Logitech M331 Silent Wireless Mouse", "799.00"),
    ("MECH-KEYBOARD", "Keychron K2 Mechanical Keyboard", "3499.00"),
    ("USBC-HUB", "Anker 7-in-1 USB-C Hub", "1999.00"),
    ("ANC-HEADPHONES", "Sony WH-1000XM5 Noise Cancelling Headphones", "26990.00"),
    ("4K-MONITOR", "LG 27-inch 4K UHD IPS Monitor", "24999.00"),
]


def main() -> None:
    outputs = load_outputs()
    table = boto3.resource("dynamodb", region_name=outputs["region"]).Table(outputs["inventory_table"])

    with table.batch_writer() as batch:
        for product_id, name, price in PRODUCTS:
            batch.put_item(
                Item={
                    "productId": product_id,
                    "name": name,
                    "price": Decimal(price),
                    "stock": STOCK,
                    "reserved": 0,
                }
            )

    print(f"Seeded {len(PRODUCTS)} products into {table.name}:")
    for product_id, name, price in PRODUCTS:
        print(f"  {product_id:<16} INR {price:>9}  stock={STOCK:<4} {name}")


if __name__ == "__main__":
    main()
