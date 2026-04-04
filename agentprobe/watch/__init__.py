"""Watch — Live Agent Monitoring Mode.

Real-time file watcher that automatically re-runs tests and analyses
when recordings or test files change. Like nodemon for AI agents.

Free tier feature — no Pro upgrade required.
"""

from agentprobe.watch.watcher import AgentWatcher, WatchEvent

__all__ = ["AgentWatcher", "WatchEvent"]
