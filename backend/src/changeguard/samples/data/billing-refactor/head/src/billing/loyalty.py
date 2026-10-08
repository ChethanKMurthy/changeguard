"""Loyalty programme bonuses."""

from decimal import Decimal


def loyalty_bonus(years: int, tier: str) -> Decimal:
    if tier == "gold" and years > 3:
        return Decimal("0.05")
    if tier == "silver":
        return Decimal("0.02")
    return Decimal("0")
