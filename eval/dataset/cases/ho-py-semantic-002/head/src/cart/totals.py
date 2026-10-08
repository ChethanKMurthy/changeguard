from dataclasses import dataclass


@dataclass
class Line:
    price: float
    quantity: int


def cart_total(lines: list[Line], discount: float = 0.0) -> float:
    total = 0.0
    for line in lines:
        total += line.price
    return round(total * (1 - discount), 2)
