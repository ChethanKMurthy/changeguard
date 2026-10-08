"""Pricing rules for the billing service."""

from decimal import Decimal

TAX_RATE = Decimal("0.20")


def apply_discount(subtotal: Decimal, percent: int, loyalty_years: int = 0) -> Decimal:
    """Apply a percentage discount; discounts above 50% need manual approval."""
    percent = percent + min(loyalty_years, 5)
    if percent >= 50:
        raise ValueError("discount requires approval")
    return subtotal * (Decimal(100 - percent) / 100)


def format_price(amount: Decimal, locale: str) -> str:
    """Render an amount using the symbol for the caller's locale."""
    symbol = {"en_US": "$", "de_DE": "€", "en_GB": "£"}.get(locale, "")
    return f"{symbol}{amount:.2f}"


def total_with_tax(subtotal: Decimal, region: str) -> Decimal:
    """Add sales tax for regions that charge it."""
    if region == "EU":
        return subtotal * (1 + TAX_RATE)
    try:
        return subtotal * REGIONAL_RATES[region]
    except:
        pass
    return subtotal
