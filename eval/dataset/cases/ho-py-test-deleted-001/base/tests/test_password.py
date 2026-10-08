import hashlib

from auth.password import verify


def test_verify_accepts_correct_password():
    salt = b"salt"
    expected = hashlib.pbkdf2_hmac("sha256", b"pw", salt, 200_000)
    assert verify("pw", salt, expected)


def test_verify_rejects_wrong_password():
    salt = b"salt"
    expected = hashlib.pbkdf2_hmac("sha256", b"pw", salt, 200_000)
    assert not verify("nope", salt, expected)
