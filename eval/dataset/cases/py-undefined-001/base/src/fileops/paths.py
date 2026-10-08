import os
from pathlib import Path


def ensure_dir(path: str) -> Path:
    os.makedirs(path, exist_ok=True)
    return Path(path)


def home_config() -> Path:
    return Path(os.path.expanduser("~")) / ".config" / "app"
