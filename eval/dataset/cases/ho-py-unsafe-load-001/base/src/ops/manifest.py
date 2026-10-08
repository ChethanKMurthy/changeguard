import yaml


def read_manifest(text: str) -> dict:
    return yaml.safe_load(text)
