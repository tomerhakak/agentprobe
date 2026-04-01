"""Recording engine for AgentProbe — captures agent execution traces."""

from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from agentprobe.core.models import (
    AgentInput,
    AgentOutput,
    AgentRecording,
    AgentStep,
    ContentBlock,
    ContentBlockType,
    DecisionRecord,
    DecisionType,
    EnvironmentSnapshot,
    InputType,
    LLMCallRecord,
    Message,
    OutputStatus,
    OutputType,
    RecordingMetadata,
    StepType,
    ToolCallRecord,
    ToolDefinition,
)
from agentprobe.utils.cost import CostCalculator
from agentprobe.utils.redaction import RedactionEngine


class RecordingSession:
    """Active recording session that captures agent execution.

    Accumulates LLM calls, tool calls, and decisions as numbered steps.
    Call :meth:`finish` to finalise the recording into an :class:`AgentRecording`.
    """

    def __init__(
        self,
        name: str,
        tags: list[str] | None = None,
        framework: str = "custom",
        redaction: RedactionEngine | None = None,
        cost_calculator: CostCalculator | None = None,
    ) -> None:
        self._name = name
        self._tags = list(tags) if tags else []
        self._framework = framework
        self._redaction = redaction or RedactionEngine()
        self._cost = cost_calculator or CostCalculator()

        self._start_time = time.perf_counter()
        self._start_utc = datetime.now(timezone.utc)
        self._steps: list[AgentStep] = []
        self._messages: list[Message] = []
        self._input: AgentInput = AgentInput()
        self._output: AgentOutput = AgentOutput()
        self._environment: EnvironmentSnapshot = EnvironmentSnapshot()
        self._finished = False

    # -- Properties ---------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def step_count(self) -> int:
        return len(self._steps)

    @property
    def is_finished(self) -> bool:
        return self._finished

    # -- Step helpers -------------------------------------------------------

    def _next_step_number(self) -> int:
        return len(self._steps) + 1

    def _ensure_active(self) -> None:
        if self._finished:
            raise RuntimeError("Cannot modify a finished recording session.")

    # -- LLM calls ----------------------------------------------------------

    def add_llm_call(
        self,
        model: str,
        input_messages: list[dict[str, Any]] | list[Message],
        output_message: dict[str, Any] | Message | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        finish_reason: str | None = None,
        cache_hit: bool = False,
    ) -> AgentStep:
        """Record an LLM API call as a step."""
        self._ensure_active()

        # Normalise messages to Message objects
        normalised_inputs = [self._normalise_message(m) for m in input_messages]
        normalised_output = (
            self._normalise_message(output_message)
            if output_message is not None
            else None
        )

        # Redact
        for msg in normalised_inputs:
            msg.content = self._redact_content(msg.content)
        if normalised_output is not None:
            normalised_output.content = self._redact_content(normalised_output.content)

        cost_usd = self._cost.calculate(model, input_tokens, output_tokens)

        llm_record = LLMCallRecord(
            model=model,
            input_messages=normalised_inputs,
            output_message=normalised_output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            finish_reason=finish_reason,
        )

        step = AgentStep(
            step_number=self._next_step_number(),
            type=StepType.LLM_CALL,
            timestamp=datetime.now(timezone.utc),
            duration_ms=latency_ms,
            llm_call=llm_record,
        )
        self._steps.append(step)

        # Mirror messages in the flat messages list
        self._messages.extend(normalised_inputs)
        if normalised_output is not None:
            self._messages.append(normalised_output)

        return step

    # -- Tool calls ---------------------------------------------------------

    def add_tool_call(
        self,
        tool_name: str,
        tool_input: Any = None,
        tool_output: Any = None,
        duration_ms: float = 0.0,
        success: bool = True,
        error: str | None = None,
        side_effects: list[str] | None = None,
    ) -> AgentStep:
        """Record a tool invocation as a step."""
        self._ensure_active()

        redacted_input = self._redaction._walk(tool_input)
        redacted_output = self._redaction._walk(tool_output)

        tool_record = ToolCallRecord(
            tool_name=tool_name,
            tool_input=redacted_input,
            tool_output=redacted_output,
            duration_ms=duration_ms,
            success=success,
            error=error,
            side_effects=side_effects or [],
        )

        step = AgentStep(
            step_number=self._next_step_number(),
            type=StepType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
            tool_call=tool_record,
        )
        self._steps.append(step)

        # Also record as messages for conversation replay
        self._messages.append(
            Message(
                role="assistant",
                content=[
                    ContentBlock(
                        type=ContentBlockType.TOOL_USE,
                        tool_name=tool_name,
                        tool_input=redacted_input,
                    )
                ],
                timestamp=datetime.now(timezone.utc),
            )
        )
        self._messages.append(
            Message(
                role="tool",
                content=[
                    ContentBlock(
                        type=ContentBlockType.TOOL_RESULT,
                        tool_name=tool_name,
                        tool_result=redacted_output,
                        is_error=not success,
                    )
                ],
                timestamp=datetime.now(timezone.utc),
            )
        )

        return step

    # -- Decisions ----------------------------------------------------------

    def add_decision(
        self,
        decision_type: str | DecisionType,
        reason: str,
        alternatives: list[str] | None = None,
    ) -> AgentStep:
        """Record an agent routing / control-flow decision."""
        self._ensure_active()

        if isinstance(decision_type, str):
            decision_type = DecisionType(decision_type)

        decision_record = DecisionRecord(
            type=decision_type,
            reason=reason,
            alternatives_considered=alternatives or [],
        )

        step = AgentStep(
            step_number=self._next_step_number(),
            type=StepType.DECISION,
            timestamp=datetime.now(timezone.utc),
            decision=decision_record,
        )
        self._steps.append(step)
        return step

    # -- Input / Output / Environment ---------------------------------------

    def set_input(
        self,
        content: Any,
        input_type: str | InputType = "text",
        context: dict[str, Any] | None = None,
    ) -> None:
        """Set the agent input for this recording."""
        self._ensure_active()
        if isinstance(input_type, str):
            input_type = InputType(input_type)
        redacted_content = self._redaction._walk(content)
        self._input = AgentInput(
            type=input_type,
            content=redacted_content,
            context=context,
        )

    def set_output(
        self,
        content: Any,
        output_type: str | OutputType = "text",
        status: str | OutputStatus = "success",
        error: str | None = None,
    ) -> None:
        """Set the agent output for this recording."""
        self._ensure_active()
        if isinstance(output_type, str):
            output_type = OutputType(output_type)
        if isinstance(status, str):
            status = OutputStatus(status)
        redacted_content = self._redaction._walk(content)
        self._output = AgentOutput(
            type=output_type,
            content=redacted_content,
            status=status,
            error=error,
        )

    def set_environment(
        self,
        model: str,
        model_params: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | list[ToolDefinition] | None = None,
    ) -> None:
        """Set the environment snapshot for this recording."""
        self._ensure_active()

        tool_defs: list[ToolDefinition] = []
        if tools:
            for t in tools:
                if isinstance(t, ToolDefinition):
                    tool_defs.append(t)
                elif isinstance(t, dict):
                    tool_defs.append(ToolDefinition(**t))

        redacted_prompt = (
            self._redaction.redact(system_prompt)
            if system_prompt is not None
            else None
        )
        self._environment = EnvironmentSnapshot(
            model=model,
            model_params=model_params or {},
            system_prompt=redacted_prompt,
            tools_available=tool_defs,
        )

    # -- Finalisation -------------------------------------------------------

    def finish(self) -> AgentRecording:
        """Finalise the session and return a complete AgentRecording."""
        if self._finished:
            raise RuntimeError("Session is already finished.")

        self._finished = True
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000

        total_tokens = sum(
            (s.llm_call.input_tokens + s.llm_call.output_tokens)
            for s in self._steps
            if s.llm_call is not None
        )
        total_cost = sum(
            s.llm_call.cost_usd for s in self._steps if s.llm_call is not None
        )

        metadata = RecordingMetadata(
            name=self._name,
            timestamp=self._start_utc,
            duration_ms=elapsed_ms,
            agent_framework=self._framework,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            tags=self._tags,
        )

        return AgentRecording(
            metadata=metadata,
            input=self._input,
            output=self._output,
            steps=self._steps,
            messages=self._messages,
            environment=self._environment,
        )

    def save(self, directory: str | Path | None = None) -> Path:
        """Finish (if needed) and save the recording to a .aprobe file.

        Returns the path to the saved file.
        """
        recording = self.finish() if not self._finished else self._build_recording()
        if directory is None:
            directory = Path.cwd() / ".agentprobe" / "recordings"
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        safe_name = self._name.replace(" ", "_").replace("/", "_")
        ts = self._start_utc.strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{ts}.aprobe"
        filepath = directory / filename

        recording.save(filepath)
        return filepath

    # -- Internal helpers ---------------------------------------------------

    def _build_recording(self) -> AgentRecording:
        """Build a recording from current state without finalising."""
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000
        total_tokens = sum(
            (s.llm_call.input_tokens + s.llm_call.output_tokens)
            for s in self._steps
            if s.llm_call is not None
        )
        total_cost = sum(
            s.llm_call.cost_usd for s in self._steps if s.llm_call is not None
        )
        metadata = RecordingMetadata(
            name=self._name,
            timestamp=self._start_utc,
            duration_ms=elapsed_ms,
            agent_framework=self._framework,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            tags=self._tags,
        )
        return AgentRecording(
            metadata=metadata,
            input=self._input,
            output=self._output,
            steps=self._steps,
            messages=self._messages,
            environment=self._environment,
        )

    def _normalise_message(self, msg: dict[str, Any] | Message) -> Message:
        """Convert a dict or Message to a Message model instance."""
        if isinstance(msg, Message):
            return msg.model_copy()
        if isinstance(msg, dict):
            return Message(**msg)
        raise TypeError(f"Expected dict or Message, got {type(msg).__name__}")

    def _redact_content(self, content: str | list[ContentBlock] | Any) -> Any:
        """Redact content regardless of whether it is text or blocks."""
        if isinstance(content, str):
            return self._redaction.redact(content)
        if isinstance(content, list):
            redacted: list[ContentBlock] = []
            for block in content:
                if isinstance(block, ContentBlock):
                    copy = block.model_copy()
                    if copy.text is not None:
                        copy.text = self._redaction.redact(copy.text)
                    if copy.tool_input is not None:
                        copy.tool_input = self._redaction._walk(copy.tool_input)
                    if copy.tool_result is not None:
                        copy.tool_result = self._redaction._walk(copy.tool_result)
                    redacted.append(copy)
                else:
                    redacted.append(block)
            return redacted
        return self._redaction._walk(content)


class Recorder:
    """Main recorder that manages recording sessions.

    Usage::

        recorder = Recorder()
        session = recorder.start_session("my-test")
        # ... interact with agent ...
        recording = session.finish()

    Or as a context manager::

        with recorder.record("my-test") as session:
            # ... interact with agent ...
        # session is auto-finished on exit
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._config = config or {}
        self._redaction = RedactionEngine(
            enabled=self._config.get("redaction_enabled", True),
            custom_patterns=self._config.get("redaction_patterns") or [],
        )
        self._cost = CostCalculator(
            custom_pricing=self._config.get("custom_pricing") or {},
        )
        self._sessions: list[RecordingSession] = []

    def start_session(
        self,
        name: str,
        tags: list[str] | None = None,
        framework: str = "custom",
    ) -> RecordingSession:
        """Create and return a new recording session."""
        session = RecordingSession(
            name=name,
            tags=tags,
            framework=framework,
            redaction=self._redaction,
            cost_calculator=self._cost,
        )
        self._sessions.append(session)
        return session

    @contextmanager
    def record(
        self,
        name: str,
        tags: list[str] | None = None,
        framework: str = "custom",
    ) -> Generator[RecordingSession, None, None]:
        """Context manager that yields an active recording session.

        The session is automatically finished on exit.
        """
        session = self.start_session(name, tags=tags, framework=framework)
        try:
            yield session
        finally:
            if not session.is_finished:
                session.finish()


# ---------------------------------------------------------------------------
# Module-level convenience decorator
# ---------------------------------------------------------------------------

def record(name: str, tags: list[str] | None = None, framework: str = "custom"):
    """Decorator that records a complete agent function execution.

    Usage::

        @record("customer-support-agent")
        def run_agent(prompt: str, session: RecordingSession) -> str:
            session.set_input(prompt)
            # ... agent logic ...
            session.set_output(result)
            return result

    The decorated function receives an additional ``session`` keyword
    argument of type :class:`RecordingSession`. The recording is
    automatically finished when the function returns.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            recorder = Recorder()
            session = recorder.start_session(name, tags=tags, framework=framework)
            kwargs["session"] = session
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception:
                if not session.is_finished:
                    session.set_output("", status="error", error="Exception during execution")
                raise
            finally:
                if not session.is_finished:
                    session.finish()

        # Attach the last recording for inspection after the call
        wrapper._last_session = None  # type: ignore[attr-defined]
        return wrapper

    return decorator
