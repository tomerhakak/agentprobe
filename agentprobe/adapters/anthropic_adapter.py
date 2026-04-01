"""Anthropic adapter — intercepts anthropic messages.create calls."""

from __future__ import annotations

import json
import time
from typing import Any

from agentprobe.adapters.base import BaseAdapter
from agentprobe.core.models import ContentBlock, ContentBlockType, Message
from agentprobe.core.recorder import RecordingSession

try:
    import anthropic as _anthropic_module
    import anthropic.resources.messages as _messages_mod

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


def _check_anthropic() -> None:
    if not _ANTHROPIC_AVAILABLE:
        raise ImportError(
            "The 'anthropic' package is required for the Anthropic adapter. "
            "Install it with: pip install anthropic"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _anthropic_messages_to_messages(
    raw: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
) -> list[Message]:
    """Convert Anthropic-style message dicts to agentprobe Messages."""
    messages: list[Message] = []

    # System prompt as a leading message
    if system:
        if isinstance(system, str):
            messages.append(Message(role="system", content=system))
        elif isinstance(system, list):
            text_parts = [
                b.get("text", "") for b in system if b.get("type") == "text"
            ]
            messages.append(Message(role="system", content="\n".join(text_parts)))

    for m in raw:
        role = m.get("role", "user")
        content = m.get("content", "")

        if isinstance(content, str):
            messages.append(Message(role=role, content=content))
        elif isinstance(content, list):
            blocks: list[ContentBlock] = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "text")
                    if btype == "text":
                        blocks.append(
                            ContentBlock(type=ContentBlockType.TEXT, text=block.get("text", ""))
                        )
                    elif btype == "tool_use":
                        blocks.append(
                            ContentBlock(
                                type=ContentBlockType.TOOL_USE,
                                tool_use_id=block.get("id"),
                                tool_name=block.get("name"),
                                tool_input=block.get("input"),
                            )
                        )
                    elif btype == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            text_parts = [
                                b.get("text", "")
                                for b in result_content
                                if isinstance(b, dict) and b.get("type") == "text"
                            ]
                            result_content = "\n".join(text_parts)
                        blocks.append(
                            ContentBlock(
                                type=ContentBlockType.TOOL_RESULT,
                                tool_use_id=block.get("tool_use_id"),
                                tool_result=result_content,
                                is_error=block.get("is_error", False),
                            )
                        )
                    else:
                        # Image or other block — just note it
                        blocks.append(
                            ContentBlock(type=ContentBlockType.TEXT, text=f"[{btype} block]")
                        )
            messages.append(Message(role=role, content=blocks))
        else:
            messages.append(Message(role=role, content=str(content)))

    return messages


def _response_to_message(response: Any) -> Message:
    """Convert an Anthropic Message response to an agentprobe Message."""
    role = getattr(response, "role", "assistant")
    content_blocks = getattr(response, "content", [])

    blocks: list[ContentBlock] = []
    for block in content_blocks:
        btype = getattr(block, "type", "text")
        if btype == "text":
            blocks.append(
                ContentBlock(type=ContentBlockType.TEXT, text=getattr(block, "text", ""))
            )
        elif btype == "tool_use":
            blocks.append(
                ContentBlock(
                    type=ContentBlockType.TOOL_USE,
                    tool_use_id=getattr(block, "id", None),
                    tool_name=getattr(block, "name", None),
                    tool_input=getattr(block, "input", None),
                )
            )

    # If only a single text block, flatten to string
    if len(blocks) == 1 and blocks[0].type == ContentBlockType.TEXT:
        return Message(role=role, content=blocks[0].text or "")

    return Message(role=role, content=blocks)


def _extract_tool_uses(response: Any) -> list[dict[str, Any]]:
    """Pull tool_use blocks from an Anthropic response."""
    results: list[dict[str, Any]] = []
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use":
            results.append(
                {
                    "id": getattr(block, "id", None),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                }
            )
    return results


def _extract_usage(response: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from an Anthropic response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)


# ---------------------------------------------------------------------------
# Streaming accumulator
# ---------------------------------------------------------------------------


class _StreamAccumulator:
    """Accumulates Anthropic streaming events into a coherent response."""

    def __init__(self) -> None:
        self.role: str = "assistant"
        self.model: str = ""
        self.text_parts: list[str] = []
        self.tool_uses: list[dict[str, Any]] = []
        self._current_tool: dict[str, Any] | None = None
        self._current_tool_json: str = ""
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.stop_reason: str | None = None

    def feed(self, event: Any) -> None:
        event_type = getattr(event, "type", "")

        if event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg:
                self.role = getattr(msg, "role", "assistant")
                self.model = getattr(msg, "model", "")
                usage = getattr(msg, "usage", None)
                if usage:
                    self.input_tokens = getattr(usage, "input_tokens", 0)

        elif event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block and getattr(block, "type", None) == "tool_use":
                self._current_tool = {
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                }
                self._current_tool_json = ""

        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta:
                dtype = getattr(delta, "type", "")
                if dtype == "text_delta":
                    self.text_parts.append(getattr(delta, "text", ""))
                elif dtype == "input_json_delta":
                    self._current_tool_json += getattr(delta, "partial_json", "")

        elif event_type == "content_block_stop":
            if self._current_tool is not None:
                try:
                    parsed_input = json.loads(self._current_tool_json) if self._current_tool_json else {}
                except (json.JSONDecodeError, TypeError):
                    parsed_input = self._current_tool_json
                self._current_tool["input"] = parsed_input
                self.tool_uses.append(self._current_tool)
                self._current_tool = None
                self._current_tool_json = ""

        elif event_type == "message_delta":
            delta = getattr(event, "delta", None)
            if delta:
                self.stop_reason = getattr(delta, "stop_reason", self.stop_reason)
            usage = getattr(event, "usage", None)
            if usage:
                self.output_tokens = getattr(usage, "output_tokens", 0)

    def to_message(self) -> Message:
        text = "".join(self.text_parts)
        blocks: list[ContentBlock] = []

        if text:
            blocks.append(ContentBlock(type=ContentBlockType.TEXT, text=text))

        for tu in self.tool_uses:
            blocks.append(
                ContentBlock(
                    type=ContentBlockType.TOOL_USE,
                    tool_use_id=tu.get("id"),
                    tool_name=tu.get("name"),
                    tool_input=tu.get("input"),
                )
            )

        if len(blocks) == 1 and blocks[0].type == ContentBlockType.TEXT:
            return Message(role=self.role, content=blocks[0].text or "")

        return Message(role=self.role, content=blocks if blocks else "")


# ---------------------------------------------------------------------------
# Anthropic Adapter
# ---------------------------------------------------------------------------


class AnthropicAdapter(BaseAdapter):
    """Instruments the ``anthropic`` library to capture messages.create calls.

    Patches both sync and async ``create`` methods on
    ``anthropic.resources.messages.Messages`` (and ``AsyncMessages``).
    """

    def __init__(self, session: RecordingSession) -> None:
        _check_anthropic()
        super().__init__(session)
        self._original_sync_create: Any = None
        self._original_async_create: Any = None

    def instrument(self) -> None:
        if self._instrumented:
            return

        # Sync
        self._original_sync_create = _messages_mod.Messages.create
        _messages_mod.Messages.create = self._make_sync_wrapper(
            self._original_sync_create
        )

        # Async
        self._original_async_create = _messages_mod.AsyncMessages.create
        _messages_mod.AsyncMessages.create = self._make_async_wrapper(
            self._original_async_create
        )

        self._instrumented = True

    def uninstrument(self) -> None:
        if not self._instrumented:
            return

        if self._original_sync_create is not None:
            _messages_mod.Messages.create = self._original_sync_create
        if self._original_async_create is not None:
            _messages_mod.AsyncMessages.create = self._original_async_create

        self._instrumented = False

    # -- wrapper factories --------------------------------------------------

    def _make_sync_wrapper(self, original_create: Any) -> Any:
        session = self._session

        def wrapper(inner_self: Any, *args: Any, **kwargs: Any) -> Any:
            messages_raw: list[dict[str, Any]] = kwargs.get("messages") or (
                args[0] if args else []
            )
            model: str = kwargs.get("model", "unknown")
            system = kwargs.get("system")
            stream: bool = kwargs.get("stream", False)

            start = time.perf_counter()
            response = original_create(inner_self, *args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if stream:
                return _SyncStreamProxy(
                    response, session, messages_raw, model, system, start
                )

            _record_response(session, response, messages_raw, model, system, elapsed_ms)
            return response

        return wrapper

    def _make_async_wrapper(self, original_create: Any) -> Any:
        session = self._session

        async def wrapper(inner_self: Any, *args: Any, **kwargs: Any) -> Any:
            messages_raw: list[dict[str, Any]] = kwargs.get("messages") or (
                args[0] if args else []
            )
            model: str = kwargs.get("model", "unknown")
            system = kwargs.get("system")
            stream: bool = kwargs.get("stream", False)

            start = time.perf_counter()
            response = await original_create(inner_self, *args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if stream:
                return _AsyncStreamProxy(
                    response, session, messages_raw, model, system, start
                )

            _record_response(session, response, messages_raw, model, system, elapsed_ms)
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
    system: Any,
    elapsed_ms: float,
) -> None:
    """Record a non-streaming Anthropic response into the session."""
    input_tokens, output_tokens = _extract_usage(response)
    detected_model = getattr(response, "model", model) or model
    stop_reason = getattr(response, "stop_reason", None)

    session.add_llm_call(
        model=detected_model,
        input_messages=_anthropic_messages_to_messages(messages_raw, system=system),
        output_message=_response_to_message(response),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=elapsed_ms,
        finish_reason=stop_reason,
    )

    # Record tool_use blocks as separate tool call steps
    for tu in _extract_tool_uses(response):
        session.add_tool_call(
            tool_name=tu["name"],
            tool_input=tu["input"],
            tool_output=None,  # result comes from the user's next message
            duration_ms=0.0,
        )


# ---------------------------------------------------------------------------
# Stream proxies
# ---------------------------------------------------------------------------


class _SyncStreamProxy:
    """Wraps a sync Anthropic stream, recording once exhausted."""

    def __init__(
        self,
        stream: Any,
        session: RecordingSession,
        messages_raw: list[dict[str, Any]],
        model: str,
        system: Any,
        start_time: float,
    ) -> None:
        self._stream = stream
        self._session = session
        self._messages_raw = messages_raw
        self._model = model
        self._system = system
        self._start_time = start_time
        self._accumulator = _StreamAccumulator()
        self._recorded = False

    def __iter__(self) -> _SyncStreamProxy:
        return self

    def __next__(self) -> Any:
        try:
            event = next(self._stream)
            self._accumulator.feed(event)
            return event
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
            input_messages=_anthropic_messages_to_messages(
                self._messages_raw, system=self._system
            ),
            output_message=acc.to_message(),
            input_tokens=acc.input_tokens,
            output_tokens=acc.output_tokens,
            latency_ms=elapsed_ms,
            finish_reason=acc.stop_reason,
        )

        for tu in acc.tool_uses:
            self._session.add_tool_call(
                tool_name=tu.get("name", ""),
                tool_input=tu.get("input"),
                tool_output=None,
                duration_ms=0.0,
            )


class _AsyncStreamProxy:
    """Wraps an async Anthropic stream, recording once exhausted."""

    def __init__(
        self,
        stream: Any,
        session: RecordingSession,
        messages_raw: list[dict[str, Any]],
        model: str,
        system: Any,
        start_time: float,
    ) -> None:
        self._stream = stream
        self._session = session
        self._messages_raw = messages_raw
        self._model = model
        self._system = system
        self._start_time = start_time
        self._accumulator = _StreamAccumulator()
        self._recorded = False

    def __aiter__(self) -> _AsyncStreamProxy:
        return self

    async def __anext__(self) -> Any:
        try:
            event = await self._stream.__anext__()
            self._accumulator.feed(event)
            return event
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
            input_messages=_anthropic_messages_to_messages(
                self._messages_raw, system=self._system
            ),
            output_message=acc.to_message(),
            input_tokens=acc.input_tokens,
            output_tokens=acc.output_tokens,
            latency_ms=elapsed_ms,
            finish_reason=acc.stop_reason,
        )

        for tu in acc.tool_uses:
            self._session.add_tool_call(
                tool_name=tu.get("name", ""),
                tool_input=tu.get("input"),
                tool_output=None,
                duration_ms=0.0,
            )
