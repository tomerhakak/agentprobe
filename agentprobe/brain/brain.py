"""Main Brain class -- the entry point for the learning system."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agentprobe.brain.collector import AnonymizedInsight, InsightCollector
from agentprobe.brain.recommender import BrainRecommender, Recommendation
from agentprobe.brain.store import BrainStore
from agentprobe.brain.sync import BrainSync

logger = logging.getLogger(__name__)


@dataclass
class BrainConfig:
    """Configuration for the brain system."""

    enabled: bool = False
    sync_enabled: bool = False
    sync_url: str = "https://brain.agentprobe.dev/api/v1"
    db_path: str = ".agentprobe/brain.db"
    queue_dir: str = ".agentprobe/brain_queue"


class Brain:
    """AgentProbe's learning engine.

    The brain collects anonymized insights from your test runs,
    learns patterns, and provides recommendations to improve your agents.

    Privacy: NO prompts, NO outputs, NO PII are ever collected.
    Only anonymized metrics: cost ranges, model names, assertion results,
    failure types.
    """

    def __init__(
        self,
        enabled: bool = False,
        sync_enabled: bool = False,
        config: Optional[BrainConfig] = None,
    ) -> None:
        """
        Args:
            enabled: Enable local brain (collects insights locally).
            sync_enabled: Enable remote sync (shares anonymized data for
                          global learning).
            config: Optional full config; overrides enabled/sync_enabled.
        """
        if config is not None:
            self._config = config
        else:
            self._config = BrainConfig(
                enabled=enabled,
                sync_enabled=sync_enabled,
            )

        self._collector = InsightCollector(enabled=self._config.enabled)

        # Lazily initialized to avoid creating DB files when disabled
        self._store: Optional[BrainStore] = None
        self._recommender: Optional[BrainRecommender] = None
        self._sync: Optional[BrainSync] = None

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_store(self) -> BrainStore:
        if self._store is None:
            self._store = BrainStore(db_path=self._config.db_path)
        return self._store

    def _get_recommender(self) -> BrainRecommender:
        if self._recommender is None:
            self._recommender = BrainRecommender(store=self._get_store())
        return self._recommender

    def _get_sync(self) -> BrainSync:
        if self._sync is None:
            self._sync = BrainSync(
                enabled=self._config.sync_enabled,
                api_url=self._config.sync_url,
                queue_dir=self._config.queue_dir,
            )
        return self._sync

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def learn_from_recording(self, recording: Any) -> Optional[AnonymizedInsight]:
        """Process a recording and extract learnings.

        Returns the anonymized insight if brain is enabled, None otherwise.
        """
        if not self._config.enabled:
            return None

        insight = self._collector.collect_from_recording(recording)
        if insight is None:
            return None

        store = self._get_store()
        store.store_insight(insight)
        logger.debug("Brain learned from recording (total: %d).", store.insight_count())

        # Optionally sync
        if self._config.sync_enabled:
            self._get_sync().sync_insights([insight])

        return insight

    def learn_from_test_results(
        self, results: Any
    ) -> List[AnonymizedInsight]:
        """Process test results and extract learnings.

        Returns the list of anonymized insights if brain is enabled.
        """
        if not self._config.enabled:
            return []

        if not isinstance(results, list):
            results = [results]

        insights = self._collector.collect_from_test_results(results)
        if not insights:
            return []

        store = self._get_store()
        for insight in insights:
            store.store_insight(insight)

        logger.debug(
            "Brain learned from %d test result(s) (total: %d).",
            len(insights),
            store.insight_count(),
        )

        # Optionally sync
        if self._config.sync_enabled:
            self._get_sync().sync_insights(insights)

        return insights

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def recommend(self) -> List[Recommendation]:
        """Get personalized recommendations based on your patterns."""
        if not self._config.enabled:
            return []
        return self._get_recommender().get_recommendations()

    # ------------------------------------------------------------------
    # Stats & reporting
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Get brain statistics: how many insights, patterns found, etc."""
        if not self._config.enabled:
            return {"enabled": False, "insight_count": 0}

        store = self._get_store()
        patterns = store.get_patterns()
        model_stats = store.get_model_stats()

        return {
            "enabled": True,
            "sync_enabled": self._config.sync_enabled,
            "insight_count": store.insight_count(),
            "models_tracked": len(model_stats),
            "frameworks_tracked": len(patterns.get("pass_rates_by_framework", {})),
            "unique_assertions": len(patterns.get("assertions_used", {})),
            "unique_failure_types": len(patterns.get("failure_types", {})),
            "error_rate": patterns.get("error_rate", 0),
            "avg_steps": patterns.get("step_distribution", {}).get("avg", 0),
        }

    def report(self) -> str:
        """Generate a human-readable brain report with recommendations."""
        if not self._config.enabled:
            return (
                "Brain is disabled. Enable it with:\n"
                "  agentprobe config set brain.enabled true\n"
                "or set enabled: true under brain: in agentprobe.yaml"
            )

        stats = self.stats()
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  AgentProbe Brain Report")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  Insights collected:   {stats['insight_count']}")
        lines.append(f"  Models tracked:       {stats['models_tracked']}")
        lines.append(f"  Frameworks tracked:   {stats['frameworks_tracked']}")
        lines.append(f"  Assertion types seen: {stats['unique_assertions']}")
        lines.append(f"  Failure types seen:   {stats['unique_failure_types']}")
        lines.append(f"  Error rate:           {stats['error_rate']}%")
        lines.append(f"  Avg steps/run:        {stats['avg_steps']}")
        lines.append(f"  Remote sync:          {'on' if stats['sync_enabled'] else 'off'}")
        lines.append("")

        # Model breakdown
        model_stats = self._get_store().get_model_stats()
        if model_stats:
            lines.append("-" * 60)
            lines.append("  Model Performance")
            lines.append("-" * 60)
            for model, ms in model_stats.items():
                lines.append(
                    f"  {model}: {ms['pass_rate']}% pass rate, "
                    f"~{ms['avg_steps']} steps/run, "
                    f"{ms['error_rate']}% errors "
                    f"({ms['run_count']} runs)"
                )
            lines.append("")

        # Recommendations
        recs = self.recommend()
        if recs:
            lines.append("-" * 60)
            lines.append(f"  Recommendations ({len(recs)})")
            lines.append("-" * 60)
            for i, rec in enumerate(recs, 1):
                priority_marker = (
                    "!!!" if rec.priority == "high" else "!!" if rec.priority == "medium" else "!"
                )
                lines.append(f"  {i}. [{rec.type.upper()}] {priority_marker} {rec.title}")
                lines.append(f"     {rec.description}")
                lines.append(f"     -> {rec.action}")
                lines.append("")
        else:
            lines.append("  No recommendations yet.")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all brain data."""
        if self._store is not None:
            self._store.clear()
            logger.info("Brain data cleared.")

    @property
    def is_enabled(self) -> bool:
        """Whether the brain is enabled."""
        return self._config.enabled

    @property
    def insight_count(self) -> int:
        """Number of insights stored."""
        if not self._config.enabled:
            return 0
        return self._get_store().insight_count()

    def close(self) -> None:
        """Close database connections."""
        if self._store is not None:
            self._store.close()
