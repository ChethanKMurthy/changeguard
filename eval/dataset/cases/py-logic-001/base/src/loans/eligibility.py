MIN_SCORE = 650


def is_eligible(credit_score: int, income: float, debt: float) -> bool:
    if credit_score > MIN_SCORE and debt / max(income, 1.0) < 0.4:
        return True
    return False
