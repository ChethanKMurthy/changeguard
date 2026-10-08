from dataclasses import dataclass


@dataclass
class Line:
    price: float
    quantity: int


def cart_total(lines: list[Line]) -> float:
    total = 0.0
    for line in lines:
        total += line.price * line.quantity
    return round(total, 2)
