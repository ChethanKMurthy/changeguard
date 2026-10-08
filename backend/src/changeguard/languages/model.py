"""Language-neutral structural model produced by the tree-sitter indexers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class LanguageId(StrEnum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"


ParamKind = Literal[
    "positional_only",
    "positional_or_keyword",
    "var_positional",
    "keyword_only",
    "var_keyword",
]


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    kind: ParamKind
    has_default: bool = False
    default: str | None = None
    annotation: str | None = None

    def render(self) -> str:
        prefix = {"var_positional": "*", "var_keyword": "**"}.get(self.kind, "")
        text = f"{prefix}{self.name}"
        if self.annotation:
            text += f": {self.annotation}"
        if self.has_default:
            text += f" = {self.default}" if self.default is not None else "?"
        return text


@dataclass(frozen=True, slots=True)
class Signature:
    params: tuple[Param, ...]
    returns: str | None = None
    is_async: bool = False

    def render(self, name: str = "") -> str:
        parts: list[str] = []
        seen_kw_marker = False
        positional_only = [p for p in self.params if p.kind == "positional_only"]
        for p in self.params:
            if (
                p.kind == "keyword_only"
                and not seen_kw_marker
                and not any(q.kind == "var_positional" for q in self.params)
            ):
                parts.append("*")
                seen_kw_marker = True
            parts.append(p.render())
            if positional_only and p is positional_only[-1]:
                parts.append("/")
        text = f"{'async ' if self.is_async else ''}{name}({', '.join(parts)})"
        if self.returns:
            text += f" -> {self.returns}"
        return text

    def param(self, name: str) -> Param | None:
        for p in self.params:
            if p.name == name:
                return p
        return None


SymbolKind = Literal["function", "method", "class", "variable", "type", "test"]


@dataclass(slots=True)
class Symbol:
    name: str
    qualname: str
    kind: SymbolKind
    file: str
    start_line: int
    end_line: int
    signature_line: int
    signature: Signature | None = None
    parent: str | None = None
    exported: bool = False
    decorators: tuple[str, ...] = ()
    complexity: int = 1
    normalized_body: str = ""
    try_blocks: int = 0
    assertions: int = 0
    synthetic: bool = False

    @property
    def is_public(self) -> bool:
        """Heuristic visibility: Python underscore convention, JS export status."""
        if self.name.startswith("__") and self.name.endswith("__"):
            return True
        return not self.name.startswith("_")

    def contains(self, line: int) -> bool:
        return self.start_line <= line <= self.end_line


ImportKind = Literal["module", "name", "wildcard", "default", "namespace"]


@dataclass(frozen=True, slots=True)
class ImportBinding:
    file: str
    line: int
    module: str  # dotted module (Python) or specifier (JS/TS)
    imported_name: str | None
    local_name: str
    kind: ImportKind
    level: int = 0  # Python relative-import depth


@dataclass(frozen=True, slots=True)
class CallSite:
    file: str
    line: int
    end_line: int
    callee: str  # dotted text such as "pricing.format_price" or "self.save"
    name: str  # final segment, e.g. "format_price"
    receiver: str | None
    positional: int
    keywords: tuple[str, ...]
    star_args: bool
    star_kwargs: bool
    awaited: bool
    enclosing: str | None
    text: str
    is_new: bool = False  # JS `new X(...)`


@dataclass(slots=True)
class FileIndex:
    path: str
    language: LanguageId
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportBinding] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    identifiers: dict[str, list[int]] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)  # exported name -> local name
    parse_error_lines: list[int] = field(default_factory=list)
    is_test: bool = False

    def symbol(self, qualname: str) -> Symbol | None:
        for s in self.symbols:
            if s.qualname == qualname:
                return s
        return None

    def innermost_symbol(
        self, line: int, kinds: tuple[str, ...] = ("function", "method", "test")
    ) -> Symbol | None:
        best: Symbol | None = None
        for s in self.symbols:
            if (
                s.kind in kinds
                and s.contains(line)
                and (
                    best is None or (s.end_line - s.start_line) < (best.end_line - best.start_line)
                )
            ):
                best = s
        return best
