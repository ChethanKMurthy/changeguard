from billing.discounts import seasonal_discount


def test_december():
    assert seasonal_discount(12) == 0.15


def test_other_months():
    assert seasonal_discount(5) == 0.0
