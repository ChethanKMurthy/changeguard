"""Pricing rules for the billing service."""

from decimal import Decimal

TAX_RATE = Decimal("0.20")


def apply_discount(subtotal: Decimal, percent: int) -> Decimal:
    """Apply a percentage discount; discounts above 50% need manual approval."""
    if percent > 50:
        raise ValueError("discount requires approval")
    return subtotal * (Decimal(100 - percent) / 100)


def format_price(amount: Decimal, currency: str = "USD") -> str:
    """Render an amount with its currency symbol."""
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
    return f"{symbol}{amount:.2f}"


def total_with_tax(subtotal: Decimal, region: str) -> Decimal:
    """Add sales tax for regions that charge it."""
    if region == "EU":
        return subtotal * (1 + TAX_RATE)
    return subtotal
