"""Assemble the final report from an analysis context."""

from __future__ import annotations

from collections import Counter
from typing import Any

from changeguard import REPORT_SCHEMA_VERSION, RULESET_VERSION, __version__
from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.secrets import redact
from changeguard.analysis.structure import SymbolChange
from changeguard.languages import STRUCTURAL_LANGUAGES
from changeguard.report.models import (
    CONFIDENCE_RANK,
    SEVERITY_RANK,
    AISummary,
    Evidence,
    FileSummary,
    Finding,
    FindingKind,
    HunkLine,
    HunkModel,
    InputSummary,
    PatchCoverage,
    Report,
    ReviewPriority,
    Severity,
    StageResult,
    Summary,
    SymbolChangeSummary,
)

MAX_HUNK_LINES_PER_FILE = 3000
_KIND_ORDER = {FindingKind.DETERMINISTIC: 0, FindingKind.HEURISTIC: 1, FindingKind.AI: 2}

BASE_LIMITATIONS = [
    "Static, name-based reference resolution: dynamic dispatch, reflection, monkey-patching, and dependency "
    "injection are not followed.",
    "Severity and confidence are categorical judgements defined per rule; they are not calibrated probabilities "
    "of a production incident.",
    "Test mapping detects tests that import and reference a changed symbol; tests that exercise it indirectly "
    "are not counted.",
    "ChangeGuard never executes code or tests; coverage numbers come only from an uploaded report.",
]


def finding_sort_key(f: Finding) -> tuple[Any, ...]:
    return (
        -SEVERITY_RANK[f.severity],
        _KIND_ORDER[f.kind],
        -CONFIDENCE_RANK[f.confidence],
        f.location.file,
        f.location.start_line or 0,
        f.rule_id,
    )


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Merge findings that describe the same issue at the same place (same category, overlapping lines)."""
    kept: list[Finding] = []
    for f in sorted(findings, key=finding_sort_key):
        merged = False
        for k in kept:
            if (
                k.category == f.category
                and k.location.file == f.location.file
                and k.location.side == f.location.side
                and _overlap(k, f)
                and k.kind != FindingKind.AI
                and f.kind != FindingKind.AI
            ):
                k.corroborated_by = list(dict.fromkeys([*k.corroborated_by, f.rule_id]))
                k.evidence_ids = list(dict.fromkeys([*k.evidence_ids, *f.evidence_ids]))
                merged = True
                break
        if not merged:
            kept.append(f)
    return kept


def _overlap(a: Finding, b: Finding) -> bool:
    if a.location.start_line is None or b.location.start_line is None:
        return False
    a_end = a.location.end_line or a.location.start_line
    b_end = b.location.end_line or b.location.start_line
    return a.location.start_line <= b_end and b.location.start_line <= a_end


def review_priority(findings: list[Finding]) -> ReviewPriority:
    """Transparent triage rule. It is a label for reviewers, not a probability."""
    blocking = [
        f
        for f in findings
        if f.severity is Severity.CRITICAL and f.kind is FindingKind.DETERMINISTIC
    ]
    if blocking:
        return ReviewPriority(
            level="block",
            rationale=f"{len(blocking)} critical finding(s) established by deterministic analysis.",
            triggered_by=[f.id for f in blocking],
        )
    high = [
        f
        for f in findings
        if SEVERITY_RANK[f.severity] >= SEVERITY_RANK[Severity.HIGH]
        and f.kind is not FindingKind.AI
    ]
    if high:
        return ReviewPriority(
            level="high",
            rationale=f"{len(high)} high-severity deterministic or heuristic finding(s).",
            triggered_by=[f.id for f in high],
        )
    elevated = [
        f for f in findings
        if (f.severity is Severity.MEDIUM and f.kind is not FindingKind.AI)
        or (f.kind is FindingKind.AI and SEVERITY_RANK[f.severity] >= SEVERITY_RANK[Severity.MEDIUM])
    ]  # fmt: skip
    if elevated:
        return ReviewPriority(
            level="elevated",
            rationale=f"{len(elevated)} medium-severity finding(s); AI-generated findings alone can raise priority at most to this level.",
            triggered_by=[f.id for f in elevated],
        )
    return ReviewPriority(
        level="routine", rationale="Only low-severity or informational findings.", triggered_by=[]
    )


def _valid_evidence(ctx: AnalysisContext, e: Evidence) -> bool:
    """Guard: evidence line numbers must exist in the revision they refer to."""
    if e.file is None or e.start_line is None:
        return True
    side = e.side or "head"
    text = ctx.source(e.file, side)
    if text is None:
        return True  # diff-only evidence: validated against hunks at creation
    count = text.count("\n") + (0 if text.endswith("\n") else 1)
    return 1 <= e.start_line <= max(count, 1) and (e.end_line or e.start_line) <= max(count, 1)


def build_report(
    ctx: AnalysisContext,
    *,
    analysis_id: str,
    created_at: str,
    title: str,
    patch_sha256: str,
    stages: list[StageResult],
    ai: AISummary,
    snapshot_stats: dict[str, Any] | None,
) -> Report:
    evidence_all = ctx.evidence.all()
    invalid = {e.id for e in evidence_all if not _valid_evidence(ctx, e)}
    if invalid:
        ctx.warnings.append(
            f"{len(invalid)} evidence item(s) failed the integrity check and were dropped."
        )
    findings: list[Finding] = []
    for f in ctx.findings:
        f.evidence_ids = [e for e in f.evidence_ids if e not in invalid]
        if f.explanation.source == "ai":
            f.explanation.evidence_ids = [e for e in f.explanation.evidence_ids if e not in invalid]
        if f.ai_analysis is not None:
            f.ai_analysis.evidence_ids = [e for e in f.ai_analysis.evidence_ids if e not in invalid]
        if f.evidence_ids:
            findings.append(f)
    findings = sorted(deduplicate(findings), key=finding_sort_key)
    referenced = {
        e
        for f in findings
        for e in (
            *f.evidence_ids,
            *f.explanation.evidence_ids,
            *(f.ai_analysis.evidence_ids if f.ai_analysis else ()),
        )
    }
    evidence = [e for e in evidence_all if e.id in referenced and e.id not in invalid]

    files = [_file_summary(ctx, cf) for cf in ctx.files]
    symbols = [_symbol_summary(sc) for sc in ctx.symbol_changes]
    testable = [s for s in ctx.symbol_changes if s.related_tests or _was_testable(s)]
    patch_cov = ctx.stage_data.get("patch_coverage")
    summary = Summary(
        files_changed=len(ctx.files),
        additions=ctx.patch.additions,
        deletions=ctx.patch.deletions,
        languages=sorted({cf.display_language for cf in ctx.files}),
        findings_total=len(findings),
        by_severity=_count(f.severity.value for f in findings),
        by_kind=_count(f.kind.value for f in findings),
        by_category=_count(f.category.value for f in findings),
        review_priority=review_priority(findings),
        changed_symbols=len([s for s in ctx.symbol_changes if s.kind != "test"]),
        breaking_symbols=len(
            [
                s
                for s in ctx.symbol_changes
                if s.signature_diff is not None and s.signature_diff.breaking
            ]
        ),
        symbols_with_tests=len([s for s in ctx.symbol_changes if s.related_tests]),
        testable_symbols=len(testable),
        patch_coverage=patch_cov if isinstance(patch_cov, PatchCoverage) else None,
    )
    limitations = list(BASE_LIMITATIONS)
    if not ctx.full_context:
        limitations.insert(
            0,
            "Diff-only mode: no repository snapshot was provided, so call-site compatibility, removed-symbol "
            "references, test mapping, and differential static analysis of modified files were not performed.",
        )
    unsupported = sorted(
        {cf.display_language for cf in ctx.files if cf.language is None} - set(STRUCTURAL_LANGUAGES)
    )
    if unsupported:
        limitations.append(
            "Line-level rules only (secrets, migrations, dependencies, prompt injection) for: "
            + ", ".join(unsupported)
            + "."
        )
    return Report(
        schema_version=REPORT_SCHEMA_VERSION,
        analysis_id=analysis_id,
        created_at=created_at,
        title=title,
        engine_version=__version__,
        ruleset_version=RULESET_VERSION,
        input=InputSummary(
            patch_sha256=patch_sha256,
            patch_format=ctx.patch.format,
            subject=ctx.patch.subject,
            mode="full_context" if ctx.full_context else "diff_only",
            has_snapshot=ctx.full_context,
            snapshot=snapshot_stats,
            has_coverage=ctx.coverage is not None,
            coverage_format=ctx.coverage.format if ctx.coverage else None,
        ),
        summary=summary,
        findings=findings,
        evidence=evidence,
        files=files,
        symbols=symbols,
        pipeline=stages,
        ai=ai,
        warnings=list(dict.fromkeys([*ctx.patch.warnings, *ctx.workspace.warnings, *ctx.warnings])),
        limitations=limitations,
    )


def _was_testable(sc: SymbolChange) -> bool:
    return (
        sc.kind in ("function", "method", "class")
        and sc.change in ("modified", "added", "renamed")
        and not sc.approximate
    )


def _count(values: Any) -> dict[str, int]:
    return dict(Counter(values))


def _file_summary(ctx: AnalysisContext, cf: Any) -> FileSummary:
    hunks: list[HunkModel] = []
    budget = MAX_HUNK_LINES_PER_FILE
    for h in cf.diff.hunks:
        if budget <= 0:
            break
        lines = [
            HunkLine(kind=ln.kind, content=redact(ln.content), old=ln.old_lineno, new=ln.new_lineno)
            for ln in h.lines[:budget]
        ]
        budget -= len(lines)
        hunks.append(
            HunkModel(header=h.header, old_start=h.old_start, old_count=h.old_count, new_start=h.new_start,
                      new_count=h.new_count, section=redact(h.section), lines=lines)
        )  # fmt: skip
    changed = [sc.qualname for sc in ctx.symbol_changes if sc.file == cf.path]
    return FileSummary(
        path=cf.path,
        old_path=cf.old_path if cf.old_path != cf.path else None,
        status=cf.status.value,
        language=cf.display_language,
        structural_support=cf.language is not None,
        is_test=cf.is_test,
        is_binary=cf.diff.is_binary,
        additions=cf.diff.additions,
        deletions=cf.diff.deletions,
        full_context=cf.full_context,
        hunks=hunks,
        changed_symbols=changed,
        coverage=ctx.coverage_matches.get(cf.path),
    )


def _symbol_summary(sc: SymbolChange) -> SymbolChangeSummary:
    before = (
        sc.before.signature.render(sc.before.name) if sc.before and sc.before.signature else None
    )
    after = sc.after.signature.render(sc.after.name) if sc.after and sc.after.signature else None
    sym = sc.symbol
    return SymbolChangeSummary(
        file=sc.file,
        qualname=sc.qualname,
        kind=sc.kind,
        change=sc.change,
        renamed_from=sc.renamed_from,
        signature_before=before,
        signature_after=after,
        breaking=bool(sc.signature_diff and sc.signature_diff.breaking),
        start_line=sym.start_line,
        end_line=sym.end_line,
        call_sites=len(sc.call_sites),
        call_site_files=len({getattr(r, "file", None) for r in sc.call_sites}),
        incompatible_call_sites=len(sc.incompatible_calls),
        related_tests=len(sc.related_tests),
        complexity_before=sc.before.complexity
        if sc.before and sc.kind in ("function", "method")
        else None,
        complexity_after=sc.after.complexity
        if sc.after and sc.kind in ("function", "method")
        else None,
        approximate=sc.approximate,
    )
