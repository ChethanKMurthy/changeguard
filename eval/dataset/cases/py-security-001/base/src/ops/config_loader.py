import json
import subprocess


def load_config(text: str) -> dict:
    return json.loads(text)


def archive_logs(directory: str) -> None:
    subprocess.run(["tar", "-czf", "logs.tgz", directory], check=True)
