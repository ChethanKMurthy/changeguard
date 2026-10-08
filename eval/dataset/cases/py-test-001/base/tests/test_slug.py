from textutil.slug import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("  Trim me  ") == "trim-me"


def test_slugify_unicode():
    assert slugify("Café Déjà Vu") == "cafe-deja-vu"
