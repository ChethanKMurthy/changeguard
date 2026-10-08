from decimal import Decimal

import pytest

from billing.pricing import apply_discount, format_price


def test_apply_discount_basic():
    assert apply_discount(Decimal("100"), 10) == Decimal("90")


def test_apply_discount_requires_approval():
    with pytest.raises(ValueError):
        apply_discount(Decimal("100"), 60)


def test_format_price_defaults_to_usd():
    assert format_price(Decimal("5")) == "$5.00"
    assert format_price(Decimal("5"), "EUR") == "€5.00"
