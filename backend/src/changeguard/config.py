"""Runtime configuration (environment variables prefixed ``CHANGEGUARD_``).

Secrets use ``SecretStr`` so they never appear in logs, reprs, or error
responses.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AIProviderName = Literal["none", "ollama", "openai", "anthropic", "replay"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHANGEGUARD_", env_file=".env", extra="ignore")

    env: Literal["development", "production", "test"] = "development"
    database_path: Path = Path("data/changeguard.db")
    log_level: str = "INFO"

    # -- input limits ---------------------------------------------------------
    max_patch_bytes: int = 2 * 1024 * 1024
    max_patch_lines: int = 200_000
    max_patch_files: int = 500
    max_archive_bytes: int = 25 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 150 * 1024 * 1024
    max_archive_members: int = 20_000
    max_source_file_bytes: int = 1024 * 1024
    max_coverage_bytes: int = 20 * 1024 * 1024

    # -- API security -----------------------------------------------------------
    api_keys: Annotated[list[SecretStr], NoDecode] = Field(default_factory=list)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    rate_limit_per_minute: int = 20
    trust_proxy_headers: bool = False
    expose_docs: bool = True

    # -- jobs -------------------------------------------------------------------
    worker_threads: int = 2
    analysis_timeout_seconds: float = 240.0
    max_stored_analyses: int = 500

    # -- AI ---------------------------------------------------------------------
    ai_provider: AIProviderName = "none"
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    ai_timeout_seconds: float = 90.0
    ai_max_context_chars: int = 24_000
    ai_max_findings: int = 8
    ai_temperature: float = 0.0
    ai_seed: int = 7
    ai_cache_enabled: bool = True
    ai_recordings_dir: Path | None = None
    ai_record: bool = False

    @field_validator("api_keys", mode="before")
    @classmethod
    def _split_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [SecretStr(v.strip()) for v in value.split(",") if v.strip()]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def auth_required(self) -> bool:
        return bool(self.api_keys)

    def default_model(self) -> str | None:
        if self.ai_model:
            return self.ai_model
        return {
            "ollama": "llama3.2:3b",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-opus-5-5",
        }.get(self.ai_provider)


@functools.cache
def get_settings() -> Settings:
    return Settings()
