"""Analysis pipeline: an explicit sequence of timed, observable stages.

Each stage reports a status (ok / skipped / warning / failed), its duration,
and a small summary. A failing non-critical stage degrades the report rather
than aborting it, and the failure is visible in the report's pipeline section.
Progress events are emitted for live UIs (server-sent events).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from changeguard.analysis.api_contract import analyze_api_contract
from changeguard.analysis.context import AnalysisContext, AnalysisOptions
from changeguard.analysis.coverage_gaps import analyze_coverage
from changeguard.analysis.dependencies import analyze_dependencies
from changeguard.analysis.logic import analyze_logic
from changeguard.analysis.metrics import analyze_metrics
from changeguard.analysis.patterns import analyze_patterns
from changeguard.analysis.references import RepositoryIndex
from changeguard.analysis.static_checks import analyze_static
from changeguard.analysis.structure import compute_symbol_changes, index_changed_files
from changeguard.analysis.tests_mapping import analyze_tests
from changeguard.analysis.textual import analyze_textual
from changeguard.analysis.workspace import build_workspace
from changeguard.ingest.prepare import PreparedInput
from changeguard.report.models import AISummary, Report, StageResult, StageStatus

log = logging.getLogger(__name__)

STAGES: list[tuple[str, str]] = [
    ("ingest", "Parse inputs"),
    ("workspace", "Reconstruct revisions"),
    ("structure", "Structural diff"),
    ("references", "Cross-file references"),
    ("static", "Static analysis"),
    ("rules", "Risk rules"),
    ("tests", "Test mapping"),
    ("coverage", "Coverage"),
    ("synthesis", "AI synthesis"),
    ("verification", "Grounding verification"),
    ("report", "Assemble report"),
]
STAGE_LABELS = dict(STAGES)

EventSink = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class SynthesisOutcome:
    summary: AISummary
    synthesis: StageResult
    verification: StageResult


class Synthesizer(Protocol):
    def run(self, ctx: AnalysisContext) -> SynthesisOutcome: ...


class AnalysisTimeoutError(RuntimeError):
    pass


@dataclass(slots=True)
class _Recorder:
    sink: EventSink | None
    deadline: float | None
    stages: list[StageResult] = field(default_factory=list)

    def emit(self, event: dict[str, Any]) -> None:
        if self.sink is not None:
            try:
                self.sink(event)
            except Exception:  # an observer must never break the analysis
                log.exception("event sink failed")

    def record(self, result: StageResult) -> None:
        self.stages.append(result)
        self.emit({"type": "stage", **result.model_dump(mode="json")})

    def run(
        self,
        name: str,
        fn: Callable[[], dict[str, Any] | None],
        *,
        critical: bool = False,
        ctx: AnalysisContext | None = None,
    ) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise AnalysisTimeoutError(f"analysis exceeded its time budget before stage '{name}'")
        if ctx is not None and name in ctx.options.disabled_stages:
            self.record(StageResult(name=name, label=STAGE_LABELS[name], status="skipped", duration_ms=0.0,
                                    notes=["disabled for this run (ablation)"]))  # fmt: skip
            return
        self.emit({"type": "stage", "name": name, "label": STAGE_LABELS[name], "status": "running"})
        started = time.perf_counter()
        status: StageStatus = "ok"
        notes: list[str] = []
        summary: dict[str, Any] = {}
        try:
            summary = fn() or {}
            if summary.pop("_skipped", None):
                status = "skipped"
            reason = summary.get("skipped")
            if reason:
                status = "skipped"
                notes.append(str(reason))
        except Exception as exc:
            if critical:
                raise
            log.exception("stage %s failed", name)
            status = "failed"
            notes.append(f"{type(exc).__name__}: stage failed; results from this stage are missing")
            if ctx is not None:
                ctx.warnings.append(
                    f"Stage '{STAGE_LABELS[name]}' failed; its checks are missing from this report."
                )
        self.record(
            StageResult(
                name=name,
                label=STAGE_LABELS[name],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                summary=summary,
                notes=notes,
            )
        )


class AnalysisPipeline:
    def __init__(
        self,
        *,
        synthesizer: Synthesizer | None = None,
        on_event: EventSink | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.synthesizer = synthesizer
        self.on_event = on_event
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        prepared: PreparedInput,
        *,
        analysis_id: str,
        created_at: str,
        options: AnalysisOptions,
    ) -> Report:
        deadline = time.monotonic() + self.timeout_seconds if self.timeout_seconds else None
        rec = _Recorder(self.on_event, deadline)
        patch = prepared.patch
        rec.record(
            StageResult(
                name="ingest",
                label=STAGE_LABELS["ingest"],
                status="ok",
                duration_ms=round(prepared.ingest_ms, 2),
                summary={
                    "files": len(patch.files),
                    "additions": patch.additions,
                    "deletions": patch.deletions,
                    "format": patch.format,
                    "snapshot_files": len(prepared.snapshot.files) if prepared.snapshot else None,
                    "coverage_format": prepared.coverage.format if prepared.coverage else None,
                },
            )
        )

        holder: dict[str, AnalysisContext] = {}

        def workspace_stage() -> dict[str, Any]:
            ws = build_workspace(patch, prepared.snapshot)
            holder["ctx"] = AnalysisContext(
                patch=patch, workspace=ws, coverage=prepared.coverage, options=options
            )
            return {
                "mode": ws.mode,
                "full_context_files": sum(1 for f in ws.files if f.full_context),
                "repository_files": len(ws.head_repo),
                "warnings": len(ws.warnings),
            }

        rec.run("workspace", workspace_stage, critical=True)
        ctx = holder["ctx"]

        def structure_stage() -> dict[str, Any]:
            indexed = index_changed_files(ctx)
            changes = compute_symbol_changes(ctx)
            return {
                **indexed,
                "changed_symbols": len(changes),
                "signature_changes": sum(1 for c in changes if c.signature_diff is not None),
                "breaking": sum(
                    1 for c in changes if c.signature_diff is not None and c.signature_diff.breaking
                ),
            }

        rec.run("structure", structure_stage, ctx=ctx)

        repo: RepositoryIndex | None = None

        def references_stage() -> dict[str, Any]:
            nonlocal repo
            if not ctx.full_context:
                return {
                    "skipped": "diff-only mode: no repository snapshot",
                    **analyze_api_contract(ctx, None),
                }
            repo = RepositoryIndex(ctx)
            ctx.repo_index = repo
            stats = analyze_api_contract(ctx, repo)
            return {**stats, "files_parsed": repo.parsed}

        rec.run("references", references_stage, ctx=ctx)
        rec.run("static", lambda: analyze_static(ctx), ctx=ctx)

        def rules_stage() -> dict[str, Any]:
            out: dict[str, Any] = {}
            out["patterns"] = analyze_patterns(ctx)
            out["textual"] = analyze_textual(ctx)
            out["dependencies"] = analyze_dependencies(ctx)
            out["logic"] = analyze_logic(ctx)
            out["metrics"] = analyze_metrics(ctx)
            return out

        rec.run("rules", rules_stage, ctx=ctx)

        def tests_stage() -> dict[str, Any]:
            if repo is None:
                return {"skipped": "test mapping requires a repository snapshot"}
            return analyze_tests(ctx, repo)

        rec.run("tests", tests_stage, ctx=ctx)
        rec.run("coverage", lambda: analyze_coverage(ctx), ctx=ctx)

        ai_summary = AISummary(
            status="disabled",
            note="AI synthesis was not requested; explanations are rule templates.",
        )
        if options.ai_enabled and self.synthesizer is not None:
            rec.emit(
                {
                    "type": "stage",
                    "name": "synthesis",
                    "label": STAGE_LABELS["synthesis"],
                    "status": "running",
                }
            )
            try:
                outcome = self.synthesizer.run(ctx)
                ai_summary = outcome.summary
                rec.record(outcome.synthesis)
                rec.record(outcome.verification)
            except Exception:
                log.exception("AI synthesis failed")
                ai_summary = AISummary(
                    status="failed",
                    note="AI synthesis failed; the deterministic report is unaffected.",
                )
                rec.record(
                    StageResult(
                        name="synthesis",
                        label=STAGE_LABELS["synthesis"],
                        status="failed",
                        duration_ms=0,
                        notes=["synthesis failed"],
                    )
                )
                rec.record(
                    StageResult(
                        name="verification",
                        label=STAGE_LABELS["verification"],
                        status="skipped",
                        duration_ms=0,
                    )
                )
        else:
            reason = (
                "AI disabled for this analysis"
                if not options.ai_enabled
                else "no AI provider configured"
            )
            if options.ai_enabled:
                ai_summary = AISummary(
                    status="skipped", note="AI was requested but no provider is configured."
                )
            rec.record(
                StageResult(
                    name="synthesis",
                    label=STAGE_LABELS["synthesis"],
                    status="skipped",
                    duration_ms=0,
                    notes=[reason],
                )
            )
            rec.record(
                StageResult(
                    name="verification",
                    label=STAGE_LABELS["verification"],
                    status="skipped",
                    duration_ms=0,
                    notes=[reason],
                )
            )

        # Imported here to keep the pipeline module free of report-building internals.
        from changeguard.report.builder import build_report

        started = time.perf_counter()
        rec.emit(
            {
                "type": "stage",
                "name": "report",
                "label": STAGE_LABELS["report"],
                "status": "running",
            }
        )
        title = options.title or patch.subject or _default_title(ctx)
        report = build_report(
            ctx,
            analysis_id=analysis_id,
            created_at=created_at,
            title=title,
            patch_sha256=prepared.patch_sha256,
            stages=rec.stages,
            ai=ai_summary,
            snapshot_stats=prepared.snapshot.stats() if prepared.snapshot else None,
        )
        result = StageResult(
            name="report",
            label=STAGE_LABELS["report"],
            status="ok",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            summary={"findings": len(report.findings), "evidence": len(report.evidence)},
        )
        report.pipeline.append(result)
        rec.emit({"type": "stage", **result.model_dump(mode="json")})
        return report


def _default_title(ctx: AnalysisContext) -> str:
    files = ctx.files
    if len(files) == 1:
        return f"Change to {files[0].path}"
    dirs = {f.path.split("/")[0] for f in files}
    scope = next(iter(dirs)) + "/" if len(dirs) == 1 and len(files) > 1 else ""
    return f"Change to {len(files)} files" + (f" in {scope}" if scope else "")
