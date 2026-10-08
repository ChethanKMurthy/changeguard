"""Sample scenarios (clearly labelled synthetic data) and one-click analysis of them."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from changeguard.api.deps import get_state, get_workspace, rate_limited, require_key
from changeguard.api.routes.analyses import _ERRORS, _load, to_summary
from changeguard.api.schemas import AnalysisSummary, SampleDetail, SampleSummary
from changeguard.api.state import AppState
from changeguard.errors import NotFoundError
from changeguard.ingest.prepare import prepare_input
from changeguard.samples import Sample, get_sample, load_samples

router = APIRouter(prefix="/api/v1", tags=["samples"])


def _summary(sample: Sample) -> SampleSummary:
    return SampleSummary(
        id=sample.id,
        title=sample.title,
        tagline=sample.tagline,
        description=sample.description,
        language=sample.language,
        tags=list(sample.tags),
        highlights=list(sample.highlights),
        files=sample.base_files(),
        has_coverage=sample.coverage_path is not None,
        synthetic=bool(sample.extra.get("synthetic", True)),
    )


@router.get(
    "/samples", response_model=list[SampleSummary], summary="List built-in sample scenarios"
)
def list_samples() -> list[SampleSummary]:
    return [_summary(s) for s in load_samples().values()]


@router.get(
    "/samples/{sample_id}",
    response_model=SampleDetail,
    responses=_ERRORS,
    summary="Get a sample scenario, including its patch",
)
def sample_detail(sample_id: str) -> SampleDetail:
    sample = get_sample(sample_id)
    if sample is None:
        raise NotFoundError("sample not found")
    coverage = sample.coverage_path
    return SampleDetail(
        **_summary(sample).model_dump(),
        patch=sample.patch_text,
        coverage_filename=coverage.name if coverage else None,
    )


@router.post(
    "/samples/{sample_id}/analyses",
    status_code=202,
    response_model=AnalysisSummary,
    responses=_ERRORS,
    summary="Analyse a sample scenario",
    dependencies=[Depends(require_key), Depends(rate_limited)],
)
async def analyse_sample(
    sample_id: str,
    state: Annotated[AppState, Depends(get_state)],
    workspace: Annotated[str | None, Depends(get_workspace)],
    ai: Annotated[bool, Query(description="Run optional AI synthesis")] = False,
    snapshot: Annotated[
        bool, Query(description="Include the repository snapshot (full-context mode)")
    ] = True,
    coverage: Annotated[bool, Query(description="Include the sample's coverage report")] = True,
) -> AnalysisSummary:
    sample = get_sample(sample_id)
    if sample is None:
        raise NotFoundError("sample not found")
    cov_path = sample.coverage_path if coverage else None
    prepared = await run_in_threadpool(
        prepare_input,
        state.settings,
        patch=sample.patch_text,
        archive=sample.archive() if snapshot else None,
        coverage=cov_path.read_bytes() if cov_path else None,
        filenames={
            "patch": "change.patch",
            "archive": f"{sample.id}.zip",
            **({"coverage": cov_path.name} if cov_path else {}),
        },
    )
    analysis_id = state.start_analysis(
        prepared,
        source="sample",
        title=f"Sample: {sample.title}",
        ai=ai,
        sample_id=sample.id,
        workspace=workspace,
    )
    return to_summary(_load(state, analysis_id, with_report=False, workspace=workspace))
