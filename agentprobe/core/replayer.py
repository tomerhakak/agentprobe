"""Replay engine for AgentProbe — re-execute recorded agent runs with
configurable overrides, mocks, and comparison utilities."""

from __future__ import annotations

import copy
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from agentprobe.core.models import (
    AgentOutput,
    AgentRecording,
    AgentStep,
    LLMCallRecord,
    Message,
    OutputStatus,
    RecordingMetadata,
    StepType,
    ToolCallRecord,
)
from agentprobe.mock.llm_mock import MockLLM
from agentprobe.mock.tool_mock import MockTool


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ReplayConfig:
    """Knobs for controlling how a recording is replayed."""

    model: str | None = None
    system_prompt: str | None = None
    mock_tools: bool = False
    use_recorded_tool_outputs: bool = True
    tool_mocks: dict[str, MockTool | Callable[..., Any]] | None = None
    step_timeout_ms: int = 30_000
    max_cost_usd: float | None = None
    mock_llm: MockLLM | None = None


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class ReplayResult:
    """Outcome of a :meth:`Replayer.replay` call."""

    original: AgentRecording
    replayed: AgentRecording
    config: ReplayConfig


@dataclass
class ReplayComparison:
    """Side-by-side comparison of an original and replayed recording."""

    original: AgentRecording
    replayed: AgentRecording
    step_diff: dict[str, Any] = field(default_factory=dict)
    output_similarity: float = 0.0
    cost_diff: dict[str, Any] = field(default_factory=dict)
    latency_diff: dict[str, Any] = field(default_factory=dict)
    tool_usage_diff: dict[str, Any] = field(default_factory=dict)
    behavior_drift: str = "LOW"
    summary: str = ""


# ---------------------------------------------------------------------------
# Replayer
# ---------------------------------------------------------------------------

class Replayer:
    """Re-execute an agent recording with optional overrides and mocks."""

    def __init__(self, config: ReplayConfig | None = None) -> None:
        self._default_config = config or ReplayConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay(
        self,
        recording: str | AgentRecording,
        config: ReplayConfig | None = None,
    ) -> ReplayResult:
        """Replay *recording* using the supplied (or default) config.

        When ``mock_llm`` is set the LLM calls are served from the mock;
        otherwise the original LLM outputs are reused verbatim.

        When ``use_recorded_tool_outputs`` is True (the default) tool
        outputs come straight from the recording.  Individual tools can
        be overridden via ``tool_mocks``.
        """
        cfg = config or self._default_config
        original = self._load(recording)

        replayed_steps: list[AgentStep] = []
        replayed_messages: list[Message] = []
        total_cost: float = 0.0
        total_tokens: int = 0
        replay_start = time.monotonic()

        for step in original.steps:
            step_start = time.monotonic()

            if step.type == StepType.LLM_CALL:
                new_step = self._replay_llm_step(step, original, cfg)
            elif step.type == StepType.TOOL_CALL:
                new_step = self._replay_tool_step(step, cfg)
            else:
                # Decisions, handoffs, memory ops — copy as-is.
                new_step = copy.deepcopy(step)

            elapsed_ms = (time.monotonic() - step_start) * 1000
            new_step.duration_ms = round(elapsed_ms, 2)
            replayed_steps.append(new_step)

            if new_step.llm_call and new_step.llm_call.output_message:
                replayed_messages.append(new_step.llm_call.output_message)
                total_cost += new_step.llm_call.cost_usd
                total_tokens += new_step.llm_call.input_tokens + new_step.llm_call.output_tokens

            # Budget guard
            if cfg.max_cost_usd is not None and total_cost > cfg.max_cost_usd:
                break

        total_duration_ms = (time.monotonic() - replay_start) * 1000

        # Build the replayed AgentRecording
        last_output = self._derive_output(replayed_steps, original)
        replayed = AgentRecording(
            metadata=RecordingMetadata(
                id=str(uuid.uuid4()),
                name=f"replay-{original.metadata.name}",
                timestamp=datetime.now(timezone.utc),
                duration_ms=round(total_duration_ms, 2),
                agent_framework=original.metadata.agent_framework,
                agent_version=original.metadata.agent_version,
                total_cost_usd=round(total_cost, 6),
                total_tokens=total_tokens,
                tags=["replay", *original.metadata.tags],
            ),
            input=copy.deepcopy(original.input),
            output=last_output,
            steps=replayed_steps,
            messages=replayed_messages,
            environment=copy.deepcopy(original.environment),
        )

        # Override model in environment if requested
        if cfg.model:
            replayed.environment.model = cfg.model
        if cfg.system_prompt:
            replayed.environment.system_prompt = cfg.system_prompt

        return ReplayResult(original=original, replayed=replayed, config=cfg)

    def compare(
        self,
        original: str | AgentRecording,
        replayed: AgentRecording | ReplayResult,
    ) -> ReplayComparison:
        """Produce a structured comparison of an original and replayed run."""
        orig = self._load(original)
        repl = replayed.replayed if isinstance(replayed, ReplayResult) else replayed

        step_diff = {
            "original_steps": orig.step_count,
            "replayed_steps": repl.step_count,
            "delta": repl.step_count - orig.step_count,
        }

        output_similarity = self._text_similarity(
            self._extract_text(orig.output),
            self._extract_text(repl.output),
        )

        orig_cost = orig.total_cost
        repl_cost = repl.total_cost
        cost_diff = {
            "original_usd": round(orig_cost, 6),
            "replayed_usd": round(repl_cost, 6),
            "delta_usd": round(repl_cost - orig_cost, 6),
            "change_pct": round(self._pct_change(orig_cost, repl_cost), 2),
        }

        orig_dur = orig.total_duration
        repl_dur = repl.total_duration
        latency_diff = {
            "original_ms": round(orig_dur, 2),
            "replayed_ms": round(repl_dur, 2),
            "delta_ms": round(repl_dur - orig_dur, 2),
            "change_pct": round(self._pct_change(orig_dur, repl_dur), 2),
        }

        tool_usage_diff = self._compute_tool_diff(orig, repl)

        drift = self._assess_drift(step_diff, output_similarity, tool_usage_diff)

        summary = self._format_summary(
            step_diff, output_similarity, cost_diff, latency_diff, tool_usage_diff, drift
        )

        return ReplayComparison(
            original=orig,
            replayed=repl,
            step_diff=step_diff,
            output_similarity=output_similarity,
            cost_diff=cost_diff,
            latency_diff=latency_diff,
            tool_usage_diff=tool_usage_diff,
            behavior_drift=drift,
            summary=summary,
        )

    def dry_run(
        self,
        recording: str | AgentRecording,
        config: ReplayConfig | None = None,
    ) -> dict[str, Any]:
        """Estimate cost and tokens without actually executing anything."""
        cfg = config or self._default_config
        original = self._load(recording)

        estimated_llm_calls = len(original.llm_steps)
        estimated_tool_calls = len(original.tool_steps)

        # If using a mock LLM the real cost is zero.
        if cfg.mock_llm is not None:
            estimated_cost = 0.0
            estimated_tokens = 0
        else:
            estimated_cost = original.total_cost
            estimated_tokens = original.total_tokens

        mocked_tools: list[str] = []
        if cfg.mock_tools:
            mocked_tools = [s.tool_call.tool_name for s in original.tool_steps if s.tool_call]
        elif cfg.tool_mocks:
            mocked_tools = list(cfg.tool_mocks.keys())

        return {
            "estimated_llm_calls": estimated_llm_calls,
            "estimated_tool_calls": estimated_tool_calls,
            "estimated_cost_usd": round(estimated_cost, 6),
            "estimated_tokens": estimated_tokens,
            "estimated_steps": original.step_count,
            "mocked_tools": mocked_tools,
            "uses_mock_llm": cfg.mock_llm is not None,
            "model_override": cfg.model,
            "max_cost_usd": cfg.max_cost_usd,
        }

    # ------------------------------------------------------------------
    # Step replay helpers
    # ------------------------------------------------------------------

    def _replay_llm_step(
        self,
        step: AgentStep,
        original: AgentRecording,
        cfg: ReplayConfig,
    ) -> AgentStep:
        new_step = AgentStep(
            step_number=step.step_number,
            type=StepType.LLM_CALL,
            timestamp=datetime.now(timezone.utc),
        )

        if cfg.mock_llm is not None:
            input_messages = step.llm_call.input_messages if step.llm_call else []
            output_msg = cfg.mock_llm.get_response(input_messages)
            new_step.llm_call = LLMCallRecord(
                model=cfg.model or (step.llm_call.model if step.llm_call else "mock"),
                input_messages=copy.deepcopy(input_messages),
                output_message=output_msg,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=0.0,
                finish_reason="stop",
            )
        elif step.llm_call is not None:
            # Reuse original LLM output verbatim.
            new_step.llm_call = copy.deepcopy(step.llm_call)
            if cfg.model:
                new_step.llm_call.model = cfg.model
        else:
            new_step.llm_call = None

        return new_step

    def _replay_tool_step(
        self,
        step: AgentStep,
        cfg: ReplayConfig,
    ) -> AgentStep:
        new_step = AgentStep(
            step_number=step.step_number,
            type=StepType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
        )

        if step.tool_call is None:
            new_step.tool_call = None
            return new_step

        tc = step.tool_call
        tool_name = tc.tool_name
        tool_input = copy.deepcopy(tc.tool_input)

        # Determine tool output
        if cfg.tool_mocks and tool_name in cfg.tool_mocks:
            mock = cfg.tool_mocks[tool_name]
            if isinstance(mock, MockTool):
                tool_output = mock.get_response(tool_input)
            elif callable(mock):
                tool_output = mock(tool_input)
            else:
                tool_output = mock
        elif cfg.mock_tools or cfg.use_recorded_tool_outputs:
            tool_output = copy.deepcopy(tc.tool_output)
        else:
            tool_output = copy.deepcopy(tc.tool_output)

        new_step.tool_call = ToolCallRecord(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            duration_ms=0.0,
            success=tc.success,
            error=tc.error,
            side_effects=[],
        )
        return new_step

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(output: AgentOutput) -> str:
        content = output.content
        if isinstance(content, str):
            return content
        return str(content)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        if not a and not b:
            return 1.0
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _pct_change(old: float, new: float) -> float:
        if old == 0:
            return 0.0 if new == 0 else 100.0
        return ((new - old) / abs(old)) * 100

    @staticmethod
    def _compute_tool_diff(orig: AgentRecording, repl: AgentRecording) -> dict[str, Any]:
        def _tool_counts(rec: AgentRecording) -> dict[str, int]:
            counts: dict[str, int] = {}
            for s in rec.tool_steps:
                if s.tool_call:
                    name = s.tool_call.tool_name
                    counts[name] = counts.get(name, 0) + 1
            return counts

        orig_counts = _tool_counts(orig)
        repl_counts = _tool_counts(repl)
        all_tools = sorted(set(orig_counts) | set(repl_counts))

        per_tool: dict[str, dict[str, int]] = {}
        for t in all_tools:
            o = orig_counts.get(t, 0)
            r = repl_counts.get(t, 0)
            per_tool[t] = {"original": o, "replayed": r, "delta": r - o}

        return {
            "original_total": sum(orig_counts.values()),
            "replayed_total": sum(repl_counts.values()),
            "per_tool": per_tool,
        }

    @staticmethod
    def _assess_drift(
        step_diff: dict[str, Any],
        output_similarity: float,
        tool_usage_diff: dict[str, Any],
    ) -> str:
        score = 0.0

        # Step count divergence
        orig_steps = step_diff.get("original_steps", 0)
        delta_steps = abs(step_diff.get("delta", 0))
        if orig_steps > 0:
            step_ratio = delta_steps / orig_steps
            score += min(step_ratio * 30, 30)

        # Output similarity (lower = more drift)
        score += (1.0 - output_similarity) * 40

        # Tool usage changes
        orig_tools = tool_usage_diff.get("original_total", 0)
        repl_tools = tool_usage_diff.get("replayed_total", 0)
        if orig_tools > 0:
            tool_ratio = abs(repl_tools - orig_tools) / orig_tools
            score += min(tool_ratio * 30, 30)

        if score <= 15:
            return "LOW"
        elif score <= 45:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _format_summary(
        step_diff: dict[str, Any],
        output_similarity: float,
        cost_diff: dict[str, Any],
        latency_diff: dict[str, Any],
        tool_usage_diff: dict[str, Any],
        drift: str,
    ) -> str:
        lines = [
            "=== Replay Comparison ===",
            f"Behavior Drift: {drift}",
            "",
            f"Steps: {step_diff['original_steps']} -> {step_diff['replayed_steps']} (delta: {step_diff['delta']:+d})",
            f"Output Similarity: {output_similarity:.1%}",
            f"Cost: ${cost_diff['original_usd']:.4f} -> ${cost_diff['replayed_usd']:.4f} ({cost_diff['change_pct']:+.1f}%)",
            f"Latency: {latency_diff['original_ms']:.0f}ms -> {latency_diff['replayed_ms']:.0f}ms ({latency_diff['change_pct']:+.1f}%)",
            "",
            "Tool Usage:",
        ]
        for name, info in tool_usage_diff.get("per_tool", {}).items():
            lines.append(f"  {name}: {info['original']} -> {info['replayed']} (delta: {info['delta']:+d})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _load(recording: str | AgentRecording) -> AgentRecording:
        if isinstance(recording, (str, Path)):
            return AgentRecording.load(recording)
        return recording

    @staticmethod
    def _derive_output(steps: list[AgentStep], original: AgentRecording) -> AgentOutput:
        """Derive the agent output from the replayed steps.  Falls back to
        the original output structure with updated content when possible."""
        # Find the last LLM output as the "final answer".
        for step in reversed(steps):
            if (
                step.type == StepType.LLM_CALL
                and step.llm_call is not None
                and step.llm_call.output_message is not None
            ):
                msg = step.llm_call.output_message
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                return AgentOutput(
                    type=original.output.type,
                    content=content,
                    status=OutputStatus.SUCCESS,
                )
        return copy.deepcopy(original.output)
