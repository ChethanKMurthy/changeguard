from inventory.stock import StockLedger


def place_order(ledger: StockLedger, sku: str, quantity: int) -> str:
    if not ledger.reserve_units(sku, quantity):
        return "backordered"
    return "reserved"
