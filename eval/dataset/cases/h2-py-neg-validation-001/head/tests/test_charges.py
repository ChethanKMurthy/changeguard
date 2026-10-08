import pytest

from billing.charges import charge


def test_charge_is_pending():
    assert charge(500)["status"] == "pending"


def test_rejects_non_positive_amounts():
    with pytest.raises(ValueError):
        charge(0)
