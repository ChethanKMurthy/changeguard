import requests


def post_event(url: str, payload: dict) -> int:
    response = requests.post(url, json=payload, timeout=10)
    return response.status_code
