"""Mock LLM responses for AgentProbe replay and testing."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agentprobe.core.models import AgentRecording, Message, StepType


class MockLLM:
    """Mock LLM responses for deterministic agent testing.

    Instances are created via the class-method factories rather than directly.
    """

    def __init__(self) -> None:
        self._mode: str = "scripted"
        self._responses: list[Message] = []
        self._response_index: int = 0
        self._static_response: Message | None = None
        self._local_model: str | None = None
        self._local_base_url: str | None = None
        self._call_count: int = 0
        self._call_history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_recording(cls, recording: str | AgentRecording) -> MockLLM:
        """Replay the exact LLM responses captured in a recording."""
        if isinstance(recording, (str, Path)):
            recording = AgentRecording.load(recording)

        instance = cls()
        instance._mode = "scripted"
        for step in recording.steps:
            if (
                step.type == StepType.LLM_CALL
                and step.llm_call is not None
                and step.llm_call.output_message is not None
            ):
                instance._responses.append(copy.deepcopy(step.llm_call.output_message))
        return instance

    @classmethod
    def scripted(cls, responses: list[str]) -> MockLLM:
        """Return the given string responses in order."""
        instance = cls()
        instance._mode = "scripted"
        instance._responses = [
            Message(role="assistant", content=text, timestamp=datetime.now(timezone.utc))
            for text in responses
        ]
        return instance

    @classmethod
    def echo(cls) -> MockLLM:
        """Return the last user message content as the assistant response."""
        instance = cls()
        instance._mode = "echo"
        return instance

    @classmethod
    def static(cls, response: str) -> MockLLM:
        """Always return the same response string."""
        instance = cls()
        instance._mode = "static"
        instance._static_response = Message(
            role="assistant",
            content=response,
            timestamp=datetime.now(timezone.utc),
        )
        return instance

    @classmethod
    def local(
        cls,
        model: str = "ollama:llama3.2",
        base_url: str = "http://localhost:11434",
    ) -> MockLLM:
        """Proxy calls to a local Ollama instance."""
        instance = cls()
        instance._mode = "local"
        instance._local_model = model.removeprefix("ollama:")
        instance._local_base_url = base_url.rstrip("/")
        return instance

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def get_response(self, messages: list[Message]) -> Message:
        """Return the next mock response based on the configured mode."""
        self._call_count += 1

        if self._mode == "scripted":
            response = self._get_scripted()
        elif self._mode == "echo":
            response = self._get_echo(messages)
        elif self._mode == "static":
            response = self._get_static()
        elif self._mode == "local":
            response = self._get_local(messages)
        else:
            response = Message(
                role="assistant",
                content="[MockLLM] Unknown mode",
                timestamp=datetime.now(timezone.utc),
            )

        self._call_history.append(
            {
                "input": [m.model_dump(mode="json") for m in messages],
                "output": response.model_dump(mode="json"),
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
    # Mode implementations
    # ------------------------------------------------------------------

    def _get_scripted(self) -> Message:
        if not self._responses:
            return Message(
                role="assistant",
                content="[MockLLM] No scripted responses available",
                timestamp=datetime.now(timezone.utc),
            )
        idx = min(self._response_index, len(self._responses) - 1)
        msg = copy.deepcopy(self._responses[idx])
        self._response_index += 1
        return msg

    def _get_echo(self, messages: list[Message]) -> Message:
        last_user = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user = m.content if isinstance(m.content, str) else str(m.content)
                break
        return Message(
            role="assistant",
            content=last_user,
            timestamp=datetime.now(timezone.utc),
        )

    def _get_static(self) -> Message:
        if self._static_response is None:
            return Message(
                role="assistant",
                content="[MockLLM] No static response configured",
                timestamp=datetime.now(timezone.utc),
            )
        return copy.deepcopy(self._static_response)

    def _get_local(self, messages: list[Message]) -> Message:
        """Send the conversation to a local Ollama chat endpoint."""
        if not self._local_base_url or not self._local_model:
            return Message(
                role="assistant",
                content="[MockLLM] Local model not configured",
                timestamp=datetime.now(timezone.utc),
            )

        ollama_messages = []
        for m in messages:
            content = m.content if isinstance(m.content, str) else str(m.content)
            ollama_messages.append({"role": m.role, "content": content})

        url = f"{self._local_base_url}/api/chat"
        payload = {
            "model": self._local_model,
            "messages": ollama_messages,
            "stream": False,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            return Message(
                role="assistant",
                content=content,
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return Message(
                role="assistant",
                content=f"[MockLLM] Local model error: {exc}",
                timestamp=datetime.now(timezone.utc),
            )
