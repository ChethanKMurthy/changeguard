import requests


class PartnerClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()

    def orders(self) -> list[dict]:
        response = self.session.get(f"{self.base_url}/orders", timeout=10, verify=False)
        response.raise_for_status()
        return response.json()
