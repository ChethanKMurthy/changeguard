"""Aggregate metrics with bootstrap confidence intervals.

Micro-averaged precision/recall/F1 over all labels and predictions. Confidence
intervals are percentile bootstrap intervals over *cases* (the unit of
sampling), so they reflect how much the numbers depend on which changes
happened to be in the dataset — with a dataset this small they are wide, and
the report says so.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from changeguard.evaluation.matching import CaseResult
from changeguard.report.models import SEVERITY_RANK, Severity


def _num(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _strings(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def _f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or (p + r) == 0:
        return None if p is None or r is None else 0.0
    return round(2 * p * r / (p + r), 4)


@dataclass(slots=True)
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float | None:
        return _f1(self.precision, self.recall)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def micro(results: list[CaseResult]) -> Counts:
    c = Counts()
    for r in results:
        c.tp += len(r.true_positives)
        c.fp += len(r.false_positives)
        c.fn += len(r.false_negatives)
    return c


@dataclass(slots=True)
class Interval:
    low: float | None
    high: float | None

    def as_list(self) -> list[float | None]:
        return [self.low, self.high]


def bootstrap(results: list[CaseResult], *, samples: int, seed: int) -> dict[str, Interval]:
    rng = random.Random(seed)  # noqa: S311 - statistical resampling, not cryptography
    n = len(results)
    stats: dict[str, list[float]] = {"precision": [], "recall": [], "f1": []}
    if n == 0:
        return {k: Interval(None, None) for k in stats}
    for _ in range(samples):
        draw = [results[rng.randrange(n)] for _ in range(n)]
        c = micro(draw)
        for key, value in (("precision", c.precision), ("recall", c.recall), ("f1", c.f1)):
            if value is not None:
                stats[key].append(value)

    def pct(values: list[float], q: float) -> float | None:
        if not values:
            return None
        values = sorted(values)
        index = min(len(values) - 1, max(0, round(q * (len(values) - 1))))
        return round(values[index], 4)

    return {k: Interval(pct(v, 0.025), pct(v, 0.975)) for k, v in stats.items()}


@dataclass(slots=True)
class SystemMetrics:
    system: str
    description: str
    cases: int
    labels: int
    predictions: int
    overall: Counts
    ci: dict[str, Interval]
    by_split: dict[str, Counts] = field(default_factory=dict)
    ci_by_split: dict[str, dict[str, Interval]] = field(default_factory=dict)
    by_category: dict[str, Counts] = field(default_factory=dict)
    by_difficulty: dict[str, Counts] = field(default_factory=dict)
    by_language: dict[str, Counts] = field(default_factory=dict)
    by_kind: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_confidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    negative_cases: int = 0
    negative_cases_with_fp: int = 0
    fp_per_negative_case: float | None = None
    unsupported_findings: int = 0
    findings_checked: int = 0
    severity_exact: float | None = None
    severity_within_one: float | None = None
    acceptable: int = 0
    errors: int = 0
    latency_ms_mean: float | None = None
    latency_ms_p95: float | None = None
    ai: dict[str, Any] = field(default_factory=dict)

    @property
    def negative_fp_rate(self) -> float | None:
        return _ratio(self.negative_cases_with_fp, self.negative_cases)

    @property
    def unsupported_rate(self) -> float | None:
        return _ratio(self.unsupported_findings, self.findings_checked)

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "description": self.description,
            "cases": self.cases,
            "labels": self.labels,
            "predictions": self.predictions,
            "acceptable": self.acceptable,
            "errors": self.errors,
            "overall": self.overall.as_dict(),
            "ci95": {k: v.as_list() for k, v in self.ci.items()},
            "by_split": {k: v.as_dict() for k, v in sorted(self.by_split.items())},
            "ci95_by_split": {
                split: {k: v.as_list() for k, v in intervals.items()}
                for split, intervals in sorted(self.ci_by_split.items())
            },
            "by_category": {k: v.as_dict() for k, v in sorted(self.by_category.items())},
            "by_difficulty": {k: v.as_dict() for k, v in sorted(self.by_difficulty.items())},
            "by_language": {k: v.as_dict() for k, v in sorted(self.by_language.items())},
            "by_kind": self.by_kind,
            "by_confidence": self.by_confidence,
            "negative_controls": {
                "cases": self.negative_cases,
                "cases_with_false_positive": self.negative_cases_with_fp,
                "false_positive_rate": self.negative_fp_rate,
                "false_positives_per_case": self.fp_per_negative_case,
            },
            "evidence": {
                "findings_checked": self.findings_checked,
                "unsupported_findings": self.unsupported_findings,
                "unsupported_rate": self.unsupported_rate,
            },
            "severity_agreement": {
                "exact": self.severity_exact,
                "within_one_level": self.severity_within_one,
            },
            "latency_ms": {"mean": self.latency_ms_mean, "p95": self.latency_ms_p95},
            "ai": self.ai,
        }


def aggregate(
    system: str,
    description: str,
    results: list[CaseResult],
    labels_by_case: dict[str, dict[str, Any]],
    *,
    bootstrap_samples: int,
    seed: int,
) -> SystemMetrics:
    overall = micro(results)
    m = SystemMetrics(
        system=system,
        description=description,
        cases=len(results),
        labels=sum(len(r.true_positives) + len(r.false_negatives) for r in results),
        predictions=sum(r.predictions for r in results),
        overall=overall,
        ci=bootstrap(results, samples=bootstrap_samples, seed=seed),
    )
    for key, attr in (
        ("by_split", "split"),
        ("by_difficulty", "difficulty"),
        ("by_language", "language"),
    ):
        groups: dict[str, list[CaseResult]] = defaultdict(list)
        for r in results:
            groups[str(getattr(r, attr))].append(r)
        setattr(m, key, {g: micro(rs) for g, rs in groups.items()})
        if key == "by_split":
            m.ci_by_split = {
                g: bootstrap(rs, samples=bootstrap_samples, seed=seed) for g, rs in groups.items()
            }

    categories: dict[str, Counts] = defaultdict(Counts)
    kinds: dict[str, Counter[str]] = defaultdict(Counter)
    confidences: dict[str, Counter[str]] = defaultdict(Counter)
    severity_pairs: list[int] = []
    for r in results:
        for label_id, p in r.true_positives:
            categories[p.category].tp += 1
            kinds[p.kind]["tp"] += 1
            confidences[p.confidence]["tp"] += 1
            label_sev = labels_by_case.get(r.case_id, {}).get(label_id)
            if label_sev is not None:
                severity_pairs.append(
                    abs(SEVERITY_RANK[Severity(p.severity)] - SEVERITY_RANK[Severity(label_sev)])
                )
        for p in r.false_positives:
            categories[p.category].fp += 1
            kinds[p.kind]["fp"] += 1
            confidences[p.confidence]["fp"] += 1
        for p in r.acceptable:
            kinds[p.kind]["acceptable"] += 1
            confidences[p.confidence]["acceptable"] += 1
        for label in r.false_negatives:
            categories[label.category.value].fn += 1
        m.acceptable += len(r.acceptable)
        if r.error:
            m.errors += 1
        m.findings_checked += r.predictions
        m.unsupported_findings += len(r.unsupported)
    m.by_category = dict(categories)
    m.by_kind = {
        k: {**dict(v), "precision": _ratio(v["tp"], v["tp"] + v["fp"])}
        for k, v in sorted(kinds.items())
    }
    m.by_confidence = {
        k: {**dict(v), "precision": _ratio(v["tp"], v["tp"] + v["fp"])}
        for k, v in sorted(confidences.items())
    }
    if severity_pairs:
        m.severity_exact = round(sum(1 for d in severity_pairs if d == 0) / len(severity_pairs), 4)
        m.severity_within_one = round(
            sum(1 for d in severity_pairs if d <= 1) / len(severity_pairs), 4
        )
    negatives = [r for r in results if r.negative]
    m.negative_cases = len(negatives)
    m.negative_cases_with_fp = sum(1 for r in negatives if r.false_positives)
    m.fp_per_negative_case = (
        round(sum(len(r.false_positives) for r in negatives) / len(negatives), 3)
        if negatives
        else None
    )
    durations = sorted(r.duration_ms for r in results)
    if durations:
        m.latency_ms_mean = round(statistics.fmean(durations), 1)
        m.latency_ms_p95 = round(durations[min(len(durations) - 1, int(0.95 * len(durations)))], 1)
    ai_runs = [r.ai for r in results if r.ai]
    if ai_runs:
        total_claims = int(sum(_num(a.get("claims_total")) for a in ai_runs))
        rejected = int(sum(_num(a.get("claims_rejected")) for a in ai_runs))
        reasons: Counter[str] = Counter()
        for a in ai_runs:
            reasons.update(_strings(a.get("rejection_reasons")))
        # AI risks that duplicate a deterministic finding are merged into it as
        # corroboration, so every AI true positive is a label the rules missed.
        ai_tp = sum(1 for r in results for _, p in r.true_positives if p.kind == "ai")
        m.ai = {
            "cases_with_ai": len(ai_runs),
            "completed": sum(1 for a in ai_runs if a.get("status") == "completed"),
            "failed": sum(1 for a in ai_runs if a.get("status") == "failed"),
            "claims_total": total_claims,
            "claims_rejected": rejected,
            "claim_rejection_rate": _ratio(rejected, total_claims),
            "rejection_reasons": dict(reasons.most_common()),
            "notes_applied": int(sum(_num(a.get("notes_applied")) for a in ai_runs)),
            "ai_findings": int(sum(_num(a.get("ai_findings")) for a in ai_runs)),
            "ai_true_positives": ai_tp,
            "mean_model_latency_ms": round(
                statistics.fmean(_num(a.get("latency_ms")) for a in ai_runs), 1
            ),
            "mean_input_tokens": round(
                statistics.fmean(_num(a.get("input_tokens")) for a in ai_runs), 1
            ),
            "mean_output_tokens": round(
                statistics.fmean(_num(a.get("output_tokens")) for a in ai_runs), 1
            ),
            "replay_misses": sum(
                1 for a in ai_runs for e in _strings(a.get("call_errors")) if "replay_miss" in e
            ),
        }
    return m
