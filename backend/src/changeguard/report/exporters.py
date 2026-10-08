"""Report exporters: JSON, Markdown (PR comments), and SARIF 2.1.0 (code scanning).

Repository content is untrusted, including inside exports: code excerpts are
written into fenced blocks whose fence is longer than any backtick run in the
content, and plain-text fields are HTML-escaped outside code spans.
"""

from __future__ import annotations

import json
import re
from typing import Any

from changeguard import __version__
from changeguard.analysis.rules.catalog import describe_rule
from changeguard.report.models import Evidence, Finding, FindingKind, Report, Severity

_SEVERITY_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}
_LANG_HINT = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".jsx": "jsx",
    ".sql": "sql", ".json": "json", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml",
}  # fmt: skip
PROJECT_URL = "https://github.com/changeguard/changeguard"


def to_json(report: Report) -> str:
    return report.model_dump_json(indent=2)


# -- Markdown -------------------------------------------------------------------------


def _fence(text: str, lang: str = "") -> str:
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


def _md(text: str) -> str:
    """Escape HTML outside inline code spans (backtick-delimited)."""
    parts = re.split(r"(`[^`\n]*`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(part)
        else:
            out.append(part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return "".join(out)


def _lang(path: str | None) -> str:
    if not path:
        return ""
    for ext, lang in _LANG_HINT.items():
        if path.endswith(ext):
            return lang
    return ""


def _location(f: Finding) -> str:
    loc = f.location
    where = loc.file
    if loc.start_line:
        where += f":{loc.start_line}" + (
            f"-{loc.end_line}" if loc.end_line and loc.end_line != loc.start_line else ""
        )
    return f"`{where}`" + (" (removed code)" if loc.side == "base" else "")


def _evidence_md(e: Evidence) -> list[str]:
    where = ""
    if e.file:
        where = f" — `{e.file}" + (f":{e.start_line}" if e.start_line else "") + "`"
    lines = [f"- **{e.id}** {_md(e.title)}{where} _(source: {_md(e.source)})_"]
    if e.excerpt:
        lines.append("")
        lines.append(
            _indent(
                _fence(
                    e.excerpt,
                    "diff"
                    if e.type.value == "diff_hunk" and e.excerpt.startswith(("-", "+"))
                    else _lang(e.file),
                ),
                2,
            )
        )
    return lines


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.split("\n"))


def to_markdown(report: Report, *, include_evidence: bool = True, max_findings: int = 50) -> str:
    s = report.summary
    kinds = s.by_kind
    lines = [
        f"# ChangeGuard report — {_md(report.title)}",
        "",
        f"> **Review priority: {s.review_priority.level.upper()}** — {_md(s.review_priority.rationale)}",
        "> Severity and confidence are categorical rule judgements, not probabilities of failure.",
        "",
        "| | |",
        "|---|---|",
        f"| Files changed | {s.files_changed} (+{s.additions} −{s.deletions}) — {', '.join(s.languages)} |",
        f"| Mode | {'Full context (repository snapshot)' if report.input.mode == 'full_context' else 'Diff only'} |",
        f"| Findings | {s.findings_total} — deterministic {kinds.get('deterministic', 0)} · heuristic {kinds.get('heuristic', 0)} · AI {kinds.get('ai', 0)} |",
        f"| Changed symbols | {s.changed_symbols} ({s.breaking_symbols} with breaking signature changes) |",
    ]
    if s.patch_coverage and s.patch_coverage.executable:
        pc = s.patch_coverage
        lines.append(
            f"| Patch coverage | {pc.percent}% ({pc.covered}/{pc.executable} changed executable lines, from uploaded report) |"
        )
    ai = report.ai
    ai_line = f"{ai.status}" + (f" — {ai.provider} / {ai.model}" if ai.model else "")
    if ai.verification:
        v = ai.verification
        ai_line += f"; {v.claims_accepted}/{v.claims_total} claims passed grounding checks"
    lines.append(f"| AI synthesis | {_md(ai_line)} |")
    lines.append(
        f"| Engine | ChangeGuard {report.engine_version} · ruleset {report.ruleset_version} · report schema {report.schema_version} |"
    )
    lines.append("")

    evidence = report.evidence_by_id()
    if report.findings:
        lines.append("## Findings")
        lines.append("")
    for index, f in enumerate(report.findings[:max_findings], start=1):
        badge = {"deterministic": "deterministic", "heuristic": "heuristic", "ai": "AI-generated"}[
            f.kind.value
        ]
        lines.append(f"### {index}. [{f.severity.value.upper()}] {_md(f.title)}")
        meta = f"`{f.rule_id}` · {badge} · confidence {f.confidence.value} · {_location(f)}"
        if f.corroborated_by:
            meta += " · corroborated by " + ", ".join(f"`{r}`" for r in f.corroborated_by)
        lines += [meta, "", _md(f.description), "", f"**Why it matters.** {_md(f.explanation.text)}", "",
                  f"**Failure scenario.** {_md(f.failure_scenario)}", ""]  # fmt: skip
        if include_evidence:
            lines.append("**Evidence**")
            lines.append("")
            for eid in f.evidence_ids:
                if eid in evidence:
                    lines += _evidence_md(evidence[eid])
            lines.append("")
        lines.append(
            f"**Suggested {f.suggested_test.kind} check.** {_md(f.suggested_test.description)}"
        )
        if f.suggested_test.code:
            lines += ["", _fence(f.suggested_test.code, f.suggested_test.language or "")]
        lines.append("")
        if f.ai_analysis and f.kind is not FindingKind.AI:
            a = f.ai_analysis
            lines += [
                f"<details><summary>AI analysis ({_md(a.model)}, passed grounding checks, confidence {a.confidence.value})</summary>",
                "",
                _md(a.explanation),
                "",
                f"_Failure scenario:_ {_md(a.failure_scenario)}",
                "",
                f"_Uncertainty:_ {_md(a.uncertainty)}",
                "",
                "</details>",
                "",
            ]
    if len(report.findings) > max_findings:
        lines.append(
            f"_…and {len(report.findings) - max_findings} more finding(s); see the JSON report._"
        )
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        lines += [f"- {_md(w)}" for w in report.warnings]
        lines.append("")
    lines.append("## Limitations")
    lines += [f"- {_md(item)}" for item in report.limitations]
    lines.append("")
    lines.append(
        f"<sub>Generated by ChangeGuard {report.engine_version} · analysis `{report.analysis_id}` · {report.created_at}</sub>"
    )
    return "\n".join(lines) + "\n"


# -- SARIF ------------------------------------------------------------------------------


def to_sarif(report: Report) -> dict[str, Any]:
    rule_ids = list(dict.fromkeys(f.rule_id for f in report.findings))
    rules = []
    for rid in rule_ids:
        meta = describe_rule(rid) or {"title": rid, "rationale": "", "category": "", "kind": "ai"}
        sample = next(f for f in report.findings if f.rule_id == rid)
        rules.append(
            {
                "id": rid,
                "name": re.sub(r"[^A-Za-z0-9]", "", str(meta["title"]).title()) or rid,
                "shortDescription": {"text": str(meta["title"])},
                "fullDescription": {"text": str(meta.get("rationale") or meta["title"])},
                "defaultConfiguration": {"level": _SEVERITY_LEVEL[sample.severity]},
                "properties": {"category": sample.category.value, "provenance": sample.kind.value},
            }
        )
    evidence = report.evidence_by_id()
    results = []
    for f in report.findings:
        location: dict[str, Any] = {
            "physicalLocation": {"artifactLocation": {"uri": f.location.file}}
        }
        if f.location.start_line:
            location["physicalLocation"]["region"] = {
                "startLine": f.location.start_line,
                "endLine": f.location.end_line or f.location.start_line,
            }
        related = []
        for i, eid in enumerate(f.evidence_ids):
            e = evidence.get(eid)
            if e is None or not e.file:
                continue
            rel: dict[str, Any] = {
                "id": i,
                "message": {"text": f"{e.id}: {e.title}"},
                "physicalLocation": {"artifactLocation": {"uri": e.file}},
            }
            if e.start_line:
                rel["physicalLocation"]["region"] = {
                    "startLine": e.start_line,
                    "endLine": e.end_line or e.start_line,
                }
            related.append(rel)
        results.append(
            {
                "ruleId": f.rule_id,
                "ruleIndex": rule_ids.index(f.rule_id),
                "level": _SEVERITY_LEVEL[f.severity],
                "message": {
                    "text": f"{f.title}. {f.description} Failure scenario: {f.failure_scenario}"
                },
                "locations": [location],
                "relatedLocations": related,
                "partialFingerprints": {"changeguardFindingId/v1": f.id},
                "properties": {
                    "severity": f.severity.value,
                    "confidence": f.confidence.value,
                    "provenance": f.kind.value,
                    "category": f.category.value,
                    "suggestedTest": f.suggested_test.description,
                    "side": f.location.side,
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ChangeGuard",
                        "version": __version__,
                        "semanticVersion": __version__,
                        "informationUri": PROJECT_URL,
                        "rules": rules,
                    }
                },
                "invocations": [{"executionSuccessful": True}],
                "results": results,
                "properties": {
                    "reviewPriority": report.summary.review_priority.level,
                    "rulesetVersion": report.ruleset_version,
                    "analysisId": report.analysis_id,
                },
            }
        ],
    }


def to_sarif_json(report: Report) -> str:
    return json.dumps(to_sarif(report), indent=2)
