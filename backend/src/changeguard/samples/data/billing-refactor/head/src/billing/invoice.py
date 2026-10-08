"""Invoice assembly."""

from decimal import Decimal

from billing.pricing import apply_discount, format_price, total_with_tax


def render_line(description: str, amount: Decimal, currency: str) -> str:
    return f"{description}: {format_price(amount, currency=currency)}"


def invoice_total(items: list[Decimal], discount: int, region: str) -> Decimal:
    subtotal = sum(items, Decimal("0"))
    discounted = apply_discount(subtotal, discount)
    return total_with_tax(discounted, region)
