from payments.ledger import balance


def test_balance_sums_amounts():
    assert balance([{"amount": 2.0}, {"amount": 3.0}]) == 5.0
