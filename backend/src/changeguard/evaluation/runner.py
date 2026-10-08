"""Evaluation runner: run systems over the dataset and produce a versioned result."""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from changeguard import REPORT_SCHEMA_VERSION, RULESET_VERSION, __version__
from changeguard.analysis.static_checks import ruff_version
from changeguard.evaluation.dataset import Case, dataset_fingerprint
from changeguard.evaluation.evidence_check import unsupported_findings
from changeguard.evaluation.matching import CaseResult, match_case
from changeguard.evaluation.metrics import SystemMetrics, aggregate
from changeguard.evaluation.systems import System

EVAL_FORMAT_VERSION = "1"


@dataclass(slots=True)
class SystemRun:
    system: System
    results: list[CaseResult]
    metrics: SystemMetrics


@dataclass(slots=True)
class EvaluationRun:
    manifest: dict[str, Any]
    runs: list[SystemRun] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)


def _git_sha(start: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=start,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = out.stdout.strip()
    if not sha or out.returncode != 0:
        return None
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=start,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return sha + ("-dirty" if dirty.stdout.strip() else "")


def evaluate_system(
    system: System, cases: list[Case], *, bootstrap_samples: int, seed: int, progress: bool = False
) -> SystemRun:
    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        output = system.run(case)
        result = match_case(case, output.predictions)
        result.duration_ms = output.duration_ms
        result.error = output.error
        result.ai = output.ai
        if output.report is not None:
            result.unsupported = unsupported_findings(case, output.report)
        results.append(result)
        if progress:
            status = (
                "ERROR"
                if output.error
                else f"tp={len(result.true_positives)} fp={len(result.false_positives)} fn={len(result.false_negatives)}"
            )
            print(
                f"  [{system.name}] {index:>2}/{len(cases)} {case.id:<28} {status}", file=sys.stderr
            )
    labels = {c.id: {label.id: label.severity.value for label in c.expected} for c in cases}
    metrics = aggregate(
        system.name,
        system.description,
        results,
        labels,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    return SystemRun(system, results, metrics)


def run_evaluation(
    cases: list[Case],
    systems: list[System],
    *,
    bootstrap_samples: int = 2000,
    seed: int = 20261008,
    progress: bool = False,
    ai_info: dict[str, Any] | None = None,
) -> EvaluationRun:
    manifest = {
        "format_version": EVAL_FORMAT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "changeguard_version": __version__,
        "ruleset_version": RULESET_VERSION,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "git_sha": _git_sha(Path(__file__).parent),
        "dataset_sha256": dataset_fingerprint(cases),
        "cases": len(cases),
        "splits": {
            s: sum(1 for c in cases if c.split == s) for s in ("dev", "holdout", "holdout-v2")
        },
        "negative_controls": sum(1 for c in cases if c.negative),
        "labels": sum(len(c.expected) for c in cases),
        "bootstrap": {"samples": bootstrap_samples, "seed": seed, "unit": "case"},
        "matching": {
            "rule": "same category and file, line ranges overlapping within ±3 lines, one-to-one"
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(terse=True),
            "machine": platform.machine(),
            "ruff": ruff_version(),
        },
        "ai": ai_info or {"mode": "off"},
    }
    run = EvaluationRun(manifest, cases=list(cases))
    for system in systems:
        run.runs.append(
            evaluate_system(
                system, cases, bootstrap_samples=bootstrap_samples, seed=seed, progress=progress
            )
        )
    return run


def case_details(run: SystemRun) -> list[dict[str, Any]]:
    out = []
    for r in run.results:
        out.append(
            {
                "case": r.case_id,
                "split": r.split,
                "negative": r.negative,
                "matched": sorted(label for label, _ in r.true_positives),
                "missed": sorted(label.id for label in r.false_negatives),
                "false_positives": sorted(p.signature for p in r.false_positives),
                "acceptable": len(r.acceptable),
                "unsupported": r.unsupported,
                "error": r.error,
                "duration_ms": round(r.duration_ms, 1),
            }
        )
    return out
