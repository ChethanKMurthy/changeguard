from core.collections_util import chunked


def batches(ids: list[int]) -> list[list[int]]:
    return chunked(ids, 100)
