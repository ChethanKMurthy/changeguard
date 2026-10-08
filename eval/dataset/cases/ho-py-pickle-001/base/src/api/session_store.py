import json


def decode_session(blob: bytes) -> dict:
    return json.loads(blob.decode("utf-8"))
