"""X-Ray Mode -- Live Agent Visualization.

Renders a beautiful tree visualization of how an agent thinks and acts,
showing cost, tokens, and timing for every step. Works from a recording
file or from a live ``AgentRecording`` object.

Free tier feature -- no Pro upgrade required.
"""

from __future__ import annotations

import html as _html
import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Data structures produced by XRayAnalyzer
# ---------------------------------------------------------------------------

@dataclass
class XRayNode:
    """A single node in the X-Ray visualization tree."""

    kind: str  # "think", "tool", "response", "decision", "memory", "handoff"
    label: str
    detail: str = ""
    duration_s: float = 0.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_name: Optional[str] = None
    tool_input: Optional[Any] = None
    tool_output: Optional[Any] = None
    is_error: bool = False
    is_slowest: bool = False
    is_most_expensive: bool = False


@dataclass
class XRaySummary:
    """Aggregate summary for the entire trace."""

    total_steps: int = 0
    llm_steps: int = 0
    tool_steps: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    total_duration_s: float = 0.0
    slowest_step: Optional[str] = None
    slowest_duration_s: float = 0.0
    most_expensive_step: Optional[str] = None
    most_expensive_cost: float = 0.0


@dataclass
class XRayResult:
    """Complete X-Ray analysis result."""

    query: str
    nodes: List[XRayNode] = field(default_factory=list)
    summary: XRaySummary = field(default_factory=XRaySummary)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_cost(cost: float) -> str:
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _fmt_duration(seconds: float) -> str:
    if seconds < 0.001:
        return "<1ms"
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


def _truncate(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _safe_json(obj: Any, max_len: int = 80) -> str:
    try:
        raw = json.dumps(obj, default=str)
    except (TypeError, ValueError):
        raw = str(obj)
    return _truncate(raw, max_len)


# ---------------------------------------------------------------------------
# XRayAnalyzer
# ---------------------------------------------------------------------------

class XRayAnalyzer:
    """Analyze an ``AgentRecording`` and produce an :class:`XRayResult`.

    Usage::

        from agentprobe.xray.visualizer import XRayAnalyzer

        analyzer = XRayAnalyzer()
        result = analyzer.analyze(recording)
        print(format_xray_terminal(result))
    """

    def analyze(self, recording: AgentRecording) -> XRayResult:
        """Build the full X-Ray tree from a recording.

        Parameters
        ----------
        recording:
            An ``AgentRecording`` instance (loaded from file or captured live).

        Returns
        -------
        XRayResult
            The analysis result with nodes and summary.
        """
        query = str(recording.input.content) if recording.input.content else "(no input)"
        nodes: List[XRayNode] = []

        for step in recording.steps:
            node = self._step_to_node(step)
            nodes.append(node)

        # Mark slowest and most expensive
        if nodes:
            slowest = max(nodes, key=lambda n: n.duration_s)
            slowest.is_slowest = True
            most_expensive = max(nodes, key=lambda n: n.cost_usd)
            if most_expensive.cost_usd > 0:
                most_expensive.is_most_expensive = True

        # Summary
        llm_nodes = [n for n in nodes if n.kind == "think"]
        tool_nodes = [n for n in nodes if n.kind == "tool"]
        total_tokens = sum(n.input_tokens + n.output_tokens for n in nodes)
        total_cost = sum(n.cost_usd for n in nodes)
        total_duration = sum(n.duration_s for n in nodes)

        summary = XRaySummary(
            total_steps=len(nodes),
            llm_steps=len(llm_nodes),
            tool_steps=len(tool_nodes),
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            total_duration_s=total_duration,
            slowest_step=slowest.label if nodes else None,
            slowest_duration_s=slowest.duration_s if nodes else 0.0,
            most_expensive_step=most_expensive.label if nodes and most_expensive.cost_usd > 0 else None,
            most_expensive_cost=most_expensive.cost_usd if nodes and most_expensive.cost_usd > 0 else 0.0,
        )

        return XRayResult(query=query, nodes=nodes, summary=summary)

    # -- Internal -----------------------------------------------------------

    def _step_to_node(self, step: AgentStep) -> XRayNode:
        """Convert a single ``AgentStep`` into an ``XRayNode``."""
        duration_s = step.duration_ms / 1000.0

        if step.type == StepType.LLM_CALL and step.llm_call:
            llm = step.llm_call
            # Try to extract a short "thought" from the output message
            thought = ""
            if llm.output_message:
                content = llm.output_message.content
                if isinstance(content, str):
                    thought = _truncate(content, 120)
                elif isinstance(content, list) and content:
                    first = content[0]
                    if hasattr(first, "text") and first.text:
                        thought = _truncate(first.text, 120)
            return XRayNode(
                kind="think",
                label=f"THINK [{_fmt_duration(duration_s)}] [{_fmt_cost(llm.cost_usd)}]",
                detail=thought or "(no output captured)",
                duration_s=duration_s,
                cost_usd=llm.cost_usd,
                input_tokens=llm.input_tokens,
                output_tokens=llm.output_tokens,
            )

        if step.type == StepType.TOOL_CALL and step.tool_call:
            tc = step.tool_call
            output_preview = ""
            if tc.tool_output is not None:
                output_preview = _safe_json(tc.tool_output, 80)
            return XRayNode(
                kind="tool",
                label=f"TOOL: {tc.tool_name}() [{_fmt_duration(duration_s)}]",
                detail=output_preview,
                duration_s=duration_s,
                tool_name=tc.tool_name,
                tool_input=tc.tool_input,
                tool_output=tc.tool_output,
                is_error=not tc.success,
            )

        if step.type == StepType.TOOL_RESULT:
            return XRayNode(
                kind="tool",
                label=f"TOOL RESULT [{_fmt_duration(duration_s)}]",
                duration_s=duration_s,
            )

        if step.type == StepType.DECISION and step.decision:
            dec = step.decision
            return XRayNode(
                kind="decision",
                label=f"DECISION: {dec.type.value} [{_fmt_duration(duration_s)}]",
                detail=dec.reason or "",
                duration_s=duration_s,
            )

        if step.type == StepType.HANDOFF:
            return XRayNode(
                kind="handoff",
                label=f"HANDOFF [{_fmt_duration(duration_s)}]",
                duration_s=duration_s,
            )

        if step.type in (StepType.MEMORY_READ, StepType.MEMORY_WRITE):
            op = "READ" if step.type == StepType.MEMORY_READ else "WRITE"
            return XRayNode(
                kind="memory",
                label=f"MEMORY {op} [{_fmt_duration(duration_s)}]",
                duration_s=duration_s,
            )

        return XRayNode(
            kind="unknown",
            label=f"{step.type.value} [{_fmt_duration(duration_s)}]",
            duration_s=duration_s,
        )


# ---------------------------------------------------------------------------
# Terminal formatter (Rich)
# ---------------------------------------------------------------------------

_KIND_ICONS = {
    "think": "\U0001f9e0",     # brain
    "tool": "\U0001f527",      # wrench
    "response": "\U0001f4ac",  # speech bubble
    "decision": "\U0001f500",  # shuffle
    "handoff": "\U0001f91d",   # handshake
    "memory": "\U0001f4be",    # floppy disk
    "unknown": "\u2753",       # question mark
}


def format_xray_terminal(result: XRayResult, *, use_color: bool = True) -> str:
    """Render an ``XRayResult`` as a beautiful terminal string.

    Parameters
    ----------
    result:
        The analysis result from :meth:`XRayAnalyzer.analyze`.
    use_color:
        If ``True`` (default), output includes ANSI escape codes for colour.

    Returns
    -------
    str
        Multi-line terminal-ready string.
    """
    lines: List[str] = []

    # Header
    header_query = _truncate(result.query, 60)
    lines.append("")
    lines.append(f"\U0001f52c Agent X-Ray \u2014 \"{header_query}\"")
    lines.append("\u2550" * 55)
    lines.append("\u2502")

    total = len(result.nodes)
    for idx, node in enumerate(result.nodes):
        is_last = idx == total - 1
        connector = "\u2514" if is_last else "\u251c"
        pipe = " " if is_last else "\u2502"
        icon = _KIND_ICONS.get(node.kind, "\u2753")

        # Markers for slowest / most expensive
        markers: List[str] = []
        if node.is_slowest:
            markers.append("\u26a1 SLOWEST")
        if node.is_most_expensive:
            markers.append("\U0001f4b8 MOST EXPENSIVE")
        marker_str = f"  ({', '.join(markers)})" if markers else ""

        lines.append(f"{connector}\u2500{icon} {node.label}{marker_str}")

        # Detail line
        if node.detail:
            wrapped = _truncate(node.detail, 100)
            lines.append(f"{pipe}  \"{wrapped}\"")

        # Token info for think nodes
        if node.kind == "think" and (node.input_tokens or node.output_tokens):
            lines.append(f"{pipe}  Tokens: {node.input_tokens} in \u2192 {node.output_tokens} out")

        # Tool input/output for tool nodes
        if node.kind == "tool" and node.tool_input is not None:
            lines.append(f"{pipe}  Input: {_safe_json(node.tool_input, 80)}")
        if node.kind == "tool" and node.tool_output is not None:
            lines.append(f"{pipe}  Output: {_safe_json(node.tool_output, 80)}")

        # Error marker
        if node.is_error:
            lines.append(f"{pipe}  \u274c ERROR")

        lines.append(f"{pipe}")

    # Footer: response summary
    s = result.summary
    lines.append(f"\U0001f4ac RESPONSE [total: {_fmt_duration(s.total_duration_s)} | {_fmt_cost(s.total_cost_usd)}]")
    lines.append("\u2550" * 55)
    lines.append(f"   Steps: {s.total_steps} | LLM: {s.llm_steps} | Tools: {s.tool_steps}")
    lines.append(f"   Cost: {_fmt_cost(s.total_cost_usd)} | Tokens: {s.total_tokens:,}")
    if s.slowest_step:
        lines.append(f"   Slowest: {s.slowest_step} ({_fmt_duration(s.slowest_duration_s)})")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML formatter
# ---------------------------------------------------------------------------

def format_xray_html(result: XRayResult) -> str:
    """Render an ``XRayResult`` as a self-contained HTML report.

    Parameters
    ----------
    result:
        The analysis result from :meth:`XRayAnalyzer.analyze`.

    Returns
    -------
    str
        A complete HTML document string.
    """
    s = result.summary
    header_query = _html.escape(_truncate(result.query, 80))

    node_rows: List[str] = []
    for node in result.nodes:
        icon = _KIND_ICONS.get(node.kind, "\u2753")
        cls_list = [node.kind]
        if node.is_slowest:
            cls_list.append("slowest")
        if node.is_most_expensive:
            cls_list.append("expensive")
        if node.is_error:
            cls_list.append("error")
        cls = " ".join(cls_list)

        badges = ""
        if node.is_slowest:
            badges += ' <span class="badge badge-slow">\u26a1 SLOWEST</span>'
        if node.is_most_expensive:
            badges += ' <span class="badge badge-cost">\U0001f4b8 MOST EXPENSIVE</span>'
        if node.is_error:
            badges += ' <span class="badge badge-error">\u274c ERROR</span>'

        detail_html = ""
        if node.detail:
            detail_html = f'<div class="detail">{_html.escape(_truncate(node.detail, 200))}</div>'
        if node.kind == "think" and (node.input_tokens or node.output_tokens):
            detail_html += f'<div class="tokens">Tokens: {node.input_tokens} in &rarr; {node.output_tokens} out</div>'
        if node.kind == "tool" and node.tool_input is not None:
            detail_html += f'<div class="io">Input: {_html.escape(_safe_json(node.tool_input, 120))}</div>'
        if node.kind == "tool" and node.tool_output is not None:
            detail_html += f'<div class="io">Output: {_html.escape(_safe_json(node.tool_output, 120))}</div>'

        node_rows.append(
            f'<div class="node {cls}">'
            f'<div class="node-header">{icon} {_html.escape(node.label)}{badges}</div>'
            f'{detail_html}'
            f'</div>'
        )

    nodes_html = "\n".join(node_rows)

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>Agent X-Ray &mdash; {header_query}</title>
    <style>
      :root {{
        --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff;
        --green: #3fb950; --red: #f85149; --yellow: #d29922;
        --border: #30363d; --card-bg: #161b22;
      }}
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{ font-family: 'SF Mono', 'Fira Code', monospace; background: var(--bg); color: var(--fg); padding: 2rem; }}
      h1 {{ color: var(--accent); margin-bottom: .5rem; font-size: 1.3rem; }}
      .subtitle {{ color: #8b949e; margin-bottom: 1.5rem; }}
      .node {{
        background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
        padding: 12px 16px; margin: 8px 0; margin-left: 24px;
        border-left: 3px solid var(--accent); position: relative;
      }}
      .node::before {{
        content: ''; position: absolute; left: -26px; top: 20px;
        width: 20px; height: 2px; background: var(--border);
      }}
      .node.think {{ border-left-color: var(--accent); }}
      .node.tool {{ border-left-color: var(--green); }}
      .node.decision {{ border-left-color: var(--yellow); }}
      .node.error {{ border-left-color: var(--red); }}
      .node.slowest {{ box-shadow: 0 0 0 1px var(--yellow); }}
      .node.expensive {{ box-shadow: 0 0 0 1px var(--red); }}
      .node-header {{ font-weight: bold; margin-bottom: 4px; }}
      .detail {{ color: #8b949e; font-style: italic; margin: 4px 0; }}
      .tokens, .io {{ color: #8b949e; font-size: 0.85em; }}
      .badge {{
        display: inline-block; font-size: 0.7em; padding: 2px 6px;
        border-radius: 4px; margin-left: 8px; font-weight: normal;
      }}
      .badge-slow {{ background: rgba(210,153,34,0.2); color: var(--yellow); }}
      .badge-cost {{ background: rgba(248,81,73,0.2); color: var(--red); }}
      .badge-error {{ background: rgba(248,81,73,0.3); color: var(--red); }}
      .summary {{
        background: var(--card-bg); border: 1px solid var(--border);
        border-radius: 8px; padding: 16px; margin-top: 1.5rem;
      }}
      .summary h2 {{ color: var(--accent); font-size: 1rem; margin-bottom: 8px; }}
      .summary .row {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
      .summary .stat {{ }}
      .summary .stat .label {{ color: #8b949e; font-size: 0.8em; }}
      .summary .stat .value {{ font-size: 1.1em; font-weight: bold; }}
    </style>
    </head>
    <body>
    <h1>\U0001f52c Agent X-Ray</h1>
    <div class="subtitle">&ldquo;{header_query}&rdquo;</div>
    <div class="trace">
    {nodes_html}
    </div>
    <div class="summary">
      <h2>\U0001f4ac Summary</h2>
      <div class="row">
        <div class="stat"><div class="label">Steps</div><div class="value">{s.total_steps}</div></div>
        <div class="stat"><div class="label">LLM Calls</div><div class="value">{s.llm_steps}</div></div>
        <div class="stat"><div class="label">Tool Calls</div><div class="value">{s.tool_steps}</div></div>
        <div class="stat"><div class="label">Cost</div><div class="value">{_fmt_cost(s.total_cost_usd)}</div></div>
        <div class="stat"><div class="label">Tokens</div><div class="value">{s.total_tokens:,}</div></div>
        <div class="stat"><div class="label">Duration</div><div class="value">{_fmt_duration(s.total_duration_s)}</div></div>
      </div>
    </div>
    </body>
    </html>
    """)
