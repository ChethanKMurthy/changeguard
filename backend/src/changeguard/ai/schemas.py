"""Structured output contract for the review model.

The JSON schema is deliberately simple (all fields required, no optional
types, closed objects) so that it is accepted by grammar-constrained local
decoding (Ollama), OpenAI strict mode, and Claude structured outputs alike.
Length and content constraints are enforced after parsing, in Python.

Note what the schema does *not* contain: additional risks have no file or
line fields. Their location is derived from the evidence they cite, which
removes a whole class of fabricated locations by construction.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

AI_CATEGORIES = (
    "logic_change",
    "behavior_change",
    "correctness",
    "security",
    "error_handling",
    "concurrency",
    "data_migration",
    "test_gap",
    "breaking_change",
)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AITest(_Closed):
    description: str
    code: str


class FindingNote(_Closed):
    finding_id: str
    explanation: str
    failure_scenario: str
    suggested_test: AITest
    evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]
    uncertainty: str


class AdditionalRisk(_Closed):
    title: str
    category: Literal[
        "logic_change", "behavior_change", "correctness", "security", "error_handling",
        "concurrency", "data_migration", "test_gap", "breaking_change",
    ]  # fmt: skip
    severity: Literal["high", "medium", "low"]
    confidence: Literal["medium", "low"]
    description: str
    failure_scenario: str
    suggested_test: AITest
    evidence_ids: list[str]
    uncertainty: str


class ReviewOutput(_Closed):
    finding_notes: list[FindingNote] = Field(default_factory=list)
    additional_risks: list[AdditionalRisk] = Field(default_factory=list)
    overall_assessment: str = ""


def _strictify(node: Any) -> Any:
    """Make every object closed with all properties required (OpenAI strict mode rules).

    Drops the cosmetic ``title``/``default`` *keywords* of schema nodes, but
    never entries of a ``properties`` mapping (a field may itself be named
    "title").
    """
    if isinstance(node, list):
        return [_strictify(v) for v in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ("title", "default"):
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: _strictify(sub) for name, sub in value.items()}
        else:
            out[key] = _strictify(value)
    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])
    return out


def review_json_schema() -> dict[str, Any]:
    """Inline JSON schema (no $ref) for providers that do not resolve references."""
    schema = ReviewOutput.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(defs[node["$ref"].split("/")[-1]])
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    result: dict[str, Any] = _strictify(inline(schema))
    return result


class OutputParseError(ValueError):
    pass


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_review(text: str) -> ReviewOutput:
    """Parse model text into :class:`ReviewOutput`, tolerating code fences and surrounding prose."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = _FENCE.sub("", candidate).strip()
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise OutputParseError("no JSON object found in model output")
        candidate = candidate[start : end + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise OutputParseError(f"invalid JSON: {exc.msg} at position {exc.pos}") from exc
    try:
        return ReviewOutput.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(p) for p in first["loc"])
        raise OutputParseError(f"schema violation at '{location}': {first['msg']}") from exc
