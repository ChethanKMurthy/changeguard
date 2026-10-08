def warm_cache(keys: list[str], loader) -> int:
    loaded = 0
    for key in keys:
        try:
            loader(key)
            loaded += 1
        except Exception:
            pass
    return loaded
