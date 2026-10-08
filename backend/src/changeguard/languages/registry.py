"""Language detection and tree-sitter parser management."""

from __future__ import annotations

import threading
from pathlib import PurePosixPath
from typing import Literal

import tree_sitter_javascript as ts_javascript
import tree_sitter_python as ts_python
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Parser, Tree

from changeguard.languages.model import LanguageId

Grammar = Literal["python", "javascript", "typescript", "tsx"]

_GRAMMARS: dict[Grammar, Language] = {
    "python": Language(ts_python.language()),
    "javascript": Language(ts_javascript.language()),
    "typescript": Language(ts_typescript.language_typescript()),
    "tsx": Language(ts_typescript.language_tsx()),
}

_EXTENSION_GRAMMAR: dict[str, Grammar] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # The JavaScript grammar includes JSX.
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
}

_DISPLAY_NAMES: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".txt": "Text",
    ".env": "Env",
}

_local = threading.local()


def grammar_for_path(path: str) -> Grammar | None:
    return _EXTENSION_GRAMMAR.get(PurePosixPath(path).suffix.lower())


def language_for_path(path: str) -> LanguageId | None:
    """Languages with structural (AST-level) support."""
    grammar = grammar_for_path(path)
    if grammar is None:
        return None
    if grammar == "python":
        return LanguageId.PYTHON
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return LanguageId.TYPESCRIPT
    return LanguageId.JAVASCRIPT


def display_language(path: str) -> str:
    name = PurePosixPath(path).name
    if name == "Dockerfile":
        return "Dockerfile"
    if name.startswith(".env"):
        return "Env"
    return _DISPLAY_NAMES.get(PurePosixPath(path).suffix.lower(), "Other")


def parse(text: str, grammar: Grammar) -> Tree:
    """Parse text with a per-thread cached parser (parsers are not thread-safe)."""
    parsers: dict[Grammar, Parser] | None = getattr(_local, "parsers", None)
    if parsers is None:
        parsers = {}
        _local.parsers = parsers
    parser = parsers.get(grammar)
    if parser is None:
        parser = Parser(_GRAMMARS[grammar])
        parsers[grammar] = parser
    return parser.parse(text.encode("utf-8"))


TEST_DIR_NAMES = frozenset({"tests", "test", "__tests__", "spec", "specs"})


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py") or name == "conftest.py":
        return True
    lowered = name.lower()
    if any(marker in lowered for marker in (".test.", ".spec.")):
        return True
    return any(part in TEST_DIR_NAMES for part in p.parts[:-1])
