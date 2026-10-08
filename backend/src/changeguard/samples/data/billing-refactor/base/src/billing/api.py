"""HTTP handlers for the billing service."""

import json

from billing.invoice import invoice_total


async def handle_invoice(request_body: str) -> dict[str, str]:
    payload = json.loads(request_body)
    total = invoice_total(payload["items"], payload.get("discount", 0), payload["region"])
    return {"total": str(total)}
