"""Shared fixtures for AgentProbe tests."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentprobe.core.models import (
    AgentInput,
    AgentOutput,
    AgentRecording,
    AgentStep,
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
from agentprobe.core.config import AgentProbeConfig


@pytest.fixture
def sample_messages() -> list[Message]:
    """List of sample Message objects."""
    return [
        Message(
            role="user",
            content="What is the weather in Paris?",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            tokens=10,
        ),
        Message(
            role="assistant",
            content="Let me check the weather for you.",
            timestamp=datetime(2024, 1, 1, 12, 0, 1, tzinfo=timezone.utc),
            tokens=8,
        ),
        Message(
            role="assistant",
            content="The weather in Paris is 15C and sunny.",
            timestamp=datetime(2024, 1, 1, 12, 0, 3, tzinfo=timezone.utc),
            tokens=12,
        ),
    ]


@pytest.fixture
def sample_recording(sample_messages: list[Message]) -> AgentRecording:
    """A complete AgentRecording with 3 steps: LLM call, tool call, LLM call."""
    steps = [
        AgentStep(
            step_number=1,
            type=StepType.LLM_CALL,
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=150.0,
            llm_call=LLMCallRecord(
                model="gpt-4",
                input_messages=[sample_messages[0]],
                output_message=sample_messages[1],
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.005,
                latency_ms=150.0,
                finish_reason="stop",
            ),
        ),
        AgentStep(
            step_number=2,
            type=StepType.TOOL_CALL,
            timestamp=datetime(2024, 1, 1, 12, 0, 1, tzinfo=timezone.utc),
            duration_ms=200.0,
            tool_call=ToolCallRecord(
                tool_name="get_weather",
                tool_input={"city": "Paris"},
                tool_output={"temperature": 15, "condition": "sunny"},
                duration_ms=200.0,
                success=True,
            ),
        ),
        AgentStep(
            step_number=3,
            type=StepType.LLM_CALL,
            timestamp=datetime(2024, 1, 1, 12, 0, 2, tzinfo=timezone.utc),
            duration_ms=100.0,
            llm_call=LLMCallRecord(
                model="gpt-4",
                input_messages=[sample_messages[0], sample_messages[1]],
                output_message=sample_messages[2],
                input_tokens=80,
                output_tokens=40,
                cost_usd=0.003,
                latency_ms=100.0,
                finish_reason="stop",
            ),
        ),
    ]

    metadata = RecordingMetadata(
        id="test-recording-001",
        name="weather-agent-test",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=450.0,
        agent_framework="custom",
        agent_version="1.0.0",
        total_cost_usd=0.008,
        total_tokens=270,
        tags=["test", "weather"],
    )

    return AgentRecording(
        metadata=metadata,
        input=AgentInput(
            type=InputType.TEXT,
            content="What is the weather in Paris?",
        ),
        output=AgentOutput(
            type=OutputType.TEXT,
            content="The weather in Paris is 15C and sunny.",
            status=OutputStatus.SUCCESS,
        ),
        steps=steps,
        messages=sample_messages,
        environment=EnvironmentSnapshot(
            model="gpt-4",
            model_params={"temperature": 0.7},
            system_prompt="You are a helpful weather assistant.",
            tools_available=[
                ToolDefinition(
                    name="get_weather",
                    description="Get weather for a city",
                    parameters={"city": {"type": "string"}},
                )
            ],
        ),
    )


@pytest.fixture
def sample_config() -> AgentProbeConfig:
    """Default AgentProbeConfig."""
    return AgentProbeConfig.default()


@pytest.fixture
def tmp_recording_dir(tmp_path: Path) -> Path:
    """Temporary directory for recording files."""
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir()
    return rec_dir
