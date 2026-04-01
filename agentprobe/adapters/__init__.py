"""Framework adapters for AgentProbe.

Adapters monkey-patch popular LLM libraries to automatically capture
calls into a :class:`~agentprobe.core.recorder.RecordingSession`.
"""

from __future__ import annotations

from agentprobe.adapters.base import BaseAdapter
from agentprobe.adapters.auto import auto_instrument

__all__ = [
    "BaseAdapter",
    "auto_instrument",
]
