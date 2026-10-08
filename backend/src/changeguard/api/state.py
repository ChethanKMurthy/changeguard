"""Application state container shared by route handlers."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from changeguard.ai.providers.base import LLMProvider, ProviderHealth
from changeguard.analysis.context import AnalysisOptions
from changeguard.api.jobs import JobRunner
from changeguard.api.security import RateLimiter
from changeguard.config import Settings
from changeguard.ingest.prepare import PreparedInput
from changeguard.storage import AnalysisStore
from changeguard.storage.db import now

Source = Literal["upload", "paste", "sample", "cli"]


@dataclass(slots=True)
class AppState:
    settings: Settings
    store: AnalysisStore
    runner: JobRunner
    limiter: RateLimiter
    provider: LLMProvider | None
    _health_cache: tuple[float, ProviderHealth] | None = field(default=None)

    def provider_health(self) -> ProviderHealth | None:
        if self.provider is None:
            return None
        cached = self._health_cache
        if cached is not None and time.monotonic() - cached[0] < 30:
            return cached[1]
        health = self.provider.health()
        self._health_cache = (time.monotonic(), health)
        return health

    def start_analysis(
        self,
        prepared: PreparedInput,
        *,
        source: Source,
        title: str | None,
        ai: bool,
        sample_id: str | None = None,
        workspace: str | None = None,
    ) -> str:
        analysis_id = "an_" + uuid.uuid4().hex[:20]
        created_at = now()
        display_title = title or prepared.patch.subject or "Untitled change"
        self.store.create(
            analysis_id=analysis_id,
            title=display_title[:200],
            source=source,
            patch_sha256=prepared.patch_sha256,
            options={
                "ai": ai,
                "has_snapshot": prepared.snapshot is not None,
                "has_coverage": prepared.coverage is not None,
            },
            sample_id=sample_id,
            workspace=workspace,
        )
        options = AnalysisOptions(ai_enabled=ai, title=title)
        self.runner.submit(analysis_id, created_at, prepared, options)
        return analysis_id
