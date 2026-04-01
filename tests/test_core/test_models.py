"""Tests for agentprobe.core.models."""

from __future__ import annotations

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
)


class TestCreateAgentRecording:
    """Test creating AgentRecording instances."""

    def test_create_agent_recording(self, sample_recording: AgentRecording) -> None:
        assert sample_recording.metadata.name == "weather-agent-test"
        assert sample_recording.metadata.id == "test-recording-001"
        assert len(sample_recording.steps) == 3
        assert len(sample_recording.messages) == 3

    def test_create_empty_recording(self) -> None:
        rec = AgentRecording()
        assert rec.metadata.name == ""
        assert rec.steps == []
        assert rec.messages == []
        assert rec.output.status == OutputStatus.SUCCESS

    def test_create_recording_with_metadata(self) -> None:
        meta = RecordingMetadata(
            name="my-agent",
            agent_framework="langchain",
            tags=["prod", "v2"],
        )
        rec = AgentRecording(metadata=meta)
        assert rec.metadata.name == "my-agent"
        assert rec.metadata.agent_framework == "langchain"
        assert rec.metadata.tags == ["prod", "v2"]
        assert rec.metadata.id  # UUID auto-generated


class TestRecordingSaveAndLoad:
    """Test saving to .aprobe and loading back."""

    def test_recording_save_and_load(
        self, sample_recording: AgentRecording, tmp_recording_dir: Path
    ) -> None:
        filepath = tmp_recording_dir / "test_rec.aprobe"
        sample_recording.save(filepath)
        assert filepath.exists()

        loaded = AgentRecording.load(filepath)
        assert loaded.metadata.id == sample_recording.metadata.id
        assert loaded.metadata.name == sample_recording.metadata.name
        assert loaded.step_count == sample_recording.step_count
        assert loaded.output.content == sample_recording.output.content
        assert loaded.input.content == sample_recording.input.content
        assert len(loaded.steps) == len(sample_recording.steps)

    def test_save_adds_suffix(
        self, sample_recording: AgentRecording, tmp_recording_dir: Path
    ) -> None:
        filepath = tmp_recording_dir / "no_suffix"
        sample_recording.save(filepath)
        expected = tmp_recording_dir / "no_suffix.aprobe"
        assert expected.exists()

    def test_save_creates_parent_dirs(
        self, sample_recording: AgentRecording, tmp_path: Path
    ) -> None:
        filepath = tmp_path / "deep" / "nested" / "dir" / "rec.aprobe"
        sample_recording.save(filepath)
        assert filepath.exists()


class TestRecordingProperties:
    """Test computed properties on AgentRecording."""

    def test_total_cost(self, sample_recording: AgentRecording) -> None:
        # 0.005 + 0.003 = 0.008
        assert sample_recording.total_cost == pytest.approx(0.008)

    def test_total_tokens(self, sample_recording: AgentRecording) -> None:
        # (100 + 50) + (80 + 40) = 270
        assert sample_recording.total_tokens == 270

    def test_step_count(self, sample_recording: AgentRecording) -> None:
        assert sample_recording.step_count == 3

    def test_llm_steps(self, sample_recording: AgentRecording) -> None:
        llm = sample_recording.llm_steps
        assert len(llm) == 2
        assert all(s.type == StepType.LLM_CALL for s in llm)

    def test_tool_steps(self, sample_recording: AgentRecording) -> None:
        tools = sample_recording.tool_steps
        assert len(tools) == 1
        assert tools[0].type == StepType.TOOL_CALL
        assert tools[0].tool_call is not None
        assert tools[0].tool_call.tool_name == "get_weather"

    def test_total_duration(self, sample_recording: AgentRecording) -> None:
        # 150 + 200 + 100 = 450
        assert sample_recording.total_duration == pytest.approx(450.0)

    def test_empty_recording_properties(self) -> None:
        rec = AgentRecording()
        assert rec.total_cost == 0.0
        assert rec.total_tokens == 0
        assert rec.step_count == 0
        assert rec.llm_steps == []
        assert rec.tool_steps == []
        assert rec.total_duration == 0.0


class TestRecordingToDict:
    """Test to_dict serialization."""

    def test_recording_to_dict(self, sample_recording: AgentRecording) -> None:
        d = sample_recording.to_dict()
        assert isinstance(d, dict)
        assert "metadata" in d
        assert "steps" in d
        assert "messages" in d
        assert "input" in d
        assert "output" in d
        assert "environment" in d
        assert d["metadata"]["name"] == "weather-agent-test"
        assert len(d["steps"]) == 3

    def test_to_dict_is_json_serializable(
        self, sample_recording: AgentRecording
    ) -> None:
        import json

        d = sample_recording.to_dict()
        # Should not raise
        serialized = json.dumps(d, default=str)
        assert isinstance(serialized, str)


class TestMessageCreation:
    """Test Message model creation."""

    def test_message_creation(self) -> None:
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.name is None
        assert msg.tool_call_id is None

    def test_message_with_all_fields(self) -> None:
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        msg = Message(
            role="assistant",
            content="Hi there",
            name="agent",
            tool_call_id="tc_123",
            timestamp=ts,
            tokens=5,
        )
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
        assert msg.name == "agent"
        assert msg.tool_call_id == "tc_123"
        assert msg.timestamp == ts
        assert msg.tokens == 5


class TestStepTypes:
    """Test different step types."""

    def test_step_types(self) -> None:
        assert StepType.LLM_CALL.value == "llm_call"
        assert StepType.TOOL_CALL.value == "tool_call"
        assert StepType.TOOL_RESULT.value == "tool_result"
        assert StepType.DECISION.value == "decision"
        assert StepType.HANDOFF.value == "handoff"
        assert StepType.MEMORY_READ.value == "memory_read"
        assert StepType.MEMORY_WRITE.value == "memory_write"

    def test_llm_step_creation(self) -> None:
        step = AgentStep(
            step_number=1,
            type=StepType.LLM_CALL,
            duration_ms=100.0,
            llm_call=LLMCallRecord(model="gpt-4"),
        )
        assert step.type == StepType.LLM_CALL
        assert step.llm_call is not None
        assert step.tool_call is None

    def test_tool_step_creation(self) -> None:
        step = AgentStep(
            step_number=1,
            type=StepType.TOOL_CALL,
            duration_ms=50.0,
            tool_call=ToolCallRecord(
                tool_name="search", tool_input={"q": "test"}
            ),
        )
        assert step.type == StepType.TOOL_CALL
        assert step.tool_call is not None
        assert step.tool_call.tool_name == "search"
        assert step.llm_call is None
