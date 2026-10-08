import hashlib
import hmac


def verify(password: str, salt: bytes, expected: bytes) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(digest, expected)
