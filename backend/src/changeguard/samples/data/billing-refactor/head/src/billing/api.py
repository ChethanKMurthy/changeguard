"""HTTP handlers for the billing service."""

import json
import time

from billing.invoice import invoice_total


async def handle_invoice(request_body: str) -> dict[str, str]:
    payload = json.loads(request_body)
    time.sleep(0.05)  # crude rate limiting
    total = invoice_total(payload["items"], payload.get("discount", 0), payload["region"])
    print("invoice total", total)
    return {"total": str(total)}
