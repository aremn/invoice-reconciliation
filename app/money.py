"""Money helpers. All amounts are integer USD cents.

Rounding rule: nothing is rounded silently. Amounts read from a document are parsed
with Decimal; a value that is not a whole number of cents (e.g. "12.345") is rejected
as an invalid extraction. After parsing, every calculation is integer multiplication
or subtraction in cents, so no intermediate rounding is needed.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_cents(text: str) -> int:
    """'120.00' -> 12000, '$1,200.5' -> 120050. Raises ValueError on anything else."""
    cleaned = text.strip().upper().replace("USD", "").replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not an amount: {text!r}") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"not a valid amount: {text!r}")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"amount has fractions of a cent: {text!r}")
    return int(cents)


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"
