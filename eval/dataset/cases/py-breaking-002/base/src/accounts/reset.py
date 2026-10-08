from accounts.tokens import make_token


def password_reset_link(user_id: int) -> str:
    return f"https://example.invalid/reset/{user_id}/{make_token()}"
