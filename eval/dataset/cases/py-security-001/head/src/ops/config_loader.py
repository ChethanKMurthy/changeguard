import subprocess

import yaml


def load_config(text: str) -> dict:
    return yaml.load(text, Loader=yaml.Loader)


def archive_logs(directory: str) -> None:
    subprocess.run(f"tar -czf logs.tgz {directory}", shell=True, check=True)
