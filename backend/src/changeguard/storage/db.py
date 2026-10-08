"""SQLite persistence for analyses, progress events, and the model response cache.

One connection per operation (SQLite connections are cheap and not
thread-safe), WAL journaling for concurrent readers, and forward-only schema
migrations tracked with ``PRAGMA user_version``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIGRATIONS: list[str] = [
    # v1: initial schema
    """
    CREATE TABLE analyses (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
        title TEXT NOT NULL,
        source TEXT NOT NULL,
        sample_id TEXT,
        patch_sha256 TEXT NOT NULL,
        options_json TEXT NOT NULL,
        summary_json TEXT,
        report_json TEXT,
        error_json TEXT,
        duration_ms REAL
    );
    CREATE INDEX idx_analyses_created ON analyses (created_at DESC);
    CREATE TABLE analysis_events (
        analysis_id TEXT NOT NULL REFERENCES analyses (id) ON DELETE CASCADE,
        seq INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        event_json TEXT NOT NULL,
        PRIMARY KEY (analysis_id, seq)
    );
    CREATE TABLE IF NOT EXISTS llm_cache (
        key TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    # v2: workspaces. A workspace is an opaque per-browser identifier set by the web
    # app's proxy; analyses created in one workspace are invisible to every other.
    """
    ALTER TABLE analyses ADD COLUMN workspace TEXT;
    CREATE INDEX idx_analyses_workspace ON analyses (workspace, created_at DESC);
    """,
]

TERMINAL = frozenset({"completed", "failed"})


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(slots=True)
class AnalysisRow:
    id: str
    created_at: str
    updated_at: str
    status: str
    title: str
    source: str
    sample_id: str | None
    patch_sha256: str
    options: dict[str, Any]
    summary: dict[str, Any] | None
    report: dict[str, Any] | None
    error: dict[str, Any] | None
    duration_ms: float | None


@dataclass(slots=True)
class EventRow:
    seq: int
    created_at: str
    event: dict[str, Any]


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 15000")
            yield conn
        finally:
            conn.close()

    def migrate(self) -> int:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            for index in range(version, len(MIGRATIONS)):
                conn.execute("BEGIN")
                try:
                    for statement in _split_sql(MIGRATIONS[index]):
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version = {index + 1}")
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            return len(MIGRATIONS)


def _split_sql(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


class AnalysisStore:
    """Analyses and their events.

    Reads take a ``workspace``: ``None`` means unscoped (an operator or the CLI,
    which sees everything); a string restricts results to that workspace, so an
    analysis from another workspace behaves exactly as if it did not exist.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- writes -------------------------------------------------------------------

    def create(
        self,
        *,
        analysis_id: str,
        title: str,
        source: str,
        patch_sha256: str,
        options: dict[str, Any],
        sample_id: str | None = None,
        workspace: str | None = None,
    ) -> None:
        stamp = now()
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO analyses (id, created_at, updated_at, status, title, source, sample_id, patch_sha256,"
                " options_json, workspace) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)",
                (
                    analysis_id,
                    stamp,
                    stamp,
                    title,
                    source,
                    sample_id,
                    patch_sha256,
                    json.dumps(options),
                    workspace,
                ),
            )

    def set_running(self, analysis_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE analyses SET status = 'running', updated_at = ? WHERE id = ?",
                (now(), analysis_id),
            )

    def complete(
        self,
        analysis_id: str,
        *,
        title: str,
        report: dict[str, Any],
        summary: dict[str, Any],
        duration_ms: float,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE analyses SET status = 'completed', updated_at = ?, title = ?, report_json = ?, summary_json = ?,"
                " duration_ms = ? WHERE id = ?",
                (
                    now(),
                    title,
                    json.dumps(report, ensure_ascii=False),
                    json.dumps(summary),
                    duration_ms,
                    analysis_id,
                ),
            )

    def fail(
        self, analysis_id: str, error: dict[str, Any], duration_ms: float | None = None
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE analyses SET status = 'failed', updated_at = ?, error_json = ?, duration_ms = ? WHERE id = ?",
                (now(), json.dumps(error), duration_ms, analysis_id),
            )

    def append_event(self, analysis_id: str, event: dict[str, Any]) -> int:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            seq = int(
                conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM analysis_events WHERE analysis_id = ?",
                    (analysis_id,),
                ).fetchone()[0]
            )
            conn.execute(
                "INSERT INTO analysis_events (analysis_id, seq, created_at, event_json) VALUES (?, ?, ?, ?)",
                (analysis_id, seq, now(), json.dumps(event, default=str)),
            )
            conn.execute("COMMIT")
        return seq

    def delete(self, analysis_id: str, *, workspace: str | None = None) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM analyses WHERE id = ? AND (? IS NULL OR workspace = ?)",
                (analysis_id, workspace, workspace),
            )
            return cur.rowcount > 0

    def prune(self, keep: int) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM analyses WHERE id IN (SELECT id FROM analyses ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
                (keep,),
            )
            return cur.rowcount

    def fail_incomplete(self) -> int:
        """Mark analyses interrupted by a restart as failed (their worker threads are gone)."""
        error = json.dumps(
            {
                "code": "interrupted",
                "message": "The server restarted before this analysis finished.",
            }
        )
        with self.db.connect() as conn:
            cur = conn.execute(
                "UPDATE analyses SET status = 'failed', updated_at = ?, error_json = ? WHERE status IN ('queued', 'running')",
                (now(), error),
            )
            return cur.rowcount

    # -- reads --------------------------------------------------------------------

    def get(
        self, analysis_id: str, *, with_report: bool = True, workspace: str | None = None
    ) -> AnalysisRow | None:
        columns = (
            "*"
            if with_report
            else "id, created_at, updated_at, status, title, source, sample_id, patch_sha256, options_json, summary_json, NULL AS report_json, error_json, duration_ms"
        )
        with self.db.connect() as conn:
            # `columns` is one of two constant strings; values travel only as bound parameters.
            row = conn.execute(
                f"SELECT {columns} FROM analyses WHERE id = ? AND (? IS NULL OR workspace = ?)",
                (analysis_id, workspace, workspace),
            ).fetchone()
        return _row(row) if row is not None else None

    def status(self, analysis_id: str) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT status FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return str(row[0]) if row is not None else None

    def list_page(
        self, *, limit: int, offset: int, query: str | None = None, workspace: str | None = None
    ) -> tuple[list[AnalysisRow], int]:
        where = "WHERE (? IS NULL OR workspace = ?)"
        params: list[object] = [workspace, workspace]
        if query:
            where += " AND title LIKE ? ESCAPE '\\'"
            params.append(
                "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
        with self.db.connect() as conn:
            # `where` is built from constant fragments; user input only ever travels as a bound parameter.
            total = int(
                conn.execute(f"SELECT COUNT(*) FROM analyses {where}", params).fetchone()[0]
            )
            query = (
                "SELECT id, created_at, updated_at, status, title, source, sample_id, patch_sha256, options_json,"
                f" summary_json, NULL AS report_json, error_json, duration_ms FROM analyses {where}"
                " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            )
            rows = conn.execute(query, [*params, limit, offset]).fetchall()
        return [_row(r) for r in rows], total

    def events_after(self, analysis_id: str, seq: int) -> list[EventRow]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT seq, created_at, event_json FROM analysis_events WHERE analysis_id = ? AND seq > ? ORDER BY seq",
                (analysis_id, seq),
            ).fetchall()
        return [
            EventRow(int(r["seq"]), str(r["created_at"]), json.loads(r["event_json"])) for r in rows
        ]


def _row(row: sqlite3.Row) -> AnalysisRow:
    def load(value: str | None) -> Any:
        return json.loads(value) if value else None

    return AnalysisRow(
        id=row["id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        status=row["status"],
        title=row["title"],
        source=row["source"],
        sample_id=row["sample_id"],
        patch_sha256=row["patch_sha256"],
        options=load(row["options_json"]) or {},
        summary=load(row["summary_json"]),
        report=load(row["report_json"]),
        error=load(row["error_json"]),
        duration_ms=row["duration_ms"],
    )
