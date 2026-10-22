"""Indian-rupee formatting for user-facing messages (statusHistory details, feed rows)."""

from __future__ import annotations

from decimal import Decimal


def format_inr(amount: Decimal | int | float | str) -> str:
    """Format with Indian digit grouping: 992403 -> '₹9,92,403', 1234.5 -> '₹1,234.50'."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    sign = "-" if value < 0 else ""
    whole, _, paise = f"{abs(value):.2f}".partition(".")
    # Last 3 digits, then groups of 2 (lakh, crore): 1234567 -> 12,34,567
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join(groups + [tail]) if groups else tail
    return f"{sign}₹{grouped}" + ("" if paise == "00" else f".{paise}")
