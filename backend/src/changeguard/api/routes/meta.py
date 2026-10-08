"""Health, capabilities, rule catalog, and evaluation results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from changeguard import REPORT_SCHEMA_VERSION, RULESET_VERSION, __version__
from changeguard.analysis.pipeline import STAGES
from changeguard.analysis.rules.catalog import all_rules
from changeguard.api.deps import get_state
from changeguard.api.schemas import AIStatus, Health, Meta, RuleInfo, StageInfo
from changeguard.api.state import AppState
from changeguard.errors import NotFoundError
from changeguard.languages import STRUCTURAL_LANGUAGES

router = APIRouter(prefix="/api/v1", tags=["meta"])

LINE_LEVEL_TYPES = [
    "SQL",
    "JSON (package.json)",
    "TOML (pyproject.toml)",
    "requirements*.txt",
    ".env files",
    "any text file (secrets, prompt injection)",
]


@router.get("/health", response_model=Health, summary="Liveness probe")
def health() -> Health:
    return Health(version=__version__)


@router.get("/meta", response_model=Meta, summary="Capabilities, limits, and AI provider status")
async def meta(state: Annotated[AppState, Depends(get_state)]) -> Meta:
    settings = state.settings
    health = await run_in_threadpool(state.provider_health)
    ai = AIStatus(
        provider="none",
        configured=False,
        detail="AI disabled (CHANGEGUARD_AI_PROVIDER=none); explanations use rule templates.",
    )
    if health is not None:
        ai = AIStatus(
            provider=health.provider,
            model=health.model,
            configured=health.configured,
            reachable=health.reachable,
            model_available=health.model_available,
            detail=health.detail,
            samples=getattr(state.runner.synthesizer, "samples", 1),
        )
    return Meta(
        version=__version__,
        ruleset_version=RULESET_VERSION,
        report_schema_version=REPORT_SCHEMA_VERSION,
        auth_required=settings.auth_required,
        structural_languages=list(STRUCTURAL_LANGUAGES),
        line_level_file_types=LINE_LEVEL_TYPES,
        input_formats={
            "patch": ["git diff", "git format-patch", "diff -u / diff -ruN"],
            "repository": [".zip", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz"],
            "coverage": ["Cobertura XML", "LCOV", "coverage.py JSON"],
        },
        limits={
            "max_patch_bytes": settings.max_patch_bytes,
            "max_patch_files": settings.max_patch_files,
            "max_archive_bytes": settings.max_archive_bytes,
            "max_archive_uncompressed_bytes": settings.max_archive_uncompressed_bytes,
            "max_source_file_bytes": settings.max_source_file_bytes,
            "max_coverage_bytes": settings.max_coverage_bytes,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
        },
        ai=ai,
        stages=[StageInfo(name=n, label=label) for n, label in STAGES],
    )


@router.get(
    "/rules", response_model=list[RuleInfo], summary="Catalog of every rule ChangeGuard can report"
)
def rules() -> list[RuleInfo]:
    return [RuleInfo.model_validate(r) for r in all_rules()]


def _evaluation_path() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "eval" / "reports" / "latest.json"
        if candidate.exists():
            return candidate
    return None


@router.get("/evaluation", summary="Latest offline evaluation report (if bundled)")
def evaluation() -> dict[str, Any]:
    path = _evaluation_path()
    if path is None:
        raise NotFoundError(
            "no evaluation report is bundled with this deployment; run `changeguard eval`"
        )
    data: dict[str, Any] = json.loads(path.read_text())
    return data
