"""CrewAI integration plugin for AgentProbe.

Provides ``AgentProbeCrewHandler`` that automatically records every agent step,
task execution, tool call, and LLM interaction in a CrewAI crew run.  Includes
built-in assertion helpers identical to the LangChain plugin.

Usage
-----
::

    from agentprobe.integrations.crewai_plugin import AgentProbeCrewHandler

    handler = AgentProbeCrewHandler(session="my-crew-test")
    crew = Crew(
        agents=[...],
        tasks=[...],
        callbacks=[handler],
    )
    result = crew.kickoff()

    # Then test
    handler.assert_cost_under(0.50)
    handler.assert_no_errors()
    handler.assert_latency_under(30.0)
    handler.assert_tool_called("search")
    handler.get_recording()  # returns full trace

Wrapping individual tasks::

    from agentprobe.integrations.crewai_plugin import AgentProbeCrewHandler

    handler = AgentProbeCrewHandler(session="task-test")

    # Manual instrumentation for fine-grained control
    handler.on_task_start(task_name="research", agent_name="researcher")
    # ... task runs ...
    handler.on_task_end(task_name="research", output="findings...")

    recording = handler.get_recording()
"""

from __future__ import annotations

import re
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agentprobe.core.models import (
    AgentRecording,
    AgentStep,
    AgentInput,
    AgentOutput,
    DecisionRecord,
    DecisionType,
    EnvironmentSnapshot,
    LLMCallRecord,
    Message,
    OutputStatus,
    RecordingMetadata,
    StepType,
    ToolCallRecord,
)
from agentprobe.utils.cost import CostCalculator
from agentprobe.utils.redaction import RedactionEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII detection patterns
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("phone_us", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ip_address", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]


# ---------------------------------------------------------------------------
# Internal task / agent span tracking
# ---------------------------------------------------------------------------

class _TaskSpan:
    """Tracks a single CrewAI task execution."""

    __slots__ = (
        "span_id",
        "task_name",
        "agent_name",
        "start_time",
        "end_time",
        "output",
        "error",
        "metadata",
    )

    def __init__(
        self,
        task_name: str,
        agent_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.span_id: str = str(uuid.uuid4())
        self.task_name = task_name
        self.agent_name = agent_name
        self.start_time: float = time.perf_counter()
        self.end_time: Optional[float] = None
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        self.metadata: Dict[str, Any] = metadata or {}

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.perf_counter() - self.start_time) * 1000.0
        return (self.end_time - self.start_time) * 1000.0

    def finish(self, output: Optional[str] = None, error: Optional[str] = None) -> None:
        self.end_time = time.perf_counter()
        self.output = output
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "task_name": self.task_name,
            "agent_name": self.agent_name,
            "duration_ms": round(self.duration_ms, 3),
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# AgentProbeCrewHandler
# ---------------------------------------------------------------------------

class AgentProbeCrewHandler:
    """CrewAI-compatible callback handler that records every event into an
    AgentProbe recording.

    This handler implements a callback interface compatible with CrewAI's
    callback system *without* requiring ``crewai`` as a hard dependency.
    All CrewAI lifecycle events (task start/end, agent delegation, tool use,
    and LLM calls) are captured as AgentProbe steps.

    Parameters
    ----------
    session:
        A human-readable name for this recording session.
    tags:
        Optional list of tags attached to the recording metadata.
    redaction:
        Whether to redact PII/secrets from recorded content.
    custom_pricing:
        Optional dict of model pricing overrides passed to
        :class:`agentprobe.utils.cost.CostCalculator`.
    """

    def __init__(
        self,
        session: str = "crewai-session",
        tags: Optional[List[str]] = None,
        redaction: bool = True,
        custom_pricing: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> None:
        self._session_name = session
        self._tags = list(tags) if tags else []
        self._redaction = RedactionEngine(enabled=redaction)
        self._cost_calc = CostCalculator(custom_pricing=custom_pricing or {})

        self._session_start = time.perf_counter()
        self._session_start_utc = datetime.now(timezone.utc)

        # Accumulated data
        self._steps: list[AgentStep] = []
        self._messages: list[Message] = []
        self._errors: list[Dict[str, Any]] = []
        self._task_spans: Dict[str, _TaskSpan] = {}  # task_name -> span
        self._active_tasks: list[str] = []  # stack of active task names
        self._tool_starts: Dict[str, float] = {}  # tool_key -> perf_counter
        self._llm_starts: Dict[str, float] = {}  # llm_key -> perf_counter
        self._llm_models: Dict[str, str] = {}  # llm_key -> model
        self._delegations: list[Dict[str, Any]] = []
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    # -- Internal helpers ---------------------------------------------------

    def _next_step(self) -> int:
        return len(self._steps) + 1

    def _run_key(self, identifier: Any) -> str:
        return str(identifier) if identifier is not None else str(uuid.uuid4())

    def _elapsed_ms(self, start: float) -> float:
        return (time.perf_counter() - start) * 1000.0

    def _redact(self, text: Any) -> Any:
        if isinstance(text, str):
            return self._redaction.redact(text)
        return self._redaction._walk(text)

    # ===================================================================
    # CrewAI callback interface — Tasks
    # ===================================================================

    def on_task_start(
        self,
        task_name: str,
        agent_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a CrewAI task begins execution.

        Parameters
        ----------
        task_name:
            Identifier for the task (e.g. the task description or key).
        agent_name:
            Name of the agent assigned to this task.
        metadata:
            Optional extra metadata to attach to this task span.
        """
        span = _TaskSpan(
            task_name=task_name,
            agent_name=agent_name,
            metadata=metadata,
        )
        self._task_spans[task_name] = span
        self._active_tasks.append(task_name)

        self._messages.append(
            Message(
                role="system",
                content=self._redact(
                    f"[CrewAI] Task started: {task_name} (agent: {agent_name})"
                ),
                timestamp=datetime.now(timezone.utc),
            )
        )

    def on_task_end(
        self,
        task_name: str,
        output: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a CrewAI task completes successfully.

        Parameters
        ----------
        task_name:
            Identifier for the task that completed.
        output:
            The task's output string, if any.
        """
        span = self._task_spans.get(task_name)
        if span is not None:
            span.finish(output=self._redact(output) if output else None)

        if task_name in self._active_tasks:
            self._active_tasks.remove(task_name)

        self._messages.append(
            Message(
                role="system",
                content=self._redact(
                    f"[CrewAI] Task completed: {task_name}"
                ),
                timestamp=datetime.now(timezone.utc),
            )
        )

    def on_task_error(
        self,
        task_name: str,
        error: str,
        **kwargs: Any,
    ) -> None:
        """Called when a CrewAI task fails.

        Parameters
        ----------
        task_name:
            Identifier for the task that failed.
        error:
            Error message or traceback string.
        """
        span = self._task_spans.get(task_name)
        if span is not None:
            span.finish(error=error)

        if task_name in self._active_tasks:
            self._active_tasks.remove(task_name)

        self._errors.append({
            "type": "task_error",
            "task": task_name,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ===================================================================
    # CrewAI callback interface — Agent delegation
    # ===================================================================

    def on_agent_delegation(
        self,
        from_agent: str,
        to_agent: str,
        task_name: str = "",
        reason: str = "",
        **kwargs: Any,
    ) -> None:
        """Called when one agent delegates work to another.

        Parameters
        ----------
        from_agent:
            Name of the delegating agent.
        to_agent:
            Name of the agent receiving the delegation.
        task_name:
            Associated task name, if any.
        reason:
            Reason for delegation.
        """
        self._delegations.append({
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task": task_name,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        decision = DecisionRecord(
            type=DecisionType.DELEGATE,
            reason=self._redact(reason) or f"Delegation from {from_agent} to {to_agent}",
            alternatives_considered=[],
        )

        step = AgentStep(
            step_number=self._next_step(),
            type=StepType.DECISION,
            timestamp=datetime.now(timezone.utc),
            decision=decision,
        )
        self._steps.append(step)

    # ===================================================================
    # CrewAI callback interface — Tools
    # ===================================================================

    def on_tool_start(
        self,
        tool_name: str,
        tool_input: Any = None,
        agent_name: str = "",
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool begins execution within a CrewAI agent.

        Parameters
        ----------
        tool_name:
            Name of the tool being invoked.
        tool_input:
            The input passed to the tool.
        agent_name:
            Name of the agent invoking the tool.
        run_id:
            Optional unique identifier for this tool run.
        """
        key = self._run_key(run_id or f"{tool_name}_{uuid.uuid4()}")
        self._tool_starts[key] = time.perf_counter()
        # Store tool_name in a way we can retrieve it
        self._tool_starts[f"{key}_name"] = tool_name  # type: ignore[assignment]
        self._tool_starts[f"{key}_input"] = tool_input  # type: ignore[assignment]

    def on_tool_end(
        self,
        tool_name: str,
        tool_output: Any = None,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool completes successfully.

        Parameters
        ----------
        tool_name:
            Name of the tool that completed.
        tool_output:
            The tool's output value.
        run_id:
            Optional unique identifier matching the corresponding start call.
        """
        # Find matching start
        key = self._run_key(run_id) if run_id else None
        start_time = time.perf_counter()

        if key and key in self._tool_starts:
            start_time_val = self._tool_starts.pop(key)
            if isinstance(start_time_val, float):
                start_time = start_time_val
            # Clean up metadata keys
            self._tool_starts.pop(f"{key}_name", None)
            self._tool_starts.pop(f"{key}_input", None)
        else:
            # Try to find by tool name
            for k in list(self._tool_starts.keys()):
                if not k.endswith("_name") and not k.endswith("_input"):
                    name_key = f"{k}_name"
                    if self._tool_starts.get(name_key) == tool_name:
                        start_val = self._tool_starts.pop(k)
                        if isinstance(start_val, float):
                            start_time = start_val
                        self._tool_starts.pop(name_key, None)
                        self._tool_starts.pop(f"{k}_input", None)
                        break

        latency_ms = self._elapsed_ms(start_time)

        tool_record = ToolCallRecord(
            tool_name=tool_name,
            tool_output=self._redact(tool_output),
            duration_ms=latency_ms,
            success=True,
        )

        step = AgentStep(
            step_number=self._next_step(),
            type=StepType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            duration_ms=latency_ms,
            tool_call=tool_record,
        )
        self._steps.append(step)

    def on_tool_error(
        self,
        tool_name: str,
        error: str,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool raises an error.

        Parameters
        ----------
        tool_name:
            Name of the tool that failed.
        error:
            Error message or traceback string.
        run_id:
            Optional unique identifier matching the corresponding start call.
        """
        self._errors.append({
            "type": "tool_error",
            "tool": tool_name,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        tool_record = ToolCallRecord(
            tool_name=tool_name,
            duration_ms=0.0,
            success=False,
            error=error,
        )

        step = AgentStep(
            step_number=self._next_step(),
            type=StepType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            tool_call=tool_record,
        )
        self._steps.append(step)

    # ===================================================================
    # CrewAI callback interface — LLM calls
    # ===================================================================

    def on_llm_start(
        self,
        model: str = "",
        prompt: str = "",
        agent_name: str = "",
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM call begins within a CrewAI agent.

        Parameters
        ----------
        model:
            The model name being called.
        prompt:
            The prompt text sent to the model.
        agent_name:
            Name of the agent making the LLM call.
        run_id:
            Optional unique identifier for this LLM run.
        """
        key = self._run_key(run_id or uuid.uuid4())
        self._llm_starts[key] = time.perf_counter()
        self._llm_models[key] = model

        if prompt:
            self._messages.append(
                Message(
                    role="user",
                    content=self._redact(prompt),
                    timestamp=datetime.now(timezone.utc),
                )
            )

    def on_llm_end(
        self,
        output: str = "",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM call completes.

        Parameters
        ----------
        output:
            The generated text output.
        model:
            The model name (overrides the one from start if provided).
        input_tokens:
            Number of input tokens consumed.
        output_tokens:
            Number of output tokens generated.
        run_id:
            Optional unique identifier matching the corresponding start call.
        """
        key = self._run_key(run_id) if run_id else None
        start_time = self._session_start  # fallback

        if key and key in self._llm_starts:
            start_time = self._llm_starts.pop(key)
            if not model:
                model = self._llm_models.pop(key, "unknown")
            else:
                self._llm_models.pop(key, None)
        else:
            # Try to find any pending start
            for k in list(self._llm_starts.keys()):
                start_time = self._llm_starts.pop(k)
                if not model:
                    model = self._llm_models.pop(k, "unknown")
                else:
                    self._llm_models.pop(k, None)
                break

        latency_ms = self._elapsed_ms(start_time)

        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        cost_usd = self._cost_calc.calculate(model, input_tokens, output_tokens)

        if output:
            self._messages.append(
                Message(
                    role="assistant",
                    content=self._redact(output),
                    timestamp=datetime.now(timezone.utc),
                    tokens=input_tokens + output_tokens,
                )
            )

        llm_record = LLMCallRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        step = AgentStep(
            step_number=self._next_step(),
            type=StepType.LLM_CALL,
            timestamp=datetime.now(timezone.utc),
            duration_ms=latency_ms,
            llm_call=llm_record,
        )
        self._steps.append(step)

    def on_llm_error(
        self,
        error: str,
        model: str = "",
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM call fails.

        Parameters
        ----------
        error:
            Error message or traceback string.
        model:
            The model that was being called.
        run_id:
            Optional unique identifier matching the corresponding start call.
        """
        key = self._run_key(run_id) if run_id else None
        if key:
            self._llm_starts.pop(key, None)
            if not model:
                model = self._llm_models.pop(key, "unknown")
            else:
                self._llm_models.pop(key, None)

        self._errors.append({
            "type": "llm_error",
            "model": model,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ===================================================================
    # CrewAI callback interface — Crew lifecycle
    # ===================================================================

    def on_crew_start(
        self,
        crew_name: str = "",
        agent_names: Optional[List[str]] = None,
        task_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a CrewAI crew begins execution.

        Parameters
        ----------
        crew_name:
            Name of the crew.
        agent_names:
            Names of all agents in the crew.
        task_names:
            Names of all tasks in the crew.
        """
        self._messages.append(
            Message(
                role="system",
                content=self._redact(
                    f"[CrewAI] Crew started: {crew_name} "
                    f"(agents: {agent_names or []}, tasks: {task_names or []})"
                ),
                timestamp=datetime.now(timezone.utc),
            )
        )

    def on_crew_end(
        self,
        crew_name: str = "",
        output: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a CrewAI crew completes.

        Parameters
        ----------
        crew_name:
            Name of the crew.
        output:
            Final crew output string.
        """
        self._messages.append(
            Message(
                role="system",
                content=self._redact(
                    f"[CrewAI] Crew completed: {crew_name}"
                ),
                timestamp=datetime.now(timezone.utc),
            )
        )

    # ===================================================================
    # Recording & assertion API
    # ===================================================================

    def get_recording(self) -> Dict[str, Any]:
        """Return the full recording as a plain dictionary.

        Returns
        -------
        dict
            A serialised :class:`AgentRecording` with all captured steps,
            messages, task spans, delegations, and errors.
        """
        recording = self._build_recording().to_dict()
        recording["task_spans"] = [
            span.to_dict() for span in self._task_spans.values()
        ]
        recording["delegations"] = list(self._delegations)
        return recording

    def _build_recording(self) -> AgentRecording:
        elapsed_ms = (time.perf_counter() - self._session_start) * 1000.0
        total_cost = sum(
            s.llm_call.cost_usd for s in self._steps if s.llm_call is not None
        )
        total_tokens = self._total_input_tokens + self._total_output_tokens

        metadata = RecordingMetadata(
            name=self._session_name,
            timestamp=self._session_start_utc,
            duration_ms=elapsed_ms,
            agent_framework="crewai",
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            tags=self._tags,
        )

        return AgentRecording(
            metadata=metadata,
            input=AgentInput(),
            output=AgentOutput(),
            steps=list(self._steps),
            messages=list(self._messages),
            environment=EnvironmentSnapshot(),
        )

    def get_cost_breakdown(self) -> Dict[str, Any]:
        """Return a per-model cost breakdown.

        Returns
        -------
        dict
            Keys: ``total_cost``, ``total_input_tokens``, ``total_output_tokens``,
            ``by_model`` (dict mapping model names to their cost/token subtotals).
        """
        by_model: Dict[str, Dict[str, float]] = {}
        for step in self._steps:
            if step.llm_call is not None:
                model = step.llm_call.model
                entry = by_model.setdefault(model, {
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "calls": 0,
                })
                entry["cost_usd"] += step.llm_call.cost_usd
                entry["input_tokens"] += step.llm_call.input_tokens
                entry["output_tokens"] += step.llm_call.output_tokens
                entry["calls"] += 1

        total_cost = sum(e["cost_usd"] for e in by_model.values())
        return {
            "total_cost": total_cost,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "by_model": by_model,
        }

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Return an ordered timeline of all recorded events.

        Returns
        -------
        list[dict]
            Each entry contains step data plus task and delegation events.
        """
        timeline: list[Dict[str, Any]] = []

        for step in self._steps:
            entry: Dict[str, Any] = {
                "step_number": step.step_number,
                "type": step.type.value,
                "timestamp": step.timestamp.isoformat() if step.timestamp else None,
                "duration_ms": round(step.duration_ms, 3),
            }
            if step.llm_call is not None:
                entry["model"] = step.llm_call.model
                entry["input_tokens"] = step.llm_call.input_tokens
                entry["output_tokens"] = step.llm_call.output_tokens
                entry["cost_usd"] = step.llm_call.cost_usd
            if step.tool_call is not None:
                entry["tool_name"] = step.tool_call.tool_name
                entry["success"] = step.tool_call.success
                entry["error"] = step.tool_call.error
            if step.decision is not None:
                entry["decision_type"] = step.decision.type.value
                entry["reason"] = step.decision.reason
            timeline.append(entry)

        # Append task span summaries
        for span in self._task_spans.values():
            timeline.append({
                "type": "task_span",
                **span.to_dict(),
            })

        # Append delegations
        for delegation in self._delegations:
            timeline.append({
                "type": "delegation",
                **delegation,
            })

        return timeline

    def get_task_summary(self) -> List[Dict[str, Any]]:
        """Return a summary of all task executions.

        Returns
        -------
        list[dict]
            Each entry contains task name, agent, duration, output, and
            error information.
        """
        return [span.to_dict() for span in self._task_spans.values()]

    # -- Assertion methods --------------------------------------------------

    def assert_cost_under(self, amount: float) -> None:
        """Assert that total cost is strictly below *amount* USD.

        Raises
        ------
        AssertionError
            If the total cost equals or exceeds *amount*.
        """
        total = sum(
            s.llm_call.cost_usd for s in self._steps if s.llm_call is not None
        )
        if total >= amount:
            raise AssertionError(
                f"Total cost ${total:.6f} exceeds limit ${amount:.6f}"
            )

    def assert_latency_under(self, seconds: float) -> None:
        """Assert that total session wall-time is below *seconds*.

        Raises
        ------
        AssertionError
            If the elapsed time equals or exceeds *seconds*.
        """
        elapsed = time.perf_counter() - self._session_start
        if elapsed >= seconds:
            raise AssertionError(
                f"Total latency {elapsed:.3f}s exceeds limit {seconds:.3f}s"
            )

    def assert_no_errors(self) -> None:
        """Assert that no errors were recorded during the session.

        Raises
        ------
        AssertionError
            If any LLM, task, tool, or delegation errors were captured.
        """
        if self._errors:
            summary = "; ".join(
                f"{e['type']}: {e['error']}" for e in self._errors
            )
            raise AssertionError(
                f"Recorded {len(self._errors)} error(s): {summary}"
            )

        tool_errors = [
            s for s in self._steps
            if s.tool_call is not None and not s.tool_call.success
        ]
        if tool_errors:
            details = "; ".join(
                f"step {s.step_number}: {s.tool_call.error}"
                for s in tool_errors
                if s.tool_call is not None
            )
            raise AssertionError(
                f"Recorded {len(tool_errors)} tool error(s): {details}"
            )

        task_errors = [
            span for span in self._task_spans.values()
            if span.error is not None
        ]
        if task_errors:
            details = "; ".join(
                f"task {s.task_name}: {s.error}" for s in task_errors
            )
            raise AssertionError(
                f"Recorded {len(task_errors)} task error(s): {details}"
            )

    def assert_tool_called(self, tool_name: str) -> None:
        """Assert that a specific tool was invoked at least once.

        Parameters
        ----------
        tool_name:
            The name of the tool to check for.

        Raises
        ------
        AssertionError
            If the tool was never invoked.
        """
        called = any(
            s.tool_call is not None and s.tool_call.tool_name == tool_name
            for s in self._steps
        )
        if not called:
            all_tools = sorted({
                s.tool_call.tool_name
                for s in self._steps
                if s.tool_call is not None
            })
            raise AssertionError(
                f"Tool {tool_name!r} was never called. "
                f"Tools called: {all_tools}"
            )

    def assert_min_quality(self, score: float) -> None:
        """Assert a minimum quality score based on heuristics.

        The quality score (0.0-1.0) is derived from:

        - Error-free execution
        - Tool success rate
        - Task completion rate
        - Presence of LLM output

        Parameters
        ----------
        score:
            Minimum acceptable quality score (0.0 to 1.0).

        Raises
        ------
        AssertionError
            If the computed quality score falls below *score*.
        """
        quality = self._compute_quality_score()
        if quality < score:
            raise AssertionError(
                f"Quality score {quality:.3f} is below minimum {score:.3f}"
            )

    def _compute_quality_score(self) -> float:
        """Compute a heuristic quality score between 0.0 and 1.0."""
        factors: list[float] = []

        # Factor 1: No errors
        factors.append(1.0 if not self._errors else 0.0)

        # Factor 2: Tool success rate
        tool_steps = [s for s in self._steps if s.tool_call is not None]
        if tool_steps:
            success_rate = sum(1 for s in tool_steps if s.tool_call and s.tool_call.success) / len(tool_steps)
            factors.append(success_rate)
        else:
            factors.append(1.0)

        # Factor 3: Task completion rate
        if self._task_spans:
            completed = sum(
                1 for s in self._task_spans.values()
                if s.end_time is not None and s.error is None
            )
            factors.append(completed / len(self._task_spans))
        else:
            factors.append(1.0)

        # Factor 4: Has LLM output
        has_output = any(s.llm_call is not None for s in self._steps)
        factors.append(1.0 if has_output else 0.3)

        return sum(factors) / len(factors) if factors else 0.0

    def assert_no_pii(self) -> None:
        """Assert that no PII patterns are found in recorded messages.

        Checks all recorded message content against common PII patterns
        (SSN, email, credit card, US phone, IP address).

        Raises
        ------
        AssertionError
            If PII is detected in any recorded message.
        """
        detections: list[str] = []
        for msg in self._messages:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            for label, pattern in _PII_PATTERNS:
                matches = pattern.findall(text)
                if matches:
                    detections.append(f"{label}: {len(matches)} match(es)")

        if detections:
            raise AssertionError(
                f"PII detected in recorded messages: {'; '.join(detections)}"
            )

    def assert_task_completed(self, task_name: str) -> None:
        """Assert that a specific task completed without errors.

        Parameters
        ----------
        task_name:
            The name of the task to check.

        Raises
        ------
        AssertionError
            If the task was not found, did not finish, or had an error.
        """
        span = self._task_spans.get(task_name)
        if span is None:
            raise AssertionError(
                f"Task {task_name!r} was not found. "
                f"Known tasks: {list(self._task_spans.keys())}"
            )
        if span.end_time is None:
            raise AssertionError(
                f"Task {task_name!r} did not complete (still running or abandoned)"
            )
        if span.error is not None:
            raise AssertionError(
                f"Task {task_name!r} failed with error: {span.error}"
            )

    def assert_delegation_occurred(
        self,
        from_agent: Optional[str] = None,
        to_agent: Optional[str] = None,
    ) -> None:
        """Assert that at least one delegation occurred matching the criteria.

        Parameters
        ----------
        from_agent:
            If provided, require the delegation to originate from this agent.
        to_agent:
            If provided, require the delegation to target this agent.

        Raises
        ------
        AssertionError
            If no matching delegation was recorded.
        """
        for d in self._delegations:
            match = True
            if from_agent is not None and d.get("from_agent") != from_agent:
                match = False
            if to_agent is not None and d.get("to_agent") != to_agent:
                match = False
            if match:
                return

        raise AssertionError(
            f"No delegation found matching from_agent={from_agent!r}, "
            f"to_agent={to_agent!r}. "
            f"Recorded delegations: {self._delegations}"
        )
