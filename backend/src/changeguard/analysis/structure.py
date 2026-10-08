"""Structural diff: which symbols changed, and how their signatures changed."""

from __future__ import annotations

import difflib
import re
import textwrap
from dataclasses import dataclass, field
from typing import Literal

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.workspace import ChangedFile
from changeguard.ingest.diff_parser import FileStatus, Hunk
from changeguard.languages import index_file
from changeguard.languages.model import FileIndex, LanguageId, Param, Signature, Symbol

_VAR_KINDS = ("var_positional", "var_keyword")
_POSITIONAL_KINDS = ("positional_only", "positional_or_keyword")
RENAME_SIMILARITY = 0.78

ChangeKind = Literal["added", "removed", "modified", "renamed"]


@dataclass(slots=True)
class SignatureDiff:
    language: LanguageId
    before: Signature
    after: Signature
    removed: list[str] = field(default_factory=list)
    added_required: list[str] = field(default_factory=list)
    added_optional: list[str] = field(default_factory=list)
    default_changed: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    default_removed: list[str] = field(default_factory=list)
    kind_changes: list[tuple[str, str, str]] = field(default_factory=list)
    var_removed: list[str] = field(default_factory=list)
    reordered: bool = False
    positional_shift: bool = False
    became_async: bool = False
    became_sync: bool = False
    returns_changed: tuple[str | None, str | None] | None = None
    # JS/TS arity (max None = unbounded because of a rest parameter)
    required_before: int = 0
    required_after: int = 0
    max_before: int | None = None
    max_after: int | None = None

    @property
    def any_change(self) -> bool:
        return bool(self.describe())

    @property
    def breaking(self) -> bool:
        if self.language is LanguageId.PYTHON:
            narrowed = any(
                old == "positional_or_keyword" and new in ("keyword_only", "positional_only")
                for _, old, new in self.kind_changes
            )
            return bool(
                self.removed
                or self.var_removed
                or self.added_required
                or self.default_removed
                or self.reordered
                or self.positional_shift
                or narrowed
                or self.became_async
            )
        max_shrunk = self.max_after is not None and (
            self.max_before is None or self.max_after < self.max_before
        )
        return self.required_after > self.required_before or max_shrunk or self.became_async

    def describe(self) -> list[str]:
        out: list[str] = []
        if self.language is LanguageId.PYTHON:
            out += [f"parameter `{n}` removed" for n in self.removed]
            out += [f"`*{n}`/`**{n}` catch-all removed" for n in self.var_removed]
            out += [f"required parameter `{n}` added" for n in self.added_required]
            out += [f"optional parameter `{n}` added" for n in self.added_optional]
            out += [
                f"parameter `{n}` lost its default (now required)" for n in self.default_removed
            ]
            out += [
                f"parameter `{n}` changed from {o.replace('_', '-')} to {k.replace('_', '-')}"
                for n, o, k in self.kind_changes
            ]
            if self.reordered:
                out.append("positional parameters were reordered")
            if self.positional_shift:
                out.append("a new parameter was inserted before existing positional parameters")
        else:
            if self.required_after != self.required_before:
                out.append(
                    f"required arguments changed from {self.required_before} to {self.required_after}"
                )
            if self.max_after != self.max_before:
                out.append(
                    f"maximum arguments changed from {_bound(self.max_before)} to {_bound(self.max_after)}"
                )
        out += [f"default of `{n}` changed from `{o}` to `{k}`" for n, o, k in self.default_changed]
        if self.became_async:
            out.append("function became async (callers now receive a coroutine/promise)")
        if self.became_sync:
            out.append("function is no longer async")
        if self.returns_changed:
            before, after = self.returns_changed
            out.append(
                f"return annotation changed from `{before or 'none'}` to `{after or 'none'}`"
            )
        return out


@dataclass(slots=True)
class SymbolChange:
    file: str
    qualname: str
    name: str
    kind: str
    change: ChangeKind
    before: Symbol | None
    after: Symbol | None
    language: LanguageId
    renamed_from: str | None = None
    signature_diff: SignatureDiff | None = None
    head_lines: set[int] = field(default_factory=set)
    base_lines: set[int] = field(default_factory=set)
    approximate: bool = False
    # Filled in by later stages.
    call_sites: list[object] = field(default_factory=list)
    incompatible_calls: list[object] = field(default_factory=list)
    related_tests: list[object] = field(default_factory=list)

    @property
    def symbol(self) -> Symbol:
        sym = self.after or self.before
        assert sym is not None
        return sym

    @property
    def is_test(self) -> bool:
        return self.kind == "test"


def _bound(value: int | None) -> str:
    return "unbounded" if value is None else str(value)


def implicit_first_param(symbol: Symbol) -> bool:
    """Whether calls bind the first parameter implicitly (Python ``self``/``cls``).

    JavaScript/TypeScript methods have no explicit receiver parameter.
    """
    if symbol.kind != "method" or not symbol.file.endswith((".py", ".pyi")):
        return False
    return not any(d.split("(")[0].endswith("staticmethod") for d in symbol.decorators)


def diff_signatures(
    before: Signature, after: Signature, language: LanguageId, implicit_first: bool
) -> SignatureDiff:
    diff = SignatureDiff(language=language, before=before, after=after)
    bp = list(before.params[1:] if implicit_first and before.params else before.params)
    ap = list(after.params[1:] if implicit_first and after.params else after.params)
    diff.became_async = after.is_async and not before.is_async
    diff.became_sync = before.is_async and not after.is_async
    if before.returns and after.returns and before.returns != after.returns:
        diff.returns_changed = (before.returns, after.returns)

    if language is not LanguageId.PYTHON:
        diff.required_before, diff.max_before = _arity(bp)
        diff.required_after, diff.max_after = _arity(ap)
        for i, (b, a) in enumerate(zip(bp, ap, strict=False)):
            if b.has_default and a.has_default and b.default != a.default and b.default is not None:
                diff.default_changed.append(
                    (a.name if a.name == b.name else f"#{i + 1}", b.default, a.default)
                )
        return diff

    b_by = {p.name: p for p in bp}
    a_by = {p.name: p for p in ap}
    diff.removed = [p.name for p in bp if p.name not in a_by and p.kind not in _VAR_KINDS]
    diff.var_removed = [
        p.name for p in bp if p.kind in _VAR_KINDS and not any(q.kind == p.kind for q in ap)
    ]
    added = [p for p in ap if p.name not in b_by and p.kind not in _VAR_KINDS]
    diff.added_required = [p.name for p in added if not p.has_default]
    diff.added_optional = [p.name for p in added if p.has_default]
    for p in ap:
        prev = b_by.get(p.name)
        if prev is None or p.kind in _VAR_KINDS:
            continue
        if prev.has_default and p.has_default and (prev.default or "") != (p.default or ""):
            diff.default_changed.append((p.name, prev.default, p.default))
        if prev.has_default and not p.has_default:
            diff.default_removed.append(p.name)
        if prev.kind != p.kind and prev.kind not in _VAR_KINDS:
            diff.kind_changes.append((p.name, prev.kind, p.kind))
    common_before = [p.name for p in bp if p.kind in _POSITIONAL_KINDS and p.name in a_by]
    common_after = [p.name for p in ap if p.kind in _POSITIONAL_KINDS and p.name in b_by]
    diff.reordered = common_before != common_after and sorted(common_before) == sorted(common_after)
    after_positional = [p for p in ap if p.kind in _POSITIONAL_KINDS]
    seen_new = False
    for p in after_positional:
        if p.name not in b_by:
            seen_new = True
        elif seen_new:
            diff.positional_shift = True
            break
    return diff


def _arity(params: list[Param]) -> tuple[int, int | None]:
    required = 0
    for p in params:
        if p.kind in _VAR_KINDS:
            break
        if not p.has_default:
            required += 1
    unbounded = any(p.kind == "var_positional" for p in params)
    return required, None if unbounded else len([p for p in params if p.kind not in _VAR_KINDS])


# -- indexing changed files ---------------------------------------------------------


def index_changed_files(ctx: AnalysisContext) -> dict[str, int]:
    """Parse base/head revisions of each changed file with structural support."""
    indexed = partial = 0
    for cf in ctx.files:
        if cf.language is None or cf.diff.is_binary:
            continue
        if cf.full_context:
            if cf.base_text is not None:
                cf.base_index = index_file(cf.old_path or cf.path, cf.base_text)
            if cf.head_text is not None:
                cf.head_index = index_file(cf.path, cf.head_text)
            indexed += 1
        else:
            cf.base_index, cf.head_index = _fragment_indexes(cf)
            partial += 1
    return {"indexed_files": indexed, "fragment_indexed_files": partial}


def _fragment_indexes(cf: ChangedFile) -> tuple[FileIndex | None, FileIndex | None]:
    """Index the visible hunk fragments of a partially known file (diff-only mode)."""
    base = _merge_fragments(cf, side="base")
    head = _merge_fragments(cf, side="head")
    return base, head


def _merge_fragments(cf: ChangedFile, side: Literal["base", "head"]) -> FileIndex | None:
    merged: FileIndex | None = None
    for hunk in cf.diff.hunks:
        rows = [
            (ln.old_lineno if side == "base" else ln.new_lineno, ln.content)
            for ln in hunk.lines
            if ln.kind == "context" or (ln.kind == "del") == (side == "base")
        ]
        pairs: list[tuple[int, str]] = [(n, c) for n, c in rows if n is not None]
        if not pairs:
            continue
        fragment = textwrap.dedent("\n".join(c for _, c in pairs)) + "\n"
        idx = index_file(cf.path, fragment)
        if idx is None:
            return None
        numbers = [n for n, _ in pairs]

        def remap(local: int, numbers: list[int] = numbers) -> int:
            return numbers[min(max(local, 1), len(numbers)) - 1]

        for s in idx.symbols:
            s.start_line, s.end_line, s.signature_line = (
                remap(s.start_line),
                remap(s.end_line),
                remap(s.signature_line),
            )
        idx.parse_error_lines = []  # fragments are syntactically incomplete by construction
        if merged is None:
            merged = idx
        else:
            merged.symbols.extend(idx.symbols)
    return merged


# -- symbol diff ------------------------------------------------------------------


def compute_symbol_changes(ctx: AnalysisContext) -> list[SymbolChange]:
    changes: list[SymbolChange] = []
    for cf in ctx.files:
        if cf.language is None or (cf.base_index is None and cf.head_index is None):
            continue
        file_changes = _file_symbol_changes(cf)
        if not cf.full_context:
            for c in file_changes:
                c.approximate = True
            file_changes += _section_header_changes(cf, file_changes)
        changes.extend(file_changes)
    ctx.symbol_changes = changes
    return changes


def _innermost(index: FileIndex, line: int) -> Symbol | None:
    best: Symbol | None = None
    for s in index.symbols:
        if s.synthetic or not s.contains(line):
            continue
        if best is None or (s.end_line - s.start_line) < (best.end_line - best.start_line):
            best = s
    return best


def _file_symbol_changes(cf: ChangedFile) -> list[SymbolChange]:
    assert cf.language is not None
    base_syms = {s.qualname: s for s in cf.base_index.symbols} if cf.base_index else {}
    head_syms = {s.qualname: s for s in cf.head_index.symbols} if cf.head_index else {}

    touched_head: dict[str, set[int]] = {}
    touched_base: dict[str, set[int]] = {}
    if cf.head_index is not None:
        for ln in cf.added:
            sym = _innermost(cf.head_index, ln)
            if sym is not None:
                touched_head.setdefault(sym.qualname, set()).add(ln)
    if cf.base_index is not None:
        for ln in cf.deleted:
            sym = _innermost(cf.base_index, ln)
            if sym is not None:
                touched_base.setdefault(sym.qualname, set()).add(ln)

    changes: list[SymbolChange] = []
    for qual, hs in head_syms.items():
        bs = base_syms.get(qual)
        if bs is None:
            continue
        sig_diff = None
        if bs.signature is not None and hs.signature is not None:
            candidate = diff_signatures(
                bs.signature, hs.signature, cf.language, implicit_first_param(hs)
            )
            sig_diff = candidate if candidate.any_change else None
        head_hit = touched_head.get(qual, set())
        base_hit = touched_base.get(qual, set())
        if hs.synthetic and sig_diff is None:
            continue
        if head_hit or base_hit or sig_diff is not None:
            changes.append(
                SymbolChange(
                    file=cf.path,
                    qualname=qual,
                    name=hs.name,
                    kind=hs.kind,
                    change="modified",
                    before=bs,
                    after=hs,
                    language=cf.language,
                    signature_diff=sig_diff,
                    head_lines=head_hit,
                    base_lines=base_hit,
                )
            )

    removed = [s for q, s in base_syms.items() if q not in head_syms and not s.synthetic]
    added = [s for q, s in head_syms.items() if q not in base_syms and not s.synthetic]
    renamed_pairs: list[tuple[Symbol, Symbol]] = []
    for r in removed:
        best: tuple[float, Symbol] | None = None
        for a in added:
            if (
                a.kind != r.kind
                or a.parent != r.parent
                or any(a is pair[1] for pair in renamed_pairs)
            ):
                continue
            ratio = _similarity(r.normalized_body, a.normalized_body)
            if ratio >= RENAME_SIMILARITY and (best is None or ratio > best[0]):
                best = (ratio, a)
        if best is not None:
            renamed_pairs.append((r, best[1]))
    renamed_from = {id(a): r for r, a in renamed_pairs}
    renamed_targets = {id(r) for r, _ in renamed_pairs}

    for a in added:
        origin = renamed_from.get(id(a))
        sig_diff = None
        if origin is not None and origin.signature is not None and a.signature is not None:
            candidate = diff_signatures(
                origin.signature, a.signature, cf.language, implicit_first_param(a)
            )
            sig_diff = candidate if candidate.any_change else None
        changes.append(
            SymbolChange(
                file=cf.path,
                qualname=a.qualname,
                name=a.name,
                kind=a.kind,
                change="renamed" if origin is not None else "added",
                before=origin,
                after=a,
                language=cf.language,
                renamed_from=origin.qualname if origin is not None else None,
                signature_diff=sig_diff,
                head_lines=set(range(a.start_line, a.end_line + 1)) & cf.added
                if cf.added
                else set(),
            )
        )
    for r in removed:
        if id(r) in renamed_targets:
            continue
        changes.append(
            SymbolChange(
                file=cf.path,
                qualname=r.qualname,
                name=r.name,
                kind=r.kind,
                change="removed",
                before=r,
                after=None,
                language=cf.language,
                base_lines=set(range(r.start_line, r.end_line + 1)) & cf.deleted,
            )
        )
    if cf.status is FileStatus.DELETED:
        for c in changes:
            c.change = "removed"
    return sorted(changes, key=lambda c: (c.symbol.start_line, c.qualname))


_SECTION_PATTERNS = (
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*class\s+([A-Za-z_]\w*)"),
    re.compile(r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)"),
    re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\(|function|[A-Za-z_$][\w$]*\s*=>)"
    ),
    re.compile(
        r"^\s*(?:public|private|protected|static|async|\s)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"
    ),
)


def _section_header_changes(cf: ChangedFile, existing: list[SymbolChange]) -> list[SymbolChange]:
    """Attribute hunks to the enclosing symbol named in git's ``@@ ... @@ <section>`` header."""
    assert cf.language is not None
    known = {c.name for c in existing}
    out: list[SymbolChange] = []
    for hunk in cf.diff.hunks:
        name = _section_symbol(hunk)
        if not name or name in known:
            continue
        changed_head = {
            ln.new_lineno for ln in hunk.lines if ln.kind == "add" and ln.new_lineno is not None
        }
        changed_base = {
            ln.old_lineno for ln in hunk.lines if ln.kind == "del" and ln.old_lineno is not None
        }
        covered = {ln for c in existing for ln in c.head_lines} | {
            ln for c in existing for ln in c.base_lines
        }
        if not (changed_head | changed_base) - covered:
            continue
        line = min(changed_head or changed_base)
        placeholder = Symbol(
            name=name, qualname=name, kind="function", file=cf.path,
            start_line=line, end_line=max(changed_head or changed_base), signature_line=line,
        )  # fmt: skip
        out.append(
            SymbolChange(
                file=cf.path,
                qualname=name,
                name=name,
                kind="function",
                change="modified",
                before=None,
                after=placeholder,
                language=cf.language,
                head_lines=changed_head,
                base_lines=changed_base,
                approximate=True,
            )
        )
        known.add(name)
    return out


def _section_symbol(hunk: Hunk) -> str | None:
    for pattern in _SECTION_PATTERNS:
        m = pattern.search(hunk.section)
        if m:
            return m.group(1)
    return None


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if matcher.real_quick_ratio() < RENAME_SIMILARITY or matcher.quick_ratio() < RENAME_SIMILARITY:
        return 0.0
    return matcher.ratio()
