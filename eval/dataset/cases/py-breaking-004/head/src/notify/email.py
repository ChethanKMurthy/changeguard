import asyncio


async def send_receipt(address: str, order_id: str) -> bool:
    message = f"Receipt for order {order_id}"
    await asyncio.sleep(0)
    return deliver(address, message)


def deliver(address: str, message: str) -> bool:
    return bool(address and message)
