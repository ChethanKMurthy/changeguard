"""Systems under evaluation: ChangeGuard configurations and naive baselines.

Baselines exist to answer "compared to what?":

* ``baseline-keyword`` flags added lines containing risky-looking tokens
  (``eval(``, ``password =``, ``DROP TABLE``, ``except:`` ...), the
  grep-based approach many teams start with;
* ``baseline-changed-symbols`` flags every changed function as risky
  ("review everything that changed").
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from changeguard.analysis.context import AnalysisContext, AnalysisOptions
from changeguard.analysis.pipeline import AnalysisPipeline, Synthesizer
from changeguard.analysis.structure import compute_symbol_changes, index_changed_files
from changeguard.analysis.workspace import build_workspace
from changeguard.config import Settings
from changeguard.evaluation.dataset import Case
from changeguard.evaluation.matching import Prediction
from changeguard.ingest.diff_parser import parse_patch
from changeguard.ingest.prepare import prepare_input
from changeguard.report.models import Finding, Report


@dataclass(slots=True)
class SystemOutput:
    predictions: list[Prediction]
    report: Report | None = None
    duration_ms: float = 0.0
    error: str | None = None
    ai: dict[str, object] = field(default_factory=dict)


class System(Protocol):
    name: str
    description: str

    def run(self, case: Case) -> SystemOutput: ...


def _prediction(f: Finding) -> Prediction:
    return Prediction(
        id=f.id,
        rule_id=f.rule_id,
        category=f.category.value,
        kind=f.kind.value,
        severity=f.severity.value,
        confidence=f.confidence.value,
        file=f.location.file,
        start_line=f.location.start_line,
        end_line=f.location.end_line,
        title=f.title,
    )


class ChangeGuardSystem:
    def __init__(
        self,
        name: str = "changeguard",
        *,
        description: str = "Deterministic + heuristic rules (no AI)",
        synthesizer: Synthesizer | None = None,
        force_diff_only: bool = False,
        disabled_stages: frozenset[str] = frozenset(),
        settings: Settings | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.synthesizer = synthesizer
        self.force_diff_only = force_diff_only
        self.disabled_stages = disabled_stages
        self.settings = settings or Settings()

    def run(self, case: Case) -> SystemOutput:
        started = time.perf_counter()
        diff_only = self.force_diff_only or case.mode == "diff_only"
        try:
            prepared = prepare_input(
                self.settings,
                patch=case.patch_text(),
                archive=None if diff_only else case.archive(),
                coverage=case.coverage_bytes(),
            )
            report = AnalysisPipeline(synthesizer=self.synthesizer).run(
                prepared,
                analysis_id=f"eval-{case.id}",
                created_at="1970-01-01T00:00:00Z",
                options=AnalysisOptions(
                    ai_enabled=self.synthesizer is not None, disabled_stages=self.disabled_stages
                ),
            )
        except Exception as exc:  # an evaluation must record failures, not abort
            return SystemOutput(
                [], None, (time.perf_counter() - started) * 1000, f"{type(exc).__name__}: {exc}"
            )
        ai: dict[str, object] = {}
        if report.ai.status != "disabled":
            v = report.ai.verification
            ai = {
                "status": report.ai.status,
                "model": report.ai.model,
                "claims_total": v.claims_total if v else 0,
                "claims_accepted": v.claims_accepted if v else 0,
                "claims_rejected": v.claims_rejected if v else 0,
                "rejection_reasons": [
                    r.split(":")[0] for c in (v.rejected if v else []) for r in c.reasons
                ],
                "notes_applied": sum(
                    1 for f in report.findings if f.ai_analysis is not None and f.kind.value != "ai"
                ),
                "ai_findings": sum(1 for f in report.findings if f.kind.value == "ai"),
                "latency_ms": sum(c.latency_ms for c in report.ai.calls),
                "input_tokens": sum(c.input_tokens or 0 for c in report.ai.calls),
                "output_tokens": sum(c.output_tokens or 0 for c in report.ai.calls),
                "cache_hits": sum(1 for c in report.ai.calls if c.cache_hit),
                "calls": len(report.ai.calls),
                "call_errors": [c.error for c in report.ai.calls if c.error],
            }
        return SystemOutput(
            [_prediction(f) for f in report.findings],
            report,
            (time.perf_counter() - started) * 1000,
            ai=ai,
        )


_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\beval\(|\bexec\(|new Function\("), "security"),
    (re.compile(r"innerHTML|dangerouslySetInnerHTML|document\.write"), "security"),
    (re.compile(r"shell\s*=\s*True|os\.system\(|child_process|execSync\(|\bexec\(`"), "security"),
    (re.compile(r"pickle\.loads?\(|yaml\.load\("), "security"),
    (re.compile(r"verify\s*=\s*False"), "security"),
    (re.compile(r"execute\(\s*f[\"']|execute\([^)]*%"), "security"),
    (re.compile(r"(?i)(password|secret|api_?key|token)\w*\s*[:=]\s*[\"']"), "secret_exposure"),
    (
        re.compile(
            r"(?i)\bdrop\s+(table|column)\b|\btruncate\b|drop_column|drop_table|\bdelete\s+from\b"
        ),
        "data_migration",
    ),
    (re.compile(r"except\s*:|except\s+Exception\s*:|catch\s*\(\w*\)\s*\{\s*\}"), "error_handling"),
    (re.compile(r"time\.sleep\(|requests\.(get|post)\("), "concurrency"),
    (re.compile(r"forEach\(\s*async"), "concurrency"),
    (re.compile(r"\.only\(|\.skip\(|pytest\.mark\.skip|\bxit\("), "test_integrity"),
    (re.compile(r"[<>]=?|==|!="), "logic_change"),
]
_MANIFESTS = re.compile(r"(^|/)(package\.json|pyproject\.toml|requirements[\w.-]*\.txt)$")


class KeywordBaseline:
    name = "baseline-keyword"
    description = "Regex search for risky-looking tokens on added lines"

    def run(self, case: Case) -> SystemOutput:
        started = time.perf_counter()
        patch = parse_patch(case.patch_text())
        predictions: list[Prediction] = []
        for fd in patch.files:
            for h in fd.hunks:
                for ln in h.lines:
                    if ln.kind != "add" or ln.new_lineno is None:
                        continue
                    if _MANIFESTS.search(fd.path):
                        predictions.append(
                            self._p(fd.path, ln.new_lineno, "dependency", len(predictions))
                        )
                        continue
                    for pattern, category in _KEYWORDS:
                        if pattern.search(ln.content):
                            predictions.append(
                                self._p(fd.path, ln.new_lineno, category, len(predictions))
                            )
                            break
        return SystemOutput(predictions, None, (time.perf_counter() - started) * 1000)

    @staticmethod
    def _p(path: str, line: int, category: str, n: int) -> Prediction:
        return Prediction(
            f"K{n}",
            f"KW-{category}",
            category,
            "heuristic",
            "medium",
            "low",
            path,
            line,
            line,
            f"keyword: {category}",
        )


class ChangedSymbolsBaseline:
    name = "baseline-changed-symbols"
    description = "Flag every changed function (signature changes as breaking)"

    def run(self, case: Case) -> SystemOutput:
        started = time.perf_counter()
        from changeguard.ingest.archive import read_snapshot

        patch = parse_patch(case.patch_text())
        snapshot = read_snapshot(case.archive()) if case.mode == "full_context" else None
        ws = build_workspace(patch, snapshot)
        ctx = AnalysisContext(patch=patch, workspace=ws, coverage=None, options=AnalysisOptions())
        index_changed_files(ctx)
        predictions: list[Prediction] = []
        for sc in compute_symbol_changes(ctx):
            if sc.kind not in ("function", "method") or sc.change == "removed":
                continue
            sym = sc.symbol
            category = "breaking_change" if sc.signature_diff is not None else "test_gap"
            pid = f"S{len(predictions)}"
            title = f"changed: {sc.qualname}"
            predictions.append(
                Prediction(
                    pid,
                    f"SYM-{category}",
                    category,
                    "heuristic",
                    "medium",
                    "low",
                    sc.file,
                    sym.signature_line,
                    sym.end_line,
                    title,
                )
            )
        return SystemOutput(predictions, None, (time.perf_counter() - started) * 1000)
