from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from changeguard.errors import ArchiveError, PatchApplyError, PayloadTooLargeError
from changeguard.evaluation.dataset import load_dataset
from changeguard.ingest.archive import ArchiveLimits, read_snapshot
from changeguard.ingest.diff_parser import parse_patch
from changeguard.ingest.patch_apply import apply_file_diff
from tests.conftest import REPO, zip_bytes

# -- patch application ----------------------------------------------------------------


def test_apply_with_offset() -> None:
    base = "header\nextra\na\nb\nc\n"
    patch = parse_patch("diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n")
    assert apply_file_diff(base, patch.files[0]) == "header\nextra\na\nB\nc\n"


def test_apply_respects_missing_trailing_newline() -> None:
    patch = parse_patch(
        "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n\\ No newline at end of file\n"
    )
    assert apply_file_diff("a\nb\n", patch.files[0]) == "a\nc"


def test_apply_mismatch_raises() -> None:
    patch = parse_patch("diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-expected\n+new\n")
    with pytest.raises(PatchApplyError):
        apply_file_diff("something else\n", patch.files[0])


def _cases() -> list:  # type: ignore[type-arg]
    return load_dataset(REPO / "eval" / "dataset")


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.id)
def test_every_dataset_patch_reproduces_head(case) -> None:  # type: ignore[no-untyped-def]
    """Property check over real git output: base + change.patch == head, for every file."""
    patch = parse_patch(case.patch_text())
    for fd in patch.files:
        base = case.read("base", fd.old_path) if fd.old_path else None
        result = apply_file_diff(base, fd)
        expected = case.read("head", fd.new_path) if fd.new_path else None
        assert result == expected, fd.path


# -- archives -------------------------------------------------------------------------


def test_zip_snapshot_and_root_prefix() -> None:
    data = zip_bytes(
        {"src/a.py": "x = 1\n", "README.md": "hi\n", "logo.png": "binary?"}, prefix="repo-main/"
    )
    snap = read_snapshot(data)
    assert snap.root_prefix == "repo-main"
    assert set(snap.files) == {"repo-main/src/a.py", "repo-main/README.md"}
    assert snap.skipped["unsupported_extension"] == 1
    snap.strip_root()
    assert set(snap.files) == {"src/a.py", "README.md"}


def test_tar_gz_snapshot_skips_symlinks_and_ignored_dirs() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, content in {"src/a.py": b"x = 1\n", "node_modules/lib/index.js": b"x\n"}.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        link = tarfile.TarInfo("src/link.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tf.addfile(link)
    snap = read_snapshot(buffer.getvalue())
    assert set(snap.files) == {"src/a.py"}
    assert snap.skipped["symlink"] == 1 and snap.skipped["ignored_directory"] == 1


@pytest.mark.parametrize("name", ["../evil.py", "/abs/evil.py", "a/../../evil.py"])
def test_zip_slip_rejected(name: str) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(name, "x = 1\n")
    with pytest.raises(ArchiveError):
        read_snapshot(buffer.getvalue())


def test_decompression_bomb_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", "0" * 900_000)
    with pytest.raises(ArchiveError, match="compression ratio"):
        read_snapshot(buffer.getvalue(), limits=ArchiveLimits(max_compression_ratio=50))


def test_total_size_limit() -> None:
    data = zip_bytes({f"f{i}.py": "x = 1\n" * 200 for i in range(10)})
    with pytest.raises(PayloadTooLargeError):
        read_snapshot(data, limits=ArchiveLimits(max_total_bytes=5_000))


def test_unknown_archive_format() -> None:
    with pytest.raises(ArchiveError, match="unsupported archive format"):
        read_snapshot(b"definitely not an archive", "x.rar")


def test_large_file_skipped(tmp_path: Path) -> None:
    data = zip_bytes({"big.py": "x = 1\n" * 1000, "small.py": "y = 2\n"})
    snap = read_snapshot(data, limits=ArchiveLimits(max_file_bytes=100))
    assert set(snap.files) == {"small.py"}
