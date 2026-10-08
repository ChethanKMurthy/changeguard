def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def clamp(value: float, low: float, high: float) -> float:
    # Keep value within [low, high].
    return max(low, min(high, value))
