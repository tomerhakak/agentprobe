"""X-Ray Mode -- Live Agent Visualization.

Renders a beautiful tree of how an agent thinks and acts, with per-step
cost, token count, and timing.  Free tier feature.
"""

from agentprobe.xray.visualizer import (
    XRayAnalyzer,
    XRayNode,
    XRayResult,
    XRaySummary,
    format_xray_html,
    format_xray_terminal,
)

__all__ = [
    "XRayAnalyzer",
    "XRayNode",
    "XRayResult",
    "XRaySummary",
    "format_xray_html",
    "format_xray_terminal",
]
