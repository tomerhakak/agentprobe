"""Optional remote sync -- sends anonymized insights to central brain API."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentprobe.brain.collector import AnonymizedInsight

logger = logging.getLogger(__name__)


class BrainSync:
    """Syncs anonymized insights with remote brain API (opt-in only).

    All data is anonymized before leaving the machine.  The sync is
    best-effort: failures are logged but never raise.  Insights that
    fail to sync are written to a local queue file and retried on the
    next sync call.
    """

    BRAIN_API_URL = "https://brain.agentprobe.dev/api/v1"  # future endpoint

    def __init__(
        self,
        enabled: bool = False,
        api_url: Optional[str] = None,
        queue_dir: str = ".agentprobe/brain_queue",
    ) -> None:
        self.enabled = enabled
        self.api_url = api_url or self.BRAIN_API_URL
        self.queue_dir = queue_dir

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def sync_insights(self, insights: List[AnonymizedInsight]) -> bool:
        """Upload anonymized insights to central brain. Returns success.

        If the network call fails the insights are queued locally so
        they can be retried later.
        """
        if not self.enabled or not insights:
            return False

        payload = [self._insight_to_dict(i) for i in insights]

        try:
            import urllib.request
            import urllib.error

            data = json.dumps({"insights": payload}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_url}/insights",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200 or resp.status == 201:
                    logger.debug("Synced %d insights to brain API.", len(insights))
                    # Try to flush any queued insights
                    self._flush_queue()
                    return True
                else:
                    logger.warning(
                        "Brain API returned status %d. Queueing insights.",
                        resp.status,
                    )
                    self._queue_insights(payload)
                    return False

        except Exception as exc:
            logger.debug(
                "Brain API sync failed (offline or unavailable): %s. Queueing insights.",
                exc,
            )
            self._queue_insights(payload)
            return False

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def fetch_global_patterns(self) -> Optional[Dict[str, Any]]:
        """Download aggregated patterns from the global brain.

        This is how individual users benefit from collective learning.
        Returns None on any failure.
        """
        if not self.enabled:
            return None

        try:
            import urllib.request

            req = urllib.request.Request(
                f"{self.api_url}/patterns",
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug("Failed to fetch global patterns: %s", exc)

        return None

    def fetch_global_recommendations(
        self, context: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """Get recommendations based on global patterns.

        Args:
            context: Dict with keys like ``framework``, ``model``,
                     ``assertion_types_used``.

        Returns None on any failure.
        """
        if not self.enabled:
            return None

        try:
            import urllib.request

            data = json.dumps(context).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_url}/recommendations",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug("Failed to fetch global recommendations: %s", exc)

        return None

    # ------------------------------------------------------------------
    # Local queue (for offline resilience)
    # ------------------------------------------------------------------

    def _queue_insights(self, payload: List[Dict[str, Any]]) -> None:
        """Write insights to a local queue file for later retry."""
        try:
            queue_path = Path(self.queue_dir)
            queue_path.mkdir(parents=True, exist_ok=True)

            # Append to a single queue file
            queue_file = queue_path / "pending.jsonl"
            with open(queue_file, "a", encoding="utf-8") as f:
                for item in payload:
                    f.write(json.dumps(item) + "\n")
        except Exception as exc:
            logger.debug("Failed to queue insights: %s", exc)

    def _flush_queue(self) -> None:
        """Try to upload any queued insights."""
        queue_file = Path(self.queue_dir) / "pending.jsonl"
        if not queue_file.exists():
            return

        try:
            lines = queue_file.read_text(encoding="utf-8").strip().split("\n")
            if not lines or lines == [""]:
                return

            payload = [json.loads(line) for line in lines if line.strip()]
            if not payload:
                return

            import urllib.request

            data = json.dumps({"insights": payload}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_url}/insights",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    # Successfully flushed, remove queue
                    queue_file.unlink(missing_ok=True)
                    logger.debug("Flushed %d queued insights.", len(payload))
        except Exception as exc:
            logger.debug("Failed to flush queue: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _insight_to_dict(insight: AnonymizedInsight) -> Dict[str, Any]:
        """Convert an AnonymizedInsight to a JSON-serializable dict."""
        return {
            "timestamp": insight.timestamp,
            "framework": insight.framework,
            "model": insight.model,
            "cost_bucket": insight.cost_bucket,
            "latency_bucket": insight.latency_bucket,
            "token_bucket": insight.token_bucket,
            "step_count": insight.step_count,
            "assertions_used": insight.assertions_used,
            "assertions_passed": insight.assertions_passed,
            "assertions_failed": insight.assertions_failed,
            "failure_types": insight.failure_types,
            "tools_used": insight.tools_used,
            "had_errors": insight.had_errors,
            "output_status": insight.output_status,
        }
