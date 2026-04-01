"""SQLite-based index for AgentProbe recordings stored as .aprobe files."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentprobe.core.models import AgentRecording


class RecordingStore:
    """SQLite index for recordings stored as .aprobe files."""

    def __init__(self, db_path: str | Path = ".agentprobe/index.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables if they don't already exist."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS recordings (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL DEFAULT '',
                path        TEXT NOT NULL,
                framework   TEXT NOT NULL DEFAULT '',
                model       TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT '',
                cost        REAL NOT NULL DEFAULT 0.0,
                tokens      INTEGER NOT NULL DEFAULT 0,
                duration    REAL NOT NULL DEFAULT 0.0,
                tags        TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_recordings_name      ON recordings(name);
            CREATE INDEX IF NOT EXISTS idx_recordings_framework  ON recordings(framework);
            CREATE INDEX IF NOT EXISTS idx_recordings_model      ON recordings(model);
            CREATE INDEX IF NOT EXISTS idx_recordings_status     ON recordings(status);
            CREATE INDEX IF NOT EXISTS idx_recordings_created_at ON recordings(created_at);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def index(self, recording: AgentRecording, file_path: Path) -> None:
        """Add or update a recording in the index."""
        now = datetime.now(timezone.utc).isoformat()
        meta = recording.metadata
        self._conn.execute(
            """
            INSERT INTO recordings
                (id, name, path, framework, model, status, cost, tokens, duration, tags, created_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name       = excluded.name,
                path       = excluded.path,
                framework  = excluded.framework,
                model      = excluded.model,
                status     = excluded.status,
                cost       = excluded.cost,
                tokens     = excluded.tokens,
                duration   = excluded.duration,
                tags       = excluded.tags,
                updated_at = excluded.updated_at
            """,
            (
                meta.id,
                meta.name,
                str(file_path.resolve()),
                meta.agent_framework,
                recording.environment.model,
                recording.output.status.value,
                recording.total_cost,
                recording.total_tokens,
                recording.total_duration,
                json.dumps(meta.tags),
                meta.timestamp.isoformat() if meta.timestamp else now,
                now,
            ),
        )
        self._conn.commit()

    def delete(self, recording_id: str) -> None:
        """Remove a recording from the index."""
        self._conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, recording_id: str) -> dict[str, Any] | None:
        """Fetch a single recording by ID."""
        row = self._conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_all(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Return all recordings ordered by creation date (newest first)."""
        rows = self._conn.execute(
            "SELECT * FROM recordings ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search(
        self,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
        framework: str | None = None,
        model: str | None = None,
        status: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search recordings by multiple criteria (all ANDed together)."""
        clauses: list[str] = []
        params: list[Any] = []

        if name is not None:
            clauses.append("name LIKE ?")
            params.append(f"%{name}%")

        if framework is not None:
            clauses.append("framework = ?")
            params.append(framework)

        if model is not None:
            clauses.append("model = ?")
            params.append(model)

        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        if after is not None:
            clauses.append("created_at >= ?")
            params.append(after)

        if before is not None:
            clauses.append("created_at <= ?")
            params.append(before)

        if tags:
            for tag in tags:
                clauses.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM recordings {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        """Total number of indexed recordings."""
        row = self._conn.execute("SELECT COUNT(*) FROM recordings").fetchone()
        return row[0]

    def stats(self) -> dict[str, Any]:
        """Aggregate statistics across all indexed recordings."""
        row = self._conn.execute(
            """
            SELECT
                COUNT(*)       AS total_recordings,
                COALESCE(SUM(cost), 0)     AS total_cost,
                COALESCE(AVG(cost), 0)     AS avg_cost,
                COALESCE(SUM(tokens), 0)   AS total_tokens,
                COALESCE(AVG(tokens), 0)   AS avg_tokens,
                COALESCE(SUM(duration), 0) AS total_duration,
                COALESCE(AVG(duration), 0) AS avg_duration,
                MIN(created_at) AS earliest,
                MAX(created_at) AS latest
            FROM recordings
            """
        ).fetchone()

        framework_rows = self._conn.execute(
            "SELECT framework, COUNT(*) AS cnt FROM recordings GROUP BY framework ORDER BY cnt DESC"
        ).fetchall()

        model_rows = self._conn.execute(
            "SELECT model, COUNT(*) AS cnt FROM recordings GROUP BY model ORDER BY cnt DESC"
        ).fetchall()

        status_rows = self._conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM recordings GROUP BY status ORDER BY cnt DESC"
        ).fetchall()

        return {
            "total_recordings": row["total_recordings"],
            "total_cost_usd": round(row["total_cost"], 6),
            "avg_cost_usd": round(row["avg_cost"], 6),
            "total_tokens": row["total_tokens"],
            "avg_tokens": round(row["avg_tokens"], 2),
            "total_duration_ms": round(row["total_duration"], 2),
            "avg_duration_ms": round(row["avg_duration"], 2),
            "earliest_recording": row["earliest"],
            "latest_recording": row["latest"],
            "by_framework": {r["framework"]: r["cnt"] for r in framework_rows},
            "by_model": {r["model"]: r["cnt"] for r in model_rows},
            "by_status": {r["status"]: r["cnt"] for r in status_rows},
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags", "[]"))
        return d

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> RecordingStore:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
