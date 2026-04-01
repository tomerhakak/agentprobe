"""OpenAI adapter — intercepts openai chat completion calls."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from agentprobe.adapters.base import BaseAdapter
from agentprobe.core.models import Message
from agentprobe.core.recorder import RecordingSession

try:
    import openai as _openai_module
    import openai.resources.chat.completions as _completions_mod

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


def _check_openai() -> None:
    if not _OPENAI_AVAILABLE:
        raise ImportError(
            "The 'openai' package is required for the OpenAI adapter. "
            "Install it with: pip install openai"
        )


# ---------------------------------------------------------------------------
# Helpers for normalising OpenAI objects into our models
# ---------------------------------------------------------------------------


def _openai_messages_to_messages(raw: list[dict[str, Any]]) -> list[Message]:
    """Convert OpenAI-style message dicts to agentprobe Messages."""
    messages: list[Message] = []
    for m in raw:
        role = m.get("role", "user")
        content = m.get("content", "")
        if content is None:
            content = ""
        messages.append(Message(role=role, content=content))
    return messages


def _choice_to_message(choice: Any) -> Message:
    """Extract a Message from an OpenAI Choice object."""
    msg = choice.message
    role = getattr(msg, "role", "assistant")
    content = getattr(msg, "content", None) or ""

    # If the response contains tool_calls, serialise them into the content
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        parts: list[str] = []
        if content:
            parts.append(content)
        for tc in tool_calls:
            fn = tc.function
            parts.append(
                f"[tool_call:{tc.id}] {fn.name}({fn.arguments})"
            )
        content = "\n".join(parts)

    # Legacy function_call support
    function_call = getattr(msg, "function_call", None)
    if function_call and not tool_calls:
        fn_name = getattr(function_call, "name", "")
        fn_args = getattr(function_call, "arguments", "{}")
        content = f"[function_call] {fn_name}({fn_args})"

    return Message(role=role, content=content)


def _extract_tool_calls_from_response(response: Any) -> list[dict[str, Any]]:
    """Pull structured tool calls out of an OpenAI response for recording."""
    results: list[dict[str, Any]] = []
    for choice in getattr(response, "choices", []):
        msg = choice.message
        for tc in getattr(msg, "tool_calls", None) or []:
            fn = tc.function
            try:
                args = json.loads(fn.arguments)
            except (json.JSONDecodeError, TypeError):
                args = fn.arguments
            results.append(
                {
                    "id": tc.id,
                    "name": fn.name,
                    "input": args,
                }
            )
        # Legacy function_call
        fc = getattr(msg, "function_call", None)
        if fc and not getattr(msg, "tool_calls", None):
            try:
                args = json.loads(fc.arguments)
            except (json.JSONDecodeError, TypeError):
                args = fc.arguments
            results.append({"id": None, "name": fc.name, "input": args})
    return results


def _extract_usage(response: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from an OpenAI response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0)


# ---------------------------------------------------------------------------
# Streaming accumulator
# ---------------------------------------------------------------------------


class _StreamAccumulator:
    """Collects streamed chunks and synthesises a pseudo-response."""

    def __init__(self) -> None:
        self.role: str = "assistant"
        self.content_parts: list[str] = []
        self.tool_calls: dict[int, dict[str, Any]] = {}  # index -> partial
        self.finish_reason: str | None = None
        self.model: str = ""
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    def feed(self, chunk: Any) -> None:
        self.model = getattr(chunk, "model", self.model) or self.model

        # Usage may appear on the final chunk (when stream_options.include_usage=True)
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            self.prompt_tokens = getattr(usage, "prompt_tokens", 0)
            self.completion_tokens = getattr(usage, "completion_tokens", 0)

        for choice in getattr(chunk, "choices", []):
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            if getattr(delta, "role", None):
                self.role = delta.role
            if getattr(delta, "content", None):
                self.content_parts.append(delta.content)

            # Streamed tool calls
            for tc_delta in getattr(delta, "tool_calls", None) or []:
                idx = tc_delta.index
                if idx not in self.tool_calls:
                    self.tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                if getattr(tc_delta, "id", None):
                    self.tool_calls[idx]["id"] = tc_delta.id
                fn = getattr(tc_delta, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        self.tool_calls[idx]["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        self.tool_calls[idx]["arguments"] += fn.arguments

            if getattr(choice, "finish_reason", None):
                self.finish_reason = choice.finish_reason

    def to_message(self) -> Message:
        content = "".join(self.content_parts)
        if self.tool_calls:
            parts: list[str] = []
            if content:
                parts.append(content)
            for _idx, tc in sorted(self.tool_calls.items()):
                parts.append(f"[tool_call:{tc['id']}] {tc['name']}({tc['arguments']})")
            content = "\n".join(parts)
        return Message(role=self.role, content=content)

    def get_tool_call_records(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for _idx, tc in sorted(self.tool_calls.items()):
            try:
                args = json.loads(tc["arguments"])
            except (json.JSONDecodeError, TypeError):
                args = tc["arguments"]
            results.append({"id": tc["id"], "name": tc["name"], "input": args})
        return results


# ---------------------------------------------------------------------------
# OpenAI Adapter
# ---------------------------------------------------------------------------


class OpenAIAdapter(BaseAdapter):
    """Instruments the ``openai`` library to capture chat completions.

    Patches both sync and async ``create`` methods on
    ``openai.resources.chat.completions.Completions`` (and its async variant).
    """

    def __init__(self, session: RecordingSession) -> None:
        _check_openai()
        super().__init__(session)
        self._original_sync_create: Any = None
        self._original_async_create: Any = None

    # -- instrument / uninstrument -----------------------------------------

    def instrument(self) -> None:
        if self._instrumented:
            return

        # Sync
        self._original_sync_create = _completions_mod.Completions.create
        _completions_mod.Completions.create = self._make_sync_wrapper(
            self._original_sync_create
        )

        # Async
        self._original_async_create = _completions_mod.AsyncCompletions.create
        _completions_mod.AsyncCompletions.create = self._make_async_wrapper(
            self._original_async_create
        )

        self._instrumented = True

    def uninstrument(self) -> None:
        if not self._instrumented:
            return

        if self._original_sync_create is not None:
            _completions_mod.Completions.create = self._original_sync_create
        if self._original_async_create is not None:
            _completions_mod.AsyncCompletions.create = self._original_async_create

        self._instrumented = False

    # -- wrapper factories --------------------------------------------------

    def _make_sync_wrapper(self, original_create: Any) -> Any:
        session = self._session

        def wrapper(inner_self: Any, *args: Any, **kwargs: Any) -> Any:
            messages_raw: list[dict[str, Any]] = kwargs.get("messages") or (
                args[0] if args else []
            )
            model: str = kwargs.get("model", "unknown")
            stream: bool = kwargs.get("stream", False)

            start = time.perf_counter()
            response = original_create(inner_self, *args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if stream:
                return _SyncStreamProxy(response, session, messages_raw, model, start)

            # Non-streaming: record immediately
            _record_response(session, response, messages_raw, model, elapsed_ms)
            return response

        return wrapper

    def _make_async_wrapper(self, original_create: Any) -> Any:
        session = self._session

        async def wrapper(inner_self: Any, *args: Any, **kwargs: Any) -> Any:
            messages_raw: list[dict[str, Any]] = kwargs.get("messages") or (
                args[0] if args else []
            )
            model: str = kwargs.get("model", "unknown")
            stream: bool = kwargs.get("stream", False)

            start = time.perf_counter()
            response = await original_create(inner_self, *args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if stream:
                return _AsyncStreamProxy(response, session, messages_raw, model, start)

            _record_response(session, response, messages_raw, model, elapsed_ms)
            return response

        return wrapper


# ---------------------------------------------------------------------------
# Recording helper (non-streaming)
# ---------------------------------------------------------------------------


def _record_response(
    session: RecordingSession,
    response: Any,
    messages_raw: list[dict[str, Any]],
    model: str,
    elapsed_ms: float,
) -> None:
    """Record a non-streaming OpenAI response into the session."""
    input_tokens, output_tokens = _extract_usage(response)
    finish_reason = None
    output_msg: Message | None = None

    if getattr(response, "choices", None):
        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        output_msg = _choice_to_message(choice)

    detected_model = getattr(response, "model", model) or model
    session.add_llm_call(
        model=detected_model,
        input_messages=_openai_messages_to_messages(messages_raw),
        output_message=output_msg,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=elapsed_ms,
        finish_reason=finish_reason,
    )

    # Record any tool calls as separate steps
    for tc in _extract_tool_calls_from_response(response):
        session.add_tool_call(
            tool_name=tc["name"],
            tool_input=tc["input"],
            tool_output=None,  # output comes from user / next message
            duration_ms=0.0,
        )


# ---------------------------------------------------------------------------
# Stream proxies — pass through chunks while accumulating for recording
# ---------------------------------------------------------------------------


class _SyncStreamProxy:
    """Wraps a sync OpenAI stream, recording once the stream is exhausted."""

    def __init__(
        self,
        stream: Any,
        session: RecordingSession,
        messages_raw: list[dict[str, Any]],
        model: str,
        start_time: float,
    ) -> None:
        self._stream = stream
        self._session = session
        self._messages_raw = messages_raw
        self._model = model
        self._start_time = start_time
        self._accumulator = _StreamAccumulator()
        self._recorded = False

    def __iter__(self) -> _SyncStreamProxy:
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._stream)
            self._accumulator.feed(chunk)
            return chunk
        except StopIteration:
            self._finalise()
            raise

    def __enter__(self) -> _SyncStreamProxy:
        if hasattr(self._stream, "__enter__"):
            self._stream.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        self._finalise()
        if hasattr(self._stream, "__exit__"):
            self._stream.__exit__(*args)

    def _finalise(self) -> None:
        if self._recorded:
            return
        self._recorded = True
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000
        acc = self._accumulator
        model = acc.model or self._model

        self._session.add_llm_call(
            model=model,
            input_messages=_openai_messages_to_messages(self._messages_raw),
            output_message=acc.to_message(),
            input_tokens=acc.prompt_tokens,
            output_tokens=acc.completion_tokens,
            latency_ms=elapsed_ms,
            finish_reason=acc.finish_reason,
        )

        for tc in acc.get_tool_call_records():
            self._session.add_tool_call(
                tool_name=tc["name"],
                tool_input=tc["input"],
                tool_output=None,
                duration_ms=0.0,
            )


class _AsyncStreamProxy:
    """Wraps an async OpenAI stream, recording once the stream is exhausted."""

    def __init__(
        self,
        stream: Any,
        session: RecordingSession,
        messages_raw: list[dict[str, Any]],
        model: str,
        start_time: float,
    ) -> None:
        self._stream = stream
        self._session = session
        self._messages_raw = messages_raw
        self._model = model
        self._start_time = start_time
        self._accumulator = _StreamAccumulator()
        self._recorded = False

    def __aiter__(self) -> _AsyncStreamProxy:
        return self

    async def __anext__(self) -> Any:
        try:
            chunk = await self._stream.__anext__()
            self._accumulator.feed(chunk)
            return chunk
        except StopAsyncIteration:
            self._finalise()
            raise

    async def __aenter__(self) -> _AsyncStreamProxy:
        if hasattr(self._stream, "__aenter__"):
            await self._stream.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        self._finalise()
        if hasattr(self._stream, "__aexit__"):
            await self._stream.__aexit__(*args)

    def _finalise(self) -> None:
        if self._recorded:
            return
        self._recorded = True
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000
        acc = self._accumulator
        model = acc.model or self._model

        self._session.add_llm_call(
            model=model,
            input_messages=_openai_messages_to_messages(self._messages_raw),
            output_message=acc.to_message(),
            input_tokens=acc.prompt_tokens,
            output_tokens=acc.completion_tokens,
            latency_ms=elapsed_ms,
            finish_reason=acc.finish_reason,
        )

        for tc in acc.get_tool_call_records():
            self._session.add_tool_call(
                tool_name=tc["name"],
                tool_input=tc["input"],
                tool_output=None,
                duration_ms=0.0,
            )
