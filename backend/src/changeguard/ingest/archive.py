"""Safe, in-memory reading of repository snapshots (.zip, .tar, .tar.gz, ...).

Threat model: the archive is attacker-controlled. We therefore

* never extract to disk: members are read into memory, one at a time;
* reject absolute paths, ``..`` traversal, drive letters, and NUL bytes;
* ignore symlinks, hard links, devices, and FIFOs (they are never followed);
* cap the number of members, per-file size, and total decompressed bytes, and
  enforce the caps on bytes actually read, not on (forgeable) header values;
* reject members whose compression ratio indicates a decompression bomb;
* only keep text files that analysis can use (source, tests, manifests, SQL).
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import IO

from changeguard.errors import ArchiveError, PayloadTooLargeError

# Directories that never contain first-party source worth analysing.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        ".turbo",
        "dist",
        "build",
        "coverage",
        "htmlcov",
        ".idea",
        ".vscode",
        "site-packages",
    }
)

TEXT_EXTENSIONS = frozenset(
    {
        ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts",
        ".json", ".toml", ".cfg", ".ini", ".txt", ".yaml", ".yml", ".sql", ".md",
        ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp",
        ".swift", ".scala", ".sh", ".env", ".lock", ".xml", ".gradle", ".properties",
    }
)  # fmt: skip
TEXT_FILENAMES = frozenset(
    {
        "Dockerfile",
        "Makefile",
        "Procfile",
        "Gemfile",
        "Pipfile",
        ".env",
        ".env.example",
        "requirements.txt",
    }
)


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_members: int = 20_000
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 150_000_000
    max_compression_ratio: float = 200.0


@dataclass(slots=True)
class Snapshot:
    """Text files of a repository snapshot, keyed by POSIX path.

    ``root_prefix`` is a single top-level directory shared by every file (as in
    GitHub "Download ZIP" archives). Whether to strip it is decided later by
    comparing against the patch paths; see :meth:`strip_root`.
    """

    files: dict[str, str]
    root_prefix: str | None = None
    skipped: Counter[str] = field(default_factory=Counter)
    format: str = "zip"
    root_stripped: bool = False

    def strip_root(self) -> None:
        if self.root_prefix and not self.root_stripped:
            cut = len(self.root_prefix) + 1
            self.files = {path[cut:]: text for path, text in self.files.items()}
            self.root_stripped = True

    def stats(self) -> dict[str, object]:
        return {
            "files": len(self.files),
            "bytes": sum(len(v) for v in self.files.values()),
            "root_prefix": self.root_prefix if self.root_stripped else None,
            "skipped": dict(self.skipped),
            "format": self.format,
        }


def read_snapshot(
    data: bytes, filename: str | None = None, limits: ArchiveLimits | None = None
) -> Snapshot:
    """Read an uploaded archive into a :class:`Snapshot`.

    The archive type is detected from magic bytes, not the file name.
    """
    limits = limits or ArchiveLimits()
    if data[:4] == b"PK\x03\x04" or data[:4] == b"PK\x05\x06":
        entries = _iter_zip(data, limits)
        fmt = "zip"
    elif _looks_like_tar(data):
        entries = _iter_tar(data, limits)
        fmt = "tar"
    else:
        hint = f" ({filename})" if filename else ""
        raise ArchiveError(
            f"unsupported archive format{hint}; upload a .zip, .tar, .tar.gz, .tar.bz2 or .tar.xz"
        )

    files: dict[str, str] = {}
    skipped: Counter[str] = Counter()
    for path, payload in entries:
        if payload is None:
            skipped[path] += 1  # path holds the skip reason
            continue
        text = _decode_text(payload)
        if text is None:
            skipped["binary_or_undecodable"] += 1
            continue
        files[path] = text

    return Snapshot(files=files, root_prefix=_common_root(list(files)), skipped=skipped, format=fmt)


# -- format readers -------------------------------------------------------------


def _iter_zip(data: bytes, limits: ArchiveLimits) -> Iterator[tuple[str, bytes | None]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise ArchiveError("the uploaded .zip file is corrupt or truncated") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_members:
            raise PayloadTooLargeError(
                f"archive has {len(infos):,} entries; the limit is {limits.max_members:,}"
            )
        budget = _Budget(limits.max_total_bytes)
        for info in infos:
            if info.is_dir():
                continue
            raw_name = info.filename.replace("\\", "/")
            path = _safe_member_path(raw_name)
            # Unix mode bits live in the high 16 bits of external_attr.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:  # symlink
                yield "symlink", None
                continue
            reason = _skip_reason(path, info.file_size, limits)
            if reason:
                yield reason, None
                continue
            if (
                info.compress_size
                and info.file_size / max(info.compress_size, 1) > limits.max_compression_ratio
            ):
                raise ArchiveError(
                    f"suspicious compression ratio for '{path}'; refusing to decompress"
                )
            try:
                with archive.open(info) as handle:
                    payload = _read_capped(handle, limits.max_file_bytes)
            except (zipfile.BadZipFile, OSError, RuntimeError, ValueError, EOFError) as exc:
                raise ArchiveError(f"could not read '{path}' from the archive") from exc
            if payload is None:
                yield "too_large", None
                continue
            budget.spend(len(payload))
            yield path, payload


def _open_tar(data: bytes) -> tarfile.TarFile:
    try:
        # Stream mode ("r|*") decompresses sequentially and never seeks, so a
        # forged member table cannot make us scan the archive repeatedly.
        return tarfile.open(fileobj=io.BytesIO(data), mode="r|*")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ArchiveError(
            "the uploaded tar archive is corrupt or uses an unsupported compression"
        ) from exc


def _iter_tar(data: bytes, limits: ArchiveLimits) -> Iterator[tuple[str, bytes | None]]:
    budget = _Budget(limits.max_total_bytes)
    with _open_tar(data) as archive:
        yield from _tar_members(archive, limits, budget)


def _tar_members(
    archive: tarfile.TarFile, limits: ArchiveLimits, budget: _Budget
) -> Iterator[tuple[str, bytes | None]]:
    count = 0
    try:
        for member in archive:
            count += 1
            if count > limits.max_members:
                raise PayloadTooLargeError(f"archive has more than {limits.max_members:,} entries")
            if member.isdir():
                continue
            path = _safe_member_path(member.name)
            if not member.isfile():
                yield ("symlink" if (member.issym() or member.islnk()) else "special_file"), None
                continue
            reason = _skip_reason(path, member.size, limits)
            if reason:
                yield reason, None
                continue
            handle = archive.extractfile(member)
            if handle is None:
                yield "special_file", None
                continue
            payload = _read_capped(handle, limits.max_file_bytes)
            if payload is None:
                yield "too_large", None
                continue
            budget.spend(len(payload))
            yield path, payload
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ArchiveError("the uploaded tar archive is corrupt or truncated") from exc


# -- helpers --------------------------------------------------------------------


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.spent = 0

    def spend(self, amount: int) -> None:
        self.spent += amount
        if self.spent > self.limit:
            raise PayloadTooLargeError(
                f"archive expands to more than {self.limit // 1_000_000} MB of text; the snapshot is too large"
            )


def _read_capped(handle: IO[bytes], cap: int) -> bytes | None:
    payload = handle.read(cap + 1)
    if len(payload) > cap:
        return None
    return payload


def _looks_like_tar(data: bytes) -> bool:
    if data[:2] == b"\x1f\x8b" or data[:3] == b"BZh" or data[:6] == b"\xfd7zXZ\x00":
        return True
    return len(data) > 262 and data[257:262] == b"ustar"


def _safe_member_path(name: str) -> str:
    if "\x00" in name:
        raise ArchiveError("archive member name contains a NUL byte")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ArchiveError(f"archive contains an absolute path: '{name[:120]}'")
    parts = [p for p in PurePosixPath(name).parts if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ArchiveError(f"archive contains a path traversal entry: '{name[:120]}'")
    if not parts:
        raise ArchiveError("archive contains an empty member name")
    return "/".join(parts)


def _skip_reason(path: str, size: int, limits: ArchiveLimits) -> str | None:
    parts = path.split("/")
    if any(part in IGNORED_DIRECTORIES for part in parts[:-1]):
        return "ignored_directory"
    name = parts[-1]
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in TEXT_EXTENSIONS and name not in TEXT_FILENAMES:
        return "unsupported_extension"
    if size > limits.max_file_bytes:
        return "too_large"
    return None


def _decode_text(payload: bytes) -> str | None:
    if b"\x00" in payload[:8192]:
        return None
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n")


def _common_root(paths: list[str]) -> str | None:
    """Return a single top-level directory shared by every path, if any.

    GitHub "Download ZIP" archives wrap the repository in ``<repo>-<ref>/``.
    """
    if not paths:
        return None
    first_parts = {p.split("/", 1)[0] for p in paths}
    if len(first_parts) != 1:
        return None
    root = next(iter(first_parts))
    if all("/" in p for p in paths):
        return root
    return None
