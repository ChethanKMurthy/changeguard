from decimal import Decimal


class Money:
    def __init__(self, value: Decimal, currency: str) -> None:
        self.value = value
        self.currency = currency

    @staticmethod
    def parse(text: str, currency: str) -> "Money":
        return Money(Decimal(text), currency)
