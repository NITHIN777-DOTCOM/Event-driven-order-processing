"""Seed the inventory table with the storefront catalogue (16 products in 5 categories).

Idempotent: re-running it overwrites each product, which resets stock to its seed value and
reserved to 0. The first 5 productIds are the original Phase 1 ones, so old orders and scripts
keep working.

Usage: python scripts/seed_inventory.py
"""

from __future__ import annotations

from decimal import Decimal

import boto3

from tf_outputs import load_outputs

# Each product's photo is frontend/public/products/<productId lower-case>.webp (credits in README.md).
# price < mrp (10-35% off); rating 3.9-4.8; stock: most 100, a few low (< 20), one at 0.
PRODUCTS = [
    {
        "productId": "WIRELESS-MOUSE", "category": "Mice", "name": "Slim Wireless Mouse",
        "price": "799", "mrp": "1099", "rating": "4.3", "ratingCount": 2814, "stock": 100,
        "highlights": ["Silent clicks, 1600 DPI optical sensor", "Up to 12 months on one AA battery",
                       "2.4 GHz USB receiver, plug and play", "Low-profile shape that slips into a laptop sleeve"],
        "description": "A quiet, low-profile mouse for everyday work. The silent switches keep shared spaces calm, and the slim shell travels well.",
    },
    {
        "productId": "MECH-KEYBOARD", "category": "Keyboards", "name": "Mechanical Keyboard, 60% Layout",
        "price": "3499", "mrp": "4999", "rating": "4.5", "ratingCount": 1290, "stock": 100,
        "highlights": ["Hot-swappable tactile switches", "Compact 60% layout frees desk space",
                       "Detachable USB-C cable", "Double-shot PBT keycaps"],
        "description": "A compact mechanical keyboard with crisp tactile switches. Hot-swap sockets let you change switches without soldering.",
    },
    {
        "productId": "USBC-HUB", "category": "Accessories", "name": "USB-C Hub, 6-in-1",
        "price": "1999", "mrp": "2799", "rating": "4.2", "ratingCount": 964, "stock": 100,
        "highlights": ["4K HDMI output at 30 Hz", "SD and microSD card readers", "100 W USB-C power pass-through",
                       "Aluminium shell with a protective bumper"],
        "description": "One cable for your display, cards and peripherals. The pass-through port keeps your laptop charging while you work.",
    },
    {
        "productId": "ANC-HEADPHONES", "category": "Audio", "name": "Noise-Cancelling Wireless Headphones",
        "price": "26990", "mrp": "34990", "rating": "4.7", "ratingCount": 5321, "stock": 100,
        "highlights": ["Adaptive active noise cancellation", "30-hour battery, 3-minute quick charge for 3 hours",
                       "Multipoint Bluetooth 5.3", "Soft protein-leather ear cushions"],
        "description": "Over-ear headphones that tune noise cancellation to your surroundings. Calls stay clear with beam-forming microphones.",
    },
    {
        "productId": "4K-MONITOR", "category": "Monitors", "name": "27-inch 4K UHD IPS Monitor",
        "price": "24999", "mrp": "32999", "rating": "4.4", "ratingCount": 1876, "stock": 100,
        "highlights": ["3840 x 2160 IPS panel, 99% sRGB", "USB-C with 65 W charging", "Height and tilt adjustable stand",
                       "Thin bezels for multi-monitor setups"],
        "description": "A sharp 27-inch 4K panel with accurate colour. A single USB-C cable carries video, data and power to your laptop.",
    },
    {
        "productId": "LOWPRO-KEYBOARD", "category": "Keyboards", "name": "Low-Profile Wireless Keyboard",
        "price": "2299", "mrp": "2899", "rating": "4.1", "ratingCount": 742, "stock": 100,
        "highlights": ["Full-size layout with number pad", "Scissor-switch keys with short travel",
                       "Pairs with up to 3 devices", "Rechargeable, about 2 months per charge"],
        "description": "A quiet, slim keyboard that feels like a laptop's. Switch between your computer, tablet and phone with one key.",
    },
    {
        "productId": "COMPACT-KEYBOARD", "category": "Keyboards", "name": "Compact 65% Mechanical Keyboard",
        "price": "5499", "mrp": "6999", "rating": "4.6", "ratingCount": 418, "stock": 14,
        "highlights": ["65% layout keeps the arrow keys", "Gasket mount for a softer typing feel",
                       "Bluetooth, 2.4 GHz and wired modes", "White backlight with 5 levels"],
        "description": "A 65% board that keeps the arrow keys and drops the rest. The gasket mount gives a softer, quieter sound.",
    },
    {
        "productId": "ERGO-MOUSE", "category": "Mice", "name": "Ergonomic Wireless Mouse",
        "price": "6499", "mrp": "8495", "rating": "4.7", "ratingCount": 3102, "stock": 100,
        "highlights": ["Sculpted shape with a thumb rest", "8000 DPI sensor tracks on glass",
                       "Free-spinning electromagnetic scroll wheel", "USB-C fast charging: 1 minute for 3 hours"],
        "description": "A full-size mouse shaped for long days. The fast scroll wheel flies through long documents and spreadsheets.",
    },
    {
        "productId": "VERTICAL-MOUSE", "category": "Mice", "name": "Vertical Ergonomic Mouse",
        "price": "3999", "mrp": "4995", "rating": "4.2", "ratingCount": 1187, "stock": 9,
        "highlights": ["57-degree vertical angle reduces wrist strain", "4 adjustable DPI levels up to 4000",
                       "Quiet thumb buttons for back and forward", "Bluetooth and USB receiver"],
        "description": "A vertical mouse that holds your hand in a natural handshake position, easing pressure on the wrist and forearm.",
    },
    {
        "productId": "WIRELESS-EARBUDS", "category": "Audio", "name": "True Wireless Earbuds",
        "price": "4999", "mrp": "6999", "rating": "4.0", "ratingCount": 2659, "stock": 100,
        "highlights": ["Active noise cancellation with transparency mode", "8 h playback, 32 h with the case",
                       "IPX4 sweat and splash resistant", "Wireless charging case"],
        "description": "Compact earbuds with active noise cancellation and a pocket-sized wireless charging case.",
    },
    {
        "productId": "USB-MIC", "category": "Audio", "name": "USB Condenser Microphone",
        "price": "5999", "mrp": "7499", "rating": "4.4", "ratingCount": 905, "stock": 18,
        "highlights": ["Cardioid pickup focuses on your voice", "24-bit / 96 kHz recording",
                       "Zero-latency headphone monitoring", "Desk tripod and shock mount included"],
        "description": "A plug-and-play studio microphone for calls, streams and voice-overs. No drivers or audio interface needed.",
    },
    {
        "productId": "PODCAST-MIC", "category": "Audio", "name": "Dynamic Podcast Microphone",
        "price": "18999", "mrp": "23999", "rating": "4.8", "ratingCount": 612, "stock": 100,
        "highlights": ["Dynamic capsule rejects room noise", "USB-C and XLR outputs",
                       "Built-in pop filter and shock isolation", "Touch-to-mute with LED indicator"],
        "description": "A broadcast-style dynamic microphone that sounds close and clear even in untreated rooms.",
    },
    {
        "productId": "CURVED-MONITOR", "category": "Monitors", "name": "34-inch Curved Ultrawide Monitor",
        "price": "32999", "mrp": "44999", "rating": "4.5", "ratingCount": 788, "stock": 100,
        "highlights": ["3440 x 1440 resolution, 21:9 aspect ratio", "1500R curve and 144 Hz refresh",
                       "HDR10 with 400 nits peak brightness", "Picture-by-picture for two inputs"],
        "description": "An ultrawide curved display with room for two windows side by side and a smooth 144 Hz refresh rate.",
    },
    {
        "productId": "LAPTOP-STAND", "category": "Accessories", "name": "Aluminium Laptop Stand",
        "price": "1799", "mrp": "2499", "rating": "4.3", "ratingCount": 4210, "stock": 100,
        "highlights": ["Raises the screen to eye level", "Fits 10- to 17-inch laptops",
                       "Open design helps cooling", "Non-slip silicone pads"],
        "description": "A solid aluminium stand that lifts your laptop to a comfortable height and keeps it cool.",
    },
    {
        "productId": "DESK-MAT", "category": "Accessories", "name": "Felt and Leather Desk Mat",
        "price": "1299", "mrp": "1599", "rating": "3.9", "ratingCount": 538, "stock": 100,
        "highlights": ["90 x 40 cm covers keyboard and mouse", "Water-resistant vegan leather top",
                       "Wool felt underside does not slide", "Stitched edges resist fraying"],
        "description": "A large two-material desk mat that protects your desk and gives the mouse a smooth, consistent glide.",
    },
    {
        "productId": "WEBCAM-1080P", "category": "Accessories", "name": "1080p Streaming Webcam",
        "price": "6999", "mrp": "8999", "rating": "4.1", "ratingCount": 1457, "stock": 0,
        "highlights": ["Full HD 1080p at 60 fps", "Auto light correction and autofocus",
                       "Dual noise-reducing microphones", "Privacy shutter and universal clip"],
        "description": "A crisp webcam for calls and streams, with automatic light correction for dim rooms.",
    },
]


def main() -> None:
    outputs = load_outputs()
    table = boto3.resource("dynamodb", region_name=outputs["region"]).Table(outputs["inventory_table"])

    with table.batch_writer() as batch:
        for product in PRODUCTS:
            batch.put_item(
                Item={
                    **product,
                    "price": Decimal(product["price"]),
                    "mrp": Decimal(product["mrp"]),
                    "rating": Decimal(product["rating"]),
                    "reserved": 0,
                    "imageKey": f"products/{product['productId'].lower()}.webp",
                }
            )

    print(f"Seeded {len(PRODUCTS)} products into {table.name}:")
    for p in PRODUCTS:
        print(f"  {p['productId']:<17} {p['category']:<12} INR {p['price']:>6} (MRP {p['mrp']:>6})  stock={p['stock']:<4} {p['name']}")


if __name__ == "__main__":
    main()
