"""Coverage of changed lines ("patch coverage"), measured from an uploaded report.

Every number in these findings comes from the uploaded coverage report; the
tool never runs tests. The report is assumed to describe the *head* revision.
A plausibility check flags reports that look stale (covered lines beyond the
end of the file or on blank/comment lines).
"""

from __future__ import annotations

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.workspace import ChangedFile
from changeguard.ingest.coverage import FileCoverage
from changeguard.ingest.diff_parser import FileStatus
from changeguard.report.models import (
    Confidence,
    EvidenceType,
    FileCoverageSummary,
    Location,
    PatchCoverage,
    Severity,
    SuggestedTest,
)

STALE_RATIO = 0.10


def analyze_coverage(ctx: AnalysisContext) -> dict[str, object]:
    report = ctx.coverage
    if report is None:
        return {"skipped": "no coverage report"}
    code_files = [
        cf for cf in ctx.files
        if cf.language is not None and not cf.is_test and cf.status is not FileStatus.DELETED and not cf.diff.is_binary
    ]  # fmt: skip
    matches, unmatched = report.match([cf.path for cf in code_files])
    total_exec = total_cov = 0
    stale_files: list[str] = []
    summaries: dict[str, FileCoverageSummary] = {}
    for cf in code_files:
        fc = matches.get(cf.path)
        if fc is None:
            if cf.added:
                _absent(ctx, cf)
            continue
        if _looks_stale(cf, fc):
            stale_files.append(cf.path)
        executable = [n for n in sorted(cf.added) if n in fc.lines]
        uncovered = [n for n in executable if fc.lines[n] == 0]
        total_exec += len(executable)
        total_cov += len(executable) - len(uncovered)
        summaries[cf.path] = FileCoverageSummary(
            covered=len(executable) - len(uncovered),
            executable=len(executable),
            uncovered_lines=uncovered,
        )
        if uncovered:
            _gaps(ctx, cf, fc, executable, uncovered, stale=cf.path in stale_files)
    if stale_files:
        ctx.warnings.append(
            "The coverage report may not match the head revision for "
            + ", ".join(stale_files[:5])
            + " (it marks lines beyond the file end or on blank lines as executable). Coverage findings for "
            "these files have reduced confidence."
        )
    ctx.coverage_matches = summaries
    patch = PatchCoverage(
        covered=total_cov,
        executable=total_exec,
        percent=round(100.0 * total_cov / total_exec, 1) if total_exec else None,
    )
    ctx.stage_data["patch_coverage"] = patch
    return {
        "format": report.format,
        "matched_files": len(matches),
        "unmatched_report_files": len(unmatched),
        "changed_executable_lines": total_exec,
        "changed_covered_lines": total_cov,
        "patch_coverage_percent": patch.percent,
        "stale_files": stale_files,
    }


def _looks_stale(cf: ChangedFile, fc: FileCoverage) -> bool:
    if cf.head_text is None or not fc.lines:
        return False
    lines = cf.head_text.split("\n")
    suspicious = 0
    for number in fc.lines:
        if number > len(lines):
            suspicious += 1
            continue
        stripped = lines[number - 1].strip()
        if not stripped or stripped.startswith(("#", "//")):
            suspicious += 1
    return suspicious / len(fc.lines) > STALE_RATIO


def _absent(ctx: AnalysisContext, cf: ChangedFile) -> None:
    ev = ctx.evidence.add(
        EvidenceType.COVERAGE,
        f"No coverage data for {cf.path}",
        source=f"coverage report ({ctx.coverage.format if ctx.coverage else 'unknown'})",
        file=cf.path,
        data={"matched": False, "changed_lines": len(cf.added)},
    )
    ctx.add_finding(
        "CG-COV-002",
        title=f"Coverage report has no data for {cf.path}",
        description=f"{len(cf.added)} line(s) changed in {cf.path}, but the uploaded coverage report does not "
        "mention the file.",
        location=Location(file=cf.path, start_line=min(cf.added), end_line=max(cf.added)),
        evidence_ids=[ev],
        failure_scenario="If no test imports this file, none of its changes are exercised in CI.",
        suggested_test=SuggestedTest(
            description="Check the coverage configuration includes this path, then add tests that import it.",
            kind="review",
        ),
        confidence=Confidence.MEDIUM,
    )


def _gaps(
    ctx: AnalysisContext,
    cf: ChangedFile,
    fc: FileCoverage,
    executable: list[int],
    uncovered: list[int],
    *,
    stale: bool,
) -> None:
    source = f"coverage report ({ctx.coverage.format if ctx.coverage else 'unknown'})"
    never_run = bool(fc.lines) and all(hits == 0 for hits in fc.lines.values())
    if never_run:
        # The test suite never executes this file at all: one finding, not one per function.
        ev = ctx.code_evidence(
            cf.path, uncovered[0], uncovered[-1], title=f"{cf.path} is never executed by the test suite",
            type=EvidenceType.COVERAGE, source=source,
            data={"uncovered_lines": uncovered, "file_executable_lines": fc.executable, "file_covered_lines": 0},
            context=0, highlight=uncovered,
        )  # fmt: skip
        ctx.add_finding(
            "CG-COV-001",
            title=f"No test executes {cf.path} ({len(uncovered)} changed executable line(s))",
            description=f"The coverage report records 0 hits for every one of the {fc.executable} executable lines in "
            f"{cf.path}, including the changed line(s) {_ranges(uncovered)}. The module is probably never imported by a test.",
            location=Location(file=cf.path, start_line=uncovered[0], end_line=uncovered[-1]),
            evidence_ids=[ev],
            failure_scenario="Any bug introduced in this file reaches production without a single test running its code.",
            suggested_test=SuggestedTest(
                description=f"Add a test module that imports {cf.path} and exercises the changed code paths.",
                kind="unit",
            ),
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM if stale else Confidence.HIGH,
            discriminator="file",
        )
        return
    groups: dict[str, list[int]] = {}
    labels: dict[str, tuple[int, int, str | None]] = {}
    for n in uncovered:
        sym = cf.head_index.innermost_symbol(n, ("function", "method")) if cf.head_index else None
        key = sym.qualname if sym else "<module>"
        groups.setdefault(key, []).append(n)
        if sym:
            labels[key] = (sym.start_line, sym.end_line, sym.qualname)
    for key, lines in groups.items():
        start, end, symbol = labels.get(key, (lines[0], lines[-1], None))
        in_scope = (
            [n for n in executable if start <= n <= end]
            if symbol
            else [
                n
                for n in executable
                if not (cf.head_index and cf.head_index.innermost_symbol(n, ("function", "method")))
            ]
        )
        ev = ctx.code_evidence(
            cf.path, lines[0], lines[-1], title=f"Uncovered changed lines in {symbol or 'module scope of ' + cf.path}",
            type=EvidenceType.COVERAGE, source=source,
            data={"uncovered_lines": lines, "changed_executable_lines": in_scope, "hits": {str(n): fc.lines.get(n, 0) for n in in_scope}},
            context=1, highlight=lines,
        )  # fmt: skip
        target = f"`{symbol}`" if symbol else f"module-level code of {cf.path}"
        ctx.add_finding(
            "CG-COV-001",
            title=f"{len(lines)} of {len(in_scope)} changed executable line(s) in {target} never run in tests",
            description=f"The coverage report shows 0 hits for changed line(s) {_ranges(lines)} of {cf.path}.",
            location=Location(file=cf.path, start_line=lines[0], end_line=lines[-1], symbol=symbol),
            evidence_ids=[ev],
            failure_scenario=f"A bug on line {lines[0]} would not fail any existing test, because the test suite "
            "never executes it.",
            suggested_test=SuggestedTest(
                description=f"Add a test that drives execution through line(s) {_ranges(lines)} of {cf.path}, then "
                "re-run coverage to confirm.",
                kind="unit",
            ),
            severity=Severity.MEDIUM if len(lines) >= 3 else Severity.LOW,
            confidence=Confidence.MEDIUM if stale else Confidence.HIGH,
            related_symbols=[symbol] if symbol else [],
            discriminator=key,
        )


def _block_start(sorted_lines: list[int], n: int) -> int:
    start = n
    while start - 1 in sorted_lines:
        start -= 1
    return start


def _ranges(lines: list[int]) -> str:
    out: list[str] = []
    start = prev = lines[0]
    for n in lines[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append(f"{start}" if start == prev else f"{start}–{prev}")
        start = prev = n
    out.append(f"{start}" if start == prev else f"{start}–{prev}")
    return ", ".join(out)
