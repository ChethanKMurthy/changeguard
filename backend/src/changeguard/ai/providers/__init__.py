"""Provider factory."""

from __future__ import annotations

from pathlib import Path

from changeguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    ProviderError,
    ProviderHealth,
)
from changeguard.config import Settings

__all__ = [
    "GenerationRequest",
    "GenerationResult",
    "LLMProvider",
    "ProviderError",
    "ProviderHealth",
    "build_provider",
]


def _live(settings: Settings, name: str) -> LLMProvider:
    model = (
        settings.ai_model
        or {"ollama": "llama3.2:3b", "openai": "gpt-4o-mini", "anthropic": "claude-opus-5-5"}[name]
    )
    key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else None
    if name == "ollama":
        from changeguard.ai.providers.ollama import OllamaProvider

        return OllamaProvider(
            model, settings.ai_base_url or "http://localhost:11434", settings.ai_timeout_seconds
        )
    if name == "openai":
        from changeguard.ai.providers.openai_compat import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            model,
            settings.ai_base_url or "https://api.openai.com/v1",
            key,
            settings.ai_timeout_seconds,
        )
    if name == "anthropic":
        from changeguard.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model, key, settings.ai_timeout_seconds)
    raise ProviderError("config", f"unknown AI provider '{name}'")


def build_provider(settings: Settings, *, replay_live: str | None = None) -> LLMProvider | None:
    """Create the configured provider, or ``None`` when AI is disabled.

    ``replay`` serves recorded responses from ``ai_recordings_dir``; with
    ``ai_record`` set (and ``replay_live`` naming a live provider) it records
    new responses through that provider.
    """
    name = settings.ai_provider
    if name == "none":
        return None
    if name == "replay":
        from changeguard.ai.prompts import load_prompt
        from changeguard.ai.providers.replay import ReplayProvider

        directory = settings.ai_recordings_dir or Path("eval/recordings")
        live = _live(settings, replay_live) if replay_live else None
        prompt = load_prompt()
        return ReplayProvider(
            directory,
            model=settings.ai_model or "recorded",
            live=live,
            record=settings.ai_record,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            provider_label=replay_live,
        )
    return _live(settings, name)
