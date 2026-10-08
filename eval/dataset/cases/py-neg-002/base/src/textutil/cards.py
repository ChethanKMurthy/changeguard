from textutil.wrap import truncate


def card_title(title: str) -> str:
    return truncate(title, 40)
