"""Local brain storage -- SQLite database for insights and learned patterns."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentprobe.brain.collector import AnonymizedInsight


class BrainStore:
    """Local SQLite store for the brain's knowledge."""

    def __init__(self, db_path: str = ".agentprobe/brain.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                framework TEXT NOT NULL,
                model TEXT NOT NULL,
                cost_bucket TEXT NOT NULL,
                latency_bucket TEXT NOT NULL,
                token_bucket TEXT NOT NULL,
                step_count INTEGER NOT NULL,
                assertions_used TEXT NOT NULL,  -- JSON array
                assertions_passed INTEGER NOT NULL DEFAULT 0,
                assertions_failed INTEGER NOT NULL DEFAULT 0,
                failure_types TEXT NOT NULL,     -- JSON array
                tools_used TEXT NOT NULL,        -- JSON array
                had_errors INTEGER NOT NULL DEFAULT 0,
                output_status TEXT NOT NULL DEFAULT 'success'
            );

            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                pattern_value TEXT NOT NULL,  -- JSON
                updated_at TEXT NOT NULL,
                UNIQUE(pattern_type, pattern_key)
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rec_type TEXT NOT NULL,
                priority TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                dismissed INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_insights_model ON insights(model);
            CREATE INDEX IF NOT EXISTS idx_insights_framework ON insights(framework);
            CREATE INDEX IF NOT EXISTS idx_insights_timestamp ON insights(timestamp);
        """
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Store / retrieve insights
    # ------------------------------------------------------------------

    def store_insight(self, insight: AnonymizedInsight) -> None:
        """Store an anonymized insight."""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO insights (
                timestamp, framework, model, cost_bucket, latency_bucket,
                token_bucket, step_count, assertions_used, assertions_passed,
                assertions_failed, failure_types, tools_used, had_errors,
                output_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                insight.timestamp,
                insight.framework,
                insight.model,
                insight.cost_bucket,
                insight.latency_bucket,
                insight.token_bucket,
                insight.step_count,
                json.dumps(insight.assertions_used),
                insight.assertions_passed,
                insight.assertions_failed,
                json.dumps(insight.failure_types),
                json.dumps(insight.tools_used),
                1 if insight.had_errors else 0,
                insight.output_status,
            ),
        )
        conn.commit()

    def get_insights(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get stored insights."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM insights ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["assertions_used"] = json.loads(d["assertions_used"])
            d["failure_types"] = json.loads(d["failure_types"])
            d["tools_used"] = json.loads(d["tools_used"])
            d["had_errors"] = bool(d["had_errors"])
            results.append(d)
        return results

    def get_patterns(self) -> Dict[str, Any]:
        """Analyze stored insights and extract patterns.

        Returns a dict with:
        - failure_types: most common failure types with counts
        - assertions_used: most used assertions with counts
        - cost_by_model: cost bucket distribution per model
        - tool_usage: tool usage frequency
        - pass_rates_by_framework: average pass rates per framework
        - models_used: model usage frequency
        - step_distribution: step count statistics
        - error_rate: fraction of runs with errors
        - total_insights: total number of insights
        """
        insights = self.get_insights(limit=10000)
        if not insights:
            return {
                "failure_types": {},
                "assertions_used": {},
                "cost_by_model": {},
                "tool_usage": {},
                "pass_rates_by_framework": {},
                "models_used": {},
                "step_distribution": {"min": 0, "max": 0, "avg": 0.0},
                "error_rate": 0.0,
                "total_insights": 0,
            }

        # Failure type frequency
        failure_counts: dict[str, int] = {}
        for ins in insights:
            for ft in ins["failure_types"]:
                failure_counts[ft] = failure_counts.get(ft, 0) + 1

        # Assertion usage frequency
        assertion_counts: dict[str, int] = {}
        for ins in insights:
            for a in ins["assertions_used"]:
                assertion_counts[a] = assertion_counts.get(a, 0) + 1

        # Cost distribution by model
        cost_by_model: dict[str, dict[str, int]] = {}
        for ins in insights:
            model = ins["model"]
            bucket = ins["cost_bucket"]
            if model not in cost_by_model:
                cost_by_model[model] = {}
            cost_by_model[model][bucket] = cost_by_model[model].get(bucket, 0) + 1

        # Tool usage
        tool_counts: dict[str, int] = {}
        for ins in insights:
            for t in ins["tools_used"]:
                tool_counts[t] = tool_counts.get(t, 0) + 1

        # Pass rates by framework
        framework_stats: dict[str, dict[str, int]] = {}
        for ins in insights:
            fw = ins["framework"]
            if fw not in framework_stats:
                framework_stats[fw] = {"passed": 0, "failed": 0, "total": 0}
            framework_stats[fw]["passed"] += ins["assertions_passed"]
            framework_stats[fw]["failed"] += ins["assertions_failed"]
            framework_stats[fw]["total"] += (
                ins["assertions_passed"] + ins["assertions_failed"]
            )

        pass_rates: dict[str, float] = {}
        for fw, stats in framework_stats.items():
            if stats["total"] > 0:
                pass_rates[fw] = round(stats["passed"] / stats["total"] * 100, 1)
            else:
                pass_rates[fw] = 0.0

        # Model usage frequency
        model_counts: dict[str, int] = {}
        for ins in insights:
            m = ins["model"]
            model_counts[m] = model_counts.get(m, 0) + 1

        # Step distribution
        steps = [ins["step_count"] for ins in insights]
        step_dist = {
            "min": min(steps) if steps else 0,
            "max": max(steps) if steps else 0,
            "avg": round(sum(steps) / len(steps), 1) if steps else 0.0,
        }

        # Error rate
        error_count = sum(1 for ins in insights if ins["had_errors"])
        error_rate = round(error_count / len(insights) * 100, 1)

        return {
            "failure_types": dict(
                sorted(failure_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "assertions_used": dict(
                sorted(assertion_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "cost_by_model": cost_by_model,
            "tool_usage": dict(
                sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "pass_rates_by_framework": pass_rates,
            "models_used": dict(
                sorted(model_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "step_distribution": step_dist,
            "error_rate": error_rate,
            "total_insights": len(insights),
        }

    def get_model_stats(self) -> Dict[str, Any]:
        """Stats per model: cost distribution, latency distribution, pass rate, common failures."""
        insights = self.get_insights(limit=10000)
        if not insights:
            return {}

        models: dict[str, dict[str, Any]] = {}

        for ins in insights:
            model = ins["model"]
            if model not in models:
                models[model] = {
                    "count": 0,
                    "cost_buckets": {},
                    "latency_buckets": {},
                    "total_passed": 0,
                    "total_assertions": 0,
                    "failures": {},
                    "avg_steps": 0.0,
                    "step_sum": 0,
                    "error_count": 0,
                }

            m = models[model]
            m["count"] += 1
            m["step_sum"] += ins["step_count"]

            # Cost distribution
            cb = ins["cost_bucket"]
            m["cost_buckets"][cb] = m["cost_buckets"].get(cb, 0) + 1

            # Latency distribution
            lb = ins["latency_bucket"]
            m["latency_buckets"][lb] = m["latency_buckets"].get(lb, 0) + 1

            # Pass rate
            total = ins["assertions_passed"] + ins["assertions_failed"]
            m["total_passed"] += ins["assertions_passed"]
            m["total_assertions"] += total

            # Failures
            for ft in ins["failure_types"]:
                m["failures"][ft] = m["failures"].get(ft, 0) + 1

            if ins["had_errors"]:
                m["error_count"] += 1

        # Compute aggregates
        result: dict[str, Any] = {}
        for model, m in models.items():
            pass_rate = (
                round(m["total_passed"] / m["total_assertions"] * 100, 1)
                if m["total_assertions"] > 0
                else 0.0
            )
            result[model] = {
                "run_count": m["count"],
                "cost_distribution": m["cost_buckets"],
                "latency_distribution": m["latency_buckets"],
                "pass_rate": pass_rate,
                "avg_steps": round(m["step_sum"] / m["count"], 1),
                "error_rate": round(m["error_count"] / m["count"] * 100, 1),
                "common_failures": dict(
                    sorted(m["failures"].items(), key=lambda x: x[1], reverse=True)[
                        :5
                    ]
                ),
            }

        return result

    def get_assertion_effectiveness(self) -> Dict[str, Any]:
        """Which assertions catch the most failures? Which always pass (potentially useless)?"""
        insights = self.get_insights(limit=10000)
        if not insights:
            return {}

        # Track per-assertion: how many times used, how many times in a failing run
        assertion_stats: dict[str, dict[str, int]] = {}

        for ins in insights:
            has_failures = ins["assertions_failed"] > 0
            for a in ins["assertions_used"]:
                if a not in assertion_stats:
                    assertion_stats[a] = {"used": 0, "in_failing_run": 0}
                assertion_stats[a]["used"] += 1
                if has_failures:
                    assertion_stats[a]["in_failing_run"] += 1

        result: dict[str, Any] = {}
        for assertion, stats in assertion_stats.items():
            failure_catch_rate = (
                round(stats["in_failing_run"] / stats["used"] * 100, 1)
                if stats["used"] > 0
                else 0.0
            )
            result[assertion] = {
                "times_used": stats["used"],
                "in_failing_runs": stats["in_failing_run"],
                "failure_catch_rate": failure_catch_rate,
                "effectiveness": (
                    "high"
                    if failure_catch_rate > 30
                    else "medium" if failure_catch_rate > 10 else "low"
                ),
                "always_passing": stats["in_failing_run"] == 0
                and stats["used"] >= 5,
            }

        return dict(
            sorted(
                result.items(),
                key=lambda x: x[1]["failure_catch_rate"],
                reverse=True,
            )
        )

    def insight_count(self) -> int:
        """Return the total number of stored insights."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM insights")
        row = cursor.fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def clear(self) -> None:
        """Delete all data from the brain store."""
        conn = self._get_conn()
        conn.executescript(
            """
            DELETE FROM insights;
            DELETE FROM patterns;
            DELETE FROM recommendations;
        """
        )
        conn.commit()
