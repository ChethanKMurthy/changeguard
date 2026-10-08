import urllib.request


def fetch(url: str, timeout: float = 30.0, retries: int = 1) -> bytes:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read()
        except OSError as exc:
            last_error = exc
    raise RuntimeError(f"failed after {retries} attempts") from last_error
