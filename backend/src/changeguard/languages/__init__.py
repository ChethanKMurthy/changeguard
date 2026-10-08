"""Language support: detection, parsing, and structural indexing."""

from __future__ import annotations

from changeguard.languages.javascript_lang import index_javascript
from changeguard.languages.model import FileIndex, LanguageId
from changeguard.languages.python_lang import index_python
from changeguard.languages.registry import (
    display_language,
    grammar_for_path,
    is_test_path,
    language_for_path,
)

__all__ = [
    "FileIndex",
    "LanguageId",
    "display_language",
    "grammar_for_path",
    "index_file",
    "is_test_path",
    "language_for_path",
]

STRUCTURAL_LANGUAGES = ("Python", "JavaScript", "TypeScript")


def index_file(path: str, source: str) -> FileIndex | None:
    """Index a file if its language has structural support; otherwise ``None``."""
    grammar = grammar_for_path(path)
    if grammar is None:
        return None
    if grammar == "python":
        return index_python(path, source)
    return index_javascript(path, source, grammar)
