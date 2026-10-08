def seasonal_discount(month: int, member: bool = False) -> float:
    if month == 12:
        return 0.15
    if member and month in (6, 7):
        return 0.10
    return 0.0
