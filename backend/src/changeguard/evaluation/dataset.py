"""Evaluation dataset: labelled code-change cases.

Layout of one case (``eval/dataset/cases/<id>/``)::

    case.yaml      metadata + labels (see eval/LABELING.md)
    base/          repository before the change
    head/          repository after the change (reference only; the harness
                   applies change.patch to base/, exactly like real usage)
    change.patch   generated with `git diff` (tools/make_patch.py)
    coverage.xml   optional coverage report for the head revision
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from changeguard.report.models import Category, Severity


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    file: str
    lines: tuple[int, int] | None = None
    severity: Severity = Severity.MEDIUM
    side: Literal["head", "base"] = "head"
    note: str = ""

    @field_validator("lines", mode="before")
    @classmethod
    def _pair(cls, value: object) -> object:
        if isinstance(value, int):
            return (value, value)
        if isinstance(value, list) and len(value) == 1:
            return (value[0], value[0])
        return value


class Acceptable(BaseModel):
    """A true-but-secondary observation: never counted as a false positive, never required."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    file: str | None = None
    lines: tuple[int, int] | None = None
    note: str = ""


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    split: Literal["dev", "holdout", "holdout-v2"]
    language: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    mode: Literal["full_context", "diff_only"] = "full_context"
    source: str = "synthetic"
    description: str
    tags: list[str] = Field(default_factory=list)
    negative: bool = False
    expected: list[Label] = Field(default_factory=list)
    acceptable: list[Acceptable] = Field(default_factory=list)

    # Populated by the loader (not part of case.yaml).
    directory: Path | None = Field(default=None, exclude=True)

    def patch_text(self) -> str:
        assert self.directory is not None
        return (self.directory / "change.patch").read_text()

    def coverage_bytes(self) -> bytes | None:
        assert self.directory is not None
        for name in ("coverage.xml", "lcov.info", "coverage.json"):
            path = self.directory / name
            if path.exists():
                return path.read_bytes()
        return None

    def archive(self) -> bytes:
        assert self.directory is not None
        buffer = io.BytesIO()
        base = self.directory / "base"
        with zipfile.ZipFile(buffer, "w") as zf:
            if base.exists():
                for path in sorted(base.rglob("*")):
                    if path.is_file():
                        zf.write(path, str(path.relative_to(base)))
        return buffer.getvalue()

    def read(self, side: Literal["head", "base"], path: str) -> str | None:
        assert self.directory is not None
        file = self.directory / side / path
        return file.read_text() if file.is_file() else None


def load_dataset(root: Path, *, split: str | None = None) -> list[Case]:
    cases_dir = root / "cases" if (root / "cases").is_dir() else root
    cases: list[Case] = []
    for directory in sorted(p for p in cases_dir.iterdir() if (p / "case.yaml").exists()):
        data = yaml.safe_load((directory / "case.yaml").read_text())
        case = Case.model_validate(data)
        if case.id != directory.name:
            raise ValueError(f"case id '{case.id}' does not match directory '{directory.name}'")
        if not (directory / "change.patch").exists():
            raise ValueError(f"case '{case.id}' has no change.patch (run tools/make_patch.py)")
        case.directory = directory
        if split is None or case.split == split:
            cases.append(case)
    return cases


def dataset_fingerprint(cases: list[Case]) -> str:
    """SHA-256 over every file of every case (identifies the exact dataset version)."""
    digest = hashlib.sha256()
    for case in sorted(cases, key=lambda c: c.id):
        assert case.directory is not None
        for path in sorted(p for p in case.directory.rglob("*") if p.is_file()):
            digest.update(str(path.relative_to(case.directory.parent)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
