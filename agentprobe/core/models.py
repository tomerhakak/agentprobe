"""Core data models for AgentProbe recordings and agent execution traces."""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ContentBlockType(str, Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class StepType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DECISION = "decision"
    HANDOFF = "handoff"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"


class DecisionType(str, Enum):
    ROUTE = "route"
    RETRY = "retry"
    DELEGATE = "delegate"
    STOP = "stop"


class InputType(str, Enum):
    TEXT = "text"
    STRUCTURED = "structured"
    MULTIMODAL = "multimodal"


class OutputStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class OutputType(str, Enum):
    TEXT = "text"
    STRUCTURED = "structured"
    MULTIMODAL = "multimodal"


# ---------------------------------------------------------------------------
# Content & Messages
# ---------------------------------------------------------------------------

class ContentBlock(BaseModel):
    """A single block of content — text, tool use request, or tool result."""

    type: ContentBlockType
    text: Optional[str] = None
    tool_use_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Any] = None
    tool_result: Optional[Any] = None
    is_error: Optional[bool] = None


class Message(BaseModel):
    """A single message in the agent conversation."""

    role: str
    content: Union[str, List[ContentBlock]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class ToolDefinition(BaseModel):
    """Schema definition for a tool available to the agent."""

    name: str
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    """Record of a single tool invocation."""

    tool_name: str
    tool_input: Any = None
    tool_output: Any = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    side_effects: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM Calls
# ---------------------------------------------------------------------------

class LLMCallRecord(BaseModel):
    """Record of a single LLM API call."""

    model: str
    input_messages: List[Message] = Field(default_factory=list)
    output_message: Optional[Message] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    finish_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

class DecisionRecord(BaseModel):
    """Record of an agent routing / control-flow decision."""

    type: DecisionType
    reason: str = ""
    alternatives_considered: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

class AgentStep(BaseModel):
    """A single step in the agent execution trace."""

    step_number: int
    type: StepType
    timestamp: Optional[datetime] = None
    duration_ms: float = 0.0
    llm_call: Optional[LLMCallRecord] = None
    tool_call: Optional[ToolCallRecord] = None
    decision: Optional[DecisionRecord] = None


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class EnvironmentSnapshot(BaseModel):
    """Snapshot of the environment at recording time."""

    model: str = ""
    model_params: Dict[str, Any] = Field(default_factory=dict)
    system_prompt: Optional[str] = None
    tools_available: List[ToolDefinition] = Field(default_factory=list)
    env_vars_hash: Optional[str] = None


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------

class AgentInput(BaseModel):
    """The input that was given to the agent."""

    type: InputType = InputType.TEXT
    content: Any = ""
    context: Optional[Dict[str, Any]] = None


class AgentOutput(BaseModel):
    """The output produced by the agent."""

    type: OutputType = OutputType.TEXT
    content: Any = ""
    status: OutputStatus = OutputStatus.SUCCESS
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Recording Metadata
# ---------------------------------------------------------------------------

class RecordingMetadata(BaseModel):
    """Metadata about a recording session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    agent_framework: str = ""
    agent_version: str = ""
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    tags: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AgentRecording — top-level container
# ---------------------------------------------------------------------------

class AgentRecording(BaseModel):
    """Complete recording of an agent execution, including all steps, messages,
    environment info, and metadata.  Serialises to / from gzipped JSON (.aprobe).
    """

    metadata: RecordingMetadata = Field(default_factory=RecordingMetadata)
    input: AgentInput = Field(default_factory=AgentInput)
    output: AgentOutput = Field(default_factory=AgentOutput)
    steps: List[AgentStep] = Field(default_factory=list)
    messages: List[Message] = Field(default_factory=list)
    environment: EnvironmentSnapshot = Field(default_factory=EnvironmentSnapshot)

    # -- Persistence --------------------------------------------------------

    def save(self, path: Union[str, Path]) -> None:
        """Save the recording as gzipped JSON (.aprobe)."""
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix(".aprobe")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, default=str)

    @classmethod
    def load(cls, path: Union[str, Path]) -> AgentRecording:
        """Load a recording from a gzipped JSON .aprobe file."""
        path = Path(path)
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    def to_dict(self) -> Dict[str, Any]:
        """Return the recording as a plain dictionary."""
        return self.model_dump(mode="json")

    # -- Computed properties ------------------------------------------------

    @property
    def total_cost(self) -> float:
        """Sum of all LLM call costs in USD."""
        return sum(
            step.llm_call.cost_usd
            for step in self.steps
            if step.llm_call is not None
        )

    @property
    def total_tokens(self) -> int:
        """Sum of all input + output tokens across LLM calls."""
        return sum(
            step.llm_call.input_tokens + step.llm_call.output_tokens
            for step in self.steps
            if step.llm_call is not None
        )

    @property
    def total_duration(self) -> float:
        """Sum of all step durations in milliseconds."""
        return sum(step.duration_ms for step in self.steps)

    @property
    def llm_steps(self) -> List[AgentStep]:
        """All steps whose type is 'llm_call'."""
        return [s for s in self.steps if s.type == StepType.LLM_CALL]

    @property
    def tool_steps(self) -> List[AgentStep]:
        """All steps whose type is 'tool_call'."""
        return [s for s in self.steps if s.type == StepType.TOOL_CALL]

    @property
    def step_count(self) -> int:
        """Total number of steps."""
        return len(self.steps)
