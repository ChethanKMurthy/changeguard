"""Analysis endpoints: create (upload/paste), list, inspect, stream progress, export, delete."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, StreamingResponse

from changeguard.api.deps import get_state, get_workspace, rate_limited, require_key
from changeguard.api.schemas import (
    AnalysisDetail,
    AnalysisLinks,
    AnalysisList,
    AnalysisSummary,
    Problem,
)
from changeguard.api.state import AppState
from changeguard.errors import InputError, NotFoundError, PayloadTooLargeError
from changeguard.ingest.prepare import prepare_input
from changeguard.report.exporters import to_json, to_markdown, to_sarif_json
from changeguard.report.models import Report
from changeguard.storage import AnalysisRow
from changeguard.storage.db import TERMINAL

router = APIRouter(prefix="/api/v1", tags=["analyses"], dependencies=[Depends(require_key)])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": Problem, "description": "Missing or invalid API key"},
    404: {"model": Problem, "description": "Analysis not found"},
    413: {"model": Problem, "description": "Input exceeds a size limit"},
    415: {"model": Problem, "description": "Unsupported input format"},
    422: {"model": Problem, "description": "Malformed input"},
    429: {"model": Problem, "description": "Rate limit exceeded"},
}
_ID = re.compile(r"^an_[0-9a-f]{20}$")


def links(analysis_id: str) -> AnalysisLinks:
    base = f"/api/v1/analyses/{analysis_id}"
    return AnalysisLinks(
        self=base,
        events=f"{base}/events",
        export_json=f"{base}/export?format=json",
        export_markdown=f"{base}/export?format=markdown",
        export_sarif=f"{base}/export?format=sarif",
    )


def to_summary(row: AnalysisRow) -> AnalysisSummary:
    return AnalysisSummary(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=row.status,  # type: ignore[arg-type]
        title=row.title,
        source=row.source,  # type: ignore[arg-type]
        sample_id=row.sample_id,
        ai_requested=bool(row.options.get("ai")),
        duration_ms=row.duration_ms,
        summary=row.summary,  # type: ignore[arg-type]
        error=row.error,  # type: ignore[arg-type]
        links=links(row.id),
    )


Workspace = Annotated[str | None, Depends(get_workspace)]


def _load(
    state: AppState, analysis_id: str, *, with_report: bool = True, workspace: str | None = None
) -> AnalysisRow:
    if not _ID.match(analysis_id):
        raise NotFoundError("analysis not found")
    row = state.store.get(analysis_id, with_report=with_report, workspace=workspace)
    if row is None:
        raise NotFoundError("analysis not found")
    return row


async def _read_upload(upload: UploadFile | None, limit: int, label: str) -> bytes | None:
    if upload is None:
        return None
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise PayloadTooLargeError(f"{label} exceeds the {limit / 1_000_000:.0f} MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    return data or None


@router.post(
    "/analyses",
    status_code=202,
    response_model=AnalysisSummary,
    responses=_ERRORS,
    summary="Start an analysis of a patch",
    dependencies=[Depends(rate_limited)],
)
async def create_analysis(
    state: Annotated[AppState, Depends(get_state)],
    workspace: Workspace,
    patch: Annotated[UploadFile | None, File(description="Unified diff / git patch file")] = None,
    patch_text: Annotated[
        str | None, Form(description="Patch pasted as text (alternative to `patch`)")
    ] = None,
    repository: Annotated[
        UploadFile | None,
        File(description="Optional snapshot of the base revision (.zip / .tar.gz)"),
    ] = None,
    coverage: Annotated[
        UploadFile | None,
        File(description="Optional coverage report (Cobertura XML, LCOV, coverage.py JSON)"),
    ] = None,
    title: Annotated[str | None, Form(max_length=200)] = None,
    ai: Annotated[
        bool, Form(description="Run optional AI synthesis (requires a configured provider)")
    ] = False,
) -> AnalysisSummary:
    settings = state.settings
    patch_bytes = await _read_upload(patch, settings.max_patch_bytes, "patch")
    if patch_bytes is None and patch_text:
        patch_bytes = patch_text.encode("utf-8")
        if len(patch_bytes) > settings.max_patch_bytes:
            raise PayloadTooLargeError(
                f"patch exceeds the {settings.max_patch_bytes / 1_000_000:.0f} MB limit"
            )
    if patch_bytes is None:
        raise InputError("provide a patch: upload a .patch/.diff file or paste the diff text")
    archive = await _read_upload(repository, settings.max_archive_bytes, "repository archive")
    coverage_bytes = await _read_upload(coverage, settings.max_coverage_bytes, "coverage report")
    filenames = {
        k: v for k, v in {
            "patch": patch.filename if patch else None,
            "archive": repository.filename if repository else None,
            "coverage": coverage.filename if coverage else None,
        }.items() if v
    }  # fmt: skip
    prepared = await run_in_threadpool(
        prepare_input,
        settings,
        patch=patch_bytes,
        archive=archive,
        coverage=coverage_bytes,
        filenames=filenames,
    )
    analysis_id = state.start_analysis(
        prepared,
        source="upload" if patch is not None else "paste",
        title=title,
        ai=ai,
        workspace=workspace,
    )
    row = _load(state, analysis_id, with_report=False, workspace=workspace)
    return to_summary(row)


@router.get("/analyses", response_model=AnalysisList, summary="List past analyses (newest first)")
def list_analyses(
    state: Annotated[AppState, Depends(get_state)],
    workspace: Workspace,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=100, description="Filter by title")] = None,
) -> AnalysisList:
    rows, total = state.store.list_page(limit=limit, offset=offset, query=q, workspace=workspace)
    return AnalysisList(
        items=[to_summary(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisDetail,
    responses=_ERRORS,
    summary="Get an analysis and its report",
)
def get_analysis(
    analysis_id: str, state: Annotated[AppState, Depends(get_state)], workspace: Workspace
) -> AnalysisDetail:
    row = _load(state, analysis_id, workspace=workspace)
    detail = AnalysisDetail(**to_summary(row).model_dump())
    if row.report is not None:
        detail.report = Report.model_validate(row.report)
    return detail


@router.delete(
    "/analyses/{analysis_id}", status_code=204, responses=_ERRORS, summary="Delete an analysis"
)
def delete_analysis(
    analysis_id: str, state: Annotated[AppState, Depends(get_state)], workspace: Workspace
) -> Response:
    _load(state, analysis_id, with_report=False, workspace=workspace)
    state.store.delete(analysis_id, workspace=workspace)
    return Response(status_code=204)


@router.get(
    "/analyses/{analysis_id}/export",
    responses={
        **_ERRORS,
        200: {
            "content": {"application/json": {}, "text/markdown": {}, "application/sarif+json": {}}
        },
    },
    summary="Export a completed report as JSON, Markdown, or SARIF",
)
def export_analysis(
    analysis_id: str,
    state: Annotated[AppState, Depends(get_state)],
    workspace: Workspace,
    format: Annotated[Literal["json", "markdown", "sarif"], Query()] = "json",
) -> Response:
    row = _load(state, analysis_id, workspace=workspace)
    if row.report is None:
        raise InputError(f"analysis is {row.status}; only completed analyses can be exported")
    report = Report.model_validate(row.report)
    stem = f"changeguard-{analysis_id}"
    if format == "markdown":
        return PlainTextResponse(
            to_markdown(report),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}.md"'},
        )
    if format == "sarif":
        return Response(
            to_sarif_json(report),
            media_type="application/sarif+json",
            headers={"Content-Disposition": f'attachment; filename="{stem}.sarif"'},
        )
    return Response(
        to_json(report),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{stem}.json"'},
    )


@router.get(
    "/analyses/{analysis_id}/events",
    responses={
        **_ERRORS,
        200: {"content": {"text/event-stream": {}}, "description": "Server-sent progress events"},
    },
    summary="Stream analysis progress (server-sent events)",
)
async def stream_events(
    analysis_id: str,
    request: Request,
    state: Annotated[AppState, Depends(get_state)],
    workspace: Workspace,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    await run_in_threadpool(_load, state, analysis_id, with_report=False, workspace=workspace)
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def events() -> AsyncIterator[str]:
        seq = start
        idle_ticks = 0
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                return
            rows = await run_in_threadpool(state.store.events_after, analysis_id, seq)
            for row in rows:
                seq = row.seq
                kind = str(row.event.get("type", "message"))
                yield f"id: {row.seq}\nevent: {kind}\ndata: {json.dumps(row.event)}\n\n"
                if kind in ("completed", "failed"):
                    return
            if not rows:
                status = await run_in_threadpool(state.store.status, analysis_id)
                if status in TERMINAL and seq > 0:
                    return
                if status is None:
                    return
                idle_ticks += 1
                if idle_ticks % 60 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
