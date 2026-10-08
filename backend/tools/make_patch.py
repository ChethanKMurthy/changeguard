"""Generate a real ``git diff`` patch from ``base/`` and ``head/`` directories.

Development tool used to build the sample scenarios and evaluation cases, so
every patch in the repository is produced by git itself (realistic hunk
headers, rename detection) rather than written by hand.

Usage::

    uv run python tools/make_patch.py <case_dir>          # writes <case_dir>/change.patch
    uv run python tools/make_patch.py --all <root_dir>    # every subdirectory with base/ and head/
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ATTRIBUTES = "*.py diff=python\n"


def _git(repo: Path, *args: str, env: dict[str, str]) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def make_patch(base: Path, head: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "repo"
        attributes = tmp_path / "attributes"
        attributes.write_text(_ATTRIBUTES)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": tmp,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "ChangeGuard",
            "GIT_AUTHOR_EMAIL": "samples@changeguard.invalid",
            "GIT_COMMITTER_NAME": "ChangeGuard",
            "GIT_COMMITTER_EMAIL": "samples@changeguard.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        }
        shutil.copytree(base, repo) if base.exists() else repo.mkdir()
        _git(repo, "init", "-q", "-b", "main", env=env)
        _git(repo, "add", "-A", env=env)
        _git(repo, "commit", "-q", "--allow-empty", "-m", "base", env=env)
        for child in repo.iterdir():
            if child.name == ".git":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        if head.exists():
            shutil.copytree(head, repo, dirs_exist_ok=True)
        _git(repo, "add", "-A", env=env)
        return _git(
            repo,
            "-c", f"core.attributesFile={attributes}",
            "diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color", "-M", "HEAD",
            env=env,
        )  # fmt: skip


def write_case(case_dir: Path) -> Path:
    patch = make_patch(case_dir / "base", case_dir / "head")
    if not patch.strip():
        raise SystemExit(f"{case_dir}: base/ and head/ are identical")
    out = case_dir / "change.patch"
    out.write_text(patch)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--all", action="store_true", help="treat PATH as a directory of cases")
    args = parser.parse_args(argv)
    cases = (
        sorted(p for p in args.path.iterdir() if (p / "head").exists() or (p / "base").exists())
        if args.all
        else [args.path]
    )
    for case in cases:
        out = write_case(case)
        print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
