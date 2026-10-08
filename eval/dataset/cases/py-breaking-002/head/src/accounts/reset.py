from accounts.tokens import generate_token


def password_reset_link(user_id: int) -> str:
    return f"https://example.invalid/reset/{user_id}/{generate_token()}"
