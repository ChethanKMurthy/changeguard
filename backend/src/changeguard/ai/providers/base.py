"""Provider-neutral interface for schema-constrained generation.

Every provider receives the same request (system prompt, user prompt, JSON
schema) and returns raw text plus usage metadata. Parsing, validation, and
grounding happen in the synthesizer, so providers stay thin and swappable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

ErrorKind = Literal[
    "timeout",
    "unavailable",
    "rate_limited",
    "refused",
    "bad_response",
    "config",
    "http",
    "replay_miss",
]


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    system: str
    user: str
    schema: dict[str, Any]
    schema_name: str = "changeguard_review"
    max_output_tokens: int = 4096
    temperature: float = 0.0
    seed: int | None = 7

    def fingerprint(self, provider: str, model: str, prompt_id: str, prompt_version: str) -> str:
        """Content hash identifying this exact request (cache and replay key)."""
        payload = {
            "provider": provider,
            "model": model,
            "prompt_id": prompt_id,
            "prompt_version": prompt_version,
            **asdict(self),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0
    finish_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    model: str | None
    configured: bool
    reachable: bool | None
    model_available: bool | None
    detail: str | None = None


class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def health(self) -> ProviderHealth: ...
