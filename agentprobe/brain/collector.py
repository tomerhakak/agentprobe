"""Collects anonymized telemetry from test runs and recordings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional


@dataclass
class AnonymizedInsight:
    """A single anonymized data point -- NO PII, NO prompts, NO outputs."""

    timestamp: str
    # What framework/model was used
    framework: str  # "langchain", "openai", etc.
    model: str  # "gpt-4o", "claude-sonnet", etc.
    # Performance metrics (ranges, not exact)
    cost_bucket: str  # "<$0.01", "$0.01-$0.05", "$0.05-$0.10", "$0.10-$0.50", ">$0.50"
    latency_bucket: str  # "<1s", "1-3s", "3-5s", "5-10s", ">10s"
    token_bucket: str  # "<500", "500-1K", "1K-5K", "5K-10K", ">10K"
    step_count: int
    # Test results
    assertions_used: List[str] = field(
        default_factory=list
    )  # ["output_contains", "called_tool", "total_cost_less_than"]
    assertions_passed: int = 0
    assertions_failed: int = 0
    # Failure patterns
    failure_types: List[str] = field(
        default_factory=list
    )  # ["output_mismatch", "cost_exceeded", "pii_detected"]
    # Agent behavior
    tools_used: List[str] = field(
        default_factory=list
    )  # tool names only, no inputs/outputs
    had_errors: bool = False
    output_status: str = "success"  # "success", "error", "timeout"


class InsightCollector:
    """Collects and anonymizes insights from recordings and test results."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def collect_from_recording(self, recording: Any) -> Optional[AnonymizedInsight]:
        """Extract anonymized insight from a recording. Returns None if disabled."""
        if not self.enabled:
            return None

        # Import here to avoid circular deps
        from agentprobe.core.models import AgentRecording, StepType

        rec: AgentRecording = recording

        # Determine model from environment or LLM steps
        model = rec.environment.model or ""
        if not model:
            for step in rec.steps:
                if step.llm_call is not None:
                    model = step.llm_call.model
                    break

        # Gather tool names (just names, never inputs/outputs)
        tools_used: list[str] = []
        for step in rec.steps:
            if step.tool_call is not None and step.tool_call.tool_name:
                if step.tool_call.tool_name not in tools_used:
                    tools_used.append(step.tool_call.tool_name)

        # Check for errors
        had_errors = any(
            step.tool_call is not None and not step.tool_call.success
            for step in rec.steps
        )

        return AnonymizedInsight(
            timestamp=datetime.now(timezone.utc).isoformat(),
            framework=rec.metadata.agent_framework or "unknown",
            model=model or "unknown",
            cost_bucket=self._bucketize_cost(rec.total_cost),
            latency_bucket=self._bucketize_latency(rec.total_duration),
            token_bucket=self._bucketize_tokens(rec.total_tokens),
            step_count=rec.step_count,
            assertions_used=[],
            assertions_passed=0,
            assertions_failed=0,
            failure_types=[],
            tools_used=tools_used,
            had_errors=had_errors,
            output_status=rec.output.status.value if rec.output else "success",
        )

    def collect_from_test_results(
        self, results: list[Any]
    ) -> list[AnonymizedInsight]:
        """Extract anonymized insights from test results."""
        if not self.enabled:
            return []

        insights: list[AnonymizedInsight] = []

        for result in results:
            # Each result is expected to be a dict or object with standard fields
            # Support both dict and object access
            def _get(obj: Any, key: str, default: Any = None) -> Any:
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            framework = _get(result, "framework", "unknown") or "unknown"
            model = _get(result, "model", "unknown") or "unknown"
            cost = float(_get(result, "total_cost_usd", 0) or 0)
            latency = float(_get(result, "total_latency_ms", 0) or 0)
            tokens = int(_get(result, "total_tokens", 0) or 0)
            step_count = int(_get(result, "step_count", 0) or 0)

            # Assertion data
            assertion_results = _get(result, "assertion_results", []) or []
            assertions_used: list[str] = []
            assertions_passed = 0
            assertions_failed = 0
            failure_types: list[str] = []

            for ar in assertion_results:
                name = _get(ar, "name", "") or _get(ar, "type", "")
                passed = _get(ar, "passed", False)
                if name and name not in assertions_used:
                    assertions_used.append(name)
                if passed:
                    assertions_passed += 1
                else:
                    assertions_failed += 1
                    failure_type = _get(ar, "failure_type", "") or _get(
                        ar, "name", ""
                    )
                    if failure_type and failure_type not in failure_types:
                        failure_types.append(failure_type)

            tools_used = _get(result, "tools_used", []) or []
            had_errors = _get(result, "had_errors", False)
            output_status = _get(result, "output_status", "success") or "success"

            insights.append(
                AnonymizedInsight(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    framework=framework,
                    model=model,
                    cost_bucket=self._bucketize_cost(cost),
                    latency_bucket=self._bucketize_latency(latency),
                    token_bucket=self._bucketize_tokens(tokens),
                    step_count=step_count,
                    assertions_used=assertions_used,
                    assertions_passed=assertions_passed,
                    assertions_failed=assertions_failed,
                    failure_types=failure_types,
                    tools_used=tools_used if isinstance(tools_used, list) else [],
                    had_errors=bool(had_errors),
                    output_status=str(output_status),
                )
            )

        return insights

    # ------------------------------------------------------------------
    # Bucketization — ensures no exact values are shared
    # ------------------------------------------------------------------

    def _bucketize_cost(self, cost: float) -> str:
        """Convert exact cost to a range bucket."""
        if cost < 0.01:
            return "<$0.01"
        elif cost < 0.05:
            return "$0.01-$0.05"
        elif cost < 0.10:
            return "$0.05-$0.10"
        elif cost < 0.50:
            return "$0.10-$0.50"
        else:
            return ">$0.50"

    def _bucketize_latency(self, latency_ms: float) -> str:
        """Convert exact latency (ms) to a range bucket."""
        seconds = latency_ms / 1000.0
        if seconds < 1:
            return "<1s"
        elif seconds < 3:
            return "1-3s"
        elif seconds < 5:
            return "3-5s"
        elif seconds < 10:
            return "5-10s"
        else:
            return ">10s"

    def _bucketize_tokens(self, tokens: int) -> str:
        """Convert exact token count to a range bucket."""
        if tokens < 500:
            return "<500"
        elif tokens < 1000:
            return "500-1K"
        elif tokens < 5000:
            return "1K-5K"
        elif tokens < 10000:
            return "5K-10K"
        else:
            return ">10K"
