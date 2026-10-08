from datetime import datetime, timezone


def audit_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
