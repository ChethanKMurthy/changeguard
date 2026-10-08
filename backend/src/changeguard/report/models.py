"""Report schema (public contract for the API, exports, and the web UI).

Design rules encoded here:

* Severity and confidence are separate, categorical fields. There is no
  blended numeric "risk score" presented as a probability.
* Every finding states its provenance (``kind``): deterministic analysis,
  heuristic rule, or AI-generated.
* Findings reference evidence by ID. Evidence is produced only by analysis of
  the uploaded inputs; AI output can cite evidence but never create it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


CONFIDENCE_RANK: dict[Confidence, int] = {
    Confidence.HIGH: 2,
    Confidence.MEDIUM: 1,
    Confidence.LOW: 0,
}


class FindingKind(StrEnum):
    DETERMINISTIC = "deterministic"
    HEURISTIC = "heuristic"
    AI = "ai"


class Category(StrEnum):
    BREAKING_CHANGE = "breaking_change"
    BEHAVIOR_CHANGE = "behavior_change"
    LOGIC_CHANGE = "logic_change"
    CORRECTNESS = "correctness"
    SYNTAX_ERROR = "syntax_error"
    SECURITY = "security"
    SECRET_EXPOSURE = "secret_exposure"  # noqa: S105 - category name, not a credential
    ERROR_HANDLING = "error_handling"
    CONCURRENCY = "concurrency"
    TEST_GAP = "test_gap"
    COVERAGE_GAP = "coverage_gap"
    TEST_INTEGRITY = "test_integrity"
    DATA_MIGRATION = "data_migration"
    DEPENDENCY = "dependency"
    COMPLEXITY = "complexity"
    DEBUG_ARTIFACT = "debug_artifact"
    CONFIGURATION = "configuration"
    TYPE_SAFETY = "type_safety"
    PROMPT_INJECTION = "prompt_injection"


class EvidenceType(StrEnum):
    DIFF_HUNK = "diff_hunk"
    CODE = "code"
    CALL_SITE = "call_site"
    SIGNATURE_CHANGE = "signature_change"
    STATIC_DIAGNOSTIC = "static_diagnostic"
    PATTERN_MATCH = "pattern_match"
    TEST_REFERENCE = "test_reference"
    COVERAGE = "coverage"
    METRIC = "metric"
    DEPENDENCY = "dependency"
    SYMBOL_REFERENCE = "symbol_reference"


Side = Literal["head", "base"]


class _Model(BaseModel):
    # Response fields with defaults are always serialised, so the OpenAPI output
    # schema marks them required (generated client types stay non-optional).
    model_config = ConfigDict(
        extra="forbid", use_enum_values=False, json_schema_serialization_defaults_required=True
    )


class Evidence(_Model):
    id: str = Field(description="Stable identifier within a report, e.g. 'E3'.")
    type: EvidenceType
    title: str
    file: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    side: Side | None = None
    excerpt: str | None = Field(
        default=None, description="Verbatim source excerpt (untrusted content)."
    )
    excerpt_start_line: int | None = None
    highlight_lines: list[int] = Field(default_factory=list)
    source: str = Field(
        description="What produced this evidence (diff, repository snapshot, ruff, coverage report, ...)."
    )
    data: dict[str, Any] = Field(default_factory=dict)


class Location(_Model):
    file: str
    start_line: int | None = None
    end_line: int | None = None
    side: Side = "head"
    symbol: str | None = None


class SuggestedTest(_Model):
    description: str
    kind: Literal["unit", "integration", "regression", "manual", "static", "review"] = "unit"
    code: str | None = None
    language: str | None = None
    source: Literal["template", "ai"] = "template"


class Explanation(_Model):
    text: str
    source: Literal["template", "ai"] = "template"
    model: str | None = None
    uncertainty: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class AIAnalysis(_Model):
    """Model-generated analysis attached to a finding. Never replaces deterministic fields."""

    explanation: str
    failure_scenario: str
    suggested_test: SuggestedTest
    confidence: Confidence
    uncertainty: str
    evidence_ids: list[str]
    model: str
    verified: bool = True
    support: float | None = Field(
        default=None,
        description="Share of self-consistency samples that agreed (when sampling > 1).",
    )


class Finding(_Model):
    id: str
    rule_id: str
    category: Category
    kind: FindingKind
    title: str
    description: str
    severity: Severity
    confidence: Confidence
    location: Location
    evidence_ids: list[str]
    failure_scenario: str
    suggested_test: SuggestedTest
    explanation: Explanation
    related_symbols: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    corroborated_by: list[str] = Field(default_factory=list)
    ai_analysis: AIAnalysis | None = None


class HunkLine(_Model):
    kind: Literal["context", "add", "del"]
    content: str
    old: int | None = None
    new: int | None = None


class HunkModel(_Model):
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str = ""
    lines: list[HunkLine]


class FileCoverageSummary(_Model):
    covered: int
    executable: int
    uncovered_lines: list[int] = Field(default_factory=list)


class FileSummary(_Model):
    path: str
    old_path: str | None = None
    status: Literal["added", "deleted", "modified", "renamed", "copied"]
    language: str
    structural_support: bool
    is_test: bool
    is_binary: bool = False
    additions: int
    deletions: int
    full_context: bool
    hunks: list[HunkModel] = Field(default_factory=list)
    changed_symbols: list[str] = Field(default_factory=list)
    coverage: FileCoverageSummary | None = None


class SymbolChangeSummary(_Model):
    file: str
    qualname: str
    kind: str
    change: Literal["added", "removed", "modified", "renamed"]
    renamed_from: str | None = None
    signature_before: str | None = None
    signature_after: str | None = None
    breaking: bool = False
    start_line: int | None = None
    end_line: int | None = None
    call_sites: int = 0
    call_site_files: int = 0
    incompatible_call_sites: int = 0
    related_tests: int = 0
    complexity_before: int | None = None
    complexity_after: int | None = None
    approximate: bool = False


StageStatus = Literal["ok", "skipped", "warning", "failed"]


class StageResult(_Model):
    name: str
    label: str
    status: StageStatus
    duration_ms: float
    summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ModelCallTrace(_Model):
    call_id: str
    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    prompt_sha256: str
    request_sha256: str
    started_at: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_hit: bool = False
    attempts: int = 1
    status: Literal["ok", "invalid_output", "timeout", "error"]
    error: str | None = None


class RejectedClaim(_Model):
    target: str = Field(
        description="What the claim was attached to (finding id or 'additional_risk')."
    )
    summary: str
    reasons: list[str]


class AIVerification(_Model):
    claims_total: int = 0
    claims_accepted: int = 0
    claims_rejected: int = 0
    rejected: list[RejectedClaim] = Field(default_factory=list)


class AISummary(_Model):
    status: Literal["disabled", "completed", "failed", "skipped"]
    provider: str | None = None
    model: str | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt_sha256: str | None = None
    samples: int = 1
    context_chars: int | None = None
    context_truncated: bool = False
    calls: list[ModelCallTrace] = Field(default_factory=list)
    verification: AIVerification | None = None
    overall_assessment: str | None = None
    note: str | None = None


class ReviewPriority(_Model):
    level: Literal["block", "high", "elevated", "routine"]
    rationale: str
    triggered_by: list[str] = Field(default_factory=list)


class PatchCoverage(_Model):
    covered: int
    executable: int
    percent: float | None


class Summary(_Model):
    files_changed: int
    additions: int
    deletions: int
    languages: list[str]
    findings_total: int
    by_severity: dict[str, int]
    by_kind: dict[str, int]
    by_category: dict[str, int]
    review_priority: ReviewPriority
    changed_symbols: int
    breaking_symbols: int
    symbols_with_tests: int
    testable_symbols: int
    patch_coverage: PatchCoverage | None = None


class InputSummary(_Model):
    patch_sha256: str
    patch_format: str
    subject: str | None = None
    mode: Literal["full_context", "diff_only"]
    has_snapshot: bool
    snapshot: dict[str, Any] | None = None
    has_coverage: bool
    coverage_format: str | None = None


class Report(_Model):
    schema_version: str
    analysis_id: str
    created_at: str
    title: str
    engine_version: str
    ruleset_version: str
    input: InputSummary
    summary: Summary
    findings: list[Finding]
    evidence: list[Evidence]
    files: list[FileSummary]
    symbols: list[SymbolChangeSummary]
    pipeline: list[StageResult]
    ai: AISummary
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.evidence}
