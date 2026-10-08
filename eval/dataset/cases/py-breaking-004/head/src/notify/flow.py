from notify.email import send_receipt


def finish_order(address: str, order_id: str) -> str:
    sent = send_receipt(address, order_id)
    return "notified" if sent else "pending"
