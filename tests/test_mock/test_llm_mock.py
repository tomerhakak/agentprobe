"""Tests for agentprobe.mock.llm_mock."""

from __future__ import annotations

import pytest

from agentprobe.core.models import Message
from agentprobe.mock.llm_mock import MockLLM


def _make_messages(*texts: str) -> list[Message]:
    """Create a list of alternating user/assistant messages from text strings."""
    messages = []
    for i, text in enumerate(texts):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append(Message(role=role, content=text))
    return messages


class TestStaticLLMMock:
    def test_static_llm_mock(self) -> None:
        mock = MockLLM.static("I am a static response.")
        msgs = _make_messages("Hello")
        response = mock.get_response(msgs)

        assert response.role == "assistant"
        assert response.content == "I am a static response."

    def test_static_llm_mock_always_same(self) -> None:
        mock = MockLLM.static("Same every time.")
        for _ in range(5):
            resp = mock.get_response(_make_messages("Different input each time"))
            assert resp.content == "Same every time."
        assert mock.call_count == 5

    def test_static_llm_mock_call_history(self) -> None:
        mock = MockLLM.static("response")
        mock.get_response(_make_messages("q1"))
        mock.get_response(_make_messages("q2"))

        assert len(mock.call_history) == 2
        assert mock.call_history[0]["output"]["content"] == "response"


class TestScriptedLLMMock:
    def test_scripted_llm_mock(self) -> None:
        mock = MockLLM.scripted(["First response", "Second response", "Third response"])
        msgs = _make_messages("Q1")

        r1 = mock.get_response(msgs)
        assert r1.content == "First response"

        r2 = mock.get_response(msgs)
        assert r2.content == "Second response"

        r3 = mock.get_response(msgs)
        assert r3.content == "Third response"

    def test_scripted_llm_mock_exhausted_stays_on_last(self) -> None:
        mock = MockLLM.scripted(["Only one"])
        msgs = _make_messages("Q")

        r1 = mock.get_response(msgs)
        assert r1.content == "Only one"

        # After exhaustion, stays on last
        r2 = mock.get_response(msgs)
        assert r2.content == "Only one"

    def test_scripted_llm_mock_empty(self) -> None:
        mock = MockLLM.scripted([])
        msgs = _make_messages("Q")
        resp = mock.get_response(msgs)
        # Should handle gracefully — returns a fallback message
        assert resp.role == "assistant"
        assert isinstance(resp.content, str)


class TestEchoLLMMock:
    def test_echo_llm_mock(self) -> None:
        mock = MockLLM.echo()
        msgs = _make_messages("Echo this back")
        resp = mock.get_response(msgs)

        assert resp.role == "assistant"
        assert resp.content == "Echo this back"

    def test_echo_llm_mock_multiple_messages(self) -> None:
        mock = MockLLM.echo()
        msgs = [
            Message(role="user", content="First message"),
            Message(role="assistant", content="Response"),
            Message(role="user", content="Last user message"),
        ]
        resp = mock.get_response(msgs)
        assert resp.content == "Last user message"

    def test_echo_llm_mock_no_user_message(self) -> None:
        mock = MockLLM.echo()
        msgs = [Message(role="assistant", content="Only assistant")]
        resp = mock.get_response(msgs)
        # No user message to echo, should return empty
        assert resp.role == "assistant"
        assert resp.content == ""
