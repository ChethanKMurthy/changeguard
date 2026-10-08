"""HTTP response models (the API contract; the frontend's TypeScript types are generated from these)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from changeguard.report.models import Category, FindingKind, Report, Severity

AnalysisStatus = Literal["queued", "running", "completed", "failed"]


class _Out(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Problem(_Out):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class AnalysisLinks(_Out):
    self: str
    events: str
    export_json: str
    export_markdown: str
    export_sarif: str


class HistorySummary(_Out):
    review_priority: str | None = None
    findings_total: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_kind: dict[str, int] = Field(default_factory=dict)
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    languages: list[str] = Field(default_factory=list)
    mode: str | None = None
    ai_status: str | None = None
    patch_coverage: float | None = None


class AnalysisError(_Out):
    code: str
    message: str


class AnalysisSummary(_Out):
    id: str
    created_at: str
    updated_at: str
    status: AnalysisStatus
    title: str
    source: Literal["upload", "paste", "sample", "cli"]
    sample_id: str | None = None
    ai_requested: bool = False
    duration_ms: float | None = None
    summary: HistorySummary | None = None
    error: AnalysisError | None = None
    links: AnalysisLinks


class AnalysisDetail(AnalysisSummary):
    report: Report | None = None


class AnalysisList(_Out):
    items: list[AnalysisSummary]
    total: int
    limit: int
    offset: int


class SampleSummary(_Out):
    id: str
    title: str
    tagline: str
    description: str
    language: str
    tags: list[str]
    highlights: list[str]
    files: list[str]
    has_coverage: bool
    synthetic: bool = True


class SampleDetail(SampleSummary):
    patch: str
    coverage_filename: str | None = None


class AIStatus(_Out):
    provider: str
    model: str | None = None
    configured: bool
    reachable: bool | None = None
    model_available: bool | None = None
    detail: str | None = None
    samples: int = 1


class StageInfo(_Out):
    name: str
    label: str


class Meta(_Out):
    name: str = "ChangeGuard"
    version: str
    ruleset_version: str
    report_schema_version: str
    auth_required: bool
    structural_languages: list[str]
    line_level_file_types: list[str]
    input_formats: dict[str, list[str]]
    limits: dict[str, int]
    ai: AIStatus
    stages: list[StageInfo]


class RuleInfo(_Out):
    id: str
    title: str
    category: Category
    kind: FindingKind
    default_severity: Severity
    rationale: str
    languages: list[str]
    source: Literal["changeguard", "ruff"]


class Health(_Out):
    status: Literal["ok"] = "ok"
    version: str
