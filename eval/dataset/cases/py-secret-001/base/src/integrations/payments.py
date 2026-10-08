import os


def api_key() -> str:
    return os.environ["PAYMENTS_API_KEY"]
