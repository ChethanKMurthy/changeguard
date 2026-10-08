from shipping.rates import shipping_cost


def test_standard_rate():
    assert shipping_cost(2.0) == 7.0
