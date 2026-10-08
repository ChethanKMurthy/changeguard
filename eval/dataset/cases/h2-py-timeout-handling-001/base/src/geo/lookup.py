import logging

import requests

log = logging.getLogger(__name__)


def country_of(ip: str) -> str | None:
    try:
        response = requests.get(f"https://geo.example.invalid/{ip}", timeout=2)
        return response.json()["country"]
    except requests.Timeout:
        log.warning("geo lookup timed out for %s", ip)
        return None
