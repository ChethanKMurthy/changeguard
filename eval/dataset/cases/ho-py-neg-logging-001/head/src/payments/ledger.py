import logging

log = logging.getLogger(__name__)


def balance(entries: list[dict[str, float]]) -> float:
    total = sum(e["amount"] for e in entries)
    log.debug("computed balance over %d entries", len(entries))
    return total
