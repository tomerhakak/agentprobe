"""Main roast engine — analyzes an agent recording and produces a funny but useful report."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from agentprobe.core.models import AgentRecording, StepType


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RoastLevel(str, Enum):
    """How brutal the comedy should be."""

    MILD = "mild"
    MEDIUM = "medium"
    SAVAGE = "savage"


class RoastCategory(str, Enum):
    """Categories of evaluation."""

    COST = "cost"
    SPEED = "speed"
    INTELLIGENCE = "intelligence"
    SECURITY = "security"
    VERBOSITY = "verbosity"
    TOOL_USAGE = "tool_usage"


class RoastGrade(str, Enum):
    """Letter grades from A+ (best) to F (worst)."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


# ---------------------------------------------------------------------------
# Grade helpers
# ---------------------------------------------------------------------------

_GRADE_ORDER: List[str] = ["F", "D", "C", "B", "A", "A+"]
_GRADE_GPA: Dict[str, float] = {"F": 0.0, "D": 1.0, "C": 2.0, "B": 3.0, "A": 4.0, "A+": 4.3}
_CATEGORY_EMOJI: Dict[str, str] = {
    "cost": "\U0001f4b8",          # 💸
    "speed": "\U0001f40c",         # 🐌
    "intelligence": "\U0001f9e0",  # 🧠
    "security": "\U0001f513",      # 🔓
    "verbosity": "\U0001f5e3",     # 🗣️
    "tool_usage": "\U0001f527",    # 🔧
}
_CATEGORY_LABELS: Dict[str, str] = {
    "cost": "Cost Roast",
    "speed": "Speed Roast",
    "intelligence": "Intelligence Roast",
    "security": "Security Roast",
    "verbosity": "Verbosity Roast",
    "tool_usage": "Tool Usage Roast",
}


def _grade_from_score(score: float) -> RoastGrade:
    """Convert a 0-100 score to a letter grade."""
    if score >= 97:
        return RoastGrade.A_PLUS
    if score >= 85:
        return RoastGrade.A
    if score >= 70:
        return RoastGrade.B
    if score >= 50:
        return RoastGrade.C
    if score >= 30:
        return RoastGrade.D
    return RoastGrade.F


def _overall_grade(grades: Dict[str, RoastGrade]) -> RoastGrade:
    """Compute the overall grade from individual category grades."""
    if not grades:
        return RoastGrade.C
    total_gpa = sum(_GRADE_GPA[g.value] for g in grades.values()) / len(grades)
    if total_gpa >= 4.15:
        return RoastGrade.A_PLUS
    if total_gpa >= 3.5:
        return RoastGrade.A
    if total_gpa >= 2.5:
        return RoastGrade.B
    if total_gpa >= 1.5:
        return RoastGrade.C
    if total_gpa >= 0.5:
        return RoastGrade.D
    return RoastGrade.F


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CategoryResult:
    """Result for a single roast category."""

    category: RoastCategory
    grade: RoastGrade
    score: float  # 0-100
    joke: str
    details: str
    suggestions: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoastReport:
    """Complete roast report for an agent recording."""

    level: RoastLevel
    overall_grade: RoastGrade
    overall_score: float
    summary_line: str
    categories: Dict[str, CategoryResult] = field(default_factory=dict)
    recording_name: str = ""
    agent_framework: str = ""
    total_steps: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the report to a plain dictionary."""
        return {
            "level": self.level.value,
            "overall_grade": self.overall_grade.value,
            "overall_score": round(self.overall_score, 1),
            "summary_line": self.summary_line,
            "recording_name": self.recording_name,
            "agent_framework": self.agent_framework,
            "total_steps": self.total_steps,
            "total_cost_usd": self.total_cost_usd,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "categories": {
                k: {
                    "category": v.category.value,
                    "grade": v.grade.value,
                    "score": round(v.score, 1),
                    "joke": v.joke,
                    "details": v.details,
                    "suggestions": v.suggestions,
                    "metrics": v.metrics,
                }
                for k, v in self.categories.items()
            },
        }


# ---------------------------------------------------------------------------
# Benchmarks (reasonable defaults for grading)
# ---------------------------------------------------------------------------

# Cost: USD per step (LLM call).  Lower is better.
_COST_BENCHMARKS = {
    "excellent": 0.005,   # < $0.005/step -> A
    "good": 0.02,         # < $0.02/step  -> B
    "average": 0.05,      # < $0.05/step  -> C
    "poor": 0.10,         # < $0.10/step  -> D
}

# Speed: ms per step.  Lower is better.
_SPEED_BENCHMARKS = {
    "excellent": 500,
    "good": 1500,
    "average": 3000,
    "poor": 6000,
}

# Verbosity: avg output tokens per LLM call.
_VERBOSITY_BENCHMARKS = {
    "excellent": 150,
    "good": 400,
    "average": 800,
    "poor": 1500,
}

# Tool usage: ratio of tool calls to total steps. A perfectly efficient agent
# uses tools only when needed (~0.3-0.5 ratio).  Too high = wasteful.
_TOOL_RATIO_BENCHMARKS = {
    "excellent": 0.4,
    "good": 0.55,
    "average": 0.7,
    "poor": 0.85,
}


# ---------------------------------------------------------------------------
# Roaster
# ---------------------------------------------------------------------------

class Roaster:
    """Analyzes an ``AgentRecording`` and produces a :class:`RoastReport`."""

    def __init__(self, level: RoastLevel = RoastLevel.MEDIUM) -> None:
        self.level = level
        # Lazy-import jokes to keep module load lightweight.
        from agentprobe.roast.jokes import JOKES, SUMMARY_LINES

        self._jokes = JOKES
        self._summary_lines = SUMMARY_LINES

    # -- Public API --------------------------------------------------------

    def roast(self, recording: AgentRecording) -> RoastReport:
        """Run the full roast analysis and return a ``RoastReport``."""
        categories: Dict[str, CategoryResult] = {}

        categories["cost"] = self._roast_cost(recording)
        categories["speed"] = self._roast_speed(recording)
        categories["intelligence"] = self._roast_intelligence(recording)
        categories["security"] = self._roast_security(recording)
        categories["verbosity"] = self._roast_verbosity(recording)
        categories["tool_usage"] = self._roast_tool_usage(recording)

        grades = {k: v.grade for k, v in categories.items()}
        overall = _overall_grade(grades)
        overall_score = sum(c.score for c in categories.values()) / max(len(categories), 1)

        # Pick a summary one-liner.
        grade_key = overall.value
        if grade_key not in self._summary_lines:
            grade_key = "C"  # fallback
        pool = self._summary_lines[grade_key].get(self.level.value, [])
        summary_line = random.choice(pool) if pool else "No comment."

        return RoastReport(
            level=self.level,
            overall_grade=overall,
            overall_score=overall_score,
            summary_line=summary_line,
            categories=categories,
            recording_name=recording.metadata.name or recording.metadata.id,
            agent_framework=recording.environment.model or recording.metadata.agent_framework,
            total_steps=recording.step_count,
            total_cost_usd=recording.total_cost,
            total_duration_ms=recording.total_duration,
            total_tokens=recording.total_tokens,
        )

    @classmethod
    def roast_recording_file(
        cls,
        path: Union[str, Path],
        level: RoastLevel = RoastLevel.MEDIUM,
    ) -> RoastReport:
        """Convenience: load a recording from disk and roast it."""
        path = Path(path)
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            recording = AgentRecording.model_validate(data)
        else:
            recording = AgentRecording.load(path)
        roaster = cls(level=level)
        return roaster.roast(recording)

    # -- Category analyzers ------------------------------------------------

    def _pick_joke(self, category: str, grade: RoastGrade) -> str:
        """Pick a random joke from the database for the given category/grade/level."""
        grade_key = grade.value
        # A+ uses A jokes in the joke DB (no separate A+ category in per-category jokes).
        if grade_key == "A+":
            grade_key = "A"
        cat_jokes = self._jokes.get(category, {})
        grade_jokes = cat_jokes.get(grade_key, {})
        level_jokes = grade_jokes.get(self.level.value, [])
        return random.choice(level_jokes) if level_jokes else ""

    # -- Cost --------------------------------------------------------------

    def _roast_cost(self, rec: AgentRecording) -> CategoryResult:
        total_cost = rec.total_cost
        llm_count = len(rec.llm_steps)
        cost_per_step = total_cost / max(llm_count, 1)

        if cost_per_step <= _COST_BENCHMARKS["excellent"]:
            score = 95.0
        elif cost_per_step <= _COST_BENCHMARKS["good"]:
            score = 80.0
        elif cost_per_step <= _COST_BENCHMARKS["average"]:
            score = 60.0
        elif cost_per_step <= _COST_BENCHMARKS["poor"]:
            score = 40.0
        else:
            score = 15.0

        # Bonus: if no LLM calls, score is neutral.
        if llm_count == 0:
            score = 75.0

        grade = _grade_from_score(score)
        suggestions: List[str] = []
        if score < 85:
            suggestions.append("Consider using a smaller/cheaper model for simple sub-tasks.")
        if score < 60:
            suggestions.append("Enable prompt caching to reduce redundant input token costs.")
            suggestions.append("Batch similar requests to amortize overhead.")
        if score < 40:
            suggestions.append("Audit each LLM call — many may be unnecessary.")
            suggestions.append("Use structured output to reduce retry costs.")

        return CategoryResult(
            category=RoastCategory.COST,
            grade=grade,
            score=score,
            joke=self._pick_joke("cost", grade),
            details=f"Total cost: ${total_cost:.4f} across {llm_count} LLM call(s) — ${cost_per_step:.4f}/call.",
            suggestions=suggestions,
            metrics={
                "total_cost_usd": round(total_cost, 6),
                "llm_calls": llm_count,
                "cost_per_call_usd": round(cost_per_step, 6),
            },
        )

    # -- Speed -------------------------------------------------------------

    def _roast_speed(self, rec: AgentRecording) -> CategoryResult:
        total_ms = rec.total_duration
        step_count = rec.step_count
        ms_per_step = total_ms / max(step_count, 1)

        if ms_per_step <= _SPEED_BENCHMARKS["excellent"]:
            score = 95.0
        elif ms_per_step <= _SPEED_BENCHMARKS["good"]:
            score = 80.0
        elif ms_per_step <= _SPEED_BENCHMARKS["average"]:
            score = 60.0
        elif ms_per_step <= _SPEED_BENCHMARKS["poor"]:
            score = 40.0
        else:
            score = 15.0

        if step_count == 0:
            score = 75.0

        grade = _grade_from_score(score)

        # Identify bottleneck step.
        bottleneck = ""
        if rec.steps:
            slowest = max(rec.steps, key=lambda s: s.duration_ms)
            bottleneck = (
                f"Slowest step: #{slowest.step_number} ({slowest.type.value}) "
                f"at {slowest.duration_ms:.0f}ms."
            )

        suggestions: List[str] = []
        if score < 85:
            suggestions.append("Profile the slowest steps for optimization opportunities.")
        if score < 60:
            suggestions.append("Consider parallelizing independent tool calls.")
            suggestions.append("Use streaming to reduce perceived latency.")
        if score < 40:
            suggestions.append("Investigate if synchronous blocking calls are stalling the pipeline.")
            suggestions.append("Cache frequent LLM calls with identical inputs.")

        return CategoryResult(
            category=RoastCategory.SPEED,
            grade=grade,
            score=score,
            joke=self._pick_joke("speed", grade),
            details=(
                f"Total duration: {total_ms:.0f}ms across {step_count} step(s) — "
                f"{ms_per_step:.0f}ms/step. {bottleneck}"
            ),
            suggestions=suggestions,
            metrics={
                "total_duration_ms": round(total_ms, 1),
                "steps": step_count,
                "ms_per_step": round(ms_per_step, 1),
            },
        )

    # -- Intelligence ------------------------------------------------------

    def _roast_intelligence(self, rec: AgentRecording) -> CategoryResult:
        """Evaluate response quality using heuristics (no external LLM needed)."""
        llm_steps = rec.llm_steps
        if not llm_steps:
            return CategoryResult(
                category=RoastCategory.INTELLIGENCE,
                grade=RoastGrade.C,
                score=50.0,
                joke=self._pick_joke("intelligence", RoastGrade.C),
                details="No LLM calls found — unable to assess intelligence.",
                suggestions=["Ensure LLM calls are captured in the recording."],
            )

        # Heuristic signals:
        total_calls = len(llm_steps)
        error_steps = sum(
            1 for s in rec.steps
            if s.tool_call and s.tool_call.success is False
        )
        retry_steps = sum(
            1 for s in rec.steps
            if s.decision and s.decision.type.value == "retry"
        )
        success = rec.output.status.value == "success"

        # Score components (weighted).
        error_rate = error_steps / max(total_calls, 1)
        retry_rate = retry_steps / max(total_calls, 1)

        score = 90.0
        score -= error_rate * 40        # errors hurt a lot
        score -= retry_rate * 20        # retries suggest confusion
        if not success:
            score -= 25                 # final failure is a big deal
        score = max(0.0, min(100.0, score))

        grade = _grade_from_score(score)

        suggestions: List[str] = []
        if error_rate > 0.1:
            suggestions.append("Reduce tool call errors — each failed call suggests a reasoning gap.")
        if retry_rate > 0.1:
            suggestions.append("High retry rate indicates the agent is uncertain. Improve prompting.")
        if not success:
            suggestions.append("The agent failed to complete the task. Review the system prompt and tool definitions.")

        hallucination_note = ""
        if error_rate > 0.3:
            hallucination_note = " High error rate may indicate hallucinated tool inputs."

        return CategoryResult(
            category=RoastCategory.INTELLIGENCE,
            grade=grade,
            score=score,
            joke=self._pick_joke("intelligence", grade),
            details=(
                f"{total_calls} LLM call(s), {error_steps} tool error(s), "
                f"{retry_steps} retry decision(s). Final status: {rec.output.status.value}."
                f"{hallucination_note}"
            ),
            suggestions=suggestions,
            metrics={
                "llm_calls": total_calls,
                "tool_errors": error_steps,
                "retries": retry_steps,
                "task_success": success,
                "error_rate": round(error_rate, 3),
            },
        )

    # -- Security ----------------------------------------------------------

    def _roast_security(self, rec: AgentRecording) -> CategoryResult:
        """Quick heuristic security check on the recording."""
        issues: List[str] = []
        severity_points = 0.0

        # Check for PII patterns in messages.
        pii_patterns = [
            (r"\b\d{3}-\d{2}-\d{4}\b", "SSN-like pattern"),
            (r"\b\d{16}\b", "credit-card-like number"),
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email address"),
            (r"(?i)\b(?:password|secret|api[_-]?key|token)\s*[:=]\s*\S+", "credential-like string"),
        ]

        message_texts: List[str] = []
        for msg in rec.messages:
            if isinstance(msg.content, str):
                message_texts.append(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if block.text:
                        message_texts.append(block.text)

        # Also check tool inputs/outputs.
        for step in rec.steps:
            if step.tool_call:
                if step.tool_call.tool_input:
                    message_texts.append(str(step.tool_call.tool_input))
                if step.tool_call.tool_output:
                    message_texts.append(str(step.tool_call.tool_output))

        all_text = "\n".join(message_texts)
        for pattern, label in pii_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                count = len(matches)
                issues.append(f"Found {count} {label}(s) in agent messages/tool data.")
                severity_points += count * 8

        # Check for potential prompt injection markers in tool outputs.
        injection_markers = [
            "ignore previous instructions",
            "ignore all previous",
            "disregard your instructions",
            "you are now",
            "new instructions:",
            "system prompt override",
        ]
        for marker in injection_markers:
            if marker.lower() in all_text.lower():
                issues.append(f"Potential prompt injection detected: '{marker}'.")
                severity_points += 15

        # Check if system prompt is exposed in outputs.
        if rec.environment.system_prompt:
            sys_prompt_fragment = rec.environment.system_prompt[:80].lower()
            for msg in rec.messages:
                content_text = ""
                if isinstance(msg.content, str):
                    content_text = msg.content
                elif isinstance(msg.content, list):
                    content_text = " ".join(b.text or "" for b in msg.content)
                if msg.role == "assistant" and sys_prompt_fragment in content_text.lower():
                    issues.append("System prompt may be leaking in assistant responses.")
                    severity_points += 20
                    break

        score = max(0.0, min(100.0, 100.0 - severity_points))
        grade = _grade_from_score(score)

        suggestions: List[str] = []
        if severity_points > 0:
            suggestions.append("Sanitize all tool outputs before passing them to the LLM context.")
        if severity_points > 20:
            suggestions.append("Add input validation to reject known prompt injection patterns.")
            suggestions.append("Implement PII redaction on agent outputs before returning to users.")
        if severity_points > 50:
            suggestions.append("Consider a dedicated guardrails layer (e.g., Guardrails AI, NeMo Guardrails).")

        if not issues:
            detail_text = "No security issues detected in this recording."
        else:
            detail_text = " ".join(issues)

        return CategoryResult(
            category=RoastCategory.SECURITY,
            grade=grade,
            score=score,
            joke=self._pick_joke("security", grade),
            details=detail_text,
            suggestions=suggestions,
            metrics={
                "issues_found": len(issues),
                "severity_points": severity_points,
                "issues": issues,
            },
        )

    # -- Verbosity ---------------------------------------------------------

    def _roast_verbosity(self, rec: AgentRecording) -> CategoryResult:
        llm_steps = rec.llm_steps
        if not llm_steps:
            return CategoryResult(
                category=RoastCategory.VERBOSITY,
                grade=RoastGrade.C,
                score=50.0,
                joke=self._pick_joke("verbosity", RoastGrade.C),
                details="No LLM calls found — unable to assess verbosity.",
                suggestions=["Ensure LLM calls are captured in the recording."],
            )

        total_output_tokens = sum(
            s.llm_call.output_tokens for s in llm_steps if s.llm_call
        )
        avg_output = total_output_tokens / max(len(llm_steps), 1)

        if avg_output <= _VERBOSITY_BENCHMARKS["excellent"]:
            score = 95.0
        elif avg_output <= _VERBOSITY_BENCHMARKS["good"]:
            score = 80.0
        elif avg_output <= _VERBOSITY_BENCHMARKS["average"]:
            score = 60.0
        elif avg_output <= _VERBOSITY_BENCHMARKS["poor"]:
            score = 40.0
        else:
            score = 15.0

        grade = _grade_from_score(score)

        suggestions: List[str] = []
        if score < 85:
            suggestions.append("Add 'be concise' or max-token guidance to the system prompt.")
        if score < 60:
            suggestions.append("Use structured output (JSON) to force brevity where possible.")
            suggestions.append("Set max_tokens on LLM calls to cap verbose responses.")
        if score < 40:
            suggestions.append("Consider post-processing to summarize long responses before returning to users.")

        return CategoryResult(
            category=RoastCategory.VERBOSITY,
            grade=grade,
            score=score,
            joke=self._pick_joke("verbosity", grade),
            details=(
                f"{total_output_tokens} output tokens across {len(llm_steps)} LLM call(s) — "
                f"avg {avg_output:.0f} tokens/call."
            ),
            suggestions=suggestions,
            metrics={
                "total_output_tokens": total_output_tokens,
                "llm_calls": len(llm_steps),
                "avg_output_tokens": round(avg_output, 1),
            },
        )

    # -- Tool usage --------------------------------------------------------

    def _roast_tool_usage(self, rec: AgentRecording) -> CategoryResult:
        tool_steps = rec.tool_steps
        total_steps = rec.step_count

        if total_steps == 0:
            return CategoryResult(
                category=RoastCategory.TOOL_USAGE,
                grade=RoastGrade.C,
                score=50.0,
                joke=self._pick_joke("tool_usage", RoastGrade.C),
                details="No steps recorded — unable to assess tool usage.",
                suggestions=["Ensure steps are captured in the recording."],
            )

        tool_ratio = len(tool_steps) / total_steps
        failed_tools = sum(
            1 for s in tool_steps if s.tool_call and not s.tool_call.success
        )
        failure_rate = failed_tools / max(len(tool_steps), 1)

        # Detect duplicate/redundant calls: same tool + same input back-to-back.
        redundant = 0
        prev: Optional[Tuple[str, str]] = None
        for s in tool_steps:
            if s.tool_call:
                key = (s.tool_call.tool_name, str(s.tool_call.tool_input))
                if key == prev:
                    redundant += 1
                prev = key

        if tool_ratio <= _TOOL_RATIO_BENCHMARKS["excellent"]:
            score = 95.0
        elif tool_ratio <= _TOOL_RATIO_BENCHMARKS["good"]:
            score = 80.0
        elif tool_ratio <= _TOOL_RATIO_BENCHMARKS["average"]:
            score = 60.0
        elif tool_ratio <= _TOOL_RATIO_BENCHMARKS["poor"]:
            score = 40.0
        else:
            score = 15.0

        # Penalize failures and redundancy.
        score -= failure_rate * 20
        score -= redundant * 5
        score = max(0.0, min(100.0, score))

        grade = _grade_from_score(score)

        suggestions: List[str] = []
        if redundant > 0:
            suggestions.append(f"Detected {redundant} redundant back-to-back tool call(s). Add deduplication logic.")
        if failure_rate > 0.1:
            suggestions.append("High tool failure rate — validate inputs before calling tools.")
        if score < 60:
            suggestions.append("Review whether all tool calls are necessary. Consider combining related calls.")
        if score < 40:
            suggestions.append("Implement a tool-selection strategy layer to prevent frivolous calls.")

        return CategoryResult(
            category=RoastCategory.TOOL_USAGE,
            grade=grade,
            score=score,
            joke=self._pick_joke("tool_usage", grade),
            details=(
                f"{len(tool_steps)} tool call(s) out of {total_steps} total step(s) "
                f"(ratio {tool_ratio:.2f}). {failed_tools} failure(s), {redundant} redundant call(s)."
            ),
            suggestions=suggestions,
            metrics={
                "tool_calls": len(tool_steps),
                "total_steps": total_steps,
                "tool_ratio": round(tool_ratio, 3),
                "failures": failed_tools,
                "failure_rate": round(failure_rate, 3),
                "redundant_calls": redundant,
            },
        )


# ---------------------------------------------------------------------------
# Terminal report formatting
# ---------------------------------------------------------------------------

_GRADE_COLORS: Dict[str, str] = {
    "A+": "bold bright_green",
    "A": "bold green",
    "B": "bold cyan",
    "C": "bold yellow",
    "D": "bold red",
    "F": "bold bright_red",
}


def format_terminal_report(report: RoastReport) -> str:
    """Produce a beautiful Rich-compatible terminal report string.

    This returns a *plain string* that contains Rich markup.  Pass it to
    ``rich.console.Console.print()`` for coloured output.
    """
    lines: List[str] = []

    # Header.
    grade_color = _GRADE_COLORS.get(report.overall_grade.value, "bold white")
    lines.append("")
    lines.append("[bold bright_magenta]" + "=" * 60 + "[/]")
    lines.append("[bold bright_magenta]  \U0001f525  AGENT ROAST REPORT  \U0001f525[/]")
    lines.append("[bold bright_magenta]" + "=" * 60 + "[/]")
    lines.append("")
    lines.append(f"  Agent:      [bold]{report.recording_name}[/bold]")
    if report.agent_framework:
        lines.append(f"  Framework:  {report.agent_framework}")
    lines.append(f"  Roast level: [italic]{report.level.value}[/italic]")
    lines.append(f"  Steps: {report.total_steps}  |  "
                 f"Cost: ${report.total_cost_usd:.4f}  |  "
                 f"Duration: {report.total_duration_ms:.0f}ms  |  "
                 f"Tokens: {report.total_tokens}")
    lines.append("")

    # Overall grade.
    lines.append(f"  Overall Grade:  [{grade_color}]{report.overall_grade.value}[/]  "
                 f"({report.overall_score:.0f}/100)")
    lines.append(f"  [italic]\"{report.summary_line}\"[/italic]")
    lines.append("")
    lines.append("[dim]" + "-" * 60 + "[/dim]")

    # Per-category results.
    for cat_key in [
        "cost", "speed", "intelligence", "security", "verbosity", "tool_usage",
    ]:
        result = report.categories.get(cat_key)
        if result is None:
            continue

        emoji = _CATEGORY_EMOJI.get(cat_key, "")
        label = _CATEGORY_LABELS.get(cat_key, cat_key)
        g_color = _GRADE_COLORS.get(result.grade.value, "bold white")

        lines.append("")
        lines.append(f"  {emoji}  [bold]{label}[/bold]  —  [{g_color}]{result.grade.value}[/]  ({result.score:.0f}/100)")
        lines.append(f"     [italic]{result.joke}[/italic]")
        lines.append(f"     {result.details}")
        if result.suggestions:
            lines.append("     [bold]Suggestions:[/bold]")
            for suggestion in result.suggestions:
                lines.append(f"       \u2022 {suggestion}")

    lines.append("")
    lines.append("[dim]" + "-" * 60 + "[/dim]")
    lines.append("[dim]  Generated by AgentProbe Roast \U0001f525[/dim]")
    lines.append("")

    return "\n".join(lines)
