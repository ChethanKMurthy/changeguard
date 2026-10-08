import yaml


def read_manifest(text: str) -> dict:
    return yaml.unsafe_load(text)
