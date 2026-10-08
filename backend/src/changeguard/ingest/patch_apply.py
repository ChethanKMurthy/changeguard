"""Pure-Python patch application.

Used to reconstruct the post-change ("head") revision from an uploaded base
snapshot. We never shell out to ``patch`` or ``git apply``: the input is
untrusted and the operation is simple enough to implement exactly.

Hunks must match the base content exactly (after line-ending normalisation).
A hunk may be found at an offset from its declared position, as GNU patch
does, which tolerates snapshots that differ slightly above the change.
"""

from __future__ import annotations

from changeguard.errors import PatchApplyError
from changeguard.ingest.diff_parser import FileDiff, FileStatus, Hunk

DEFAULT_MAX_OFFSET = 300


def split_lines(text: str) -> tuple[list[str], bool]:
    """Split text into lines; return (lines, ends_with_newline)."""
    if text == "":
        return [], True
    ends_with_newline = text.endswith("\n")
    body = text[:-1] if ends_with_newline else text
    return body.split("\n"), ends_with_newline


def join_lines(lines: list[str], ends_with_newline: bool) -> str:
    if not lines:
        return ""
    return "\n".join(lines) + ("\n" if ends_with_newline else "")


def apply_file_diff(
    base: str | None, diff: FileDiff, *, max_offset: int = DEFAULT_MAX_OFFSET
) -> str | None:
    """Apply ``diff`` to ``base`` and return the new content (``None`` if deleted)."""
    if diff.is_binary:
        raise PatchApplyError(f"cannot apply binary change to {diff.path}")
    if diff.status is FileStatus.DELETED:
        return None
    if diff.status is FileStatus.ADDED:
        base = ""
    if base is None:
        raise PatchApplyError(f"base content for {diff.old_path or diff.path} is not available")

    base_lines, base_trailing_newline = split_lines(base.replace("\r\n", "\n"))
    out: list[str] = []
    cursor = 0  # next unconsumed index into base_lines
    drift = 0  # accumulated offset between declared and actual hunk positions
    trailing_newline = base_trailing_newline
    touched_eof = False

    for hunk in diff.hunks:
        old_side = [ln.content for ln in hunk.lines if ln.kind != "add"]
        new_side = [ln.content for ln in hunk.lines if ln.kind != "del"]
        declared = (hunk.old_start - 1 if hunk.old_count > 0 else hunk.old_start) + drift
        position = _locate(base_lines, old_side, declared, cursor, max_offset)
        if position is None:
            raise PatchApplyError(
                f"hunk '{hunk.header}' does not match the snapshot content of {diff.old_path or diff.path}",
                detail={"file": diff.path, "hunk": hunk.header},
            )
        drift += position - declared
        out.extend(base_lines[cursor:position])
        out.extend(new_side)
        cursor = position + len(old_side)
        if cursor >= len(base_lines):
            touched_eof = True
            trailing_newline = _new_side_trailing_newline(hunk, default=trailing_newline)

    out.extend(base_lines[cursor:])
    if not touched_eof:
        trailing_newline = base_trailing_newline
    return join_lines(out, trailing_newline)


def _new_side_trailing_newline(hunk: Hunk, *, default: bool) -> bool:
    """Whether the new side of a hunk that reaches EOF ends with a newline."""
    new_side = [ln for ln in hunk.lines if ln.kind != "del"]
    if not new_side:
        return default
    return not new_side[-1].no_newline_at_eof


def _locate(
    base: list[str], expected: list[str], declared: int, cursor: int, max_offset: int
) -> int | None:
    """Find where ``expected`` occurs in ``base``, searching outward from ``declared``."""
    if not expected:
        # Pure insertion: trust the declared position, clamped to the file.
        return min(max(declared, cursor), len(base))
    n = len(expected)
    upper_bound = len(base) - n
    for delta in range(max_offset + 1):
        for candidate in (declared - delta, declared + delta) if delta else (declared,):
            if cursor <= candidate <= upper_bound and base[candidate : candidate + n] == expected:
                return candidate
    return None
