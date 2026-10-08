from accounts.tokens import make_token


def invite_code() -> str:
    return make_token(16)
