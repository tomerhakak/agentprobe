"""Timeline — Time Travel Debugger for AI agents.

Step forward and backward through agent execution, inspect state at each
point, set breakpoints, and watch variables change over time.

Free tier feature — no Pro upgrade required.
"""

from agentprobe.timeline.debugger import TimelineDebugger, TimelineState, Breakpoint

__all__ = ["TimelineDebugger", "TimelineState", "Breakpoint"]
