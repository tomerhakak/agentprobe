"""LangChain integration plugin for AgentProbe.

Provides ``AgentProbeCallbackHandler`` and ``AgentProbeTracer`` that
automatically record every LLM call, chain run, tool invocation, and agent
action into an AgentProbe recording session.  Built-in assertion helpers make
it trivial to write cost / latency / quality guards in your test suite.

Usage
-----
::

    from agentprobe.integrations.langchain_plugin import AgentProbeCallbackHandler

    handler = AgentProbeCallbackHandler(session="my-test")
    agent.run("query", callbacks=[handler])

    # Then test
    handler.assert_cost_under(0.10)
    handler.assert_no_errors()
    handler.assert_latency_under(5.0)
    handler.get_recording()  # returns full trace

Full tracer with parent-child relationships::

    from agentprobe.integrations.langchain_plugin import AgentProbeTracer

    tracer = AgentProbeTracer(session="my-traced-run")
    agent.run("query", callbacks=[tracer])

    timeline = tracer.get_timeline()
    recording = tracer.get_recording()
"""

from __future__ import annotations

import re
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

from agentprobe.core.models import (
    AgentRecording,
    AgentStep,
    LLMCallRecord,
    Message,
    RecordingMetadata,
    StepType,
    ToolCallRecord,
    AgentInput,
    AgentOutput,
    EnvironmentSnapshot,
    OutputStatus,
)
from agentprobe.utils.cost import CostCalculator
from agentprobe.utils.redaction import RedactionEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII detection patterns (shared with asserter)
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("phone_us", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ip_address", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]


# ---------------------------------------------------------------------------
# Internal span model for parent-child tracing
# ---------------------------------------------------------------------------

class _Span:
    """Lightweight span used by :class:`AgentProbeTracer` to track nesting."""

    __slots__ = (
        "span_id",
        "parent_id",
        "name",
        "span_type",
        "start_time",
        "end_time",
        "metadata",
        "error",
        "children",
    )

    def __init__(
        self,
        name: str,
        span_type: str,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.span_id: str = str(uuid.uuid4())
        self.parent_id: Optional[str] = parent_id
        self.name = name
        self.span_type = span_type
        self.start_time: float = time.perf_counter()
        self.end_time: Optional[float] = None
        self.metadata: Dict[str, Any] = metadata or {}
        self.error: Optional[str] = None
        self.children: list[str] = []

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.perf_counter() - self.start_time) * 1000.0
        return (self.end_time - self.start_time) * 1000.0

    def finish(self) -> None:
        self.end_time = time.perf_counter()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "type": self.span_type,
            "duration_ms": round(self.duration_ms, 3),
            "metadata": self.metadata,
            "error": self.error,
            "children": list(self.children),
        }


# ---------------------------------------------------------------------------
# AgentProbeCallbackHandler
# ---------------------------------------------------------------------------

class AgentProbeCallbackHandler:
    """LangChain-compatible callback handler that records every event into an
    AgentProbe recording.

    This handler implements the LangChain ``BaseCallbackHandler`` interface
    *without* requiring ``langchain`` as a hard dependency.  When ``langchain``
    is installed, it also inherits from ``BaseCallbackHandler`` so that type
    checks pass.

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
        session: str = "langchain-session",
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
        self._llm_starts: Dict[str, float] = {}  # run_id -> perf_counter
        self._chain_starts: Dict[str, float] = {}
        self._tool_starts: Dict[str, float] = {}
        self._llm_models: Dict[str, str] = {}  # run_id -> model name
        self._agent_actions: list[Dict[str, Any]] = []
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    # -- Internal helpers ---------------------------------------------------

    def _next_step(self) -> int:
        return len(self._steps) + 1

    def _run_key(self, run_id: Any) -> str:
        """Normalise a run ID to a string."""
        return str(run_id) if run_id is not None else str(uuid.uuid4())

    def _elapsed_ms(self, start: float) -> float:
        return (time.perf_counter() - start) * 1000.0

    def _redact(self, text: Any) -> Any:
        if isinstance(text, str):
            return self._redaction.redact(text)
        return self._redaction._walk(text)

    def _extract_token_usage(self, response: Any) -> tuple[int, int, str]:
        """Extract (input_tokens, output_tokens, model) from an LLM response.

        Works with LangChain ``LLMResult`` objects as well as plain dicts.
        """
        input_tokens = 0
        output_tokens = 0
        model = ""

        if response is None:
            return input_tokens, output_tokens, model

        # LangChain LLMResult
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if isinstance(usage, dict):
                input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            model = llm_output.get("model_name", "") or llm_output.get("model", "")

        return input_tokens, output_tokens, model

    # ===================================================================
    # LangChain callback interface — LLM
    # ===================================================================

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM call begins."""
        key = self._run_key(run_id)
        self._llm_starts[key] = time.perf_counter()

        # Try to capture model name from serialized or invocation params
        model_name = (
            serialized.get("name", "")
            or serialized.get("id", [""])[-1]
            if serialized
            else ""
        )
        invocation = kwargs.get("invocation_params") or {}
        if isinstance(invocation, dict):
            model_name = invocation.get("model_name", "") or invocation.get("model", "") or model_name
        self._llm_models[key] = model_name

        # Record input messages
        for prompt in prompts:
            self._messages.append(
                Message(
                    role="user",
                    content=self._redact(prompt),
                    timestamp=datetime.now(timezone.utc),
                )
            )

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[Any],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chat model call begins (ChatOpenAI, ChatAnthropic, etc.)."""
        key = self._run_key(run_id)
        self._llm_starts[key] = time.perf_counter()

        model_name = (
            serialized.get("name", "")
            or serialized.get("id", [""])[-1]
            if serialized
            else ""
        )
        invocation = kwargs.get("invocation_params") or {}
        if isinstance(invocation, dict):
            model_name = invocation.get("model_name", "") or invocation.get("model", "") or model_name
        self._llm_models[key] = model_name

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM call completes."""
        key = self._run_key(run_id)
        start = self._llm_starts.pop(key, time.perf_counter())
        latency_ms = self._elapsed_ms(start)

        input_tokens, output_tokens, resp_model = self._extract_token_usage(response)
        model = resp_model or self._llm_models.pop(key, "unknown")

        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        cost_usd = self._cost_calc.calculate(model, input_tokens, output_tokens)

        # Extract output text
        output_text = ""
        if response is not None:
            generations = getattr(response, "generations", None)
            if generations and len(generations) > 0 and len(generations[0]) > 0:
                output_text = getattr(generations[0][0], "text", str(generations[0][0]))

        output_msg = Message(
            role="assistant",
            content=self._redact(output_text),
            timestamp=datetime.now(timezone.utc),
            tokens=input_tokens + output_tokens,
        )
        self._messages.append(output_msg)

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
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM call raises an error."""
        key = self._run_key(run_id)
        start = self._llm_starts.pop(key, time.perf_counter())
        latency_ms = self._elapsed_ms(start)
        model = self._llm_models.pop(key, "unknown")

        self._errors.append({
            "type": "llm_error",
            "model": model,
            "error": str(error),
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        llm_record = LLMCallRecord(
            model=model,
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

    # ===================================================================
    # LangChain callback interface — Chains
    # ===================================================================

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain starts running."""
        key = self._run_key(run_id)
        self._chain_starts[key] = time.perf_counter()

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain finishes."""
        key = self._run_key(run_id)
        self._chain_starts.pop(key, None)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain errors."""
        key = self._run_key(run_id)
        self._chain_starts.pop(key, None)
        self._errors.append({
            "type": "chain_error",
            "error": str(error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ===================================================================
    # LangChain callback interface — Tools
    # ===================================================================

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts execution."""
        key = self._run_key(run_id)
        self._tool_starts[key] = time.perf_counter()

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes successfully."""
        key = self._run_key(run_id)
        start = self._tool_starts.pop(key, time.perf_counter())
        latency_ms = self._elapsed_ms(start)

        # Try to extract tool name from kwargs
        tool_name = kwargs.get("name", "unknown_tool")

        tool_record = ToolCallRecord(
            tool_name=tool_name,
            tool_output=self._redact(output),
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
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool raises an error."""
        key = self._run_key(run_id)
        start = self._tool_starts.pop(key, time.perf_counter())
        latency_ms = self._elapsed_ms(start)

        tool_name = kwargs.get("name", "unknown_tool")

        self._errors.append({
            "type": "tool_error",
            "tool": tool_name,
            "error": str(error),
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        tool_record = ToolCallRecord(
            tool_name=tool_name,
            duration_ms=latency_ms,
            success=False,
            error=str(error),
        )

        step = AgentStep(
            step_number=self._next_step(),
            type=StepType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            duration_ms=latency_ms,
            tool_call=tool_record,
        )
        self._steps.append(step)

    # ===================================================================
    # LangChain callback interface — Agent
    # ===================================================================

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when the agent decides on an action."""
        tool = getattr(action, "tool", "unknown")
        tool_input = getattr(action, "tool_input", "")
        log_text = getattr(action, "log", "")

        self._agent_actions.append({
            "tool": tool,
            "tool_input": self._redact(tool_input),
            "log": self._redact(log_text),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when the agent finishes its run."""
        output = getattr(finish, "return_values", {})
        log_text = getattr(finish, "log", "")

        self._agent_actions.append({
            "type": "finish",
            "return_values": self._redact(output),
            "log": self._redact(log_text),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ===================================================================
    # LangChain retriever callbacks (no-ops for compatibility)
    # ===================================================================

    def on_retriever_start(self, serialized: Dict[str, Any], query: str, **kwargs: Any) -> None:
        """Called when a retriever starts. Recorded as metadata only."""

    def on_retriever_end(self, documents: Any, **kwargs: Any) -> None:
        """Called when a retriever finishes."""

    def on_retriever_error(self, error: BaseException, **kwargs: Any) -> None:
        """Called when a retriever errors."""
        self._errors.append({
            "type": "retriever_error",
            "error": str(error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def on_text(self, text: str, **kwargs: Any) -> None:
        """Called with intermediate text output."""

    # ===================================================================
    # Recording & assertion API
    # ===================================================================

    def get_recording(self) -> Dict[str, Any]:
        """Return the full recording as a plain dictionary.

        Returns
        -------
        dict
            A serialised :class:`AgentRecording` containing all captured steps,
            messages, metadata, and errors.
        """
        return self._build_recording().to_dict()

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
            agent_framework="langchain",
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
            Each entry contains ``step_number``, ``type``, ``timestamp``,
            ``duration_ms``, and type-specific metadata.
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
            timeline.append(entry)

        # Append agent actions
        for action in self._agent_actions:
            timeline.append({
                "type": "agent_action",
                **action,
            })

        return timeline

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
            If any LLM, chain, tool, or retriever errors were captured.
        """
        if self._errors:
            summary = "; ".join(
                f"{e['type']}: {e['error']}" for e in self._errors
            )
            raise AssertionError(
                f"Recorded {len(self._errors)} error(s): {summary}"
            )

        # Also check tool call steps for failures
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
            # Also check agent actions
            called = any(
                a.get("tool") == tool_name for a in self._agent_actions
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

        - Presence of output content
        - No errors recorded
        - Reasonable token usage
        - Successful tool calls

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

        # Factor 1: No errors (1.0 if clean, 0.0 if errors)
        factors.append(1.0 if not self._errors else 0.0)

        # Factor 2: Tool success rate
        tool_steps = [s for s in self._steps if s.tool_call is not None]
        if tool_steps:
            success_rate = sum(1 for s in tool_steps if s.tool_call and s.tool_call.success) / len(tool_steps)
            factors.append(success_rate)
        else:
            factors.append(1.0)

        # Factor 3: Has LLM output (at least one generation)
        has_output = any(s.llm_call is not None for s in self._steps)
        factors.append(1.0 if has_output else 0.3)

        # Factor 4: Reasonable step count (penalise > 50 steps slightly)
        step_count = len(self._steps)
        if step_count == 0:
            factors.append(0.2)
        elif step_count <= 50:
            factors.append(1.0)
        else:
            factors.append(max(0.5, 1.0 - (step_count - 50) / 200.0))

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


# ---------------------------------------------------------------------------
# AgentProbeTracer — extended tracer with parent-child relationships
# ---------------------------------------------------------------------------

class AgentProbeTracer(AgentProbeCallbackHandler):
    """Extended LangChain tracer that maintains parent-child span relationships.

    Inherits all callback methods from :class:`AgentProbeCallbackHandler` and
    additionally records a span tree with nesting information.  Useful for
    detailed performance analysis and visual timeline rendering.

    Parameters
    ----------
    session:
        A human-readable name for this tracing session.
    tags:
        Optional list of tags attached to the recording metadata.
    redaction:
        Whether to redact PII/secrets from recorded content.
    custom_pricing:
        Optional dict of model pricing overrides.
    """

    def __init__(
        self,
        session: str = "langchain-trace",
        tags: Optional[List[str]] = None,
        redaction: bool = True,
        custom_pricing: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> None:
        super().__init__(
            session=session,
            tags=tags,
            redaction=redaction,
            custom_pricing=custom_pricing,
        )
        self._spans: Dict[str, _Span] = {}
        self._root_spans: list[str] = []
        self._run_to_span: Dict[str, str] = {}  # run_id -> span_id

    # -- Span helpers -------------------------------------------------------

    def _start_span(
        self,
        run_id: Any,
        name: str,
        span_type: str,
        parent_run_id: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> _Span:
        key = self._run_key(run_id)
        parent_span_id: Optional[str] = None
        if parent_run_id is not None:
            parent_key = self._run_key(parent_run_id)
            parent_span_id = self._run_to_span.get(parent_key)

        span = _Span(
            name=name,
            span_type=span_type,
            parent_id=parent_span_id,
            metadata=metadata,
        )
        self._spans[span.span_id] = span
        self._run_to_span[key] = span.span_id

        if parent_span_id is not None and parent_span_id in self._spans:
            self._spans[parent_span_id].children.append(span.span_id)
        else:
            self._root_spans.append(span.span_id)

        return span

    def _end_span(self, run_id: Any, error: Optional[str] = None) -> Optional[_Span]:
        key = self._run_key(run_id)
        span_id = self._run_to_span.get(key)
        if span_id is None:
            return None
        span = self._spans.get(span_id)
        if span is not None:
            span.finish()
            if error is not None:
                span.error = error
        return span

    # -- Override callbacks to add span tracking ----------------------------

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        model_name = ""
        if serialized:
            model_name = serialized.get("name", "") or serialized.get("id", [""])[-1]
        self._start_span(
            run_id,
            name=f"llm:{model_name}",
            span_type="llm",
            parent_run_id=parent_run_id,
            metadata={"model": model_name, "prompt_count": len(prompts)},
        )
        super().on_llm_start(
            serialized, prompts, run_id=run_id, parent_run_id=parent_run_id,
            tags=tags, metadata=metadata, **kwargs,
        )

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[Any],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        model_name = ""
        if serialized:
            model_name = serialized.get("name", "") or serialized.get("id", [""])[-1]
        self._start_span(
            run_id,
            name=f"chat:{model_name}",
            span_type="llm",
            parent_run_id=parent_run_id,
            metadata={"model": model_name, "message_count": len(messages)},
        )
        super().on_chat_model_start(
            serialized, messages, run_id=run_id, parent_run_id=parent_run_id,
            tags=tags, metadata=metadata, **kwargs,
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        span = self._end_span(run_id)
        if span is not None:
            input_tokens, output_tokens, model = self._extract_token_usage(response)
            span.metadata.update({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": model or span.metadata.get("model", ""),
            })
        super().on_llm_end(response, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id, error=str(error))
        super().on_llm_error(error, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        chain_name = ""
        if serialized:
            chain_name = serialized.get("name", "") or serialized.get("id", [""])[-1]
        self._start_span(
            run_id,
            name=f"chain:{chain_name}",
            span_type="chain",
            parent_run_id=parent_run_id,
            metadata={"chain_name": chain_name},
        )
        super().on_chain_start(
            serialized, inputs, run_id=run_id, parent_run_id=parent_run_id,
            tags=tags, metadata=metadata, **kwargs,
        )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id)
        super().on_chain_end(outputs, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id, error=str(error))
        super().on_chain_error(error, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        tool_name = ""
        if serialized:
            tool_name = serialized.get("name", "") or serialized.get("id", [""])[-1]
        self._start_span(
            run_id,
            name=f"tool:{tool_name}",
            span_type="tool",
            parent_run_id=parent_run_id,
            metadata={"tool_name": tool_name, "input": self._redact(input_str)},
        )
        super().on_tool_start(
            serialized, input_str, run_id=run_id, parent_run_id=parent_run_id,
            tags=tags, metadata=metadata, **kwargs,
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id)
        super().on_tool_end(output, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id, error=str(error))
        super().on_tool_error(error, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    # -- Tracer-specific API ------------------------------------------------

    def get_span_tree(self) -> List[Dict[str, Any]]:
        """Return the full span tree as a nested list of dicts.

        Returns
        -------
        list[dict]
            Each root span with a ``children`` key containing nested child
            spans, recursively.
        """
        def _build(span_id: str) -> Optional[Dict[str, Any]]:
            span = self._spans.get(span_id)
            if span is None:
                return None
            result = span.to_dict()
            result["children"] = [
                _build(child_id)
                for child_id in span.children
                if child_id in self._spans
            ]
            return result

        return [
            tree for span_id in self._root_spans
            if (tree := _build(span_id)) is not None
        ]

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Return a flat timeline including span nesting information.

        Extends the base class timeline with ``span_id`` and ``parent_span_id``
        for each entry.

        Returns
        -------
        list[dict]
            Ordered list of events with span relationship data.
        """
        base_timeline = super().get_timeline()

        # Enrich with span data
        span_list = sorted(
            self._spans.values(),
            key=lambda s: s.start_time,
        )
        span_entries = [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_id,
                "name": s.name,
                "type": s.span_type,
                "duration_ms": round(s.duration_ms, 3),
                "error": s.error,
                "metadata": s.metadata,
            }
            for s in span_list
        ]

        return base_timeline + span_entries

    def get_recording(self) -> Dict[str, Any]:
        """Return the full recording enriched with span tree data.

        Returns
        -------
        dict
            The base recording dict plus a ``span_tree`` key.
        """
        recording = super().get_recording()
        recording["span_tree"] = self.get_span_tree()
        return recording
