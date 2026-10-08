def compute(amount: float, region: str) -> float:
    return amount * (0.2 if region == "EU" else 0.07)
