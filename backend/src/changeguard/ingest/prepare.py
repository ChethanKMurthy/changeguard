"""Validate and parse raw inputs (patch, snapshot archive, coverage report)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from changeguard.config import Settings
from changeguard.errors import PatchParseError, PayloadTooLargeError
from changeguard.ingest.archive import ArchiveLimits, Snapshot, read_snapshot
from changeguard.ingest.coverage import CoverageReport, parse_coverage
from changeguard.ingest.diff_parser import ParseLimits, PatchSet, parse_patch


@dataclass(slots=True)
class PreparedInput:
    patch_text: str
    patch: PatchSet
    patch_sha256: str
    snapshot: Snapshot | None = None
    coverage: CoverageReport | None = None
    ingest_ms: float = 0.0
    filenames: dict[str, str] = field(default_factory=dict)


def decode_patch(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # Legacy encodings occur in old repositories; latin-1 never fails and
        # preserves byte offsets, so line structure stays intact.
        return data.decode("latin-1")


def prepare_input(
    settings: Settings,
    *,
    patch: str | bytes,
    archive: bytes | None = None,
    coverage: bytes | None = None,
    filenames: dict[str, str] | None = None,
) -> PreparedInput:
    started = time.perf_counter()
    raw = patch.encode("utf-8") if isinstance(patch, str) else patch
    if len(raw) > settings.max_patch_bytes:
        raise PayloadTooLargeError(
            f"patch is {len(raw) / 1e6:.1f} MB; the limit is {settings.max_patch_bytes / 1e6:.1f} MB"
        )
    if not raw.strip():
        raise PatchParseError("patch is empty")
    text = patch if isinstance(patch, str) else decode_patch(patch)
    parsed = parse_patch(
        text, ParseLimits(max_files=settings.max_patch_files, max_lines=settings.max_patch_lines)
    )

    snapshot = None
    if archive:
        if len(archive) > settings.max_archive_bytes:
            raise PayloadTooLargeError(
                f"repository archive is {len(archive) / 1e6:.1f} MB; the limit is {settings.max_archive_bytes / 1e6:.0f} MB"
            )
        snapshot = read_snapshot(
            archive,
            (filenames or {}).get("archive"),
            ArchiveLimits(
                max_members=settings.max_archive_members,
                max_file_bytes=settings.max_source_file_bytes,
                max_total_bytes=settings.max_archive_uncompressed_bytes,
            ),
        )
    report = None
    if coverage:
        if len(coverage) > settings.max_coverage_bytes:
            raise PayloadTooLargeError(
                f"coverage report is {len(coverage) / 1e6:.1f} MB; the limit is {settings.max_coverage_bytes / 1e6:.0f} MB"
            )
        report = parse_coverage(coverage, (filenames or {}).get("coverage"))
    return PreparedInput(
        patch_text=text,
        patch=parsed,
        patch_sha256=hashlib.sha256(raw).hexdigest(),
        snapshot=snapshot,
        coverage=report,
        ingest_ms=(time.perf_counter() - started) * 1000,
        filenames=dict(filenames or {}),
    )
