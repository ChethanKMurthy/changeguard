import asyncio


async def poll(fetch, interval: float = 1.0, attempts: int = 5):
    for _ in range(attempts):
        result = await fetch()
        if result is not None:
            return result
        await asyncio.sleep(interval)
    return None
