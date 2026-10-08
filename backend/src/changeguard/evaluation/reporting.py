"""Write evaluation results (JSON + Markdown) and compare against a committed baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from changeguard.evaluation.runner import EvaluationRun, case_details

LIMITATIONS = [
    "The dataset is small and synthetic: each case was written for this project to exercise a specific risk "
    "pattern. Results measure agreement with the labelling guideline on these cases, not effectiveness on real "
    "repositories.",
    "The rules and the dev-split cases were written by the same author, so dev-split numbers are optimistic by "
    "construction. The holdout splits were written after the ruleset was frozen; their first runs, recorded "
    "before any holdout-informed change, are the more honest estimate, but they share the same author and style.",
    "Bootstrap intervals resample cases; with this few cases they are wide and should be read as rough bounds.",
    "Labels mark where a reviewer should look, not whether the change causes a production incident. Nothing "
    "here estimates incident probability.",
    "AI metrics measure grounding (cited evidence exists and matches) and agreement with labels. They do not "
    "measure the correctness or usefulness of explanations, which would require human rating.",
]


def _holdout_history() -> dict[str, Any] | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "eval" / "reports" / "holdout-history.json"
        if candidate.exists():
            loaded: dict[str, Any] = json.loads(candidate.read_text())
            return loaded
    return None


def run_to_json(run: EvaluationRun) -> dict[str, Any]:
    return {
        "holdout_history": _holdout_history(),
        "manifest": run.manifest,
        "systems": [r.metrics.as_dict() for r in run.runs],
        "cases": {r.system.name: case_details(r) for r in run.runs},
        "misses": _misses(run),
        "limitations": LIMITATIONS,
    }


def _misses(run: EvaluationRun) -> list[dict[str, Any]]:
    """Labels the primary system missed, with what the case tests and which other systems found them."""
    if not run.runs:
        return []
    by_id = {c.id: c for c in run.cases}
    found_by: dict[tuple[str, str], list[str]] = {}
    for other in run.runs[1:]:
        for detail in case_details(other):
            for label_id in detail["matched"]:
                found_by.setdefault((detail["case"], label_id), []).append(other.system.name)
    misses: list[dict[str, Any]] = []
    for detail in case_details(run.runs[0]):
        case = by_id.get(detail["case"])
        if case is None:
            continue
        labels = {label.id: label for label in case.expected}
        for label_id in detail["missed"]:
            label = labels.get(label_id)
            if label is None:
                continue
            misses.append(
                {
                    "case": case.id,
                    "title": case.title,
                    "split": case.split,
                    "description": case.description,
                    "label": label_id,
                    "category": str(getattr(label.category, "value", label.category)),
                    "file": label.file,
                    "lines": list(label.lines) if label.lines else None,
                    "note": label.note,
                    "found_by": found_by.get((case.id, label_id), []),
                }
            )
    return misses


def _fmt(value: float | None, pct: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%" if pct else f"{value:.3f}"


def _ci(ci: list[float | None]) -> str:
    lo, hi = ci
    if lo is None or hi is None:
        return ""
    return f" [{lo * 100:.0f}–{hi * 100:.0f}]"


def run_to_markdown(data: dict[str, Any]) -> str:
    m = data["manifest"]
    lines = [
        "# ChangeGuard evaluation report",
        "",
        f"Generated {m['generated_at']} · ChangeGuard {m['changeguard_version']} · ruleset {m['ruleset_version']}"
        + (f" · commit `{m['git_sha']}`" if m.get("git_sha") else ""),
        "",
        f"Dataset: {m['cases']} cases ({', '.join(f'{n} {split}' for split, n in m['splits'].items())}), "
        f"{m['labels']} labels, {m['negative_controls']} negative controls · sha256 `{m['dataset_sha256'][:16]}…`",
        "",
        f"Matching: {m['matching']['rule']}. Confidence intervals: 95% percentile bootstrap over cases "
        f"({m['bootstrap']['samples']} resamples, seed {m['bootstrap']['seed']}).",
        "",
        "## Systems",
        "",
        "| System | Precision [95% CI] | Recall [95% CI] | F1 | Neg. control FP rate | Unsupported evidence |",
        "|---|---|---|---|---|---|",
    ]
    for s in data["systems"]:
        o = s["overall"]
        neg = s["negative_controls"]
        ev = s["evidence"]
        unsupported = (
            "—"
            if s["system"].startswith("baseline")
            else f"{ev['unsupported_findings']}/{ev['findings_checked']}"
        )
        lines.append(
            f"| `{s['system']}` — {s['description']} | {_fmt(o['precision'])}{_ci(s['ci95']['precision'])} | "
            f"{_fmt(o['recall'])}{_ci(s['ci95']['recall'])} | {_fmt(o['f1'])} | "
            f"{_fmt(neg['false_positive_rate'])} ({neg['cases_with_false_positive']}/{neg['cases']}) | {unsupported} |"
        )
    history = data.get("holdout_history")
    if history:
        lines += [
            "",
            "## Clean holdout estimates (first run, before any holdout-informed change)",
            "",
            "| Split | Ruleset | System | Precision | Recall | F1 | Neg. control FP rate |",
            "|---|---|---|---|---|---|---|",
        ]
        for run in history["runs"]:
            for name, m_ in run["systems"].items():
                lines.append(
                    f"| {run['split']} | {run['ruleset']} | `{name}` | {_fmt(m_['precision'])} | "
                    f"{_fmt(m_['recall'])} | {_fmt(m_['f1'])} | {_fmt(m_['negative_fp_rate'])} |"
                )
        lines += [
            "",
            "Changes made after each first run (later numbers on that split are optimistic):",
            "",
        ]
        lines += [
            f"- **{run['split']}**: " + " ".join(run["changes_after"]) for run in history["runs"]
        ]
    primary = data["systems"][0]
    lines += [
        "",
        f"## `{primary['system']}` by split",
        "",
        "| Split | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|---|",
    ]
    for split, c in primary["by_split"].items():
        lines.append(
            f"| {split} | {c['tp']} | {c['fp']} | {c['fn']} | {_fmt(c['precision'])} | {_fmt(c['recall'])} | {_fmt(c['f1'])} |"
        )
    lines += [
        "",
        f"## `{primary['system']}` by category",
        "",
        "| Category | TP | FP | FN | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for cat, c in primary["by_category"].items():
        lines.append(
            f"| {cat} | {c['tp']} | {c['fp']} | {c['fn']} | {_fmt(c['precision'])} | {_fmt(c['recall'])} |"
        )
    lines += [
        "",
        f"## `{primary['system']}` precision by provenance and confidence",
        "",
        "| Group | TP | FP | Acceptable | Precision |",
        "|---|---|---|---|---|",
    ]
    for group, rows in (("kind", primary["by_kind"]), ("confidence", primary["by_confidence"])):
        for key, c in rows.items():
            lines.append(
                f"| {group}: {key} | {c.get('tp', 0)} | {c.get('fp', 0)} | {c.get('acceptable', 0)} | {_fmt(c.get('precision'))} |"
            )
    sev = primary["severity_agreement"]
    lines += [
        "",
        f"Severity agreement on matched findings: exact {_fmt(sev['exact'])}, within one level {_fmt(sev['within_one_level'])}.",
        "",
    ]
    ai_systems = [s for s in data["systems"] if s.get("ai")]
    if ai_systems:
        lines += ["## AI synthesis", ""]
        for s in ai_systems:
            a = s["ai"]
            lines += [
                f"### `{s['system']}`",
                "",
                f"- Model calls completed for {a['completed']}/{a['cases_with_ai']} cases ({a['failed']} failed, {a.get('replay_misses', 0)} replay misses).",
                f"- Claims: {a['claims_total']} made, {a['claims_rejected']} rejected by grounding verification (rejection rate {_fmt(a['claim_rejection_rate'])}).",
                "- Rejection reasons: "
                + (", ".join(f"{k} × {v}" for k, v in a["rejection_reasons"].items()) or "none"),
                f"- Explanations attached to deterministic findings: {a['notes_applied']}; AI-only findings: {a['ai_findings']} ({a['ai_true_positives']} matched a label).",
                f"- Mean model latency {a['mean_model_latency_ms'] / 1000:.1f}s; mean tokens in/out {a['mean_input_tokens']:.0f}/{a['mean_output_tokens']:.0f}.",
                "",
            ]
    lines += ["## Per-case results", ""]
    for name, cases in data["cases"].items():
        if name != primary["system"]:
            continue
        lines += ["| Case | Split | Matched | Missed | False positives |", "|---|---|---|---|---|"]
        for c in cases:
            lines.append(
                f"| `{c['case']}`{' (negative)' if c['negative'] else ''} | {c['split']} | {', '.join(c['matched']) or '—'} | "
                f"{', '.join(c['missed']) or '—'} | {', '.join(c['false_positives']) or '—'} |"
            )
    lines += (
        ["", "## What this evaluation cannot establish", ""]
        + [f"- {item}" for item in data["limitations"]]
        + [""]
    )
    return "\n".join(lines)


_FRONTEND_KEYS = (
    "system", "description", "cases", "labels", "predictions", "overall", "ci95", "by_split", "ci95_by_split", "by_category",
    "by_kind", "by_confidence", "negative_controls", "evidence", "severity_agreement", "latency_ms", "ai",
)  # fmt: skip


def frontend_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Trimmed view for the web UI's evaluation page."""
    return {
        "holdout_history": data.get("holdout_history"),
        "manifest": data["manifest"],
        "systems": [{k: s[k] for k in _FRONTEND_KEYS} for s in data["systems"]],
        "cases": data["cases"].get(data["systems"][0]["system"], []),
        "misses": data.get("misses", []),
        "limitations": data["limitations"],
    }


@dataclass(slots=True)
class RegressionResult:
    passed: bool
    messages: list[str] = field(default_factory=list)


def compare_to_baseline(
    current: dict[str, Any], baseline: dict[str, Any], *, tolerance: float = 0.02
) -> RegressionResult:
    """Fail when headline metrics drop beyond ``tolerance`` or a previously matched label is now missed."""
    result = RegressionResult(True)
    cur = {s["system"]: s for s in current["systems"]}
    for base in baseline["systems"]:
        name = base["system"]
        if name not in cur:
            continue
        now = cur[name]
        for metric in ("precision", "recall", "f1"):
            before, after = base["overall"][metric], now["overall"][metric]
            if before is not None and after is not None and after < before - tolerance:
                result.passed = False
                result.messages.append(f"{name}: {metric} dropped {before:.3f} → {after:.3f}")
        before_fp = base["negative_controls"]["false_positive_rate"] or 0.0
        after_fp = now["negative_controls"]["false_positive_rate"] or 0.0
        if after_fp > before_fp + 0.05:
            result.passed = False
            result.messages.append(
                f"{name}: negative-control false-positive rate rose {before_fp:.3f} → {after_fp:.3f}"
            )
        if now["evidence"]["unsupported_findings"] > base["evidence"]["unsupported_findings"]:
            result.passed = False
            result.messages.append(
                f"{name}: unsupported-evidence findings rose to {now['evidence']['unsupported_findings']}"
            )
        base_cases = {c["case"]: c for c in baseline["cases"].get(name, [])}
        for c in current["cases"].get(name, []):
            prev = base_cases.get(c["case"])
            if prev is None:
                continue
            lost = sorted(set(prev["matched"]) - set(c["matched"]))
            if lost:
                result.passed = False
                result.messages.append(f"{name}: {c['case']} no longer finds {', '.join(lost)}")
            new_fp = sorted(set(c["false_positives"]) - set(prev["false_positives"]))
            if new_fp:
                result.messages.append(
                    f"{name}: {c['case']} new false positive(s): {', '.join(new_fp)} (warning)"
                )
    if result.passed and not result.messages:
        result.messages.append("no regressions against the baseline")
    return result


def write_outputs(
    data: dict[str, Any], out_dir: Path, *, frontend_path: Path | None = None
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    json_path = out_dir / "latest.json"
    json_path.write_text(json.dumps(data, indent=2) + "\n")
    written.append(json_path)
    md_path = out_dir / "latest.md"
    md_path.write_text(run_to_markdown(data))
    written.append(md_path)
    if frontend_path is not None:
        frontend_path.parent.mkdir(parents=True, exist_ok=True)
        frontend_path.write_text(json.dumps(frontend_summary(data), indent=2) + "\n")
        written.append(frontend_path)
    return written
