"""Coverage report parsing and path reconciliation.

Supported formats
-----------------
* Cobertura XML (``coverage xml``, Jest/Istanbul ``cobertura`` reporter)
* LCOV tracefiles (``lcov.info`` from Istanbul/c8/Jest, ``coverage lcov``)
* coverage.py JSON (``coverage json``)

The report is untrusted: XML is parsed with ``defusedxml`` (no external
entities, no entity expansion bombs), and all numbers are validated.

ChangeGuard only *reads* coverage numbers. It never runs tests, so every
coverage statement in a report is attributed to the uploaded file.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

import defusedxml.ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from changeguard.errors import CoverageParseError

CoverageFormat = Literal["cobertura", "lcov", "coverage.py-json"]
MAX_LINE_NUMBER = 5_000_000


@dataclass(slots=True)
class FileCoverage:
    path: str
    # line number -> hit count (0 = executable but not executed)
    lines: dict[int, int] = field(default_factory=dict)

    @property
    def executable(self) -> int:
        return len(self.lines)

    @property
    def covered(self) -> int:
        return sum(1 for hits in self.lines.values() if hits > 0)


@dataclass(slots=True)
class CoverageReport:
    format: CoverageFormat
    files: dict[str, FileCoverage]
    source_roots: list[str] = field(default_factory=list)

    def match(self, repo_paths: list[str]) -> tuple[dict[str, FileCoverage], list[str]]:
        """Map repository paths to coverage entries.

        Coverage tools record paths relative to different roots (absolute
        paths, ``src/``-relative module paths, ...). We match on the longest
        shared path suffix and require the match to be unambiguous. Returns
        ``(matches, unmatched_coverage_paths)``.
        """
        matches: dict[str, FileCoverage] = {}
        used: set[str] = set()
        basenames = Counter(PurePosixPath(p).name for p in repo_paths)
        for repo_path in repo_paths:
            best: tuple[int, str] | None = None
            ambiguous = False
            repo_parts = PurePosixPath(repo_path).parts
            for cov_path in self.files:
                score = _shared_suffix(
                    repo_parts, PurePosixPath(_strip_roots(cov_path, self.source_roots)).parts
                )
                if score == 0:
                    continue
                # Require the file name plus one directory to match, unless the
                # file sits at the repository root or its name is unique.
                min_score = 1 if basenames[repo_parts[-1]] == 1 else min(2, len(repo_parts))
                if score < min_score:
                    continue
                if best is None or score > best[0]:
                    best, ambiguous = (score, cov_path), False
                elif score == best[0]:
                    ambiguous = True
            if best is not None and not ambiguous:
                matches[repo_path] = self.files[best[1]]
                used.add(best[1])
        unmatched = sorted(set(self.files) - used)
        return matches, unmatched


def parse_coverage(data: bytes, filename: str | None = None) -> CoverageReport:
    """Detect the format from content and parse the report."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CoverageParseError("coverage report is not valid UTF-8 text") from exc
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return _parse_cobertura(text)
    if stripped.startswith("{"):
        return _parse_coverage_json(text)
    if "SF:" in text and "end_of_record" in text:
        return _parse_lcov(text)
    hint = f" '{filename}'" if filename else ""
    raise CoverageParseError(
        f"could not recognise coverage report{hint}; supported formats are Cobertura XML, LCOV, and coverage.py JSON"
    )


def _parse_cobertura(text: str) -> CoverageReport:
    try:
        root = SafeET.fromstring(text)
    except DefusedXmlException as exc:
        raise CoverageParseError(
            "coverage XML uses forbidden constructs (entities or DTDs)"
        ) from exc
    except SafeET.ParseError as exc:
        raise CoverageParseError("coverage XML is malformed") from exc
    if root.tag != "coverage":
        raise CoverageParseError("XML root element is not <coverage>; expected a Cobertura report")
    roots = [
        (s.text or "").strip().replace("\\", "/")
        for s in root.iter("source")
        if (s.text or "").strip()
    ]
    files: dict[str, FileCoverage] = {}
    for cls in root.iter("class"):
        filename = (cls.get("filename") or "").replace("\\", "/")
        if not filename:
            continue
        cov = files.setdefault(filename, FileCoverage(filename))
        for line in cls.iter("line"):
            number = _to_int(line.get("number"))
            hits = _to_int(line.get("hits"))
            if number is None or hits is None:
                raise CoverageParseError(f"invalid <line> entry for '{filename}'")
            _record(cov, number, hits)
    if not files:
        raise CoverageParseError("Cobertura report contains no <class> entries")
    return CoverageReport("cobertura", files, roots)


def _parse_lcov(text: str) -> CoverageReport:
    files: dict[str, FileCoverage] = {}
    current: FileCoverage | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("SF:"):
            path = line[3:].strip().replace("\\", "/")
            current = files.setdefault(path, FileCoverage(path))
        elif line.startswith("DA:"):
            if current is None:
                raise CoverageParseError(f"LCOV DA record outside a file section (line {lineno})")
            parts = line[3:].split(",")
            number = _to_int(parts[0]) if parts else None
            hits = _to_int(parts[1]) if len(parts) > 1 else None
            if number is None or hits is None:
                raise CoverageParseError(f"invalid LCOV DA record (line {lineno})")
            _record(current, number, hits)
        elif line == "end_of_record":
            current = None
    if not files:
        raise CoverageParseError("LCOV report contains no SF records")
    return CoverageReport("lcov", files)


def _parse_coverage_json(text: str) -> CoverageReport:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CoverageParseError("coverage JSON is malformed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        raise CoverageParseError(
            "coverage JSON must contain a 'files' object (coverage.py `coverage json` format)"
        )
    files: dict[str, FileCoverage] = {}
    for path, entry in payload["files"].items():
        if not isinstance(path, str) or not isinstance(entry, dict):
            raise CoverageParseError("coverage JSON 'files' entries must be objects")
        norm = path.replace("\\", "/")
        cov = FileCoverage(norm)
        for key, hits in (("executed_lines", 1), ("missing_lines", 0)):
            numbers = entry.get(key, [])
            if not isinstance(numbers, list):
                raise CoverageParseError(f"'{key}' for '{path}' must be a list")
            for number in numbers:
                if not isinstance(number, int) or isinstance(number, bool):
                    raise CoverageParseError(f"non-integer line number in '{key}' for '{path}'")
                _record(cov, number, hits)
        files[norm] = cov
    if not files:
        raise CoverageParseError("coverage JSON contains no files")
    return CoverageReport("coverage.py-json", files)


def _record(cov: FileCoverage, number: int, hits: int) -> None:
    if number < 1 or number > MAX_LINE_NUMBER or hits < 0:
        raise CoverageParseError(f"out-of-range line or hit count in coverage for '{cov.path}'")
    cov.lines[number] = max(cov.lines.get(number, 0), hits)


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value.isdigit():
        return None
    return int(value)


def _strip_roots(path: str, roots: list[str]) -> str:
    for root in sorted(roots, key=len, reverse=True):
        prefix = root.rstrip("/") + "/"
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path.lstrip("/")


def _shared_suffix(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    count = 0
    for x, y in zip(reversed(a), reversed(b), strict=False):
        if x != y:
            break
        count += 1
    return count
