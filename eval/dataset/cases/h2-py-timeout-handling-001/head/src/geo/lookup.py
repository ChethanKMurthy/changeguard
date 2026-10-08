import logging

import requests

log = logging.getLogger(__name__)


def country_of(ip: str) -> str | None:
    response = requests.get(f"https://geo.example.invalid/{ip}", timeout=2)
    return response.json()["country"]
