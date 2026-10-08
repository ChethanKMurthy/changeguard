def warm_cache(keys: list[str], loader) -> int:
    loaded = 0
    for key in keys:
        loader(key)
        loaded += 1
    return loaded
