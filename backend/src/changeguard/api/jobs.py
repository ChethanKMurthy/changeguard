"""Background execution of analyses on a bounded thread pool."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from changeguard.analysis.context import AnalysisOptions
from changeguard.analysis.pipeline import AnalysisPipeline, AnalysisTimeoutError, Synthesizer
from changeguard.errors import ChangeGuardError
from changeguard.ingest.prepare import PreparedInput
from changeguard.report.models import Report
from changeguard.storage import AnalysisStore

log = logging.getLogger(__name__)


def history_summary(report: Report) -> dict[str, Any]:
    s = report.summary
    return {
        "review_priority": s.review_priority.level,
        "findings_total": s.findings_total,
        "by_severity": s.by_severity,
        "by_kind": s.by_kind,
        "files_changed": s.files_changed,
        "additions": s.additions,
        "deletions": s.deletions,
        "languages": s.languages,
        "mode": report.input.mode,
        "ai_status": report.ai.status,
        "patch_coverage": s.patch_coverage.percent if s.patch_coverage else None,
    }


class JobRunner:
    def __init__(
        self,
        store: AnalysisStore,
        *,
        workers: int,
        timeout_seconds: float,
        synthesizer: Synthesizer | None,
        max_stored: int,
    ) -> None:
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.synthesizer = synthesizer
        self.max_stored = max_stored
        self.pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="analysis")

    def submit(
        self, analysis_id: str, created_at: str, prepared: PreparedInput, options: AnalysisOptions
    ) -> None:
        self.pool.submit(self._run, analysis_id, created_at, prepared, options)

    def run_sync(
        self, analysis_id: str, created_at: str, prepared: PreparedInput, options: AnalysisOptions
    ) -> None:
        self._run(analysis_id, created_at, prepared, options)

    def _run(
        self, analysis_id: str, created_at: str, prepared: PreparedInput, options: AnalysisOptions
    ) -> None:
        started = time.perf_counter()
        self.store.set_running(analysis_id)

        def sink(event: dict[str, Any]) -> None:
            self.store.append_event(analysis_id, event)

        sink({"type": "started", "analysis_id": analysis_id})
        try:
            pipeline = AnalysisPipeline(
                synthesizer=self.synthesizer if options.ai_enabled else None,
                on_event=sink,
                timeout_seconds=self.timeout_seconds,
            )
            report = pipeline.run(
                prepared, analysis_id=analysis_id, created_at=created_at, options=options
            )
        except ChangeGuardError as exc:
            error = {"code": exc.code, "message": exc.message}
            self.store.fail(analysis_id, error, (time.perf_counter() - started) * 1000)
            sink({"type": "failed", "error": error})
            return
        except AnalysisTimeoutError as exc:
            error = {"code": "timeout", "message": str(exc)}
            self.store.fail(analysis_id, error, (time.perf_counter() - started) * 1000)
            sink({"type": "failed", "error": error})
            return
        except Exception:
            log.exception("analysis %s crashed", analysis_id)
            error = {
                "code": "internal_error",
                "message": "The analysis failed unexpectedly. The error has been logged.",
            }
            self.store.fail(analysis_id, error, (time.perf_counter() - started) * 1000)
            sink({"type": "failed", "error": error})
            return
        duration = (time.perf_counter() - started) * 1000
        self.store.complete(
            analysis_id,
            title=report.title,
            report=report.model_dump(mode="json"),
            summary=history_summary(report),
            duration_ms=duration,
        )
        sink(
            {
                "type": "completed",
                "analysis_id": analysis_id,
                "duration_ms": round(duration, 1),
                "summary": history_summary(report),
            }
        )
        if self.max_stored > 0:
            self.store.prune(self.max_stored)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
