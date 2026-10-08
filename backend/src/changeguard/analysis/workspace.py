"""Reconstruction of the base and head revisions of every changed file.

Two modes:

* **full context** — a repository snapshot of the base revision was uploaded.
  The patch is applied to it in memory, yielding complete base and head
  repositories. Cross-file analysis (call sites, tests, imports) is possible.
* **diff only** — just the patch. Added and deleted files are fully known;
  modified files are only known through their hunks. Analyses that need
  complete files are skipped or downgraded, and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from changeguard.errors import PatchApplyError
from changeguard.ingest.archive import Snapshot
from changeguard.ingest.diff_parser import FileDiff, FileStatus, PatchSet
from changeguard.ingest.patch_apply import apply_file_diff
from changeguard.languages import display_language, is_test_path, language_for_path
from changeguard.languages.model import FileIndex, LanguageId


@dataclass(slots=True)
class ChangedFile:
    diff: FileDiff
    path: str
    old_path: str | None
    display_language: str
    language: LanguageId | None
    base_text: str | None
    head_text: str | None
    full_context: bool
    is_test: bool
    added: set[int]
    deleted: set[int]
    base_index: FileIndex | None = None
    head_index: FileIndex | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> FileStatus:
        return self.diff.status

    def head_lines(self) -> list[str] | None:
        return self.head_text.split("\n") if self.head_text is not None else None

    def base_lines(self) -> list[str] | None:
        return self.base_text.split("\n") if self.base_text is not None else None


@dataclass(slots=True)
class Workspace:
    mode: str  # "full_context" | "diff_only"
    files: list[ChangedFile]
    base_repo: dict[str, str]
    head_repo: dict[str, str]
    warnings: list[str] = field(default_factory=list)

    def file(self, path: str) -> ChangedFile | None:
        for f in self.files:
            if f.path == path:
                return f
        return None


def build_workspace(patch: PatchSet, snapshot: Snapshot | None) -> Workspace:
    warnings: list[str] = []
    if snapshot is None:
        return Workspace("diff_only", [_diff_only_file(fd) for fd in patch.files], {}, {}, warnings)

    _align_snapshot_root(patch, snapshot, warnings)
    base_repo = snapshot.files
    head_repo = dict(base_repo)
    changed: list[ChangedFile] = []
    missing = 0
    for fd in patch.files:
        base_text = base_repo.get(fd.old_path) if fd.old_path else None
        cf = _new_changed_file(fd, base_text=base_text, head_text=None, full=False)
        if fd.is_binary:
            cf.notes.append("binary change; content not analysed")
            changed.append(cf)
            continue
        if fd.status is not FileStatus.ADDED and base_text is None:
            missing += 1
            fallback = _diff_only_file(fd)
            fallback.notes.append("file not present in snapshot; analysed from diff hunks only")
            changed.append(fallback)
            continue
        try:
            head_text = apply_file_diff(base_text, fd)
        except PatchApplyError as exc:
            warnings.append(f"{exc.message}; analysed {fd.path} from its diff hunks only.")
            fallback = _diff_only_file(fd)
            fallback.notes.append("patch did not apply to snapshot; analysed from diff hunks only")
            changed.append(fallback)
            continue
        cf.head_text = head_text
        cf.full_context = True
        changed.append(cf)
        if fd.old_path and fd.status in (FileStatus.RENAMED, FileStatus.DELETED):
            head_repo.pop(fd.old_path, None)
        if head_text is not None:
            head_repo[fd.path] = head_text
    if missing:
        warnings.append(
            f"{missing} changed file(s) were not found in the repository snapshot. Is the snapshot from the "
            "patch's base revision?"
        )
    return Workspace("full_context", changed, base_repo, head_repo, warnings)


def _align_snapshot_root(patch: PatchSet, snapshot: Snapshot, warnings: list[str]) -> None:
    """Strip a wrapping directory (e.g. ``repo-main/``) when that makes patch paths match."""
    old_paths = [f.old_path for f in patch.files if f.old_path and f.status is not FileStatus.ADDED]
    if not old_paths or not snapshot.root_prefix:
        return
    direct = sum(1 for p in old_paths if p in snapshot.files)
    prefix = snapshot.root_prefix + "/"
    stripped = sum(1 for p in old_paths if prefix + p in snapshot.files)
    if stripped > direct:
        snapshot.strip_root()
        warnings.append(
            f"Repository snapshot was wrapped in '{snapshot.root_prefix}/'; the prefix was removed."
        )


def _new_changed_file(
    fd: FileDiff, *, base_text: str | None, head_text: str | None, full: bool
) -> ChangedFile:
    path = fd.path
    return ChangedFile(
        diff=fd,
        path=path,
        old_path=fd.old_path,
        display_language=display_language(path),
        language=language_for_path(path),
        base_text=base_text,
        head_text=head_text,
        full_context=full,
        is_test=is_test_path(path),
        added=fd.added_lines(),
        deleted=fd.deleted_lines(),
    )


def _diff_only_file(fd: FileDiff) -> ChangedFile:
    """Build a file view from the hunks alone."""
    if fd.is_binary:
        return _new_changed_file(fd, base_text=None, head_text=None, full=False)
    if fd.status is FileStatus.ADDED:
        # Every line is in the diff, so the head content is fully known.
        try:
            head = apply_file_diff("", fd)
        except PatchApplyError:
            head = None
        return _new_changed_file(fd, base_text=None, head_text=head, full=head is not None)
    if fd.status is FileStatus.DELETED and fd.hunks:
        base_lines = [ln.content for h in fd.hunks for ln in h.lines if ln.kind != "add"]
        trailing = not any(
            ln.no_newline_at_eof for h in fd.hunks for ln in h.lines if ln.kind != "add"
        )
        base = "\n".join(base_lines) + ("\n" if trailing and base_lines else "")
        return _new_changed_file(fd, base_text=base, head_text=None, full=True)
    return _new_changed_file(fd, base_text=None, head_text=None, full=False)
