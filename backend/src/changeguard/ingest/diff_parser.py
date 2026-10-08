"""Parser for unified diffs and git patches.

Supported inputs
----------------
* ``git diff`` / ``git show`` output, including the extended headers git emits
  for renames, copies, mode changes, and binary files.
* ``git format-patch`` output. Mail headers and commit messages are skipped;
  the ``Subject:`` line is kept as a default analysis title.
* Plain ``diff -u`` / ``diff -ruN`` output, with or without timestamps.

The parser is deliberately strict about hunk structure: line counts in every
``@@`` header must match the hunk body, otherwise the patch is rejected with
the offending line number. Silent mis-parses would produce wrong line numbers
downstream, which is exactly what the product promises never to do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from changeguard.errors import PatchParseError, PayloadTooLargeError

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_NO_NEWLINE_MARKER = "\\"
_DEV_NULL = "/dev/null"
_PREFIX_PAIRS = {("a", "b"), ("i", "w"), ("c", "w"), ("c", "i"), ("o", "w"), ("i", "o")}
_EXTENDED_HEADER_PREFIXES = (
    "old mode ",
    "new mode ",
    "deleted file mode ",
    "new file mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "index ",
)
MAX_PATH_LENGTH = 1024


class FileStatus(StrEnum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    COPIED = "copied"


LineKind = Literal["context", "add", "del"]


@dataclass(slots=True)
class DiffLine:
    kind: LineKind
    content: str
    old_lineno: int | None
    new_lineno: int | None
    no_newline_at_eof: bool = False


@dataclass(slots=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def header(self) -> str:
        section = f" {self.section}" if self.section else ""
        return (
            f"@@ -{self.old_start},{self.old_count} +{self.new_start},{self.new_count} @@{section}"
        )

    @property
    def new_end(self) -> int:
        """Last line number on the new side covered by this hunk (inclusive)."""
        return self.new_start + max(self.new_count, 1) - 1

    @property
    def old_end(self) -> int:
        return self.old_start + max(self.old_count, 1) - 1


@dataclass(slots=True)
class FileDiff:
    old_path: str | None
    new_path: str | None
    status: FileStatus
    hunks: list[Hunk] = field(default_factory=list)
    is_binary: bool = False
    old_mode: str | None = None
    new_mode: str | None = None
    similarity: int | None = None

    @property
    def path(self) -> str:
        """The path that identifies the file after the change (or before, if deleted)."""
        path = self.new_path or self.old_path
        assert path is not None  # guaranteed by the parser
        return path

    @property
    def additions(self) -> int:
        return sum(1 for h in self.hunks for line in h.lines if line.kind == "add")

    @property
    def deletions(self) -> int:
        return sum(1 for h in self.hunks for line in h.lines if line.kind == "del")

    def added_lines(self) -> set[int]:
        """New-side line numbers that were added or modified."""
        return {
            line.new_lineno
            for h in self.hunks
            for line in h.lines
            if line.kind == "add" and line.new_lineno is not None
        }

    def deleted_lines(self) -> set[int]:
        """Old-side line numbers that were removed or modified."""
        return {
            line.old_lineno
            for h in self.hunks
            for line in h.lines
            if line.kind == "del" and line.old_lineno is not None
        }

    def line_text(self, line_no: int, side: Literal["new", "old"] = "new") -> str | None:
        """Return the content of a line visible in the hunks, if present."""
        for h in self.hunks:
            for line in h.lines:
                number = line.new_lineno if side == "new" else line.old_lineno
                if number == line_no and (
                    line.kind == "context" or (line.kind == "add") == (side == "new")
                ):
                    return line.content
        return None


@dataclass(slots=True)
class PatchSet:
    files: list[FileDiff]
    format: Literal["git", "unified", "format-patch"]
    subject: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(f.deletions for f in self.files)


@dataclass(frozen=True, slots=True)
class ParseLimits:
    max_files: int = 500
    max_lines: int = 200_000


def parse_patch(text: str, limits: ParseLimits | None = None) -> PatchSet:
    """Parse a patch into a :class:`PatchSet`.

    Raises :class:`PatchParseError` for malformed input and
    :class:`PayloadTooLargeError` when configured limits are exceeded.
    """
    limits = limits or ParseLimits()
    if "\x00" in text:
        raise PatchParseError("patch contains NUL bytes; binary content is not a valid diff")
    # Normalise line endings. CRLF patches are common when diffs are produced on
    # Windows; analysis is line-ending agnostic.
    had_crlf = "\r\n" in text
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > limits.max_lines:
        raise PayloadTooLargeError(
            f"patch has {len(lines):,} lines; the limit is {limits.max_lines:,}",
            detail={"lines": len(lines), "limit": limits.max_lines},
        )
    parser = _Parser(lines, limits)
    patch = parser.parse()
    if had_crlf:
        patch.warnings.append("Patch used CRLF line endings; they were normalised to LF.")
    return patch


class _Parser:
    def __init__(self, lines: list[str], limits: ParseLimits) -> None:
        self.lines = lines
        self.limits = limits
        self.i = 0
        self.files: list[FileDiff] = []
        self.subject: str | None = None
        self.saw_git_header = False
        self.saw_mbox_header = False

    # -- driver -----------------------------------------------------------------

    def parse(self) -> PatchSet:
        n = len(self.lines)
        while self.i < n:
            line = self.lines[self.i]
            if line.startswith("diff --git "):
                self.saw_git_header = True
                self._parse_git_file()
            elif (
                line.startswith("--- ")
                and self.i + 1 < n
                and self.lines[self.i + 1].startswith("+++ ")
            ):
                self._parse_plain_file()
            else:
                self._scan_preamble_line(line)
                self.i += 1
            if len(self.files) > self.limits.max_files:
                raise PayloadTooLargeError(
                    f"patch touches more than {self.limits.max_files} files",
                    detail={"limit": self.limits.max_files},
                )
        if not self.files:
            raise PatchParseError(
                "no file changes found; expected a unified diff (git diff, git format-patch, or diff -u)"
            )
        self._reject_duplicates()
        fmt: Literal["git", "unified", "format-patch"]
        if self.saw_mbox_header:
            fmt = "format-patch"
        elif self.saw_git_header:
            fmt = "git"
        else:
            fmt = "unified"
        files = self.files
        if fmt == "unified":
            files = _strip_plain_prefixes(files)
        for f in files:
            for p in (f.old_path, f.new_path):
                if p is not None:
                    _validate_path(p)
        return PatchSet(files=files, format=fmt, subject=self.subject)

    def _scan_preamble_line(self, line: str) -> None:
        if line.startswith("From ") and re.match(r"^From [0-9a-f]{7,40} ", line):
            self.saw_mbox_header = True
        elif line.startswith("Subject: ") and self.subject is None:
            subject = line[len("Subject: ") :].strip()
            subject = re.sub(r"^\[PATCH[^\]]*\]\s*", "", subject)
            self.subject = subject[:200] or None

    def _reject_duplicates(self) -> None:
        seen: set[str] = set()
        for f in self.files:
            if f.path in seen:
                raise PatchParseError(
                    f"patch modifies '{f.path}' more than once (a multi-commit series?); "
                    "provide a single combined diff such as `git diff base..head`"
                )
            seen.add(f.path)

    # -- git-style file sections ------------------------------------------------

    def _parse_git_file(self) -> None:
        header_line_no = self.i + 1
        header = self.lines[self.i]
        old_path, new_path, uses_prefix = _paths_from_git_header(header[len("diff --git ") :])
        self.i += 1
        meta: dict[str, str] = {}
        is_binary = False
        n = len(self.lines)
        while self.i < n:
            line = self.lines[self.i]
            if line.startswith(("diff --git ", "@@ ", "--- ")):
                break
            if line.startswith(_EXTENDED_HEADER_PREFIXES):
                key, _, value = line.partition(" ")
                if key in {
                    "old",
                    "new",
                    "deleted",
                    "similarity",
                    "dissimilarity",
                    "rename",
                    "copy",
                }:
                    key2, _, value2 = value.partition(" ")
                    if key in {"old", "new"} and key2 == "file":
                        # "new file mode 100644"
                        _, _, mode = value2.partition(" ")
                        meta[f"{key} file mode"] = mode
                    elif key == "deleted":
                        _, _, mode = value2.partition(" ")
                        meta["deleted file mode"] = mode
                    else:
                        meta[f"{key} {key2}"] = value2
                else:
                    meta[key] = value
                self.i += 1
                continue
            if line.startswith("Binary files ") and line.endswith(" differ"):
                is_binary = True
                self.i += 1
                continue
            if line == "GIT binary patch":
                is_binary = True
                self.i += 1
                # Skip base85 payload until the next file header or end of input.
                while self.i < n and not self.lines[self.i].startswith("diff --git "):
                    self.i += 1
                break
            # Any other line ends the header (e.g. a format-patch signature).
            break

        if "rename from" in meta:
            old_path = _unquote(meta["rename from"])
        if "rename to" in meta:
            new_path = _unquote(meta["rename to"])
        if "copy from" in meta:
            old_path = _unquote(meta["copy from"])
        if "copy to" in meta:
            new_path = _unquote(meta["copy to"])

        hunks: list[Hunk] = []
        if self.i < n and self.lines[self.i].startswith("--- "):
            if self.i + 1 >= n or not self.lines[self.i + 1].startswith("+++ "):
                raise PatchParseError(
                    "'---' header without matching '+++' header", line_number=self.i + 1
                )
            minus = _path_from_marker(self.lines[self.i][4:])
            plus = _path_from_marker(self.lines[self.i + 1][4:])
            old_path = None if minus == _DEV_NULL else _strip_prefix(minus, uses_prefix)
            new_path = None if plus == _DEV_NULL else _strip_prefix(plus, uses_prefix)
            self.i += 2
            hunks = self._parse_hunks()

        if "new file mode" in meta:
            old_path = None
        if "deleted file mode" in meta:
            new_path = None
        if old_path is None and new_path is None:
            raise PatchParseError(
                "file section has neither an old nor a new path", line_number=header_line_no
            )

        status = _infer_status(old_path, new_path, meta)
        similarity = None
        if "similarity index" in meta:
            similarity = _parse_percentage(meta["similarity index"])
        self.files.append(
            FileDiff(
                old_path=old_path,
                new_path=new_path,
                status=status,
                hunks=hunks,
                is_binary=is_binary,
                old_mode=meta.get("old mode") or meta.get("deleted file mode"),
                new_mode=meta.get("new mode") or meta.get("new file mode"),
                similarity=similarity,
            )
        )

    # -- plain unified diffs --------------------------------------------------

    def _parse_plain_file(self) -> None:
        minus = _path_from_marker(self.lines[self.i][4:])
        plus = _path_from_marker(self.lines[self.i + 1][4:])
        self.i += 2
        hunks = self._parse_hunks()
        old_path = None if minus == _DEV_NULL else minus
        new_path = None if plus == _DEV_NULL else plus
        if old_path is None and new_path is None:
            raise PatchParseError(
                "file section has neither an old nor a new path", line_number=self.i
            )
        status = _infer_status(old_path, new_path, {})
        if status is FileStatus.RENAMED:
            # Plain diffs label the two sides differently (old/x vs new/x); that
            # is not a rename. Prefix stripping happens after all files are read.
            status = FileStatus.MODIFIED
        self.files.append(
            FileDiff(old_path=old_path, new_path=new_path, status=status, hunks=hunks)
        )

    # -- hunks ----------------------------------------------------------------

    def _parse_hunks(self) -> list[Hunk]:
        hunks: list[Hunk] = []
        n = len(self.lines)
        while self.i < n and self.lines[self.i].startswith("@@"):
            hunks.append(self._parse_hunk())
        if hunks and self.i < n:
            stray = self.lines[self.i]
            looks_like_body = stray.startswith(("+", " ")) or (
                stray.startswith("-") and stray != "-- " and not stray.startswith("--- ")
            )
            if looks_like_body:
                raise PatchParseError(
                    "hunk body does not match the line counts in its header", line_number=self.i + 1
                )
        return hunks

    def _parse_hunk(self) -> Hunk:
        header_line_no = self.i + 1
        match = HUNK_HEADER_RE.match(self.lines[self.i])
        if match is None:
            raise PatchParseError("invalid hunk header", line_number=header_line_no)
        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) is not None else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        hunk = Hunk(old_start, old_count, new_start, new_count, match.group(5).strip())
        self.i += 1

        old_remaining, new_remaining = old_count, new_count
        old_no = old_start if old_count > 0 else old_start + 1
        new_no = new_start if new_count > 0 else new_start + 1
        n = len(self.lines)
        while old_remaining > 0 or new_remaining > 0:
            if self.i >= n:
                raise PatchParseError(
                    f"patch ended inside hunk (expected {old_remaining} more old and "
                    f"{new_remaining} more new lines)",
                    line_number=header_line_no,
                )
            raw = self.lines[self.i]
            if raw.startswith(_NO_NEWLINE_MARKER):
                if hunk.lines:
                    hunk.lines[-1].no_newline_at_eof = True
                self.i += 1
                continue
            # Some editors strip the single leading space of empty context lines.
            tag = raw[0] if raw else " "
            content = raw[1:]
            if tag == " ":
                hunk.lines.append(DiffLine("context", content, old_no, new_no))
                old_no += 1
                new_no += 1
                old_remaining -= 1
                new_remaining -= 1
            elif tag == "-":
                hunk.lines.append(DiffLine("del", content, old_no, None))
                old_no += 1
                old_remaining -= 1
            elif tag == "+":
                hunk.lines.append(DiffLine("add", content, None, new_no))
                new_no += 1
                new_remaining -= 1
            else:
                raise PatchParseError(
                    f"unexpected line inside hunk: {raw[:60]!r}", line_number=self.i + 1
                )
            if old_remaining < 0 or new_remaining < 0:
                raise PatchParseError(
                    "hunk body does not match the line counts in its header",
                    line_number=header_line_no,
                )
            self.i += 1
        # A trailing "\ No newline at end of file" belongs to the final line.
        if self.i < n and self.lines[self.i].startswith(_NO_NEWLINE_MARKER) and hunk.lines:
            hunk.lines[-1].no_newline_at_eof = True
            self.i += 1
        return hunk


# -- helpers --------------------------------------------------------------------


def _infer_status(old_path: str | None, new_path: str | None, meta: dict[str, str]) -> FileStatus:
    if old_path is None:
        return FileStatus.ADDED
    if new_path is None:
        return FileStatus.DELETED
    if "copy from" in meta:
        return FileStatus.COPIED
    if old_path != new_path:
        return FileStatus.RENAMED
    return FileStatus.MODIFIED


def _parse_percentage(value: str) -> int | None:
    value = value.strip().rstrip("%")
    return int(value) if value.isdigit() else None


def _path_from_marker(rest: str) -> str:
    """Extract the path from the remainder of a ``---``/``+++`` line."""
    if rest.startswith('"'):
        path, _ = _read_quoted(rest)
        return path
    # Timestamps (diff -u) and git's trailing tab for paths with spaces.
    path = rest.split("\t", 1)[0]
    return path.rstrip() if path.rstrip() == _DEV_NULL else path


def _strip_prefix(path: str, uses_prefix: bool) -> str:
    """Strip git's ``a/``/``b/`` (or mnemonic ``i/``/``w/``) prefix when the patch uses one."""
    if uses_prefix and len(path) > 2 and path[1] == "/":
        return path[2:]
    return path


def _has_prefix_pair(old: str, new: str) -> bool:
    return (
        len(old) > 2
        and len(new) > 2
        and old[1] == "/"
        and new[1] == "/"
        and (old[0], new[0]) in _PREFIX_PAIRS
    )


def _paths_from_git_header(rest: str) -> tuple[str | None, str | None, bool]:
    """Extract paths from ``diff --git <old> <new>`` and detect prefix usage.

    Returns ``(old, new, uses_prefix)``. The paths are only used when no
    ``---``/``+++`` or rename headers follow (binary files, mode-only changes);
    ``uses_prefix`` tells the caller whether ``---``/``+++`` paths carry
    ``a/``/``b/`` prefixes, which avoids guessing from directory names.
    """
    if rest.startswith('"'):
        old, remainder = _read_quoted(rest)
        remainder = remainder.lstrip(" ")
        new = _read_quoted(remainder)[0] if remainder.startswith('"') else remainder
        prefixed = _has_prefix_pair(old, new)
        return _strip_prefix(old, prefixed), _strip_prefix(new, prefixed), prefixed
    # Unquoted paths may contain spaces; git emits "a/<p> b/<p>" for
    # non-renames, so look for the split that yields two identical paths.
    for idx in (m.start() for m in re.finditer(" ", rest)):
        left, right = rest[:idx], rest[idx + 1 :]
        if _has_prefix_pair(left, right) and left[2:] == right[2:]:
            return left[2:], right[2:], True
        if left == right:  # --no-prefix
            return left, right, False
    parts = rest.split(" ")
    if len(parts) == 2:
        prefixed = _has_prefix_pair(parts[0], parts[1])
        return _strip_prefix(parts[0], prefixed), _strip_prefix(parts[1], prefixed), prefixed
    return rest, rest, False


_ESCAPES = {
    "n": "\n",
    "t": "\t",
    '"': '"',
    "\\": "\\",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "r": "\r",
    "v": "\v",
}


def _read_quoted(text: str) -> tuple[str, str]:
    """Read a C-style quoted string as emitted by git; return (value, remainder)."""
    assert text.startswith('"')
    out = bytearray()
    i = 1
    while i < len(text):
        ch = text[i]
        if ch == '"':
            return out.decode("utf-8", errors="replace"), text[i + 1 :]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in _ESCAPES:
                out.extend(_ESCAPES[nxt].encode())
                i += 2
                continue
            if nxt in "01234567":
                octal = text[i + 1 : i + 4]
                if len(octal) == 3 and all(c in "01234567" for c in octal):
                    out.append(int(octal, 8) & 0xFF)
                    i += 4
                    continue
        out.extend(ch.encode("utf-8"))
        i += 1
    raise PatchParseError("unterminated quoted path in patch header")


def _unquote(value: str) -> str:
    value = value.strip()
    if value.startswith('"'):
        return _read_quoted(value)[0]
    return value


def _strip_plain_prefixes(files: list[FileDiff]) -> list[FileDiff]:
    """Emulate ``patch -p1`` for ``diff -ruN old new`` output.

    If every file's two sides differ only in their first path component
    (e.g. ``old/src/x.py`` vs ``new/src/x.py``), strip that component.
    """

    def split_first(p: str | None) -> tuple[str, str] | None:
        if p is None or "/" not in p:
            return None
        head, _, tail = p.partition("/")
        if head in ("", ".", "..") or head.endswith(":"):
            return None  # absolute, relative-parent, or drive paths are never stripped (validation rejects them)
        return head, tail

    def tails_agree(f: FileDiff) -> bool:
        a, b = split_first(f.old_path), split_first(f.new_path)
        if f.old_path is None:
            return b is not None
        if f.new_path is None:
            return a is not None
        return a is not None and b is not None and a[1] == b[1]

    if not all(tails_agree(f) for f in files):
        return files
    for f in files:
        old = split_first(f.old_path)
        new = split_first(f.new_path)
        f.old_path = old[1] if old else None
        f.new_path = new[1] if new else None
    return files


def _validate_path(path: str) -> None:
    if not path or len(path) > MAX_PATH_LENGTH:
        raise PatchParseError("patch contains an empty or overly long file path")
    if any(ord(c) < 32 for c in path):
        raise PatchParseError("patch contains a file path with control characters")
    if "\\" in path:
        raise PatchParseError(f"unsupported path separator in '{path[:80]}'")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise PatchParseError(f"absolute paths are not allowed: '{path[:80]}'")
    if any(part == ".." for part in path.split("/")):
        raise PatchParseError(f"path traversal is not allowed: '{path[:80]}'")
