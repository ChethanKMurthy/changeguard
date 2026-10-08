"""Metric-based rules over symbol changes: complexity, error handling, test integrity."""

from __future__ import annotations

from collections import defaultdict

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.structure import SymbolChange
from changeguard.ingest.diff_parser import FileStatus
from changeguard.report.models import Confidence, EvidenceType, Location, Severity, SuggestedTest

COMPLEXITY_THRESHOLD = 10
COMPLEXITY_DELTA = 4
NEW_FUNCTION_THRESHOLD = 15


def analyze_metrics(ctx: AnalysisContext) -> dict[str, int]:
    stats = {"complexity": 0, "error_handling": 0, "assertions": 0, "deleted_tests": 0}
    removed_tests: dict[str, list[SymbolChange]] = defaultdict(list)
    for sc in ctx.symbol_changes:
        if sc.approximate:
            continue
        if sc.kind == "test":
            if sc.change == "removed":
                removed_tests[sc.file].append(sc)
            elif (
                sc.change == "modified"
                and sc.before
                and sc.after
                and sc.after.assertions < sc.before.assertions
            ):
                _assertions_removed(ctx, sc)
                stats["assertions"] += 1
            continue
        if sc.kind not in ("function", "method"):
            continue
        if _complexity(ctx, sc):
            stats["complexity"] += 1
        if (
            sc.change == "modified"
            and sc.before
            and sc.after
            and sc.after.try_blocks < sc.before.try_blocks
        ):
            _error_handling_removed(ctx, sc)
            stats["error_handling"] += 1
    for path, tests in removed_tests.items():
        _tests_removed(ctx, path, tests)
        stats["deleted_tests"] += len(tests)
    return stats


def _complexity(ctx: AnalysisContext, sc: SymbolChange) -> bool:
    after = sc.after
    if after is None:
        return False
    before_cc = sc.before.complexity if sc.before is not None and sc.change != "added" else None
    if before_cc is not None:
        if (
            after.complexity < COMPLEXITY_THRESHOLD
            or after.complexity - before_cc < COMPLEXITY_DELTA
        ):
            return False
    elif after.complexity < NEW_FUNCTION_THRESHOLD:
        return False
    ev = ctx.evidence.add(
        EvidenceType.METRIC,
        f"Cyclomatic complexity of {sc.qualname}",
        source="tree-sitter metric",
        file=sc.file,
        start_line=after.start_line,
        end_line=after.end_line,
        side="head",
        data={"before": before_cc, "after": after.complexity, "metric": "cyclomatic_complexity"},
    )
    change = (
        f"from {before_cc} to {after.complexity}"
        if before_cc is not None
        else f"{after.complexity} (new function)"
    )
    ctx.add_finding(
        "CG-CPX-001",
        title=f"Complexity of `{after.name}` is now {after.complexity}",
        description=f"Cyclomatic complexity of `{sc.qualname}` changed {change}.",
        location=Location(
            file=sc.file, start_line=after.start_line, end_line=after.end_line, symbol=sc.qualname
        ),
        evidence_ids=[ev],
        failure_scenario=f"`{after.name}` now has at least {after.complexity} independent paths; untested branches "
        "hide edge-case failures.",
        suggested_test=SuggestedTest(
            description=f"Add tests until each branch of `{after.name}` is exercised (branch coverage), or split the "
            "function into smaller units.",
            kind="unit",
        ),
        confidence=Confidence.HIGH,
        related_symbols=[sc.qualname],
    )
    return True


def _error_handling_removed(ctx: AnalysisContext, sc: SymbolChange) -> None:
    assert sc.before is not None and sc.after is not None
    removed_try_lines = sorted(
        n for n in sc.base_lines
        if (text := _base_line(ctx, sc.file, n)) is not None and text.strip().startswith(("try", "except", "catch", "} catch"))
    )  # fmt: skip
    focus = removed_try_lines[0] if removed_try_lines else sc.before.start_line
    ev = ctx.code_evidence(
        sc.before.file, focus, removed_try_lines[-1] if removed_try_lines else focus, side="base",
        title=f"Removed error handling in {sc.qualname}", type=EvidenceType.DIFF_HUNK, source="diff",
        data={"try_blocks_before": sc.before.try_blocks, "try_blocks_after": sc.after.try_blocks}, context=3,
        highlight=removed_try_lines or None,
    )  # fmt: skip
    ctx.add_finding(
        "CG-ERR-002",
        title=f"Error handling removed from `{sc.after.name}`",
        description=f"`{sc.qualname}` had {sc.before.try_blocks} try block(s) and now has {sc.after.try_blocks}.",
        location=Location(
            file=sc.file,
            start_line=sc.after.start_line,
            end_line=sc.after.end_line,
            symbol=sc.qualname,
        ),
        evidence_ids=[ev],
        failure_scenario=f"An exception that `{sc.after.name}` used to handle now propagates to its callers, which "
        "may crash a request or background job.",
        suggested_test=SuggestedTest(
            description=f"Add a test where the dependency inside `{sc.after.name}` raises, and assert the intended "
            "behaviour (handled, logged, or deliberately propagated).",
            kind="unit",
        ),
        confidence=Confidence.MEDIUM,
        related_symbols=[sc.qualname],
    )


def _base_line(ctx: AnalysisContext, path: str, number: int) -> str | None:
    text = ctx.source(path, "base")
    if text is None:
        return None
    lines = text.split("\n")
    return lines[number - 1] if 0 < number <= len(lines) else None


def _assertions_removed(ctx: AnalysisContext, sc: SymbolChange) -> None:
    assert sc.before is not None and sc.after is not None
    ev = ctx.code_evidence(
        sc.file, sc.after.start_line, min(sc.after.end_line, sc.after.start_line + 25),
        title=f"Assertions in {sc.qualname}", type=EvidenceType.METRIC, source="tree-sitter metric",
        data={"assertions_before": sc.before.assertions, "assertions_after": sc.after.assertions}, context=0,
        highlight=sorted(sc.head_lines),
    )  # fmt: skip
    ctx.add_finding(
        "CG-TST-004",
        title=f"Assertions removed from test `{sc.after.name}`",
        description=f"`{sc.qualname}` asserts {sc.after.assertions} time(s), down from {sc.before.assertions}.",
        location=Location(
            file=sc.file,
            start_line=sc.after.start_line,
            end_line=sc.after.end_line,
            symbol=sc.qualname,
        ),
        evidence_ids=[ev],
        failure_scenario="Behaviour previously checked by the removed assertions can regress while the test still passes.",
        suggested_test=SuggestedTest(
            description="Confirm the removed assertions are obsolete; otherwise restore them or move them to a new test.",
            kind="review",
        ),
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        related_symbols=[sc.qualname],
    )


def _tests_removed(ctx: AnalysisContext, path: str, tests: list[SymbolChange]) -> None:
    cf = ctx.workspace.file(path)
    deleted_file = cf is not None and cf.status is FileStatus.DELETED
    first = min(t.before.start_line for t in tests if t.before)
    last = max(t.before.end_line for t in tests if t.before)
    ev = ctx.code_evidence(
        tests[0].before.file if tests[0].before else path, first, min(last, first + 20), side="base",
        title=f"Removed tests in {path}", type=EvidenceType.DIFF_HUNK, source="diff",
        data={"removed_tests": [t.qualname for t in tests]}, context=0,
    )  # fmt: skip
    names = ", ".join(f"`{t.name}`" for t in tests[:6]) + (" …" if len(tests) > 6 else "")
    ctx.add_finding(
        "CG-TST-005",
        title=(
            f"Test file deleted ({len(tests)} tests)"
            if deleted_file
            else f"{len(tests)} test(s) removed"
        )
        + f" in {path}",
        description=f"Removed: {names}.",
        location=Location(file=path, start_line=first, end_line=last, side="base"),
        evidence_ids=[ev],
        failure_scenario="The behaviour these tests verified is no longer checked in CI.",
        suggested_test=SuggestedTest(
            description="Check that the removed tests' behaviour is gone or covered elsewhere before merging.",
            kind="review",
        ),
        confidence=Confidence.HIGH,
        discriminator=path,
    )
