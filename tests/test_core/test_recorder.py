"""Tests for agentprobe.core.recorder."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentprobe.core.models import AgentRecording, Message, StepType
from agentprobe.core.recorder import Recorder, RecordingSession, record


class TestRecordingSessionBasic:
    def test_recording_session_basic(self) -> None:
        recorder = Recorder()
        session = recorder.start_session("test-session", tags=["unit"])
        assert session.name == "test-session"
        assert session.step_count == 0
        assert not session.is_finished

        recording = session.finish()
        assert session.is_finished
        assert isinstance(recording, AgentRecording)
        assert recording.metadata.name == "test-session"
        assert recording.metadata.tags == ["unit"]

    def test_cannot_modify_finished_session(self) -> None:
        recorder = Recorder()
        session = recorder.start_session("done")
        session.finish()
        with pytest.raises(RuntimeError, match="finished"):
            session.add_tool_call("some_tool")

    def test_cannot_finish_twice(self) -> None:
        recorder = Recorder()
        session = recorder.start_session("done")
        session.finish()
        with pytest.raises(RuntimeError, match="already finished"):
            session.finish()


class TestRecordingSessionWithLLMCall:
    def test_recording_session_with_llm_call(self) -> None:
        recorder = Recorder()
        session = recorder.start_session("llm-test")

        step = session.add_llm_call(
            model="gpt-4",
            input_messages=[{"role": "user", "content": "Hello"}],
            output_message={"role": "assistant", "content": "Hi there"},
            input_tokens=10,
            output_tokens=5,
            latency_ms=100.0,
            finish_reason="stop",
        )

        assert step.type == StepType.LLM_CALL
        assert step.llm_call is not None
        assert step.llm_call.model == "gpt-4"
        assert step.llm_call.input_tokens == 10
        assert step.llm_call.output_tokens == 5
        assert session.step_count == 1

        recording = session.finish()
        assert recording.step_count == 1
        assert len(recording.llm_steps) == 1


class TestRecordingSessionWithToolCall:
    def test_recording_session_with_tool_call(self) -> None:
        recorder = Recorder()
        session = recorder.start_session("tool-test")

        step = session.add_tool_call(
            tool_name="search",
            tool_input={"query": "pytest"},
            tool_output={"results": ["result1"]},
            duration_ms=50.0,
            success=True,
        )

        assert step.type == StepType.TOOL_CALL
        assert step.tool_call is not None
        assert step.tool_call.tool_name == "search"
        assert step.tool_call.success is True
        assert session.step_count == 1

        recording = session.finish()
        assert len(recording.tool_steps) == 1
        # Tool calls also generate messages (tool_use + tool_result)
        assert len(recording.messages) >= 2


class TestRecordingSessionSaveAndLoad:
    def test_recording_session_save_and_load(self, tmp_recording_dir: Path) -> None:
        recorder = Recorder()
        session = recorder.start_session("save-test", tags=["save"])

        session.set_input("What is 2+2?")
        session.add_llm_call(
            model="gpt-4",
            input_messages=[{"role": "user", "content": "What is 2+2?"}],
            output_message={"role": "assistant", "content": "4"},
            input_tokens=10,
            output_tokens=1,
        )
        session.set_output("4")

        filepath = session.save(directory=tmp_recording_dir)
        assert filepath.exists()
        assert filepath.suffix == ".aprobe"

        loaded = AgentRecording.load(filepath)
        assert loaded.metadata.name == "save-test"
        assert loaded.step_count == 1
        assert loaded.output.content == "4"


class TestRecordDecorator:
    def test_record_decorator(self) -> None:
        @record("decorator-test", tags=["deco"])
        def my_agent(prompt: str, session: RecordingSession) -> str:
            session.set_input(prompt)
            session.add_llm_call(
                model="gpt-4",
                input_messages=[{"role": "user", "content": prompt}],
                output_message={"role": "assistant", "content": "decorated reply"},
                input_tokens=5,
                output_tokens=3,
            )
            session.set_output("decorated reply")
            return "decorated reply"

        result = my_agent("test prompt")
        assert result == "decorated reply"


class TestRecordContextManager:
    def test_record_context_manager(self) -> None:
        recorder = Recorder()

        with recorder.record("ctx-test", tags=["ctx"]) as session:
            session.set_input("hello")
            session.add_tool_call(
                tool_name="echo",
                tool_input={"text": "hello"},
                tool_output="hello",
            )
            session.set_output("hello")

        # Session is auto-finished after the with block
        assert session.is_finished

    def test_context_manager_auto_finishes_on_exception(self) -> None:
        recorder = Recorder()

        with pytest.raises(ValueError):
            with recorder.record("err-test") as session:
                session.add_tool_call(tool_name="x", tool_input={})
                raise ValueError("boom")

        assert session.is_finished
