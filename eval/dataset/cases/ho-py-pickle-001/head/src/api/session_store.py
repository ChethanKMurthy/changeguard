import pickle


def decode_session(blob: bytes) -> dict:
    return pickle.loads(blob)
