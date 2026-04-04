"""Chaos Engineering Engine for AI Agents.

Systematically inject failures into agent execution to test resilience:
- Tool failures (timeout, error, garbage output)
- LLM degradation (high latency, truncated responses, hallucinations)
- Resource exhaustion (token budget exceeded, cost spikes)
- Network chaos (intermittent failures, partial responses)
- Adversarial inputs (prompt injection, conflicting instructions)

Free tier: 5 scenarios per run. Pro: unlimited + custom chaos profiles.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from agentprobe.core.models import (
    AgentRecording, AgentStep, StepType, ToolCallRecord, LLMCallRecord,
)


# ---------------------------------------------------------------------------
# Chaos Scenario Types
# ---------------------------------------------------------------------------

class ChaosType(str, Enum):
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    TOOL_GARBAGE = "tool_garbage"
    TOOL_SLOW = "tool_slow"
    LLM_TIMEOUT = "llm_timeout"
    LLM_TRUNCATED = "llm_truncated"
    LLM_HALLUCINATION = "llm_hallucination"
    LLM_REFUSAL = "llm_refusal"
    COST_SPIKE = "cost_spike"
    TOKEN_EXHAUSTION = "token_exhaustion"
    INTERMITTENT_FAILURE = "intermittent_failure"
    CASCADING_FAILURE = "cascading_failure"


class ChaosSeverity(str, Enum):
    LOW = "low"          # mild disruption, should barely notice
    MEDIUM = "medium"    # noticeable issues, should handle gracefully
    HIGH = "high"        # serious problems, tests resilience
    CRITICAL = "critical"  # catastrophic, tests failure recovery


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

@dataclass
class ChaosScenario:
    """A single chaos injection scenario."""

    name: str
    type: ChaosType
    severity: ChaosSeverity
    description: str
    target: str = "*"  # tool name or "*" for all
    probability: float = 1.0  # 0.0-1.0, chance of triggering
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "severity": self.severity.value,
            "description": self.description,
            "target": self.target,
            "probability": self.probability,
            "params": self.params,
        }


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ChaosInjection:
    """Record of a single chaos injection during a run."""

    step_index: int
    scenario_name: str
    chaos_type: str
    original_output: Any = None
    injected_output: Any = None
    agent_recovered: bool = False
    recovery_steps: int = 0


@dataclass
class ChaosResult:
    """Complete result of a chaos engineering run."""

    recording_name: str = ""
    scenarios_applied: int = 0
    injections: List[ChaosInjection] = field(default_factory=list)
    total_injected: int = 0
    recovered_count: int = 0
    failed_count: int = 0
    resilience_score: float = 0.0  # 0-100
    grade: str = ""
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recording_name": self.recording_name,
            "scenarios_applied": self.scenarios_applied,
            "total_injected": self.total_injected,
            "recovered_count": self.recovered_count,
            "failed_count": self.failed_count,
            "resilience_score": round(self.resilience_score, 1),
            "grade": self.grade,
            "recommendations": self.recommendations,
            "injections": [
                {
                    "step": inj.step_index,
                    "scenario": inj.scenario_name,
                    "type": inj.chaos_type,
                    "recovered": inj.agent_recovered,
                    "recovery_steps": inj.recovery_steps,
                }
                for inj in self.injections
            ],
        }


# ---------------------------------------------------------------------------
# Built-in scenario library
# ---------------------------------------------------------------------------

BUILT_IN_SCENARIOS: List[ChaosScenario] = [
    ChaosScenario(
        name="Tool Timeout Storm",
        type=ChaosType.TOOL_TIMEOUT,
        severity=ChaosSeverity.HIGH,
        description="All tool calls timeout after 30s — does your agent retry or give up?",
        params={"timeout_ms": 30000},
    ),
    ChaosScenario(
        name="Garbage In, Garbage Out",
        type=ChaosType.TOOL_GARBAGE,
        severity=ChaosSeverity.MEDIUM,
        description="Tools return random garbage instead of real output",
        params={"garbage_type": "random_json"},
    ),
    ChaosScenario(
        name="The Slow Lane",
        type=ChaosType.TOOL_SLOW,
        severity=ChaosSeverity.LOW,
        description="Every tool call takes 10x longer than normal",
        params={"multiplier": 10},
    ),
    ChaosScenario(
        name="LLM Brain Freeze",
        type=ChaosType.LLM_TRUNCATED,
        severity=ChaosSeverity.MEDIUM,
        description="LLM responses are truncated to 50 tokens — can your agent handle incomplete answers?",
        params={"max_tokens": 50},
    ),
    ChaosScenario(
        name="Refusal Revolution",
        type=ChaosType.LLM_REFUSAL,
        severity=ChaosSeverity.HIGH,
        description="LLM refuses to answer 50% of the time",
        probability=0.5,
        params={"refusal_message": "I'm sorry, I can't help with that request."},
    ),
    ChaosScenario(
        name="Hallucination Station",
        type=ChaosType.LLM_HALLUCINATION,
        severity=ChaosSeverity.CRITICAL,
        description="LLM confidently returns completely wrong information",
        params={"hallucination_type": "confident_wrong"},
    ),
    ChaosScenario(
        name="Cost Explosion",
        type=ChaosType.COST_SPIKE,
        severity=ChaosSeverity.MEDIUM,
        description="Every LLM call costs 100x more — will the budget hold?",
        params={"cost_multiplier": 100},
    ),
    ChaosScenario(
        name="Token Famine",
        type=ChaosType.TOKEN_EXHAUSTION,
        severity=ChaosSeverity.HIGH,
        description="Token budget drops to 1000 total — extreme constraint testing",
        params={"max_tokens": 1000},
    ),
    ChaosScenario(
        name="Flaky Friend",
        type=ChaosType.INTERMITTENT_FAILURE,
        severity=ChaosSeverity.MEDIUM,
        description="30% of all operations randomly fail — classic flaky API behavior",
        probability=0.3,
    ),
    ChaosScenario(
        name="Domino Effect",
        type=ChaosType.CASCADING_FAILURE,
        severity=ChaosSeverity.CRITICAL,
        description="One tool failure triggers all subsequent tools to fail — cascade resilience test",
        params={"trigger_tool": "first_used"},
    ),
    ChaosScenario(
        name="Selective Strike",
        type=ChaosType.TOOL_ERROR,
        severity=ChaosSeverity.LOW,
        description="The most-used tool always returns an error",
        target="most_used",
        params={"error_message": "Service temporarily unavailable"},
    ),
    ChaosScenario(
        name="LLM Amnesia",
        type=ChaosType.LLM_TRUNCATED,
        severity=ChaosSeverity.HIGH,
        description="LLM forgets context — each response ignores previous messages",
        params={"amnesia_mode": True},
    ),
]


# ---------------------------------------------------------------------------
# Chaos Engine
# ---------------------------------------------------------------------------

class ChaosEngine:
    """Chaos engineering engine for AI agent resilience testing.

    Usage::

        engine = ChaosEngine()
        result = engine.run(recording)
        print(f"Resilience: {result.resilience_score}/100 ({result.grade})")

        # Custom scenarios
        engine.add_scenario(ChaosScenario(
            name="My Custom Chaos",
            type=ChaosType.TOOL_ERROR,
            severity=ChaosSeverity.MEDIUM,
            description="Custom failure scenario",
            target="web_search",
        ))

        # Run specific scenarios only
        result = engine.run(recording, scenarios=["Tool Timeout Storm", "Flaky Friend"])
    """

    MAX_FREE_SCENARIOS = 5

    def __init__(self, seed: Optional[int] = None) -> None:
        self._scenarios: List[ChaosScenario] = list(BUILT_IN_SCENARIOS)
        self._rng = random.Random(seed)

    def add_scenario(self, scenario: ChaosScenario) -> None:
        """Add a custom chaos scenario."""
        self._scenarios.append(scenario)

    def list_scenarios(self) -> List[ChaosScenario]:
        """List all available scenarios."""
        return list(self._scenarios)

    def run(
        self,
        recording: AgentRecording,
        scenarios: Optional[List[str]] = None,
        max_scenarios: int = MAX_FREE_SCENARIOS,
    ) -> ChaosResult:
        """Run chaos scenarios against a recording.

        Simulates what would happen if the injected failures occurred during
        execution and evaluates how the agent would (or wouldn't) handle them.
        """
        # Select scenarios
        if scenarios:
            selected = [s for s in self._scenarios if s.name in scenarios]
        else:
            selected = self._rng.sample(
                self._scenarios, min(max_scenarios, len(self._scenarios))
            )

        result = ChaosResult(
            recording_name=recording.metadata.name,
            scenarios_applied=len(selected),
        )

        for scenario in selected:
            injections = self._apply_scenario(recording, scenario)
            result.injections.extend(injections)

        result.total_injected = len(result.injections)
        result.recovered_count = sum(1 for i in result.injections if i.agent_recovered)
        result.failed_count = result.total_injected - result.recovered_count

        # Calculate resilience score
        if result.total_injected > 0:
            recovery_rate = result.recovered_count / result.total_injected
            severity_weights = {"low": 0.5, "medium": 1.0, "high": 1.5, "critical": 2.0}
            weighted_recovery = 0.0
            weighted_total = 0.0
            for inj in result.injections:
                scenario_match = next((s for s in selected if s.name == inj.scenario_name), None)
                weight = severity_weights.get(scenario_match.severity.value, 1.0) if scenario_match else 1.0
                weighted_total += weight
                if inj.agent_recovered:
                    weighted_recovery += weight
            result.resilience_score = (weighted_recovery / max(weighted_total, 1)) * 100
        else:
            result.resilience_score = 100.0

        result.grade = self._grade(result.resilience_score)
        result.recommendations = self._recommend(result, selected)

        return result

    # -- Scenario application ----------------------------------------------

    def _apply_scenario(self, recording: AgentRecording, scenario: ChaosScenario) -> List[ChaosInjection]:
        """Simulate a chaos scenario against a recording and evaluate impact."""
        injections: List[ChaosInjection] = []
        steps = recording.steps
        cascade_triggered = False

        for i, step in enumerate(steps):
            if not self._should_inject(step, scenario, cascade_triggered):
                continue

            inj = ChaosInjection(
                step_index=i,
                scenario_name=scenario.name,
                chaos_type=scenario.type.value,
            )

            # Determine if agent would recover
            if scenario.type in (ChaosType.TOOL_TIMEOUT, ChaosType.TOOL_ERROR, ChaosType.TOOL_GARBAGE):
                inj.agent_recovered = self._would_recover_from_tool_failure(steps, i)
                inj.recovery_steps = self._count_recovery_steps(steps, i)

            elif scenario.type in (ChaosType.LLM_TRUNCATED, ChaosType.LLM_REFUSAL, ChaosType.LLM_HALLUCINATION):
                inj.agent_recovered = self._would_recover_from_llm_failure(steps, i)
                inj.recovery_steps = self._count_recovery_steps(steps, i)

            elif scenario.type == ChaosType.INTERMITTENT_FAILURE:
                if self._rng.random() < scenario.probability:
                    inj.agent_recovered = self._would_recover_from_tool_failure(steps, i)
                else:
                    continue

            elif scenario.type == ChaosType.CASCADING_FAILURE:
                if step.type == StepType.TOOL_CALL and not cascade_triggered:
                    cascade_triggered = True
                    inj.agent_recovered = False
                elif cascade_triggered and step.type == StepType.TOOL_CALL:
                    inj.agent_recovered = False
                else:
                    continue

            elif scenario.type in (ChaosType.COST_SPIKE, ChaosType.TOKEN_EXHAUSTION):
                inj.agent_recovered = True  # cost issues don't crash

            injections.append(inj)

        return injections

    def _should_inject(self, step: AgentStep, scenario: ChaosScenario, cascade: bool) -> bool:
        """Determine if a chaos injection should occur at this step."""
        if scenario.type in (ChaosType.TOOL_TIMEOUT, ChaosType.TOOL_ERROR, ChaosType.TOOL_GARBAGE, ChaosType.TOOL_SLOW):
            if step.type != StepType.TOOL_CALL:
                return False
            if scenario.target not in ("*", "most_used"):
                if step.tool_call and step.tool_call.tool_name != scenario.target:
                    return False

        if scenario.type in (ChaosType.LLM_TIMEOUT, ChaosType.LLM_TRUNCATED, ChaosType.LLM_HALLUCINATION, ChaosType.LLM_REFUSAL):
            if step.type != StepType.LLM_CALL:
                return False

        if scenario.type == ChaosType.CASCADING_FAILURE and cascade:
            return step.type == StepType.TOOL_CALL

        return True

    def _would_recover_from_tool_failure(self, steps: List[AgentStep], fail_idx: int) -> bool:
        """Heuristic: does the agent have retry/fallback patterns after tool calls?"""
        remaining = steps[fail_idx + 1:]
        # Check for retry pattern: another tool call or LLM call follows
        for step in remaining[:5]:
            if step.type == StepType.TOOL_CALL:
                return True
            if step.type == StepType.DECISION:
                return True
        # If there's an LLM call after, it might handle the error
        for step in remaining[:3]:
            if step.type == StepType.LLM_CALL:
                return True
        return False

    def _would_recover_from_llm_failure(self, steps: List[AgentStep], fail_idx: int) -> bool:
        """Heuristic: can the agent handle a bad LLM response?"""
        remaining = steps[fail_idx + 1:]
        for step in remaining[:3]:
            if step.type == StepType.LLM_CALL:
                return True
            if step.type == StepType.DECISION and step.decision and step.decision.type.value == "retry":
                return True
        return False

    def _count_recovery_steps(self, steps: List[AgentStep], fail_idx: int) -> int:
        """Count how many steps until the agent gets back on track."""
        remaining = steps[fail_idx + 1:]
        for i, step in enumerate(remaining):
            if step.type == StepType.TOOL_CALL and step.tool_call and step.tool_call.success:
                return i + 1
        return 0

    def _grade(self, score: float) -> str:
        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def _recommend(self, result: ChaosResult, scenarios: List[ChaosScenario]) -> List[str]:
        """Generate actionable recommendations based on chaos results."""
        recs: List[str] = []

        if result.resilience_score < 50:
            recs.append("CRITICAL: Agent has poor failure resilience. Add retry logic and fallback strategies.")

        tool_failures = [i for i in result.injections if "tool" in i.chaos_type and not i.agent_recovered]
        if tool_failures:
            recs.append(f"Add error handling for tool failures — {len(tool_failures)} tool chaos injections were not recovered.")

        llm_failures = [i for i in result.injections if "llm" in i.chaos_type and not i.agent_recovered]
        if llm_failures:
            recs.append(f"Implement LLM response validation — {len(llm_failures)} LLM chaos injections caused unrecoverable failures.")

        cascade = [i for i in result.injections if i.chaos_type == "cascading_failure"]
        if cascade and not any(i.agent_recovered for i in cascade):
            recs.append("Add circuit-breaker patterns to prevent cascading failures across tools.")

        if not recs:
            recs.append("Excellent resilience! Consider adding custom chaos scenarios for edge cases specific to your domain.")

        return recs

    # -- Rendering ---------------------------------------------------------

    def render_report(self, result: ChaosResult) -> str:
        """Render a chaos engineering report."""
        severity_emoji = {
            "low": "\U0001f7e2", "medium": "\U0001f7e1",
            "high": "\U0001f7e0", "critical": "\U0001f534",
        }
        grade_emoji = {
            "A+": "\U0001f3c6", "A": "\u2b50", "B": "\U0001f44d",
            "C": "\u26a0\ufe0f", "D": "\U0001f4a3", "F": "\U0001f480",
        }

        lines: List[str] = []
        g_emoji = grade_emoji.get(result.grade, "")
        lines.append(f"\U0001f300 CHAOS ENGINEERING REPORT {g_emoji}")
        lines.append(f"   Recording: {result.recording_name}")
        lines.append(f"   Scenarios: {result.scenarios_applied}")
        lines.append(f"   Injections: {result.total_injected}")
        lines.append(f"   Recovered: {result.recovered_count}/{result.total_injected}")
        lines.append(f"   Resilience: {result.resilience_score:.0f}/100 ({result.grade})")
        lines.append("")

        for inj in result.injections:
            status = "\u2705" if inj.agent_recovered else "\u274c"
            lines.append(f"   {status} [{inj.chaos_type}] {inj.scenario_name} @ step {inj.step_index}")
            if inj.agent_recovered and inj.recovery_steps > 0:
                lines.append(f"      Recovered in {inj.recovery_steps} steps")

        if result.recommendations:
            lines.append("\n   \U0001f4cb Recommendations:")
            for rec in result.recommendations:
                lines.append(f"      \u2022 {rec}")

        return "\n".join(lines)
