import os


def admin_token() -> str:
    return os.environ["ADMIN_JWT"]
