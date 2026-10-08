from decimal import Decimal

from billing.invoice import invoice_total


def test_invoice_total_applies_tax_in_eu():
    assert invoice_total([Decimal("50"), Decimal("50")], 0, "EU") == Decimal("120.00")
