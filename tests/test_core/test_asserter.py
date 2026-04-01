"""Tests for agentprobe.core.asserter."""

from __future__ import annotations

import json

import pytest

from agentprobe.core.asserter import Assertions, AssertionError as AProbeAssertionError
from agentprobe.core.models import (
    AgentOutput,
    AgentRecording,
    AgentStep,
    LLMCallRecord,
    OutputStatus,
    OutputType,
    StepType,
    ToolCallRecord,
)


@pytest.fixture
def assertions_obj(sample_recording: AgentRecording) -> Assertions:
    """Fresh Assertions instance with sample_recording pre-loaded."""
    a = Assertions()
    a.set_recording(sample_recording)
    return a


# ---------------------------------------------------------------------------
# Output assertions
# ---------------------------------------------------------------------------


class TestOutputContains:
    def test_output_contains(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.output_contains("Paris")
        assert result.passed

    def test_output_contains_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.output_contains("London")

    def test_output_contains_case_insensitive(
        self, assertions_obj: Assertions
    ) -> None:
        result = assertions_obj.output_contains("paris", case_sensitive=False)
        assert result.passed


class TestOutputNotContains:
    def test_output_not_contains(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.output_not_contains("London")
        assert result.passed

    def test_output_not_contains_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.output_not_contains("Paris")


class TestOutputMatchesRegex:
    def test_output_matches_regex(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.output_matches(r"\d+C")
        assert result.passed

    def test_output_matches_regex_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.output_matches(r"\d{5}-\d{4}")


class TestOutputSimilarTo:
    def test_output_similar_to(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.output_similar_to(
            "The weather in Paris is 15 degrees and sunny.", threshold=0.7
        )
        assert result.passed

    def test_output_similar_to_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.output_similar_to(
                "Completely unrelated text about quantum physics.",
                threshold=0.95,
            )


# ---------------------------------------------------------------------------
# Behavioral assertions
# ---------------------------------------------------------------------------


class TestCalledTool:
    def test_called_tool(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.called_tool("get_weather")
        assert result.passed

    def test_called_tool_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.called_tool("nonexistent_tool")

    def test_called_tool_with_count(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.called_tool("get_weather", times=1)
        assert result.passed

    def test_called_tool_with_wrong_count(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.called_tool("get_weather", times=5)


class TestNotCalledTool:
    def test_not_called_tool(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.not_called_tool("send_email")
        assert result.passed

    def test_not_called_tool_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.not_called_tool("get_weather")


class TestCalledToolsInOrder:
    def test_called_tools_in_order(self, assertions_obj: Assertions) -> None:
        # Only one tool call exists: get_weather
        result = assertions_obj.called_tools_in_order(["get_weather"])
        assert result.passed

    def test_called_tools_in_order_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.called_tools_in_order(["get_weather", "nonexistent"])


# ---------------------------------------------------------------------------
# Performance assertions
# ---------------------------------------------------------------------------


class TestStepsLessThan:
    def test_steps_less_than(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.steps_less_than(10)
        assert result.passed

    def test_steps_less_than_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.steps_less_than(2)


class TestTotalCostLessThan:
    def test_total_cost_less_than(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.total_cost_less_than(1.0)
        assert result.passed

    def test_total_cost_less_than_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.total_cost_less_than(0.001)


class TestTotalLatencyLessThan:
    def test_total_latency_less_than(self, assertions_obj: Assertions) -> None:
        # total_duration = 450ms
        result = assertions_obj.total_latency_less_than(1000)
        assert result.passed

    def test_total_latency_less_than_fails(self, assertions_obj: Assertions) -> None:
        with pytest.raises(AProbeAssertionError):
            assertions_obj.total_latency_less_than(100)


# ---------------------------------------------------------------------------
# Safety assertions
# ---------------------------------------------------------------------------


class TestNoPiiInOutput:
    def test_no_pii_in_output_passes(self, assertions_obj: Assertions) -> None:
        # Default recording has no PII
        result = assertions_obj.no_pii_in_output()
        assert result.passed

    def test_no_pii_detects_ssn(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            output=AgentOutput(
                type=OutputType.TEXT,
                content="My SSN is 123-45-6789",
                status=OutputStatus.SUCCESS,
            )
        )
        a.set_recording(rec)
        with pytest.raises(AProbeAssertionError):
            a.no_pii_in_output()

    def test_no_pii_detects_email(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            output=AgentOutput(
                type=OutputType.TEXT,
                content="Contact me at user@example.com",
                status=OutputStatus.SUCCESS,
            )
        )
        a.set_recording(rec)
        with pytest.raises(AProbeAssertionError):
            a.no_pii_in_output()

    def test_no_pii_detects_credit_card(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            output=AgentOutput(
                type=OutputType.TEXT,
                content="Card number: 4111 1111 1111 1111",
                status=OutputStatus.SUCCESS,
            )
        )
        a.set_recording(rec)
        with pytest.raises(AProbeAssertionError):
            a.no_pii_in_output()


# ---------------------------------------------------------------------------
# JSON assertions
# ---------------------------------------------------------------------------


class TestOutputJsonValid:
    def test_output_json_valid(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            output=AgentOutput(
                type=OutputType.TEXT,
                content='{"key": "value", "num": 42}',
                status=OutputStatus.SUCCESS,
            )
        )
        a.set_recording(rec)
        result = a.output_json_valid()
        assert result.passed

    def test_output_json_valid_fails(self, assertions_obj: Assertions) -> None:
        # The sample output is plain text, not JSON
        with pytest.raises(AProbeAssertionError):
            assertions_obj.output_json_valid()


# ---------------------------------------------------------------------------
# Status assertions
# ---------------------------------------------------------------------------


class TestCompletedSuccessfully:
    def test_completed_successfully(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.completed_successfully()
        assert result.passed

    def test_completed_successfully_fails(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            output=AgentOutput(
                type=OutputType.TEXT,
                content="Error occurred",
                status=OutputStatus.ERROR,
                error="Something went wrong",
            )
        )
        a.set_recording(rec)
        with pytest.raises(AProbeAssertionError):
            a.completed_successfully()


class TestNoErrors:
    def test_no_errors(self, assertions_obj: Assertions) -> None:
        result = assertions_obj.no_errors()
        assert result.passed

    def test_no_errors_fails(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            steps=[
                AgentStep(
                    step_number=1,
                    type=StepType.TOOL_CALL,
                    tool_call=ToolCallRecord(
                        tool_name="bad_tool",
                        tool_input={},
                        success=False,
                        error="Tool crashed",
                    ),
                )
            ]
        )
        a.set_recording(rec)
        with pytest.raises(AProbeAssertionError):
            a.no_errors()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestAllPassedSummary:
    def test_all_passed_summary(self, assertions_obj: Assertions) -> None:
        assertions_obj.output_contains("Paris")
        assertions_obj.called_tool("get_weather")
        assertions_obj.completed_successfully()

        assert assertions_obj.all_passed()
        summary = assertions_obj.summary()
        assert "3/3 passed" in summary
        assert "0 failed" in summary

    def test_summary_with_failures(self) -> None:
        a = Assertions()
        rec = AgentRecording(
            output=AgentOutput(
                type=OutputType.TEXT,
                content="Hello world",
                status=OutputStatus.SUCCESS,
            )
        )
        a.set_recording(rec)
        a.output_contains("Hello")  # passes

        with pytest.raises(AProbeAssertionError):
            a.output_contains("nonexistent")  # fails

        assert not a.all_passed()
        summary = a.summary()
        assert "1/2 passed" in summary
        assert "1 failed" in summary

    def test_empty_summary(self) -> None:
        a = Assertions()
        assert a.summary() == "No assertions recorded."
