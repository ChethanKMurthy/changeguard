import requests


async def current_temperature(city: str) -> float:
    response = requests.get(f"https://weather.example.invalid/{city}", timeout=5)
    return float(response.json()["temp"])
