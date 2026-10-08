from pathlib import Path


def ensure_dir(path: str) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def home_config() -> Path:
    return Path(os.path.expanduser("~")) / ".config" / "app"
