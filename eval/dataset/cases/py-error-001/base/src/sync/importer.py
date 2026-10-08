import json
import logging

log = logging.getLogger(__name__)


def import_records(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("skipping malformed record")
    return records
