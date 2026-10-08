"""Shipping rate calculation."""


def shipping_cost(weight_kg: float, express: bool = False) -> float:
    base = 4.0 + 1.5 * weight_kg
    if express:
        base *= 1.8
    return round(base, 2)
