from events.model import Event


def user_signed_up(user_id: int) -> Event:
    return Event("user.signed_up", {"user_id": user_id})
