"""Tests for agentprobe.mock.tool_mock."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentprobe.core.models import AgentRecording
from agentprobe.mock.tool_mock import MockTool, MockToolkit


class TestStaticMock:
    def test_static_mock(self) -> None:
        mock = MockTool.static("weather", {"temp": 20, "unit": "C"})
        result = mock.get_response({"city": "Paris"})
        assert result == {"temp": 20, "unit": "C"}

        # Same response every time
        result2 = mock.get_response({"city": "London"})
        assert result2 == {"temp": 20, "unit": "C"}

    def test_static_mock_string_response(self) -> None:
        mock = MockTool.static("echo", "hello")
        assert mock.get_response("anything") == "hello"


class TestSequenceMock:
    def test_sequence_mock(self) -> None:
        mock = MockTool.sequence("counter", ["first", "second", "third"])
        assert mock.get_response({}) == "first"
        assert mock.get_response({}) == "second"
        assert mock.get_response({}) == "third"

    def test_sequence_mock_cycles_last(self) -> None:
        mock = MockTool.sequence("counter", ["a", "b"])
        mock.get_response({})  # a
        mock.get_response({})  # b
        result = mock.get_response({})  # stays on b
        assert result == "b"


class TestFunctionMock:
    def test_function_mock(self) -> None:
        def handler(input_data):
            return {"echo": input_data}

        mock = MockTool.function("echo", handler)
        result = mock.get_response({"msg": "hi"})
        assert result == {"echo": {"msg": "hi"}}

    def test_function_mock_with_computation(self) -> None:
        def adder(input_data):
            return {"sum": input_data.get("a", 0) + input_data.get("b", 0)}

        mock = MockTool.function("add", adder)
        result = mock.get_response({"a": 3, "b": 7})
        assert result == {"sum": 10}


class TestErrorMock:
    def test_error_mock(self) -> None:
        mock = MockTool.error("failing_tool", "Something broke")
        result = mock.get_response({})
        assert result["error"] == "Something broke"
        assert result["success"] is False

    def test_error_mock_default_message(self) -> None:
        mock = MockTool.error("failing_tool")
        result = mock.get_response({})
        assert result["error"] == "Tool error"


class TestMockFromRecording:
    def test_mock_from_recording(
        self, sample_recording: AgentRecording, tmp_recording_dir: Path
    ) -> None:
        filepath = tmp_recording_dir / "for_mock.aprobe"
        sample_recording.save(filepath)

        mock = MockTool.from_recording(sample_recording, "get_weather")
        # The recorded input was {"city": "Paris"} -> {"temperature": 15, "condition": "sunny"}
        result = mock.get_response({"city": "Paris"})
        assert result == {"temperature": 15, "condition": "sunny"}

    def test_mock_from_recording_unknown_input(
        self, sample_recording: AgentRecording
    ) -> None:
        mock = MockTool.from_recording(sample_recording, "get_weather")
        # Unknown input falls back to the default response
        result = mock.get_response({"city": "Unknown"})
        assert "error" in result

    def test_mock_from_recording_missing_tool(
        self, sample_recording: AgentRecording
    ) -> None:
        mock = MockTool.from_recording(sample_recording, "nonexistent_tool")
        result = mock.get_response({})
        assert "error" in result


class TestMockCallCountAndHistory:
    def test_mock_call_count_and_history(self) -> None:
        mock = MockTool.static("test_tool", "ok")
        assert mock.call_count == 0
        assert mock.call_history == []

        mock.get_response("input1")
        mock.get_response("input2")
        mock.get_response("input3")

        assert mock.call_count == 3
        assert len(mock.call_history) == 3
        assert mock.call_history[0]["input"] == "input1"
        assert mock.call_history[0]["output"] == "ok"
        assert mock.call_history[1]["input"] == "input2"
        assert "timestamp" in mock.call_history[0]


class TestMockToolkit:
    def test_mock_toolkit(self) -> None:
        weather = MockTool.static("weather", {"temp": 20})
        search = MockTool.static("search", {"results": []})

        toolkit = MockToolkit([weather, search])
        assert len(toolkit) == 2
        assert toolkit.has_mock("weather")
        assert toolkit.has_mock("search")
        assert not toolkit.has_mock("email")
        assert set(toolkit.tool_names) == {"weather", "search"}

        mock = toolkit.get_mock("weather")
        assert mock is not None
        assert mock.get_response({}) == {"temp": 20}

    def test_mock_toolkit_add_remove(self) -> None:
        toolkit = MockToolkit([])
        assert len(toolkit) == 0

        toolkit.add(MockTool.static("new_tool", "hello"))
        assert len(toolkit) == 1
        assert toolkit.has_mock("new_tool")

        toolkit.remove("new_tool")
        assert len(toolkit) == 0
        assert not toolkit.has_mock("new_tool")

    def test_mock_toolkit_iteration(self) -> None:
        t1 = MockTool.static("a", 1)
        t2 = MockTool.static("b", 2)
        toolkit = MockToolkit([t1, t2])
        names = {m.name for m in toolkit}
        assert names == {"a", "b"}
