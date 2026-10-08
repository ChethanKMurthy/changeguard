import json
import logging

log = logging.getLogger(__name__)


def import_records(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        records.append(json.loads(line))
    return records
