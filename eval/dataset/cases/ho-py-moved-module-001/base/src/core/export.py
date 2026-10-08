from core.helpers import chunked


def pages(rows: list[str]) -> list[list[str]]:
    return chunked(rows, 50)
