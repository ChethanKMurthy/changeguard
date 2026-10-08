from mail.sender import send


def disk_alert(admin: str, percent: int) -> dict:
    return send(admin, f"Disk at {percent}%")
