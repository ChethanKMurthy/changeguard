from metrics.stats import clamp, mean


def test_mean():
    assert mean([1.0, 2.0, 3.0]) == 2.0
    assert mean([]) == 0.0


def test_clamp():
    assert clamp(5.0, 0.0, 1.0) == 1.0
