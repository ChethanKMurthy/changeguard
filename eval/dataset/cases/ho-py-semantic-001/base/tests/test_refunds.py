from billing.refunds import refund_amount


def test_full_refund_when_unused():
    assert refund_amount(30.0, 0, 30) == 30.0
