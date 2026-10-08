from geo.distance import haversine_km


def test_same_point_is_zero():
    assert haversine_km(51.5, -0.1, 51.5, -0.1) == 0.0
