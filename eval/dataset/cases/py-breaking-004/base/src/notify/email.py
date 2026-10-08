def send_receipt(address: str, order_id: str) -> bool:
    message = f"Receipt for order {order_id}"
    return deliver(address, message)


def deliver(address: str, message: str) -> bool:
    return bool(address and message)
