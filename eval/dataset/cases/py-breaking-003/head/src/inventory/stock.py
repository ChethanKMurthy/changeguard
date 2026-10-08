class StockLedger:
    def __init__(self) -> None:
        self.levels: dict[tuple[str, str], int] = {}

    def reserve_units(self, sku: str, quantity: int, warehouse: str) -> bool:
        available = self.levels.get((warehouse, sku), 0)
        if available < quantity:
            return False
        self.levels[(warehouse, sku)] = available - quantity
        return True

    def reserve_bundle(self, skus: list[str]) -> bool:
        return all(self.reserve_units(sku, 1) for sku in skus)
