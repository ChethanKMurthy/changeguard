def refund_amount(paid: float, used_days: int, period_days: int) -> float:
    unused_ratio = (period_days - used_days) / period_days
    return round(paid * unused_ratio, 2)
