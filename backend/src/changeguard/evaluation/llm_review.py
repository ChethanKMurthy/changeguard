"""Model-only review baseline: "why not just ask a model to review the change?"

The model receives what a human reviewer would have: the full diff, every file
of the repository after the change (with line numbers), and the coverage
report when the case has one. It is told the category taxonomy the labels use
and answers with findings in a closed JSON schema. Nothing it says is checked
against the evidence; its findings are scored exactly as reported, with the
same matching as every other system.

Responses go through the same record/replay layer as the AI synthesis, so CI
recomputes these numbers from committed recordings without calling a model.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from changeguard.ai.prompts import PromptTemplate, load_prompt
from changeguard.ai.providers.base import GenerationRequest, LLMProvider, ProviderError
from changeguard.evaluation.dataset import Case
from changeguard.evaluation.matching import Prediction
from changeguard.evaluation.systems import SystemOutput
from changeguard.report.models import Category, Severity

MAX_REPOSITORY_CHARS = 600_000
MAX_COVERAGE_CHARS = 100_000

LLM_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["file", "start_line", "end_line", "category", "severity", "title"],
                "properties": {
                    "file": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "category": {"type": "string", "enum": [c.value for c in Category]},
                    "severity": {"type": "string", "enum": [s.value for s in Severity]},
                    "title": {"type": "string"},
                },
            },
        }
    },
}

_CATEGORIES = {c.value for c in Category}
_SEVERITIES = {s.value for s in Severity}


def render_repository(case: Case) -> str:
    """Every file of the head revision, numbered like an editor shows it."""
    if case.mode == "diff_only":
        return "(not provided: only the diff is available for this change)"
    assert case.directory is not None
    head = case.directory / "head"
    parts: list[str] = []
    for path in sorted(p for p in head.rglob("*") if p.is_file()):
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        numbered = "\n".join(f"{i:>5} | {line}" for i, line in enumerate(text.splitlines(), 1))
        parts.append(f"### {path.relative_to(head).as_posix()}\n{numbered}")
    rendered = "\n\n".join(parts)
    if len(rendered) > MAX_REPOSITORY_CHARS:
        rendered = rendered[:MAX_REPOSITORY_CHARS] + "\n(truncated: repository exceeds the budget)"
    return rendered or "(empty repository)"


def render_coverage(case: Case) -> str:
    data = case.coverage_bytes()
    if data is None:
        return "(no coverage report for this change)"
    text = data.decode("utf-8", errors="replace")
    return text[:MAX_COVERAGE_CHARS]


def parse_findings(text: str) -> list[dict[str, Any]]:
    """Findings from a model response; malformed entries are dropped, not repaired."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is None:
            raise ProviderError("bad_response", "response is not JSON") from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ProviderError("bad_response", "response is not JSON") from exc
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ProviderError("bad_response", "response has no findings list")
    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("category") not in _CATEGORIES or not isinstance(item.get("file"), str):
            continue
        findings.append(item)
    return findings


def _line(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _path(value: str) -> str:
    value = value.strip()
    for prefix in ("a/", "b/", "./"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value


class LLMReviewBaseline:
    def __init__(self, provider: LLMProvider, *, label: str) -> None:
        self.provider = provider
        self.prompt: PromptTemplate = load_prompt("llm_review", "v1")
        self.name = f"baseline-llm-review:{label}"
        self.description = f"The model alone reviews the whole change ({label}), unverified"

    def request(self, case: Case) -> GenerationRequest:
        return GenerationRequest(
            system=self.prompt.system,
            user=self.prompt.render_user(
                diff=case.patch_text(),
                repository=render_repository(case),
                coverage=render_coverage(case),
            ),
            schema=LLM_REVIEW_SCHEMA,
            schema_name="llm_review",
            max_output_tokens=8192,
        )

    def run(self, case: Case) -> SystemOutput:
        started = time.perf_counter()
        try:
            result = self.provider.generate(self.request(case))
            findings = parse_findings(result.text)
        except ProviderError as exc:
            error = f"{exc.kind}: {exc.message}"
            return SystemOutput(
                [],
                None,
                (time.perf_counter() - started) * 1000,
                error,
                ai={"status": "failed", "calls": 1, "call_errors": [error]},
            )
        predictions = []
        for n, f in enumerate(findings):
            start = _line(f.get("start_line"))
            end = _line(f.get("end_line")) or start
            severity = f.get("severity") if f.get("severity") in _SEVERITIES else "medium"
            predictions.append(
                Prediction(
                    id=f"L{n}",
                    rule_id=f"LLM-{f['category']}",
                    category=f["category"],
                    kind="ai",
                    severity=str(severity),
                    confidence="medium",
                    file=_path(f["file"]),
                    start_line=start,
                    end_line=end,
                    title=str(f.get("title", ""))[:300],
                )
            )
        ai: dict[str, object] = {
            "status": "completed",
            "model": result.model,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens or 0,
            "output_tokens": result.output_tokens or 0,
            "findings": len(predictions),
            "calls": 1,
        }
        return SystemOutput(predictions, None, (time.perf_counter() - started) * 1000, ai=ai)
