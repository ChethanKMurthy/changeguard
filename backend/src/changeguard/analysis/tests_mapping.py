"""Map changed symbols to the tests that exercise them.

A test is *related* to a changed symbol when the test body references the
symbol's name (or its class, for methods) and the test file imports the
symbol's module. Tests that only mention the name without a resolvable import
are kept as weaker "name match" evidence. Coverage through indirect calls
(e.g. an API test hitting a handler that calls the symbol) is not detected; the
rule's rationale states this limitation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from changeguard.analysis.codegen import regression_test, relative_test_hint
from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.references import RepositoryIndex
from changeguard.analysis.structure import SymbolChange
from changeguard.languages import is_test_path
from changeguard.languages.model import FileIndex, LanguageId, Symbol
from changeguard.report.models import Confidence, EvidenceType, Location, Severity, SuggestedTest

_SKIP_FILES = frozenset(
    {"setup.py", "conftest.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py"}
)
MAX_TEST_GAP_FINDINGS = 12


@dataclass(frozen=True, slots=True)
class TestRef:
    file: str
    test: str
    start_line: int
    end_line: int
    strength: Literal["import", "name", "indirect"]
    modified_in_change: bool
    via: str | None = None  # for indirect references: the tested same-file caller


def _skip(sc: SymbolChange) -> bool:
    name = PurePosixPath(sc.file).name
    lowered = sc.file.lower()
    if name in _SKIP_FILES or "/migrations/" in f"/{lowered}" or "alembic/" in lowered:
        return True
    if sc.kind not in ("function", "method", "class"):
        return True
    return sc.symbol.synthetic


def related_tests(
    repo: RepositoryIndex, sc: SymbolChange, changed_paths: set[str]
) -> list[TestRef]:
    return _direct_tests(repo, sc.symbol, sc.file, sc.language, changed_paths)


def _direct_tests(
    repo: RepositoryIndex, sym: Symbol, file: str, language: LanguageId, changed_paths: set[str]
) -> list[TestRef]:
    names = {sym.name}
    if sym.parent:
        names.add(sym.parent.rsplit(".", 1)[-1])
    family_python = language is LanguageId.PYTHON
    refs: list[TestRef] = []
    for path in repo.candidate_files(names):
        if not is_test_path(path) or path.endswith((".py", ".pyi")) != family_python:
            continue
        idx = repo.index(path)
        if idx is None:
            continue
        imports_module = _imports_target(repo, idx, file)
        for test in (s for s in idx.symbols if s.kind == "test"):
            lines = set(range(test.start_line, test.end_line + 1))
            hits = [n for n in names if any(ln in lines for ln in idx.identifiers.get(n, ()))]
            if not hits or (sym.parent and sym.name not in hits and not imports_module):
                continue
            refs.append(
                TestRef(
                    file=path,
                    test=test.qualname,
                    start_line=test.start_line,
                    end_line=test.end_line,
                    strength="import" if imports_module else "name",
                    modified_in_change=path in changed_paths,
                )
            )
    return refs


def _indirect_tests(
    repo: RepositoryIndex, sc: SymbolChange, changed_paths: set[str]
) -> list[TestRef]:
    """Tests of same-file callers of a non-public helper (one level of indirection)."""
    sym = sc.symbol
    idx = repo.index(sc.file)
    if idx is None:
        return []
    callers: dict[str, Symbol] = {}
    for call in idx.calls:
        local = call.receiver is None and call.callee == sym.name
        via_self = (
            sym.parent is not None
            and call.receiver in ("self", "cls", "this")
            and call.name == sym.name
        )
        if (local or via_self) and call.enclosing and call.enclosing != sc.qualname:
            caller = idx.symbol(call.enclosing)
            if caller is not None and caller.kind in ("function", "method"):
                callers[caller.qualname] = caller
    refs: list[TestRef] = []
    for caller in callers.values():
        for t in _direct_tests(repo, caller, sc.file, sc.language, changed_paths):
            refs.append(
                TestRef(
                    t.file,
                    t.test,
                    t.start_line,
                    t.end_line,
                    "indirect",
                    t.modified_in_change,
                    via=caller.qualname,
                )
            )
    return refs


def _imports_target(repo: RepositoryIndex, idx: FileIndex, target: str) -> bool:
    for b in idx.imports:
        resolved = repo.resolve(b)
        if resolved is not None and resolved.target == target:
            return True
    return False


def analyze_tests(ctx: AnalysisContext, repo: RepositoryIndex | None) -> dict[str, int]:
    stats = {"testable_symbols": 0, "with_tests": 0, "test_gaps": 0}
    if repo is None:
        return stats
    changed_paths = {cf.path for cf in ctx.files}
    gaps = 0
    for sc in ctx.symbol_changes:
        if (
            sc.change not in ("modified", "added", "renamed")
            or sc.is_test
            or sc.approximate
            or _skip(sc)
        ):
            continue
        cf = ctx.workspace.file(sc.file)
        if cf is None or cf.is_test:
            continue
        if sc.change == "modified" and not sc.head_lines and sc.signature_diff is None:
            continue  # only deletions inside the symbol; nothing new to test
        if (
            sc.change == "renamed"
            and sc.signature_diff is None
            and sc.before is not None
            and sc.after is not None
            and sc.before.normalized_body == sc.after.normalized_body
        ):
            continue  # pure rename: no behaviour to test
        stats["testable_symbols"] += 1
        tests = related_tests(repo, sc, changed_paths)
        if not tests and not _exported(sc):
            tests = _indirect_tests(repo, sc, changed_paths)
        sc.related_tests = list(tests)
        if tests:
            stats["with_tests"] += 1
            continue
        if gaps >= MAX_TEST_GAP_FINDINGS:
            continue
        gaps += 1
        _report_gap(ctx, sc)
    stats["test_gaps"] = gaps
    return stats


def _exported(sc: SymbolChange) -> bool:
    sym = sc.symbol
    if sc.language is LanguageId.PYTHON:
        return not sym.name.startswith("_") or (
            sym.name.startswith("__") and sym.name.endswith("__")
        )
    return sym.exported or sym.parent is not None


def _report_gap(ctx: AnalysisContext, sc: SymbolChange) -> None:
    sym = sc.symbol
    lines = sorted(sc.head_lines) or [sym.start_line]
    ev = ctx.code_evidence(
        sc.file, sym.start_line, min(sym.end_line, sym.start_line + 20),
        title=f"{sc.change.capitalize()} {sym.kind} {sc.qualname}", type=EvidenceType.CODE,
        data={"change": sc.change, "test_search": "no test file imports this module and references the symbol"},
        context=0, highlight=lines,
    )  # fmt: skip
    public = _exported(sc)
    hint = relative_test_hint(sc.file, sc.language)
    ctx.add_finding(
        "CG-TST-001",
        title=f"No tests reference {'new' if sc.change == 'added' else 'changed'} `{sc.qualname}`",
        description=f"No test in the repository imports `{sc.file}` and references `{sym.name}`"
        + (f" (or its class `{sym.parent}`)" if sym.parent else "")
        + f". {len(sc.head_lines)} changed line(s) in this {sym.kind} are not verified by a directly related test.",
        location=Location(
            file=sc.file, start_line=sym.start_line, end_line=sym.end_line, symbol=sc.qualname
        ),
        evidence_ids=[ev],
        failure_scenario=f"A regression in `{sym.name}` ships unnoticed because CI has no test that targets it.",
        suggested_test=SuggestedTest(
            description=f"Add focused tests for `{sym.name}` (e.g. in {hint}) covering the changed lines.",
            kind="unit",
            code=regression_test(
                sym,
                sc.file,
                sc.language,
                purpose="behaviour",
                body_comment="cover the changed lines; add one case per branch you touched",
            ),
            language=sc.language.value,
        ),
        severity=Severity.MEDIUM if public else Severity.LOW,
        confidence=Confidence.MEDIUM,
        related_symbols=[sc.qualname],
    )
