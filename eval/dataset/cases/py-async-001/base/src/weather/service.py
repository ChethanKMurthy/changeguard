import httpx


async def current_temperature(city: str) -> float:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"https://weather.example.invalid/{city}")
    return float(response.json()["temp"])
