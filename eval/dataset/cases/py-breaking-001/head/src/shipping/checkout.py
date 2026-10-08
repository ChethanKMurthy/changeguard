from shipping.rates import shipping_cost


def checkout_total(subtotal: float, weight_kg: float, express: bool) -> float:
    return subtotal + shipping_cost(weight_kg, express=express, insured=subtotal > 500)
