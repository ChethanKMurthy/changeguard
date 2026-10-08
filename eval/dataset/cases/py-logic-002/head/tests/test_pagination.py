from reports.pagination import page_slices


def test_two_pages():
    assert page_slices(10, 5) == [(0, 5), (5, 10)]
