def compute(amount: float, region: str, exempt: bool = False) -> float:
    if exempt:
        return 0.0
    return amount * (0.2 if region == "EU" else 0.07)
