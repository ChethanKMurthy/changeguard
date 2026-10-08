from http_client.client import fetch


def download_report(url: str) -> bytes:
    return fetch(url)
