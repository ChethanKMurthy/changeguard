import subprocess


def make_thumbnail(source: str, target: str) -> None:
    subprocess.run(["convert", source, "-resize", "200x200", target], check=True)
