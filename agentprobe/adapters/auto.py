"""Auto-detection and instrumentation of available LLM frameworks."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from agentprobe.core.recorder import RecordingSession

logger = logging.getLogger("agentprobe.adapters.auto")

# Registry of (module_name, adapter_class_path) pairs.
# adapter_class_path is "module:ClassName" within agentprobe.adapters.
_ADAPTER_REGISTRY: list[tuple[str, str]] = [
    ("openai", "agentprobe.adapters.openai_adapter:OpenAIAdapter"),
    ("anthropic", "agentprobe.adapters.anthropic_adapter:AnthropicAdapter"),
]


def _resolve_adapter_class(class_path: str) -> type | None:
    """Import and return an adapter class from a 'module:ClassName' path."""
    module_path, class_name = class_path.rsplit(":", 1)
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except (ImportError, AttributeError) as exc:
        logger.debug("Could not load adapter %s: %s", class_path, exc)
        return None


def auto_instrument(
    session: RecordingSession | None = None,
) -> list[Any]:
    """Auto-detect and instrument all available LLM frameworks.

    Tries to patch every known framework whose library is installed.
    Frameworks that are not installed are silently skipped.

    Parameters
    ----------
    session:
        The recording session to capture calls into. If ``None``, a new
        default session is created automatically.

    Returns
    -------
    list
        A list of active adapter instances (already instrumented). Call
        ``.uninstrument()`` on each — or use :func:`auto_uninstrument`
        — to restore original behaviour.
    """
    if session is None:
        from agentprobe.core.recorder import Recorder

        recorder = Recorder()
        session = recorder.start_session("auto", framework="auto")

    active_adapters: list[Any] = []

    for lib_name, adapter_path in _ADAPTER_REGISTRY:
        # Check if the target library is importable
        try:
            importlib.import_module(lib_name)
        except ImportError:
            logger.debug("Skipping %s adapter — library not installed.", lib_name)
            continue

        adapter_cls = _resolve_adapter_class(adapter_path)
        if adapter_cls is None:
            continue

        try:
            adapter = adapter_cls(session)
            adapter.instrument()
            active_adapters.append(adapter)
            logger.info("Instrumented %s", lib_name)
        except Exception as exc:
            logger.warning("Failed to instrument %s: %s", lib_name, exc)

    return active_adapters


def auto_uninstrument(adapters: list[Any]) -> None:
    """Uninstrument all adapters returned by :func:`auto_instrument`.

    Parameters
    ----------
    adapters:
        The list of adapter instances to restore.
    """
    for adapter in adapters:
        try:
            adapter.uninstrument()
        except Exception as exc:
            logger.warning("Failed to uninstrument %s: %s", type(adapter).__name__, exc)
