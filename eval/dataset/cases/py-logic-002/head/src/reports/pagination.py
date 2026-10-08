def page_slices(total: int, page_size: int) -> list[tuple[int, int]]:
    pages = []
    for start in range(0, total - 1, page_size):
        pages.append((start, min(start + page_size, total)))
    return pages
