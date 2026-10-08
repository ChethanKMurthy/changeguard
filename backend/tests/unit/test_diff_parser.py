from __future__ import annotations

import pytest

from changeguard.errors import PatchParseError, PayloadTooLargeError
from changeguard.ingest.diff_parser import FileStatus, ParseLimits, parse_patch

GIT_MODIFY = """\
diff --git a/src/app.py b/src/app.py
index 3b18e51..b1a4f8c 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@ def main():
 import os
-print("old")
+print("new")
+print("extra")
 x = 1
 y = 2
"""


def test_git_modification_line_numbers() -> None:
    patch = parse_patch(GIT_MODIFY)
    assert patch.format == "git"
    (f,) = patch.files
    assert f.status is FileStatus.MODIFIED
    assert f.path == "src/app.py"
    assert f.additions == 2 and f.deletions == 1
    assert f.added_lines() == {2, 3}
    assert f.deleted_lines() == {2}
    hunk = f.hunks[0]
    assert hunk.section == "def main():"
    assert [(ln.kind, ln.old_lineno, ln.new_lineno) for ln in hunk.lines] == [
        ("context", 1, 1),
        ("del", 2, None),
        ("add", None, 2),
        ("add", None, 3),
        ("context", 3, 4),
        ("context", 4, 5),
    ]


def test_new_deleted_and_renamed_files() -> None:
    text = """\
diff --git a/new.py b/new.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+a = 1
+b = 2
diff --git a/gone.py b/gone.py
deleted file mode 100644
index e69de29..0000000
--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-x = 1
diff --git a/old/name.py b/new/name.py
similarity index 100%
rename from old/name.py
rename to new/name.py
"""
    added, deleted, renamed = parse_patch(text).files
    assert (
        added.status is FileStatus.ADDED
        and added.old_path is None
        and added.added_lines() == {1, 2}
    )
    assert (
        deleted.status is FileStatus.DELETED
        and deleted.new_path is None
        and deleted.path == "gone.py"
    )
    assert renamed.status is FileStatus.RENAMED
    assert (renamed.old_path, renamed.new_path, renamed.similarity) == (
        "old/name.py",
        "new/name.py",
        100,
    )
    assert renamed.hunks == []


def test_binary_and_mode_only_changes() -> None:
    text = """\
diff --git a/img/logo.png b/img/logo.png
index 1111111..2222222 100644
Binary files a/img/logo.png and b/img/logo.png differ
diff --git a/run.sh b/run.sh
old mode 100644
new mode 100755
"""
    binary, mode = parse_patch(text).files
    assert binary.is_binary and binary.path == "img/logo.png"
    assert mode.old_mode == "100644" and mode.new_mode == "100755" and not mode.hunks


def test_no_newline_markers() -> None:
    text = """\
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-old
\\ No newline at end of file
+new
\\ No newline at end of file
"""
    hunk = parse_patch(text).files[0].hunks[0]
    assert all(line.no_newline_at_eof for line in hunk.lines)


def test_format_patch_subject_is_kept() -> None:
    text = """\
From 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b Mon Sep 17 00:00:00 2001
From: Dev <dev@example.invalid>
Subject: [PATCH] Tighten discount threshold

---
 src/a.py | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1 +1 @@
-x = 1
+x = 2
--\x20
2.43.0
"""
    patch = parse_patch(text)
    assert patch.format == "format-patch"
    assert patch.subject == "Tighten discount threshold"
    assert patch.files[0].added_lines() == {1}


def test_plain_unified_diff_with_timestamps_strips_first_component() -> None:
    text = """\
--- old/src/util.py\t2026-01-01 10:00:00.000000000 +0000
+++ new/src/util.py\t2026-01-02 10:00:00.000000000 +0000
@@ -1,2 +1,2 @@
-a = 1
+a = 2
 b = 3
"""
    patch = parse_patch(text)
    assert patch.format == "unified"
    assert patch.files[0].path == "src/util.py"
    assert patch.files[0].status is FileStatus.MODIFIED


def test_quoted_paths_with_unicode_and_spaces() -> None:
    text = (
        'diff --git "a/docs/caf\\303\\251 notes.md" "b/docs/caf\\303\\251 notes.md"\n'
        "index 1..2 100644\n"
        '--- "a/docs/caf\\303\\251 notes.md"\n'
        '+++ "b/docs/caf\\303\\251 notes.md"\n'
        "@@ -1 +1 @@\n-a\n+b\n"
    )
    assert parse_patch(text).files[0].path == "docs/café notes.md"


def test_crlf_patch_is_normalised_with_warning() -> None:
    patch = parse_patch(GIT_MODIFY.replace("\n", "\r\n"))
    assert patch.files[0].added_lines() == {2, 3}
    assert any("CRLF" in w for w in patch.warnings)


def test_empty_context_line_without_leading_space() -> None:
    text = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,3 +1,3 @@\n x = 1\n\n-y = 2\n+y = 3\n"
    hunk = parse_patch(text).files[0].hunks[0]
    assert [ln.kind for ln in hunk.lines] == ["context", "context", "del", "add"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("hello world\n", "no file changes"),
        (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n x\n",
            "ended inside hunk",
        ),
        (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n x\n+y\n",
            "unexpected line|does not match",
        ),
        ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n?x\n", "unexpected line"),
        ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ bogus @@\n", "invalid hunk header"),
    ],
)
def test_malformed_patches_are_rejected(text: str, message: str) -> None:
    with pytest.raises(PatchParseError, match=message):
        parse_patch(text)


@pytest.mark.parametrize(
    "path", ["../etc/passwd", "/etc/passwd", "a/../../b.py", "C:/windows/x.py"]
)
def test_unsafe_paths_are_rejected(path: str) -> None:
    text = f"--- {path}\n+++ {path}\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(PatchParseError):
        parse_patch(text)


def test_nul_bytes_rejected() -> None:
    with pytest.raises(PatchParseError, match="NUL"):
        parse_patch("diff --git a/a b/a\x00\n")


def test_duplicate_file_sections_rejected() -> None:
    section = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(PatchParseError, match="more than once"):
        parse_patch(section + section)


def test_limits_enforced() -> None:
    section = "diff --git a/{0}.py b/{0}.py\n--- a/{0}.py\n+++ b/{0}.py\n@@ -1 +1 @@\n-a\n+b\n"
    text = "".join(section.format(i) for i in range(5))
    with pytest.raises(PayloadTooLargeError):
        parse_patch(text, ParseLimits(max_files=3))
    with pytest.raises(PayloadTooLargeError):
        parse_patch(text, ParseLimits(max_lines=10))
