"""Time Travel Debugger — step through agent execution like a VCR.

Navigate forward/backward through every step of an agent recording,
inspect tool I/O, LLM prompts & responses, costs accrued at each point,
and set breakpoints on tool names, cost thresholds, or custom predicates.

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Breakpoint
# ---------------------------------------------------------------------------

class BreakpointType(str, Enum):
    TOOL_NAME = "tool_name"
    COST_THRESHOLD = "cost_threshold"
    STEP_TYPE = "step_type"
    TOKEN_THRESHOLD = "token_threshold"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class Breakpoint:
    """A conditional breakpoint in the timeline."""

    id: int
    type: BreakpointType
    condition: str = ""
    value: Any = None
    predicate: Optional[Callable[[AgentStep, "TimelineState"], bool]] = None
    hit_count: int = 0
    enabled: bool = True

    def matches(self, step: AgentStep, state: "TimelineState") -> bool:
        if not self.enabled:
            return False

        if self.type == BreakpointType.TOOL_NAME:
            if step.tool_call and step.tool_call.tool_name == self.value:
                self.hit_count += 1
                return True

        elif self.type == BreakpointType.COST_THRESHOLD:
            if state.cumulative_cost >= self.value:
                self.hit_count += 1
                return True

        elif self.type == BreakpointType.STEP_TYPE:
            if step.type.value == self.value:
                self.hit_count += 1
                return True

        elif self.type == BreakpointType.TOKEN_THRESHOLD:
            if state.cumulative_tokens >= self.value:
                self.hit_count += 1
                return True

        elif self.type == BreakpointType.ERROR:
            if step.tool_call and not step.tool_call.success:
                self.hit_count += 1
                return True
            if step.llm_call and step.llm_call.finish_reason == "error":
                self.hit_count += 1
                return True

        elif self.type == BreakpointType.CUSTOM and self.predicate:
            if self.predicate(step, state):
                self.hit_count += 1
                return True

        return False


# ---------------------------------------------------------------------------
# Timeline State — snapshot at each position
# ---------------------------------------------------------------------------

@dataclass
class TimelineState:
    """Complete state snapshot at a given position in the timeline."""

    position: int
    total_steps: int
    current_step: Optional[AgentStep] = None
    cumulative_cost: float = 0.0
    cumulative_tokens: int = 0
    cumulative_duration_ms: float = 0.0
    tools_called: List[str] = field(default_factory=list)
    tools_called_count: Dict[str, int] = field(default_factory=dict)
    llm_calls_count: int = 0
    decisions_made: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    hit_breakpoints: List[Breakpoint] = field(default_factory=list)

    @property
    def progress_pct(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.position + 1) / self.total_steps * 100

    @property
    def is_at_start(self) -> bool:
        return self.position <= 0

    @property
    def is_at_end(self) -> bool:
        return self.position >= self.total_steps - 1

    def cost_delta(self) -> float:
        if self.current_step and self.current_step.llm_call:
            return self.current_step.llm_call.cost_usd
        return 0.0

    def token_delta(self) -> int:
        if self.current_step and self.current_step.llm_call:
            return self.current_step.llm_call.input_tokens + self.current_step.llm_call.output_tokens
        return 0


# ---------------------------------------------------------------------------
# Timeline Debugger
# ---------------------------------------------------------------------------

class TimelineDebugger:
    """VCR-style time-travel debugger for agent recordings.

    Usage::

        dbg = TimelineDebugger(recording)
        dbg.add_breakpoint_tool("web_search")
        dbg.add_breakpoint_cost(0.10)

        state = dbg.current()       # inspect position 0
        state = dbg.step_forward()  # advance one step
        state = dbg.step_back()     # rewind one step
        state = dbg.goto(5)         # jump to step 5
        state = dbg.run()           # run until breakpoint or end
        state = dbg.run_back()      # run backward until breakpoint or start

        snapshot = dbg.snapshot()   # full JSON-serializable snapshot
    """

    def __init__(self, recording: AgentRecording) -> None:
        self._recording = recording
        self._steps = list(recording.steps)
        self._position = 0
        self._breakpoints: List[Breakpoint] = []
        self._bp_counter = 0
        self._history: List[int] = [0]  # positions visited

    # -- Navigation --------------------------------------------------------

    def current(self) -> TimelineState:
        """Return the state at the current position."""
        return self._build_state(self._position)

    def step_forward(self, n: int = 1) -> TimelineState:
        """Advance *n* steps forward (default 1)."""
        new_pos = min(self._position + n, len(self._steps) - 1)
        self._position = max(new_pos, 0)
        self._history.append(self._position)
        return self._build_state(self._position)

    def step_back(self, n: int = 1) -> TimelineState:
        """Rewind *n* steps backward (default 1)."""
        new_pos = max(self._position - n, 0)
        self._position = new_pos
        self._history.append(self._position)
        return self._build_state(self._position)

    def goto(self, position: int) -> TimelineState:
        """Jump to an absolute step position."""
        self._position = max(0, min(position, len(self._steps) - 1))
        self._history.append(self._position)
        return self._build_state(self._position)

    def goto_start(self) -> TimelineState:
        """Jump to the first step."""
        return self.goto(0)

    def goto_end(self) -> TimelineState:
        """Jump to the last step."""
        return self.goto(len(self._steps) - 1)

    def run(self) -> TimelineState:
        """Run forward until a breakpoint is hit or the end is reached."""
        while self._position < len(self._steps) - 1:
            self._position += 1
            state = self._build_state(self._position)
            if state.hit_breakpoints:
                self._history.append(self._position)
                return state
        self._history.append(self._position)
        return self._build_state(self._position)

    def run_back(self) -> TimelineState:
        """Run backward until a breakpoint is hit or the start is reached."""
        while self._position > 0:
            self._position -= 1
            state = self._build_state(self._position)
            if state.hit_breakpoints:
                self._history.append(self._position)
                return state
        self._history.append(self._position)
        return self._build_state(self._position)

    def next_tool(self, tool_name: Optional[str] = None) -> TimelineState:
        """Jump forward to the next tool call (optionally filtered by name)."""
        for i in range(self._position + 1, len(self._steps)):
            step = self._steps[i]
            if step.type == StepType.TOOL_CALL:
                if tool_name is None or (step.tool_call and step.tool_call.tool_name == tool_name):
                    self._position = i
                    self._history.append(i)
                    return self._build_state(i)
        return self.current()

    def next_llm(self) -> TimelineState:
        """Jump forward to the next LLM call."""
        for i in range(self._position + 1, len(self._steps)):
            if self._steps[i].type == StepType.LLM_CALL:
                self._position = i
                self._history.append(i)
                return self._build_state(i)
        return self.current()

    def next_error(self) -> TimelineState:
        """Jump forward to the next error."""
        for i in range(self._position + 1, len(self._steps)):
            step = self._steps[i]
            if step.tool_call and not step.tool_call.success:
                self._position = i
                self._history.append(i)
                return self._build_state(i)
        return self.current()

    # -- Breakpoints -------------------------------------------------------

    def add_breakpoint_tool(self, tool_name: str) -> Breakpoint:
        """Break when a specific tool is called."""
        bp = Breakpoint(id=self._next_bp_id(), type=BreakpointType.TOOL_NAME, condition=f"tool == {tool_name!r}", value=tool_name)
        self._breakpoints.append(bp)
        return bp

    def add_breakpoint_cost(self, threshold_usd: float) -> Breakpoint:
        """Break when cumulative cost exceeds a threshold."""
        bp = Breakpoint(id=self._next_bp_id(), type=BreakpointType.COST_THRESHOLD, condition=f"cost >= ${threshold_usd:.4f}", value=threshold_usd)
        self._breakpoints.append(bp)
        return bp

    def add_breakpoint_tokens(self, threshold: int) -> Breakpoint:
        """Break when cumulative tokens exceed a threshold."""
        bp = Breakpoint(id=self._next_bp_id(), type=BreakpointType.TOKEN_THRESHOLD, condition=f"tokens >= {threshold}", value=threshold)
        self._breakpoints.append(bp)
        return bp

    def add_breakpoint_step_type(self, step_type: str) -> Breakpoint:
        """Break on a specific step type (e.g. 'tool_call', 'decision')."""
        bp = Breakpoint(id=self._next_bp_id(), type=BreakpointType.STEP_TYPE, condition=f"type == {step_type!r}", value=step_type)
        self._breakpoints.append(bp)
        return bp

    def add_breakpoint_error(self) -> Breakpoint:
        """Break on any error."""
        bp = Breakpoint(id=self._next_bp_id(), type=BreakpointType.ERROR, condition="is_error")
        self._breakpoints.append(bp)
        return bp

    def add_breakpoint_custom(self, label: str, predicate: Callable[[AgentStep, TimelineState], bool]) -> Breakpoint:
        """Break on a custom predicate."""
        bp = Breakpoint(id=self._next_bp_id(), type=BreakpointType.CUSTOM, condition=label, predicate=predicate)
        self._breakpoints.append(bp)
        return bp

    def remove_breakpoint(self, bp_id: int) -> bool:
        """Remove a breakpoint by ID. Returns True if found."""
        before = len(self._breakpoints)
        self._breakpoints = [bp for bp in self._breakpoints if bp.id != bp_id]
        return len(self._breakpoints) < before

    def toggle_breakpoint(self, bp_id: int) -> bool:
        """Toggle a breakpoint on/off. Returns new enabled state."""
        for bp in self._breakpoints:
            if bp.id == bp_id:
                bp.enabled = not bp.enabled
                return bp.enabled
        return False

    def list_breakpoints(self) -> List[Breakpoint]:
        """Return all breakpoints."""
        return list(self._breakpoints)

    # -- Inspection --------------------------------------------------------

    def inspect_step(self, position: Optional[int] = None) -> Dict[str, Any]:
        """Return a detailed inspection of a step."""
        pos = position if position is not None else self._position
        if pos < 0 or pos >= len(self._steps):
            return {"error": "position out of range"}

        step = self._steps[pos]
        info: Dict[str, Any] = {
            "position": pos,
            "step_number": step.step_number,
            "type": step.type.value,
            "duration_ms": step.duration_ms,
            "timestamp": str(step.timestamp) if step.timestamp else None,
        }

        if step.llm_call:
            lc = step.llm_call
            info["llm_call"] = {
                "model": lc.model,
                "input_tokens": lc.input_tokens,
                "output_tokens": lc.output_tokens,
                "cost_usd": lc.cost_usd,
                "latency_ms": lc.latency_ms,
                "cache_hit": lc.cache_hit,
                "finish_reason": lc.finish_reason,
                "input_preview": _preview_messages(lc.input_messages),
                "output_preview": _preview_message(lc.output_message) if lc.output_message else None,
            }

        if step.tool_call:
            tc = step.tool_call
            info["tool_call"] = {
                "tool_name": tc.tool_name,
                "input": tc.tool_input,
                "output": _truncate(str(tc.tool_output), 500) if tc.tool_output else None,
                "success": tc.success,
                "error": tc.error,
                "duration_ms": tc.duration_ms,
                "side_effects": tc.side_effects,
            }

        if step.decision:
            info["decision"] = {
                "type": step.decision.type.value,
                "reason": step.decision.reason,
                "alternatives": step.decision.alternatives_considered,
            }

        return info

    def snapshot(self) -> Dict[str, Any]:
        """Return a full JSON-serializable snapshot of the debugger state."""
        state = self.current()
        return {
            "position": state.position,
            "total_steps": state.total_steps,
            "progress_pct": round(state.progress_pct, 1),
            "cumulative_cost": state.cumulative_cost,
            "cumulative_tokens": state.cumulative_tokens,
            "cumulative_duration_ms": state.cumulative_duration_ms,
            "tools_called": state.tools_called,
            "llm_calls_count": state.llm_calls_count,
            "errors": state.errors,
            "current_step": self.inspect_step(),
            "breakpoints": [
                {"id": bp.id, "type": bp.type.value, "condition": bp.condition, "enabled": bp.enabled, "hits": bp.hit_count}
                for bp in self._breakpoints
            ],
            "history": self._history[-20:],
        }

    def diff(self, pos_a: int, pos_b: int) -> Dict[str, Any]:
        """Compare state at two positions."""
        state_a = self._build_state(pos_a)
        state_b = self._build_state(pos_b)
        return {
            "from": pos_a,
            "to": pos_b,
            "cost_delta": state_b.cumulative_cost - state_a.cumulative_cost,
            "token_delta": state_b.cumulative_tokens - state_a.cumulative_tokens,
            "duration_delta_ms": state_b.cumulative_duration_ms - state_a.cumulative_duration_ms,
            "new_tools": [t for t in state_b.tools_called if t not in state_a.tools_called],
            "new_errors": [e for e in state_b.errors if e not in state_a.errors],
            "steps_between": abs(pos_b - pos_a),
        }

    # -- Rich rendering ----------------------------------------------------

    def render_timeline_bar(self, width: int = 60) -> str:
        """Render a visual timeline bar with position indicator."""
        if not self._steps:
            return "[empty timeline]"

        bar_chars: List[str] = []
        for i, step in enumerate(self._steps):
            if i == self._position:
                bar_chars.append("\u25bc")  # ▼ current position
            elif step.type == StepType.LLM_CALL:
                bar_chars.append("\u2588")  # █ LLM
            elif step.type == StepType.TOOL_CALL:
                if step.tool_call and not step.tool_call.success:
                    bar_chars.append("\u2573")  # ╳ error
                else:
                    bar_chars.append("\u2592")  # ▒ tool
            elif step.type == StepType.DECISION:
                bar_chars.append("\u25c6")  # ◆ decision
            else:
                bar_chars.append("\u2591")  # ░ other

        return "".join(bar_chars)

    def render_step_label(self, position: Optional[int] = None) -> str:
        """Human-readable label for a step."""
        pos = position if position is not None else self._position
        if pos < 0 or pos >= len(self._steps):
            return "(out of range)"

        step = self._steps[pos]
        parts = [f"[{pos}/{len(self._steps)-1}]"]

        if step.type == StepType.LLM_CALL and step.llm_call:
            parts.append(f"LLM: {step.llm_call.model}")
            parts.append(f"({step.llm_call.input_tokens}+{step.llm_call.output_tokens} tok)")
            parts.append(f"${step.llm_call.cost_usd:.4f}")
        elif step.type == StepType.TOOL_CALL and step.tool_call:
            status = "\u2713" if step.tool_call.success else "\u2717"
            parts.append(f"Tool: {step.tool_call.tool_name} {status}")
        elif step.type == StepType.DECISION and step.decision:
            parts.append(f"Decision: {step.decision.type.value}")
        else:
            parts.append(step.type.value)

        parts.append(f"[{step.duration_ms:.0f}ms]")
        return "  ".join(parts)

    # -- Internal ----------------------------------------------------------

    def _build_state(self, position: int) -> TimelineState:
        """Build a complete state snapshot at a given position."""
        position = max(0, min(position, len(self._steps) - 1))

        cum_cost = 0.0
        cum_tokens = 0
        cum_duration = 0.0
        tools: List[str] = []
        tool_counts: Dict[str, int] = {}
        llm_count = 0
        decisions: List[str] = []
        errors: List[str] = []

        for i in range(position + 1):
            step = self._steps[i]
            cum_duration += step.duration_ms

            if step.llm_call:
                cum_cost += step.llm_call.cost_usd
                cum_tokens += step.llm_call.input_tokens + step.llm_call.output_tokens
                llm_count += 1

            if step.tool_call:
                name = step.tool_call.tool_name
                if name not in tools:
                    tools.append(name)
                tool_counts[name] = tool_counts.get(name, 0) + 1
                if not step.tool_call.success:
                    errors.append(f"Step {i}: {name} — {step.tool_call.error or 'failed'}")

            if step.decision:
                decisions.append(f"Step {i}: {step.decision.type.value} — {step.decision.reason}")

        current_step = self._steps[position] if self._steps else None

        state = TimelineState(
            position=position,
            total_steps=len(self._steps),
            current_step=current_step,
            cumulative_cost=cum_cost,
            cumulative_tokens=cum_tokens,
            cumulative_duration_ms=cum_duration,
            tools_called=tools,
            tools_called_count=tool_counts,
            llm_calls_count=llm_count,
            decisions_made=decisions,
            errors=errors,
        )

        # Check breakpoints
        if current_step:
            for bp in self._breakpoints:
                if bp.matches(current_step, state):
                    state.hit_breakpoints.append(bp)

        return state

    def _next_bp_id(self) -> int:
        self._bp_counter += 1
        return self._bp_counter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preview_messages(messages, max_chars: int = 200) -> str:
    if not messages:
        return "(empty)"
    parts = []
    for msg in messages[-3:]:
        role = msg.role
        content = msg.content if isinstance(msg.content, str) else "[structured]"
        parts.append(f"{role}: {_truncate(content, 80)}")
    return " | ".join(parts)


def _preview_message(msg, max_chars: int = 200) -> str:
    content = msg.content if isinstance(msg.content, str) else "[structured]"
    return _truncate(content, max_chars)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
