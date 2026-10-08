from billing.charges import charge


def test_charge_is_pending():
    assert charge(500)["status"] == "pending"
