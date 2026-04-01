"""Configurable tool mocking for AgentProbe replay and testing."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agentprobe.core.models import AgentRecording, StepType


class MockTool:
    """Mock a tool with configurable responses.

    Each rule in *responses* is a dict with two keys:
      - ``match``: one of
          - ``"default"``  — matches everything (catch-all)
          - ``dict``       — matches when the dict is a subset of the input
          - ``callable``   — matches when the callable returns truthy
      - ``response``: the value to return (or a callable that receives the
        input and returns the value).
    """

    def __init__(
        self,
        name: str,
        responses: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self._responses: list[dict[str, Any]] = responses or []
        self._call_count: int = 0
        self._call_history: list[dict[str, Any]] = []
        self._sequence_index: int = 0

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_recording(
        cls,
        recording: str | AgentRecording,
        tool_name: str,
    ) -> MockTool:
        """Create a mock that replays the exact tool responses found in a
        recording, matched by input equality.  If the same input appears
        multiple times only the first match is used."""
        if isinstance(recording, (str, Path)):
            recording = AgentRecording.load(recording)

        responses: list[dict[str, Any]] = []
        for step in recording.steps:
            if (
                step.type == StepType.TOOL_CALL
                and step.tool_call is not None
                and step.tool_call.tool_name == tool_name
            ):
                tc = step.tool_call
                responses.append(
                    {
                        "match": copy.deepcopy(tc.tool_input) if isinstance(tc.tool_input, dict) else "default",
                        "response": copy.deepcopy(tc.tool_output),
                    }
                )

        # Always add a fallback so replays don't crash on unexpected inputs.
        if not any(r["match"] == "default" for r in responses):
            responses.append(
                {"match": "default", "response": {"error": f"No recorded response for tool '{tool_name}'"}}
            )

        return cls(name=tool_name, responses=responses)

    @classmethod
    def sequence(cls, name: str, responses: list[Any]) -> MockTool:
        """Return responses in insertion order; cycle back to the last entry
        once the list is exhausted."""
        rules = [{"match": "__sequence__", "response": r} for r in responses]
        return cls(name=name, responses=rules)

    @classmethod
    def function(cls, name: str, handler: Callable[..., Any]) -> MockTool:
        """Use *handler(input_data)* to generate every response."""
        return cls(
            name=name,
            responses=[{"match": "default", "response": handler}],
        )

    @classmethod
    def static(cls, name: str, response: Any) -> MockTool:
        """Always return the same response."""
        return cls(
            name=name,
            responses=[{"match": "default", "response": response}],
        )

    @classmethod
    def error(cls, name: str, error_message: str = "Tool error") -> MockTool:
        """Always return an error response."""
        return cls(
            name=name,
            responses=[
                {"match": "default", "response": {"error": error_message, "success": False}}
            ],
        )

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def get_response(self, input_data: Any) -> Any:
        """Match *input_data* against the rules and return the appropriate
        response."""
        self._call_count += 1
        response: Any = None

        # Handle sequence mode
        if self._responses and self._responses[0].get("match") == "__sequence__":
            idx = min(self._sequence_index, len(self._responses) - 1)
            response = copy.deepcopy(self._responses[idx]["response"])
            self._sequence_index += 1
        else:
            response = self._match(input_data)

        self._call_history.append(
            {
                "input": copy.deepcopy(input_data),
                "output": copy.deepcopy(response),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return response

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list[dict[str, Any]]:
        return list(self._call_history)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match(self, input_data: Any) -> Any:
        default: Any = None

        for rule in self._responses:
            matcher = rule["match"]
            resp = rule["response"]

            if matcher == "default":
                default = resp
                continue

            if callable(matcher):
                if matcher(input_data):
                    return self._resolve(resp, input_data)
                continue

            if isinstance(matcher, dict) and isinstance(input_data, dict):
                if self._dict_matches(matcher, input_data):
                    return self._resolve(resp, input_data)
                continue

        if default is not None:
            return self._resolve(default, input_data)

        return {"error": f"No matching response for tool '{self.name}'"}

    @staticmethod
    def _dict_matches(pattern: dict[str, Any], data: dict[str, Any]) -> bool:
        """Return True when every key/value in *pattern* is also in *data*."""
        for key, value in pattern.items():
            if key not in data:
                return False
            if data[key] != value:
                return False
        return True

    @staticmethod
    def _resolve(response: Any, input_data: Any) -> Any:
        """If *response* is callable, invoke it with *input_data*."""
        if callable(response):
            return response(input_data)
        return copy.deepcopy(response)


class MockToolkit:
    """Collection of :class:`MockTool` instances keyed by tool name."""

    def __init__(self, mocks: list[MockTool]) -> None:
        self._mocks: dict[str, MockTool] = {m.name: m for m in mocks}

    def get_mock(self, tool_name: str) -> MockTool | None:
        return self._mocks.get(tool_name)

    def has_mock(self, tool_name: str) -> bool:
        return tool_name in self._mocks

    def add(self, mock: MockTool) -> None:
        self._mocks[mock.name] = mock

    def remove(self, tool_name: str) -> None:
        self._mocks.pop(tool_name, None)

    @property
    def tool_names(self) -> list[str]:
        return list(self._mocks.keys())

    def __len__(self) -> int:
        return len(self._mocks)

    def __iter__(self):  # noqa: ANN204
        return iter(self._mocks.values())
