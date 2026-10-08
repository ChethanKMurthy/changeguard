"""Content-addressed cache of validated model responses.

Keyed by the request fingerprint (provider, model, prompt id/version, full
prompt text, schema, decoding parameters). Only responses that parsed and
validated are cached, so a transient malformed output is never pinned.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from changeguard.ai.providers.base import GenerationResult


class ResponseCache(Protocol):
    def get(self, key: str) -> GenerationResult | None: ...

    def put(self, key: str, result: GenerationResult, *, provider: str) -> None: ...


class NullCache:
    def get(self, key: str) -> GenerationResult | None:
        return None

    def put(self, key: str, result: GenerationResult, *, provider: str) -> None:
        return None


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[str, GenerationResult] = {}

    def get(self, key: str) -> GenerationResult | None:
        return self._items.get(key)

    def put(self, key: str, result: GenerationResult, *, provider: str) -> None:
        self._items[key] = result


class SQLiteCache:
    """Cache table living in the application database (see storage migrations)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL,"
            " response_json TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        return conn

    def get(self, key: str) -> GenerationResult | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT response_json FROM llm_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return GenerationResult(
            text=data["text"],
            model=data["model"],
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            latency_ms=float(data.get("latency_ms", 0.0)),
            finish_reason=data.get("finish_reason"),
            meta={"cached": True},
        )

    def put(self, key: str, result: GenerationResult, *, provider: str) -> None:
        payload = json.dumps(
            {
                "text": result.text,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
                "finish_reason": result.finish_reason,
            }
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, provider, model, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    key,
                    provider,
                    result.model,
                    payload,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
