"""Record/replay of model responses ("cassettes") for reproducible evaluation.

In **record** mode the wrapped live provider is called and every response is
written to ``<dir>/<request-fingerprint>.json``. In **replay** mode responses
are served from disk and a missing recording is an explicit error — never a
silent substitution. This lets CI recompute AI metrics from versioned model
outputs without running a model, while any prompt or context change shows up
as a replay miss that forces re-recording.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from changeguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    ProviderError,
    ProviderHealth,
)


class ReplayProvider:
    name = "replay"

    def __init__(
        self,
        directory: Path,
        *,
        model: str,
        live: LLMProvider | None = None,
        record: bool = False,
        prompt_id: str = "",
        prompt_version: str = "",
        provider_label: str | None = None,
    ) -> None:
        self.directory = directory
        self.model = live.model if live is not None else model
        self.live = live
        self.record = record and live is not None
        self.prompt_id = prompt_id
        self.prompt_version = prompt_version
        # The label is part of the recording key; it must be the same when
        # recording (through a live provider) and when replaying (without one).
        self.provider_label = provider_label or (live.name if live is not None else "replay")
        self.name = self.provider_label

    def _path(self, request: GenerationRequest) -> Path:
        key = request.fingerprint(
            self.provider_label, self.model, self.prompt_id, self.prompt_version
        )
        return self.directory / f"{key}.json"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        path = self._path(request)
        if path.exists() and not (self.record and self.live is not None and _force_rerecord()):
            data = json.loads(path.read_text())
            return GenerationResult(
                text=data["text"],
                model=data["model"],
                input_tokens=data.get("input_tokens"),
                output_tokens=data.get("output_tokens"),
                latency_ms=float(data.get("latency_ms", 0.0)),
                finish_reason=data.get("finish_reason"),
                meta={"replayed": True, "recorded_at": data.get("recorded_at")},
            )
        if not self.record or self.live is None:
            raise ProviderError(
                "replay_miss",
                f"no recording for this request ({path.name}); re-record with --ai record",
            )
        result = self.live.generate(request)
        self.directory.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "provider": self.live.name,
                    "model": result.model,
                    "prompt_id": self.prompt_id,
                    "prompt_version": self.prompt_version,
                    "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "text": result.text,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": round(result.latency_ms, 1),
                    "finish_reason": result.finish_reason,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        return result

    def health(self) -> ProviderHealth:
        count = len(list(self.directory.glob("*.json"))) if self.directory.exists() else 0
        return ProviderHealth(
            self.name,
            self.model,
            True,
            True,
            count > 0,
            f"{count} recorded response(s) in {self.directory}",
        )


def _force_rerecord() -> bool:
    import os

    return os.environ.get("CHANGEGUARD_AI_RERECORD") == "1"
