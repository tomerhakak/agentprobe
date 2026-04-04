"""Agent Path Coverage Tracker.

Like code coverage, but for agent execution paths. Tracks which tools,
decision branches, step patterns, and strategies an agent has exercised
across multiple recordings/test runs.

Helps answer: "Have we tested all the ways this agent can behave?"

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ToolCoverage:
    """Coverage stats for a single tool."""

    name: str
    times_called: int = 0
    times_succeeded: int = 0
    times_failed: int = 0
    unique_inputs: int = 0
    recordings_seen: int = 0

    @property
    def success_rate(self) -> float:
        if self.times_called == 0:
            return 0.0
        return self.times_succeeded / self.times_called

    @property
    def is_covered(self) -> bool:
        return self.times_called > 0


@dataclass
class BranchCoverage:
    """Coverage of a decision branch."""

    decision_type: str
    reason: str
    times_taken: int = 0
    recordings_seen: int = 0


@dataclass
class PatternCoverage:
    """Coverage of a step sequence pattern."""

    pattern: str  # e.g. "LTL", "LTTTDL"
    description: str = ""
    times_seen: int = 0
    recordings: List[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    """Complete agent path coverage report."""

    total_recordings: int = 0
    total_steps_analyzed: int = 0

    # Tool coverage
    tools_available: List[str] = field(default_factory=list)
    tools_covered: List[str] = field(default_factory=list)
    tools_uncovered: List[str] = field(default_factory=list)
    tool_coverage_pct: float = 0.0
    tool_details: List[ToolCoverage] = field(default_factory=list)

    # Branch coverage
    branches_covered: int = 0
    branches_total: int = 0
    branch_coverage_pct: float = 0.0
    branch_details: List[BranchCoverage] = field(default_factory=list)

    # Pattern coverage
    unique_patterns: int = 0
    pattern_details: List[PatternCoverage] = field(default_factory=list)

    # Step type coverage
    step_type_counts: Dict[str, int] = field(default_factory=dict)
    step_types_covered: List[str] = field(default_factory=list)
    step_types_uncovered: List[str] = field(default_factory=list)

    # Model coverage
    models_used: Dict[str, int] = field(default_factory=dict)

    # Error coverage
    error_paths_tested: int = 0
    error_recovery_paths: int = 0

    # Overall
    overall_coverage_pct: float = 0.0
    grade: str = ""
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_recordings": self.total_recordings,
            "tool_coverage": {
                "covered": len(self.tools_covered),
                "total": len(self.tools_available),
                "pct": round(self.tool_coverage_pct, 1),
                "uncovered": self.tools_uncovered,
            },
            "branch_coverage": {
                "covered": self.branches_covered,
                "total": self.branches_total,
                "pct": round(self.branch_coverage_pct, 1),
            },
            "pattern_coverage": {
                "unique_patterns": self.unique_patterns,
            },
            "overall_coverage_pct": round(self.overall_coverage_pct, 1),
            "grade": self.grade,
            "suggestions": self.suggestions,
        }


# ---------------------------------------------------------------------------
# Coverage Tracker
# ---------------------------------------------------------------------------

class CoverageTracker:
    """Track and report agent behavioral coverage across recordings.

    Usage::

        tracker = CoverageTracker()

        # Add available tools (from agent config)
        tracker.set_available_tools(["web_search", "calculator", "file_read", "file_write"])

        # Feed recordings
        tracker.add(recording1)
        tracker.add(recording2)

        # Generate report
        report = tracker.report()
        print(f"Coverage: {report.overall_coverage_pct:.1f}%")
        print(f"Uncovered tools: {report.tools_uncovered}")
    """

    def __init__(self) -> None:
        self._recordings: List[AgentRecording] = []
        self._available_tools: Set[str] = set()
        self._tool_stats: Dict[str, ToolCoverage] = {}
        self._branches: Dict[str, BranchCoverage] = {}
        self._patterns: Counter = Counter()
        self._pattern_recordings: Dict[str, List[str]] = defaultdict(list)
        self._step_type_counts: Counter = Counter()
        self._model_counts: Counter = Counter()
        self._error_count = 0
        self._recovery_count = 0

    def set_available_tools(self, tools: Sequence[str]) -> None:
        """Set the list of tools available to the agent."""
        self._available_tools = set(tools)

    def add(self, recording: AgentRecording) -> None:
        """Add a recording to the coverage tracker."""
        self._recordings.append(recording)
        rec_name = recording.metadata.name or recording.metadata.id

        # Track tools from environment
        for tool_def in recording.environment.tools_available:
            self._available_tools.add(tool_def.name)

        tools_in_this_rec: Set[str] = set()

        for step in recording.steps:
            self._step_type_counts[step.type.value] += 1

            if step.tool_call:
                name = step.tool_call.tool_name
                self._available_tools.add(name)
                if name not in self._tool_stats:
                    self._tool_stats[name] = ToolCoverage(name=name)
                tc = self._tool_stats[name]
                tc.times_called += 1
                if step.tool_call.success:
                    tc.times_succeeded += 1
                else:
                    tc.times_failed += 1
                    self._error_count += 1
                tools_in_this_rec.add(name)

            if step.llm_call:
                self._model_counts[step.llm_call.model] += 1

            if step.decision:
                key = f"{step.decision.type.value}:{step.decision.reason[:50]}"
                if key not in self._branches:
                    self._branches[key] = BranchCoverage(
                        decision_type=step.decision.type.value,
                        reason=step.decision.reason,
                    )
                self._branches[key].times_taken += 1
                self._branches[key].recordings_seen += 1

        for name in tools_in_this_rec:
            self._tool_stats[name].recordings_seen += 1

        # Track recovery (tool failure followed by successful tool call)
        for i, step in enumerate(recording.steps):
            if step.tool_call and not step.tool_call.success:
                for future in recording.steps[i+1:i+5]:
                    if future.tool_call and future.tool_call.success:
                        self._recovery_count += 1
                        break

        # Track step patterns (sliding window of 3)
        pattern = self._extract_pattern(recording)
        for window_size in (2, 3, 4):
            for i in range(len(pattern) - window_size + 1):
                sub = pattern[i:i + window_size]
                self._patterns[sub] += 1
                if rec_name not in self._pattern_recordings[sub]:
                    self._pattern_recordings[sub].append(rec_name)

    def report(self) -> CoverageReport:
        """Generate a comprehensive coverage report."""
        report = CoverageReport()
        report.total_recordings = len(self._recordings)
        report.total_steps_analyzed = sum(len(r.steps) for r in self._recordings)

        # Tool coverage
        report.tools_available = sorted(self._available_tools)
        report.tools_covered = sorted(
            name for name, tc in self._tool_stats.items() if tc.is_covered
        )
        report.tools_uncovered = sorted(
            self._available_tools - set(report.tools_covered)
        )
        if self._available_tools:
            report.tool_coverage_pct = len(report.tools_covered) / len(self._available_tools) * 100
        report.tool_details = sorted(self._tool_stats.values(), key=lambda t: t.times_called, reverse=True)

        # Branch coverage
        report.branch_details = list(self._branches.values())
        report.branches_covered = len(self._branches)
        all_decision_types = {"route", "retry", "delegate", "stop"}
        report.branches_total = max(len(all_decision_types), len(self._branches))
        report.branch_coverage_pct = (report.branches_covered / max(report.branches_total, 1)) * 100

        # Pattern coverage
        report.pattern_details = [
            PatternCoverage(
                pattern=p,
                description=self._describe_pattern(p),
                times_seen=c,
                recordings=self._pattern_recordings.get(p, []),
            )
            for p, c in self._patterns.most_common(20)
        ]
        report.unique_patterns = len(self._patterns)

        # Step type coverage
        report.step_type_counts = dict(self._step_type_counts)
        all_types = {"llm_call", "tool_call", "tool_result", "decision", "handoff", "memory_read", "memory_write"}
        report.step_types_covered = sorted(self._step_type_counts.keys())
        report.step_types_uncovered = sorted(all_types - set(report.step_types_covered))

        # Model coverage
        report.models_used = dict(self._model_counts.most_common())

        # Error coverage
        report.error_paths_tested = self._error_count
        report.error_recovery_paths = self._recovery_count

        # Overall coverage (weighted average)
        tool_weight = 0.40
        branch_weight = 0.25
        type_weight = 0.20
        error_weight = 0.15

        type_cov = len(report.step_types_covered) / max(len(all_types), 1) * 100
        error_cov = min(100, self._error_count * 20)  # At least 5 error tests for 100%

        report.overall_coverage_pct = (
            report.tool_coverage_pct * tool_weight +
            report.branch_coverage_pct * branch_weight +
            type_cov * type_weight +
            error_cov * error_weight
        )

        report.grade = self._grade(report.overall_coverage_pct)
        report.suggestions = self._suggest(report)

        return report

    # -- Rendering ---------------------------------------------------------

    def render_report(self, report: CoverageReport) -> str:
        """Render a text coverage report."""
        bar_filled = "\u2588"
        bar_empty = "\u2591"
        bar_width = 25

        def bar(pct: float) -> str:
            filled = round(pct / 100 * bar_width)
            return bar_filled * filled + bar_empty * (bar_width - filled)

        lines: List[str] = []
        lines.append("\U0001f4ca AGENT COVERAGE REPORT")
        lines.append(f"   Recordings analyzed: {report.total_recordings}")
        lines.append(f"   Steps analyzed: {report.total_steps_analyzed}")
        lines.append("")

        # Tool coverage
        lines.append(f"\U0001f527 Tool Coverage: {report.tool_coverage_pct:.0f}%")
        lines.append(f"   {bar(report.tool_coverage_pct)} {len(report.tools_covered)}/{len(report.tools_available)}")
        if report.tools_uncovered:
            lines.append(f"   Uncovered: {', '.join(report.tools_uncovered[:5])}")

        # Branch coverage
        lines.append(f"\n\U0001f500 Branch Coverage: {report.branch_coverage_pct:.0f}%")
        lines.append(f"   {bar(report.branch_coverage_pct)} {report.branches_covered}/{report.branches_total}")

        # Pattern coverage
        lines.append(f"\n\U0001f9ec Unique Patterns: {report.unique_patterns}")
        for pc in report.pattern_details[:5]:
            lines.append(f"   [{pc.pattern}] {pc.description} ({pc.times_seen}x)")

        # Error coverage
        lines.append(f"\n\u26a0\ufe0f Error Paths: {report.error_paths_tested} tested, {report.error_recovery_paths} recovered")

        # Overall
        lines.append(f"\n\U0001f3af Overall Coverage: {report.overall_coverage_pct:.0f}% ({report.grade})")
        lines.append(f"   {bar(report.overall_coverage_pct)}")

        if report.suggestions:
            lines.append("\n\U0001f4a1 Suggestions:")
            for s in report.suggestions:
                lines.append(f"   \u2022 {s}")

        return "\n".join(lines)

    # -- Internal ----------------------------------------------------------

    def _extract_pattern(self, recording: AgentRecording) -> str:
        mapping = {
            StepType.LLM_CALL: "L", StepType.TOOL_CALL: "T",
            StepType.TOOL_RESULT: "R", StepType.DECISION: "D",
            StepType.HANDOFF: "H", StepType.MEMORY_READ: "M",
            StepType.MEMORY_WRITE: "W",
        }
        return "".join(mapping.get(s.type, "?") for s in recording.steps)

    def _describe_pattern(self, pattern: str) -> str:
        labels = {"L": "think", "T": "tool", "R": "result", "D": "decide", "H": "handoff", "M": "memory", "W": "write"}
        return " \u2192 ".join(labels.get(c, c) for c in pattern)

    def _grade(self, pct: float) -> str:
        if pct >= 90:
            return "A+"
        if pct >= 80:
            return "A"
        if pct >= 65:
            return "B"
        if pct >= 50:
            return "C"
        if pct >= 35:
            return "D"
        return "F"

    def _suggest(self, report: CoverageReport) -> List[str]:
        suggestions: List[str] = []
        if report.tools_uncovered:
            suggestions.append(f"Add tests that exercise: {', '.join(report.tools_uncovered[:3])}")
        if report.error_paths_tested == 0:
            suggestions.append("No error paths tested! Add tests with intentional tool failures.")
        if "decision" in report.step_types_uncovered:
            suggestions.append("No decision steps tested — add tests with routing/branching agents.")
        if "handoff" in report.step_types_uncovered:
            suggestions.append("No handoff steps tested — add multi-agent delegation tests.")
        if report.unique_patterns < 3:
            suggestions.append("Low pattern diversity — add diverse test scenarios to exercise different agent strategies.")
        if not suggestions:
            suggestions.append("Great coverage! Consider adding edge-case and adversarial tests.")
        return suggestions
