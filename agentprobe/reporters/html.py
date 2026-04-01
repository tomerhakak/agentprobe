"""HTML reporter — generates self-contained HTML test reports."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentprobe.core.models import AgentRecording, StepType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_cost(cost: float) -> str:
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _format_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


def _esc(text: str) -> str:
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# CSS (Tailwind-inspired, fully inlined)
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
       background: #0f1117; color: #e4e4e7; line-height: 1.6; padding: 2rem; }
h1 { font-size: 1.8rem; font-weight: 700; margin-bottom: 0.5rem; }
h2 { font-size: 1.3rem; font-weight: 600; margin-bottom: 0.5rem; color: #a1a1aa; }
h3 { font-size: 1.1rem; font-weight: 600; margin: 1rem 0 0.5rem; }
a { color: #60a5fa; text-decoration: none; }
.container { max-width: 1200px; margin: 0 auto; }
.header { border-bottom: 1px solid #27272a; padding-bottom: 1.5rem; margin-bottom: 2rem; }
.subtitle { color: #71717a; font-size: 0.9rem; }

/* Summary cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.card { background: #18181b; border: 1px solid #27272a; border-radius: 0.75rem; padding: 1.25rem; }
.card-label { font-size: 0.8rem; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em; }
.card-value { font-size: 1.8rem; font-weight: 700; margin-top: 0.25rem; }
.card-value.green { color: #22c55e; }
.card-value.red { color: #ef4444; }
.card-value.yellow { color: #eab308; }
.card-value.blue { color: #3b82f6; }

/* Test list */
.test-list { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 2rem; }
.test-row { background: #18181b; border: 1px solid #27272a; border-radius: 0.5rem; overflow: hidden; }
.test-header { display: flex; align-items: center; padding: 0.75rem 1rem; cursor: pointer; gap: 0.75rem; }
.test-header:hover { background: #1f1f23; }
.test-icon { font-size: 1.2rem; flex-shrink: 0; }
.test-name { flex: 1; font-weight: 500; }
.test-badge { padding: 0.15rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
.badge-pass { background: #052e16; color: #22c55e; }
.badge-fail { background: #450a0a; color: #ef4444; }
.badge-warn { background: #422006; color: #eab308; }
.badge-skip { background: #1c1917; color: #78716c; }
.test-meta { color: #71717a; font-size: 0.85rem; display: flex; gap: 1rem; }
.test-detail { display: none; padding: 0.75rem 1rem 1rem 3rem; border-top: 1px solid #27272a;
               background: #111113; font-size: 0.9rem; }
.test-detail.open { display: block; }
.error-msg { color: #ef4444; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.85rem;
             background: #1c0a0a; padding: 0.5rem 0.75rem; border-radius: 0.375rem; margin-top: 0.5rem;
             white-space: pre-wrap; word-break: break-word; }

/* Trace */
.trace { margin-top: 0.75rem; }
.trace-step { display: flex; gap: 0.5rem; padding: 0.3rem 0; font-size: 0.85rem; font-family: monospace; }
.trace-num { color: #3b82f6; min-width: 2rem; text-align: right; }
.trace-type { min-width: 6rem; }
.trace-type.llm { color: #06b6d4; }
.trace-type.tool { color: #a855f7; }
.trace-type.decision { color: #eab308; }
.trace-info { color: #71717a; }

/* Charts (simple inline bar charts) */
.bar-chart { margin: 1.5rem 0; }
.bar-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.4rem; font-size: 0.85rem; }
.bar-label { width: 120px; text-align: right; color: #a1a1aa; }
.bar-track { flex: 1; background: #27272a; border-radius: 4px; height: 20px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-fill.cost { background: linear-gradient(90deg, #22c55e, #eab308); }
.bar-fill.latency { background: linear-gradient(90deg, #3b82f6, #8b5cf6); }
.bar-value { width: 80px; color: #71717a; font-size: 0.8rem; }

footer { margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #27272a;
         color: #52525b; font-size: 0.8rem; text-align: center; }
"""

_JS = """\
document.querySelectorAll('.test-header').forEach(function(h) {
  h.addEventListener('click', function() {
    var detail = h.nextElementSibling;
    if (detail) detail.classList.toggle('open');
  });
});
"""


# ---------------------------------------------------------------------------
# HTMLReporter
# ---------------------------------------------------------------------------

class HTMLReporter:
    """Generates self-contained HTML test reports."""

    def generate_test_report(self, results: list[Any], output_path: str) -> None:
        """Generate a complete HTML report file.

        Parameters
        ----------
        results:
            List of test result objects with attributes: name, status,
            duration_ms, cost_usd, error_message, error_type, recording.
        output_path:
            File path to write the HTML to.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        passed = sum(1 for r in results if getattr(r, "status", "") == "pass")
        failed = sum(1 for r in results if getattr(r, "status", "") == "fail")
        warned = sum(1 for r in results if getattr(r, "status", "") == "warn")
        skipped = sum(1 for r in results if getattr(r, "status", "") == "skip")
        total_cost = sum(getattr(r, "cost_usd", 0.0) for r in results)
        total_duration = sum(getattr(r, "duration_ms", 0.0) for r in results)

        parts: list[str] = []
        parts.append(f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>")
        parts.append(f"<meta name='viewport' content='width=device-width,initial-scale=1'>")
        parts.append(f"<title>AgentProbe Test Report</title>")
        parts.append(f"<style>{_CSS}</style></head><body>")
        parts.append(f"<div class='container'>")

        # Header
        parts.append(f"<div class='header'>")
        parts.append(f"<h1>AgentProbe Test Report</h1>")
        parts.append(f"<div class='subtitle'>Generated {now} &mdash; {len(results)} tests</div>")
        parts.append(f"</div>")

        # Summary cards
        parts.append(f"<div class='cards'>")
        parts.append(self._card("Passed", str(passed), "green"))
        parts.append(self._card("Failed", str(failed), "red"))
        parts.append(self._card("Warnings", str(warned), "yellow"))
        parts.append(self._card("Total Cost", _format_cost(total_cost), "blue"))
        parts.append(self._card("Duration", _format_duration(total_duration), "blue"))
        parts.append(self._card("Total", str(len(results)), "blue"))
        parts.append(f"</div>")

        # Cost chart
        max_cost = max((getattr(r, "cost_usd", 0.0) for r in results), default=0.001) or 0.001
        parts.append(f"<h3>Cost per Test</h3>")
        parts.append(f"<div class='bar-chart'>")
        for r in sorted(results, key=lambda x: getattr(x, "cost_usd", 0.0), reverse=True):
            cost = getattr(r, "cost_usd", 0.0)
            pct = min(cost / max_cost * 100, 100)
            parts.append(
                f"<div class='bar-row'>"
                f"<span class='bar-label'>{_esc(getattr(r, 'name', ''))[:20]}</span>"
                f"<div class='bar-track'><div class='bar-fill cost' style='width:{pct:.1f}%'></div></div>"
                f"<span class='bar-value'>{_format_cost(cost)}</span>"
                f"</div>"
            )
        parts.append(f"</div>")

        # Latency chart
        max_dur = max((getattr(r, "duration_ms", 0.0) for r in results), default=1.0) or 1.0
        parts.append(f"<h3>Latency per Test</h3>")
        parts.append(f"<div class='bar-chart'>")
        for r in sorted(results, key=lambda x: getattr(x, "duration_ms", 0.0), reverse=True):
            dur = getattr(r, "duration_ms", 0.0)
            pct = min(dur / max_dur * 100, 100)
            parts.append(
                f"<div class='bar-row'>"
                f"<span class='bar-label'>{_esc(getattr(r, 'name', ''))[:20]}</span>"
                f"<div class='bar-track'><div class='bar-fill latency' style='width:{pct:.1f}%'></div></div>"
                f"<span class='bar-value'>{_format_duration(dur)}</span>"
                f"</div>"
            )
        parts.append(f"</div>")

        # Test details
        parts.append(f"<h3>Test Results</h3>")
        parts.append(f"<div class='test-list'>")
        for r in results:
            parts.append(self._test_row(r))
        parts.append(f"</div>")

        # Footer
        parts.append(f"<footer>Generated by AgentProbe &mdash; pytest for AI Agents</footer>")
        parts.append(f"</div>")
        parts.append(f"<script>{_JS}</script>")
        parts.append(f"</body></html>")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("\n".join(parts), encoding="utf-8")

    # -- Helpers ------------------------------------------------------------

    def _card(self, label: str, value: str, color: str) -> str:
        return (
            f"<div class='card'>"
            f"<div class='card-label'>{_esc(label)}</div>"
            f"<div class='card-value {color}'>{_esc(value)}</div>"
            f"</div>"
        )

    def _test_row(self, result: Any) -> str:
        status = getattr(result, "status", "pass")
        name = getattr(result, "name", "unknown")
        duration = getattr(result, "duration_ms", 0.0)
        cost = getattr(result, "cost_usd", 0.0)
        error_msg = getattr(result, "error_message", None)
        error_type = getattr(result, "error_type", None)
        recording: AgentRecording | None = getattr(result, "recording", None)

        icons = {"pass": "\u2705", "fail": "\u274c", "warn": "\u26a0\ufe0f", "skip": "\u23ed\ufe0f", "error": "\u274c"}
        badge_cls = {"pass": "badge-pass", "fail": "badge-fail", "warn": "badge-warn", "skip": "badge-skip", "error": "badge-fail"}

        parts = ["<div class='test-row'>"]
        parts.append("<div class='test-header'>")
        icon = icons.get(status, "\u2753")
        parts.append(f"<span class='test-icon'>{icon}</span>")
        escaped_name = _esc(name)
        parts.append(f"<span class='test-name'>{escaped_name}</span>")
        badge = badge_cls.get(status, "badge-skip")
        escaped_status = _esc(status.upper())
        parts.append(f"<span class='test-badge {badge}'>{escaped_status}</span>")
        parts.append(f"<span class='test-meta'><span>{_format_duration(duration)}</span><span>{_format_cost(cost)}</span></span>")
        parts.append(f"</div>")

        # Detail section
        parts.append(f"<div class='test-detail'>")
        if error_msg:
            prefix = f"{_esc(error_type)}: " if error_type else ""
            parts.append(f"<div class='error-msg'>{prefix}{_esc(error_msg)}</div>")

        if recording and recording.steps:
            parts.append(f"<div class='trace'><strong>Execution Trace ({recording.step_count} steps)</strong>")
            for step in recording.steps[:30]:  # Limit to first 30 steps for readability
                parts.append(self._trace_step_html(step))
            if recording.step_count > 30:
                parts.append(f"<div class='trace-step'><span class='trace-info'>... and {recording.step_count - 30} more steps</span></div>")
            parts.append(f"</div>")

        parts.append(f"</div>")
        parts.append(f"</div>")
        return "\n".join(parts)

    def _trace_step_html(self, step: Any) -> str:
        step_type = step.type.value if hasattr(step.type, "value") else str(step.type)
        type_cls = ""
        info = ""

        if step_type == "llm_call" and step.llm_call:
            type_cls = "llm"
            llm = step.llm_call
            info = f"{llm.model} | {llm.input_tokens}+{llm.output_tokens} tok | {_format_cost(llm.cost_usd)}"
        elif step_type == "tool_call" and step.tool_call:
            type_cls = "tool"
            tc = step.tool_call
            status = "\u2713" if tc.success else "\u2717"
            info = f"{status} {tc.tool_name}"
            if tc.error:
                info += f" | {_esc(tc.error[:60])}"
        elif step_type == "decision" and step.decision:
            type_cls = "decision"
            info = f"{step.decision.type.value}: {_esc(step.decision.reason[:60])}"

        return (
            f"<div class='trace-step'>"
            f"<span class='trace-num'>#{step.step_number}</span>"
            f"<span class='trace-type {type_cls}'>{_esc(step_type)}</span>"
            f"<span class='trace-info'>{info} ({_format_duration(step.duration_ms)})</span>"
            f"</div>"
        )
