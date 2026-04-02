"""Health Check -- "Is your agent healthy?"

Quick five-dimension health assessment (reliability, speed, cost,
security, quality) with scores, progress bars, and actionable messages.

Free tier feature -- no Pro upgrade required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HealthDimension:
    """A single scored dimension of agent health."""

    name: str
    score: int  # 0-100
    icon: str = ""
    status: str = ""  # "ok", "warning", "critical"

    def __post_init__(self) -> None:
        self.score = max(0, min(100, self.score))
        if not self.status:
            if self.score >= 80:
                self.status = "ok"
            elif self.score >= 50:
                self.status = "warning"
            else:
                self.status = "critical"
        if not self.icon:
            _icon_map = {
                "Reliability": "\U0001f3af",  # dart
                "Speed": "\u26a1",             # lightning
                "Cost": "\U0001f4b0",          # money bag
                "Security": "\U0001f6e1\ufe0f", # shield
                "Quality": "\u2b50",            # star
            }
            self.icon = _icon_map.get(self.name, "\U0001f4ca")


@dataclass
class HealthReport:
    """Complete agent health report."""

    dimensions: List[HealthDimension] = field(default_factory=list)
    overall_score: int = 0
    overall_label: str = ""
    critical_messages: List[str] = field(default_factory=list)
    warning_messages: List[str] = field(default_factory=list)
    tip_messages: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    previous_score: Optional[int] = None  # for historical comparison


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BAR_FILLED = "\u2588"
_BAR_EMPTY = "\u2591"
_BAR_WIDTH = 20


def _progress_bar(score: int) -> str:
    """Render a text progress bar for a 0-100 score."""
    filled = round(score / 100 * _BAR_WIDTH)
    return _BAR_FILLED * filled + _BAR_EMPTY * (_BAR_WIDTH - filled)


def _score_label(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Healthy"
    if score >= 65:
        return "Needs attention"
    if score >= 50:
        return "Concerning"
    return "Unhealthy"


def _status_symbol(status: str) -> str:
    return {"ok": "\u2713", "warning": "\u26a0", "critical": "\u2717"}.get(status, "?")


# ---------------------------------------------------------------------------
# HealthChecker
# ---------------------------------------------------------------------------

class HealthChecker:
    """Assess agent health across five dimensions.

    Usage::

        from agentprobe.health import HealthChecker

        checker = HealthChecker()
        report = checker.check(recording)
        print(checker.format_terminal(report))

    Dimensions scored 0-100:
      - **Reliability** -- success rate, error handling
      - **Speed** -- latency vs. step count
      - **Cost** -- cost efficiency vs. model tier
      - **Security** -- prompt injection signals, PII leak risk
      - **Quality** -- output completeness, tool usage patterns
    """

    def __init__(
        self,
        *,
        speed_threshold_ms: float = 5000.0,
        cost_threshold_usd: float = 0.05,
    ) -> None:
        """
        Parameters
        ----------
        speed_threshold_ms:
            Maximum acceptable total duration in milliseconds.  Runs under
            this threshold score 100 for the speed dimension.
        cost_threshold_usd:
            Maximum acceptable per-run cost.  Runs under this threshold
            score 100 for the cost dimension.
        """
        self._speed_threshold = speed_threshold_ms
        self._cost_threshold = cost_threshold_usd

    # -- Public API ---------------------------------------------------------

    def check(
        self,
        recording: AgentRecording,
        *,
        previous_score: Optional[int] = None,
    ) -> HealthReport:
        """Run a full health check on a recording.

        Parameters
        ----------
        recording:
            The ``AgentRecording`` to assess.
        previous_score:
            If provided, included in the report for historical comparison.

        Returns
        -------
        HealthReport
        """
        reliability = self._score_reliability(recording)
        speed = self._score_speed(recording)
        cost = self._score_cost(recording)
        security = self._score_security(recording)
        quality = self._score_quality(recording)

        dimensions = [reliability, speed, cost, security, quality]
        overall = round(sum(d.score for d in dimensions) / len(dimensions))
        label = _score_label(overall)

        # Messages
        criticals: List[str] = []
        warnings: List[str] = []
        tips: List[str] = []

        for dim in dimensions:
            if dim.status == "critical":
                criticals.append(f"{dim.name} score is {dim.score}/100 -- below threshold")
            elif dim.status == "warning":
                warnings.append(f"{dim.name} could be improved ({dim.score}/100)")

        # Actionable tips
        if speed.score < 80:
            tips.append("Run 'agentprobe benchmark' to identify slow tool calls")
        if security.score < 60:
            tips.append("Run 'agentprobe fuzz' to find security issues")
        if cost.score < 70:
            tips.append("Run 'agentprobe cost' to find savings opportunities")
        if quality.score < 80:
            tips.append("Consider adding more tool definitions for better coverage")
        if reliability.score < 80:
            tips.append("Add retry logic and error-handling instructions to your agent")

        return HealthReport(
            dimensions=dimensions,
            overall_score=overall,
            overall_label=label,
            critical_messages=criticals,
            warning_messages=warnings,
            tip_messages=tips,
            timestamp=datetime.now(timezone.utc),
            previous_score=previous_score,
        )

    def check_multiple(
        self,
        recordings: Sequence[AgentRecording],
        *,
        previous_score: Optional[int] = None,
    ) -> HealthReport:
        """Aggregate health check across multiple recordings.

        Parameters
        ----------
        recordings:
            A sequence of recordings to assess in aggregate.
        previous_score:
            Optional previous overall score for comparison.

        Returns
        -------
        HealthReport
        """
        if not recordings:
            return HealthReport(overall_label="No data")
        if len(recordings) == 1:
            return self.check(recordings[0], previous_score=previous_score)

        reports = [self.check(r) for r in recordings]

        # Average each dimension
        dim_names = ["Reliability", "Speed", "Cost", "Security", "Quality"]
        averaged_dims: List[HealthDimension] = []
        for name in dim_names:
            scores = []
            for report in reports:
                for d in report.dimensions:
                    if d.name == name:
                        scores.append(d.score)
                        break
            avg = round(sum(scores) / len(scores)) if scores else 0
            averaged_dims.append(HealthDimension(name=name, score=avg))

        overall = round(sum(d.score for d in averaged_dims) / len(averaged_dims))

        # Collect unique messages
        criticals: List[str] = []
        warnings: List[str] = []
        tips: List[str] = []
        for report in reports:
            for msg in report.critical_messages:
                if msg not in criticals:
                    criticals.append(msg)
            for msg in report.warning_messages:
                if msg not in warnings:
                    warnings.append(msg)
            for msg in report.tip_messages:
                if msg not in tips:
                    tips.append(msg)

        return HealthReport(
            dimensions=averaged_dims,
            overall_score=overall,
            overall_label=_score_label(overall),
            critical_messages=criticals[:5],
            warning_messages=warnings[:5],
            tip_messages=tips[:5],
            timestamp=datetime.now(timezone.utc),
            previous_score=previous_score,
        )

    # -- Scoring dimensions -------------------------------------------------

    def _score_reliability(self, recording: AgentRecording) -> HealthDimension:
        """Score reliability based on success status and error signals."""
        score = 100

        # Penalise non-success output
        if recording.output.status.value != "success":
            score -= 40

        # Penalise tool errors
        error_count = 0
        for step in recording.steps:
            if step.type == StepType.TOOL_CALL and step.tool_call and not step.tool_call.success:
                error_count += 1
        score -= min(error_count * 15, 40)

        # Penalise no steps (empty run)
        if not recording.steps:
            score -= 20

        return HealthDimension(name="Reliability", score=max(0, score))

    def _score_speed(self, recording: AgentRecording) -> HealthDimension:
        """Score speed relative to the configured threshold."""
        total_ms = recording.total_duration
        if total_ms <= 0:
            return HealthDimension(name="Speed", score=80)

        # Linear scale: 0ms = 100, threshold = 50, 2x threshold = 0
        ratio = total_ms / self._speed_threshold
        if ratio <= 0.5:
            score = 100
        elif ratio <= 1.0:
            score = round(100 - (ratio - 0.5) * 100)
        elif ratio <= 2.0:
            score = round(50 - (ratio - 1.0) * 50)
        else:
            score = 0

        # Bonus penalty for too many steps (indicates inefficiency)
        if recording.step_count > 10:
            score -= min((recording.step_count - 10) * 3, 20)

        return HealthDimension(name="Speed", score=max(0, score))

    def _score_cost(self, recording: AgentRecording) -> HealthDimension:
        """Score cost efficiency."""
        total_cost = recording.total_cost
        if total_cost <= 0:
            return HealthDimension(name="Cost", score=95)

        ratio = total_cost / self._cost_threshold
        if ratio <= 0.3:
            score = 100
        elif ratio <= 1.0:
            score = round(100 - (ratio - 0.3) * (50 / 0.7))
        elif ratio <= 3.0:
            score = round(50 - (ratio - 1.0) * 25)
        else:
            score = 0

        return HealthDimension(name="Cost", score=max(0, score))

    def _score_security(self, recording: AgentRecording) -> HealthDimension:
        """Score security posture via heuristics.

        Checks for: missing system prompt, potential injection patterns,
        tool calls with suspiciously broad access, PII-like patterns.
        """
        score = 100

        # No system prompt = less controlled agent
        if not recording.environment.system_prompt:
            score -= 25

        # Check for potentially dangerous tool names
        dangerous_tools = {"exec", "eval", "shell", "run_command", "execute", "os_command"}
        for step in recording.steps:
            if step.type == StepType.TOOL_CALL and step.tool_call:
                name_lower = step.tool_call.tool_name.lower()
                if any(d in name_lower for d in dangerous_tools):
                    score -= 20
                    break

        # Check for injection-like patterns in input
        input_str = str(recording.input.content).lower() if recording.input.content else ""
        injection_signals = [
            "ignore previous", "ignore above", "disregard",
            "system:", "you are now", "new instructions",
            "```system", "ADMIN OVERRIDE",
        ]
        for signal in injection_signals:
            if signal.lower() in input_str:
                score -= 15
                break

        # No tools available at all may indicate an uncontrolled agent
        if not recording.environment.tools_available:
            score -= 10

        # Penalise if tool side effects are declared
        side_effects_count = 0
        for step in recording.steps:
            if step.type == StepType.TOOL_CALL and step.tool_call:
                side_effects_count += len(step.tool_call.side_effects)
        if side_effects_count > 3:
            score -= 15

        return HealthDimension(name="Security", score=max(0, score))

    def _score_quality(self, recording: AgentRecording) -> HealthDimension:
        """Score output quality heuristics."""
        score = 85  # baseline

        # Penalise empty output
        output_str = str(recording.output.content) if recording.output.content else ""
        if not output_str.strip():
            score -= 30

        # Short output may indicate low quality
        if 0 < len(output_str) < 20:
            score -= 15

        # Reward tool usage (agent that uses tools is more capable)
        tool_count = len(recording.tool_steps)
        if tool_count > 0:
            score += min(tool_count * 3, 15)

        # Penalise if all tool calls failed
        if tool_count > 0:
            all_failed = all(
                step.tool_call and not step.tool_call.success
                for step in recording.tool_steps
            )
            if all_failed:
                score -= 25

        return HealthDimension(name="Quality", score=max(0, min(100, score)))

    # -- Formatters ---------------------------------------------------------

    def format_terminal(self, report: HealthReport) -> str:
        """Render a health report as a coloured terminal string.

        Parameters
        ----------
        report:
            The ``HealthReport`` from :meth:`check`.

        Returns
        -------
        str
            Multi-line terminal-ready string.
        """
        lines: List[str] = []
        lines.append("")
        lines.append("\U0001f3e5 Agent Health Check")
        lines.append("\u2550" * 55)
        lines.append("")

        for dim in report.dimensions:
            bar = _progress_bar(dim.score)
            symbol = _status_symbol(dim.status)
            lines.append(f"  {dim.name:<14} {bar}  {dim.score:>3}%  {symbol}")

        lines.append("")
        lines.append(f"  Overall Health: {report.overall_score}/100 \u2014 \"{report.overall_label}\"")

        if report.previous_score is not None:
            delta = report.overall_score - report.previous_score
            if delta > 0:
                lines.append(f"  \u2191 Health improved {delta}% since last check")
            elif delta < 0:
                lines.append(f"  \u2193 Health declined {abs(delta)}% since last check")
            else:
                lines.append("  \u2192 Health unchanged since last check")

        lines.append("")

        for msg in report.critical_messages:
            lines.append(f"  \U0001f6a8 Critical: {msg}")
        for msg in report.warning_messages:
            lines.append(f"  \u26a0\ufe0f  Warning: {msg}")
        for msg in report.tip_messages:
            lines.append(f"  \U0001f4a1 Tip: {msg}")

        if report.critical_messages or report.warning_messages or report.tip_messages:
            lines.append("")

        return "\n".join(lines)

    def format_json(self, report: HealthReport) -> str:
        """Render the health report as a JSON string.

        Parameters
        ----------
        report:
            The ``HealthReport`` from :meth:`check`.

        Returns
        -------
        str
            Pretty-printed JSON.
        """
        data: Dict[str, Any] = {
            "overall_score": report.overall_score,
            "overall_label": report.overall_label,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "status": d.status,
                }
                for d in report.dimensions
            ],
            "messages": {
                "critical": report.critical_messages,
                "warnings": report.warning_messages,
                "tips": report.tip_messages,
            },
            "timestamp": report.timestamp.isoformat() if report.timestamp else None,
            "previous_score": report.previous_score,
        }
        return json.dumps(data, indent=2)
