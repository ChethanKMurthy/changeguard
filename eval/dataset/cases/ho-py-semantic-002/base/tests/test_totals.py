from cart.totals import Line, cart_total


def test_single_line():
    assert cart_total([Line(2.5, 1)]) == 2.5
