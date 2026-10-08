from app.models import User


def export_row(user: User) -> list[str]:
    return [str(user.id), user.email, user.legacy_email or ""]
