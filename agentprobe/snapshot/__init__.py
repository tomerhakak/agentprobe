"""Snapshot — Snapshot Testing for Agent Behavior.

Capture agent behavior as snapshots and detect regressions automatically,
like Jest snapshots but for AI agent outputs and decision patterns.

Free tier feature — no Pro upgrade required.
"""

from agentprobe.snapshot.manager import SnapshotManager, SnapshotResult

__all__ = ["SnapshotManager", "SnapshotResult"]
