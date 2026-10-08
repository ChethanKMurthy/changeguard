from textutil.wrap import truncate


def test_short_text_unchanged():
    assert truncate("hi", 10) == "hi"


def test_long_text_truncated():
    assert truncate("abcdefghij", 5) == "abcd…"


def test_custom_ellipsis():
    assert truncate("abcdefghij", 5, "...") == "ab..."
