from datetime import datetime


def audit_timestamp() -> str:
    return datetime.now().isoformat()
