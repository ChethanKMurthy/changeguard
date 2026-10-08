import billing.tax as tax


def line_tax(amount: float, region: str) -> float:
    return tax.compute(amount, region=region, exempt=False)
