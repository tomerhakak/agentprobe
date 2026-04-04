"""Live Agent Watch Mode.

Real-time file watcher that automatically re-runs tests and analyses
when recordings or test files change. Like nodemon for AI agents.

Monitors:
- .aprobe recording files (new/modified)
- Test files (test_*.py, *_test.py)
- Config files (agentprobe.yaml)

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class WatchEventType(str, Enum):
    RECORDING_ADDED = "recording_added"
    RECORDING_MODIFIED = "recording_modified"
    TEST_MODIFIED = "test_modified"
    CONFIG_MODIFIED = "config_modified"


@dataclass
class WatchEvent:
    """A file change event detected by the watcher."""

    type: WatchEventType
    path: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "path": self.path,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Watch Config
# ---------------------------------------------------------------------------

@dataclass
class WatchConfig:
    """Configuration for the file watcher."""

    recording_dirs: List[str] = field(default_factory=lambda: [".agentprobe/recordings"])
    test_dirs: List[str] = field(default_factory=lambda: ["tests"])
    config_files: List[str] = field(default_factory=lambda: ["agentprobe.yaml"])
    recording_extensions: List[str] = field(default_factory=lambda: [".aprobe"])
    test_patterns: List[str] = field(default_factory=lambda: ["test_*.py", "*_test.py"])
    poll_interval_s: float = 1.0
    debounce_s: float = 2.0
    auto_run_tests: bool = True
    auto_run_health: bool = False
    auto_run_roast: bool = False
    auto_run_xray: bool = False


# ---------------------------------------------------------------------------
# Agent Watcher
# ---------------------------------------------------------------------------

class AgentWatcher:
    """File watcher for AI agent development — auto-runs tests on changes.

    Usage::

        watcher = AgentWatcher()

        @watcher.on_event
        def handle(event):
            print(f"Changed: {event.path}")

        watcher.start()   # blocks until Ctrl+C
        # or
        watcher.start_async()  # non-blocking

    CLI usage::

        agentprobe watch                  # watch with defaults
        agentprobe watch --health --roast # also run health & roast
    """

    def __init__(self, config: Optional[WatchConfig] = None) -> None:
        self._config = config or WatchConfig()
        self._callbacks: List[Callable[[WatchEvent], None]] = []
        self._running = False
        self._file_hashes: Dict[str, str] = {}
        self._last_event_time: float = 0.0
        self._events_fired: int = 0

    def on_event(self, callback: Callable[[WatchEvent], None]) -> Callable:
        """Register an event callback. Can be used as a decorator."""
        self._callbacks.append(callback)
        return callback

    def start(self) -> None:
        """Start watching for file changes (blocking)."""
        self._running = True
        self._scan_initial()
        try:
            while self._running:
                events = self._poll()
                for event in events:
                    self._fire(event)
                time.sleep(self._config.poll_interval_s)
        except KeyboardInterrupt:
            self._running = False

    def stop(self) -> None:
        """Stop the watcher."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def events_fired(self) -> int:
        return self._events_fired

    # -- Internal ----------------------------------------------------------

    def _scan_initial(self) -> None:
        """Build initial hash map of watched files."""
        for path in self._get_watched_files():
            self._file_hashes[path] = self._hash_file(path)

    def _poll(self) -> List[WatchEvent]:
        """Check for file changes since last poll."""
        now = time.time()
        if now - self._last_event_time < self._config.debounce_s:
            return []

        events: List[WatchEvent] = []
        current_files = self._get_watched_files()

        for path in current_files:
            current_hash = self._hash_file(path)
            previous_hash = self._file_hashes.get(path)

            if previous_hash is None:
                # New file
                event_type = self._classify_path(path)
                if event_type:
                    events.append(WatchEvent(type=event_type, path=path))
            elif current_hash != previous_hash:
                # Modified file
                event_type = self._classify_path(path, modified=True)
                if event_type:
                    events.append(WatchEvent(type=event_type, path=path))

            self._file_hashes[path] = current_hash

        if events:
            self._last_event_time = now

        return events

    def _get_watched_files(self) -> List[str]:
        """Get list of all files being watched."""
        files: List[str] = []

        for dir_path in self._config.recording_dirs:
            p = Path(dir_path)
            if p.exists():
                for ext in self._config.recording_extensions:
                    files.extend(str(f) for f in p.rglob(f"*{ext}"))

        for dir_path in self._config.test_dirs:
            p = Path(dir_path)
            if p.exists():
                for pattern in self._config.test_patterns:
                    files.extend(str(f) for f in p.rglob(pattern))

        for cfg in self._config.config_files:
            if Path(cfg).exists():
                files.append(cfg)

        return files

    def _classify_path(self, path: str, modified: bool = False) -> Optional[WatchEventType]:
        """Classify a file path into an event type."""
        p = Path(path)
        if p.suffix in self._config.recording_extensions:
            return WatchEventType.RECORDING_MODIFIED if modified else WatchEventType.RECORDING_ADDED
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            return WatchEventType.TEST_MODIFIED
        if p.name in [Path(c).name for c in self._config.config_files]:
            return WatchEventType.CONFIG_MODIFIED
        return None

    def _hash_file(self, path: str) -> str:
        """Compute a quick hash of a file's content."""
        try:
            stat = os.stat(path)
            return f"{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            return ""

    def _fire(self, event: WatchEvent) -> None:
        """Fire event to all registered callbacks."""
        self._events_fired += 1
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                pass  # Don't let callback errors crash the watcher

    # -- Rendering ---------------------------------------------------------

    @staticmethod
    def render_banner(config: WatchConfig) -> str:
        """Render the watch mode startup banner."""
        lines: List[str] = []
        lines.append("\U0001f440 WATCH MODE")
        lines.append(f"   Recordings: {', '.join(config.recording_dirs)}")
        lines.append(f"   Tests: {', '.join(config.test_dirs)}")
        lines.append(f"   Poll interval: {config.poll_interval_s}s")
        lines.append("")
        actions = []
        if config.auto_run_tests:
            actions.append("tests")
        if config.auto_run_health:
            actions.append("health")
        if config.auto_run_roast:
            actions.append("roast")
        if config.auto_run_xray:
            actions.append("xray")
        lines.append(f"   Auto-run: {', '.join(actions) if actions else 'none'}")
        lines.append("   Press Ctrl+C to stop.")
        return "\n".join(lines)

    @staticmethod
    def render_event(event: WatchEvent) -> str:
        """Render a single event notification."""
        type_emoji = {
            WatchEventType.RECORDING_ADDED: "\U0001f4e5",
            WatchEventType.RECORDING_MODIFIED: "\U0001f504",
            WatchEventType.TEST_MODIFIED: "\U0001f9ea",
            WatchEventType.CONFIG_MODIFIED: "\u2699\ufe0f",
        }
        emoji = type_emoji.get(event.type, "\U0001f514")
        ts = event.timestamp.strftime("%H:%M:%S")
        return f"   {emoji} [{ts}] {event.type.value}: {Path(event.path).name}"
