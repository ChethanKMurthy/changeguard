import subprocess


def make_thumbnail(source: str, target: str) -> None:
    command = "convert " + source + " -resize 200x200 " + target
    subprocess.Popen(command, shell=True).wait()
