"""Base class for all framework adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentprobe.core.recorder import RecordingSession


class BaseAdapter(ABC):
    """Base class for framework adapters.

    An adapter instruments (monkey-patches) a third-party library so that
    all LLM and tool calls are transparently recorded into the bound
    :class:`RecordingSession`.

    Subclasses must implement :meth:`instrument` and :meth:`uninstrument`.
    """

    def __init__(self, session: RecordingSession) -> None:
        self._session = session
        self._instrumented = False

    @property
    def session(self) -> RecordingSession:
        """The recording session this adapter writes into."""
        return self._session

    @property
    def is_instrumented(self) -> bool:
        """Whether the adapter has patched the target library."""
        return self._instrumented

    @abstractmethod
    def instrument(self) -> None:
        """Patch the target framework to capture calls."""
        ...

    @abstractmethod
    def uninstrument(self) -> None:
        """Restore the original framework methods."""
        ...

    def __enter__(self) -> BaseAdapter:
        self.instrument()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        self.uninstrument()
