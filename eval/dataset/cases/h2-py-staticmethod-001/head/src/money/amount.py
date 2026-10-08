from decimal import Decimal


class Money:
    def __init__(self, value: Decimal, currency: str) -> None:
        self.value = value
        self.currency = currency

    @staticmethod
    def parse(text: str) -> "Money":
        value, currency = text.split(" ")
        return Money(Decimal(value), currency)
