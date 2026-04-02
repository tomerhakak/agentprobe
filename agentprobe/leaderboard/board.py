"""Agent Leaderboard -- SQLite-backed ranking and historical tracking.

Stores agent evaluation results locally and renders beautiful terminal
leaderboards with composite scores, badges, and trend sparklines.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agentprobe.core.models import AgentRecording

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_DB_DIR = Path.home() / ".agentprobe"
_DEFAULT_DB_NAME = "leaderboard.db"

# Composite-score weights (must sum to 1.0)
_DEFAULT_WEIGHTS: Dict[str, float] = {
    "quality": 0.30,
    "security": 0.25,
    "cost_efficiency": 0.20,
    "speed": 0.15,
    "reliability": 0.10,
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LeaderboardEntry:
    """A single row in the leaderboard."""

    agent_name: str
    score: float = 0.0
    quality: float = 0.0
    security: float = 0.0
    cost_efficiency: float = 0.0
    speed: float = 0.0
    reliability: float = 0.0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    runs: int = 0
    updated_at: str = ""
    badge: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "agent_name": self.agent_name,
            "score": self.score,
            "quality": self.quality,
            "security": self.security,
            "cost_efficiency": self.cost_efficiency,
            "speed": self.speed,
            "reliability": self.reliability,
            "cost_usd": self.cost_usd,
            "latency_s": self.latency_s,
            "runs": self.runs,
            "updated_at": self.updated_at,
            "badge": self.badge,
        }


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


class Leaderboard:
    """Local, SQLite-backed agent leaderboard.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Defaults to
        ``~/.agentprobe/leaderboard.db``.
    weights:
        Optional dict overriding composite-score weights.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        if db_path is None:
            _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            self._db_path = str(_DEFAULT_DB_DIR / _DEFAULT_DB_NAME)
        else:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db_path = db_path

        self.weights = weights or dict(_DEFAULT_WEIGHTS)
        self._init_db()

    # -- Public API ---------------------------------------------------------

    def add_entry(
        self,
        agent_name: str,
        recording: Optional[AgentRecording] = None,
        test_results: Optional[Dict[str, Any]] = None,
    ) -> LeaderboardEntry:
        """Add or update a leaderboard entry for *agent_name*.

        Metrics are derived from the *recording* and/or *test_results*.
        """
        quality = 0.0
        security = 0.0
        cost_efficiency = 0.0
        speed = 0.0
        reliability = 0.0
        cost_usd = 0.0
        latency_s = 0.0

        if test_results:
            quality = float(test_results.get("quality", 0.0))
            security = float(test_results.get("security", 0.0))
            reliability = float(test_results.get("reliability", 0.0))
            cost_efficiency = float(test_results.get("cost_efficiency", 0.0))
            speed = float(test_results.get("speed", 0.0))

        if recording:
            cost_usd = recording.total_cost
            latency_s = recording.total_duration / 1000.0 if recording.total_duration else 0.0

            # Derive cost_efficiency (0-100 scale, lower cost -> higher score)
            if cost_efficiency == 0.0:
                cost_efficiency = max(0.0, 100.0 - cost_usd * 10000.0)

            # Derive speed (0-100 scale, lower latency -> higher score)
            if speed == 0.0:
                speed = max(0.0, 100.0 - latency_s * 10.0)

            # Derive quality from output status if not provided
            if quality == 0.0:
                if recording.output.status.value == "success":
                    quality = 80.0
                else:
                    quality = 30.0

        # Composite score
        score = (
            quality * self.weights.get("quality", 0.30)
            + security * self.weights.get("security", 0.25)
            + cost_efficiency * self.weights.get("cost_efficiency", 0.20)
            + speed * self.weights.get("speed", 0.15)
            + reliability * self.weights.get("reliability", 0.10)
        )

        now = datetime.now(timezone.utc).isoformat()

        con = self._connect()
        try:
            # Increment run count
            row = con.execute(
                "SELECT runs FROM entries WHERE agent_name = ?", (agent_name,)
            ).fetchone()
            runs = (row[0] + 1) if row else 1

            con.execute(
                """
                INSERT INTO entries
                    (agent_name, score, quality, security, cost_efficiency,
                     speed, reliability, cost_usd, latency_s, runs, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_name) DO UPDATE SET
                    score=excluded.score,
                    quality=excluded.quality,
                    security=excluded.security,
                    cost_efficiency=excluded.cost_efficiency,
                    speed=excluded.speed,
                    reliability=excluded.reliability,
                    cost_usd=excluded.cost_usd,
                    latency_s=excluded.latency_s,
                    runs=excluded.runs,
                    updated_at=excluded.updated_at
                """,
                (
                    agent_name, score, quality, security, cost_efficiency,
                    speed, reliability, cost_usd, latency_s, runs, now,
                ),
            )

            # History row
            con.execute(
                """
                INSERT INTO history
                    (agent_name, score, quality, security, cost_efficiency,
                     speed, reliability, cost_usd, latency_s, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_name, score, quality, security, cost_efficiency,
                    speed, reliability, cost_usd, latency_s, now,
                ),
            )
            con.commit()
        finally:
            con.close()

        entry = LeaderboardEntry(
            agent_name=agent_name,
            score=round(score, 1),
            quality=round(quality, 1),
            security=round(security, 1),
            cost_efficiency=round(cost_efficiency, 1),
            speed=round(speed, 1),
            reliability=round(reliability, 1),
            cost_usd=cost_usd,
            latency_s=round(latency_s, 1),
            runs=runs,
            updated_at=now,
        )
        return entry

    def get_rankings(self, sort_by: str = "score") -> List[LeaderboardEntry]:
        """Return all entries sorted by *sort_by* (descending).

        Valid sort keys: score, quality, security, cost_efficiency, speed,
        reliability, cost_usd, latency_s.
        """
        valid = {
            "score", "quality", "security", "cost_efficiency",
            "speed", "reliability", "cost_usd", "latency_s",
        }
        if sort_by not in valid:
            sort_by = "score"

        # cost_usd and latency_s: lower is better -> ascending
        direction = "ASC" if sort_by in ("cost_usd", "latency_s") else "DESC"

        con = self._connect()
        try:
            rows = con.execute(
                f"SELECT * FROM entries ORDER BY {sort_by} {direction}"
            ).fetchall()
        finally:
            con.close()

        entries = [self._row_to_entry(r) for r in rows]
        self._assign_badges(entries)
        return entries

    def get_history(self, agent_name: str) -> List[Dict[str, Any]]:
        """Return historical score snapshots for *agent_name*."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT * FROM history WHERE agent_name = ? ORDER BY recorded_at ASC",
                (agent_name,),
            ).fetchall()
        finally:
            con.close()

        return [
            {
                "agent_name": r[1],
                "score": r[2],
                "quality": r[3],
                "security": r[4],
                "cost_efficiency": r[5],
                "speed": r[6],
                "reliability": r[7],
                "cost_usd": r[8],
                "latency_s": r[9],
                "recorded_at": r[10],
            }
            for r in rows
        ]

    def format_trend(self, agent_name: str) -> str:
        """Return a sparkline showing score trend for *agent_name*."""
        history = self.get_history(agent_name)
        if not history:
            return f"{agent_name}: (no data)"

        scores = [h["score"] for h in history]
        sparkline = self._sparkline(scores)
        latest = scores[-1]
        delta = scores[-1] - scores[0] if len(scores) > 1 else 0.0
        direction = "+" if delta >= 0 else ""
        return f"{agent_name}: {sparkline}  {latest:.1f} ({direction}{delta:.1f})"

    def format_terminal(self) -> str:
        """Generate a beautiful terminal leaderboard table."""
        entries = self.get_rankings()
        if not entries:
            return "  No agents tracked yet. Run some tests first!"

        lines: List[str] = []
        lines.append("")
        lines.append("  AgentProbe Leaderboard")
        lines.append("=" * 72)
        header = (
            f"  {'#':>2}  {'Agent':<22} {'Score':>6}  {'Cost':>8}  "
            f"{'Speed':>6}  {'Security':>8}  {'Quality':>7}  "
        )
        lines.append(header)
        lines.append("-" * 72)

        for rank, entry in enumerate(entries, 1):
            cost_str = f"${entry.cost_usd:.4f}" if entry.cost_usd < 0.01 else f"${entry.cost_usd:.3f}"
            speed_str = f"{entry.latency_s:.1f}s"
            sec_str = f"{entry.security:.0f}/100"
            qual_str = f"{entry.quality:.0f}%"
            badge = f"  {entry.badge}" if entry.badge else ""

            line = (
                f"  {rank:>2}  {entry.agent_name:<22} {entry.score:>6.1f}  "
                f"{cost_str:>8}  {speed_str:>6}  {sec_str:>8}  "
                f"{qual_str:>7}{badge}"
            )
            lines.append(line)

        lines.append("=" * 72)

        # Footer
        total = len(entries)
        best = entries[0].agent_name if entries else "-"
        worst_sec = min(entries, key=lambda e: e.security).agent_name if entries else "-"
        lines.append(
            f"  {total} agents tracked | Best: {best} | Worst security: {worst_sec}"
        )
        lines.append("")

        return "\n".join(lines)

    def delete_agent(self, agent_name: str) -> bool:
        """Remove an agent from the leaderboard and history. Returns True if found."""
        con = self._connect()
        try:
            cur = con.execute(
                "DELETE FROM entries WHERE agent_name = ?", (agent_name,)
            )
            con.execute(
                "DELETE FROM history WHERE agent_name = ?", (agent_name,)
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def clear(self) -> None:
        """Remove ALL leaderboard data."""
        con = self._connect()
        try:
            con.execute("DELETE FROM entries")
            con.execute("DELETE FROM history")
            con.commit()
        finally:
            con.close()

    # -- Private helpers ----------------------------------------------------

    def _init_db(self) -> None:
        """Create the database tables if they don't exist."""
        con = self._connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    agent_name      TEXT PRIMARY KEY,
                    score           REAL DEFAULT 0,
                    quality         REAL DEFAULT 0,
                    security        REAL DEFAULT 0,
                    cost_efficiency REAL DEFAULT 0,
                    speed           REAL DEFAULT 0,
                    reliability     REAL DEFAULT 0,
                    cost_usd        REAL DEFAULT 0,
                    latency_s       REAL DEFAULT 0,
                    runs            INTEGER DEFAULT 0,
                    updated_at      TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name      TEXT NOT NULL,
                    score           REAL DEFAULT 0,
                    quality         REAL DEFAULT 0,
                    security        REAL DEFAULT 0,
                    cost_efficiency REAL DEFAULT 0,
                    speed           REAL DEFAULT 0,
                    reliability     REAL DEFAULT 0,
                    cost_usd        REAL DEFAULT 0,
                    latency_s       REAL DEFAULT 0,
                    recorded_at     TEXT DEFAULT ''
                );
                """
            )
            con.commit()
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    @staticmethod
    def _row_to_entry(row: Tuple[Any, ...]) -> LeaderboardEntry:
        return LeaderboardEntry(
            agent_name=row[0],
            score=round(row[1], 1),
            quality=round(row[2], 1),
            security=round(row[3], 1),
            cost_efficiency=round(row[4], 1),
            speed=round(row[5], 1),
            reliability=round(row[6], 1),
            cost_usd=row[7],
            latency_s=round(row[8], 1),
            runs=row[9],
            updated_at=row[10],
        )

    @staticmethod
    def _assign_badges(entries: List[LeaderboardEntry]) -> None:
        """Assign badges based on rank and metrics."""
        if not entries:
            return

        # Top entry gets crown
        entries[0].badge = "\U0001f451"  # crown

        for entry in entries:
            if entry.runs == 1:
                entry.badge = entry.badge or "\U0001f195"  # NEW

        # Bottom entries with low score get warning
        for entry in entries:
            if entry.score < 60 or entry.security < 50:
                entry.badge = entry.badge or "\u26a0\ufe0f"  # warning

    @staticmethod
    def _sparkline(values: Sequence[float]) -> str:
        """Generate a text sparkline from a sequence of values."""
        if not values:
            return ""
        bars = " _.-~*"
        lo = min(values)
        hi = max(values)
        span = hi - lo if hi != lo else 1.0
        return "".join(
            bars[min(int((v - lo) / span * (len(bars) - 1)), len(bars) - 1)]
            for v in values
        )
