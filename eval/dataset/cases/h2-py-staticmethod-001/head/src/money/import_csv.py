from money.amount import Money


def row_amount(row: dict[str, str]) -> Money:
    return Money.parse(row["amount"], row["currency"])
