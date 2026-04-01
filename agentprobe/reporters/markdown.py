"""Markdown reporter — generates reports suitable for PR comments."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentprobe.core.models import AgentRecording


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


_STATUS_EMOJI = {
    "pass": "\u2705",
    "fail": "\u274c",
    "warn": "\u26a0\ufe0f",
    "skip": "\u23ed\ufe0f",
    "error": "\u274c",
}


# ---------------------------------------------------------------------------
# MarkdownReporter
# ---------------------------------------------------------------------------

class MarkdownReporter:
    """Generates Markdown test reports suitable for PR comments and CI summaries."""

    def generate_test_report(self, results: list[Any], output_path: str) -> None:
        """Generate a Markdown report file.

        Parameters
        ----------
        results:
            List of test result objects with attributes: name, status,
            duration_ms, cost_usd, error_message, error_type, recording.
        output_path:
            File path to write the Markdown to.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        passed = sum(1 for r in results if getattr(r, "status", "") == "pass")
        failed = sum(1 for r in results if getattr(r, "status", "") == "fail")
        warned = sum(1 for r in results if getattr(r, "status", "") == "warn")
        skipped = sum(1 for r in results if getattr(r, "status", "") == "skip")
        total_cost = sum(getattr(r, "cost_usd", 0.0) for r in results)
        total_duration = sum(getattr(r, "duration_ms", 0.0) for r in results)

        lines: list[str] = []

        # Title
        all_pass = failed == 0
        status_icon = "\u2705" if all_pass else "\u274c"
        lines.append(f"# {status_icon} AgentProbe Test Report")
        lines.append("")
        lines.append(f"> Generated {now} | {len(results)} tests")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| **Passed** | {passed} |")
        lines.append(f"| **Failed** | {failed} |")
        lines.append(f"| **Warnings** | {warned} |")
        lines.append(f"| **Skipped** | {skipped} |")
        lines.append(f"| **Total Cost** | {_format_cost(total_cost)} |")
        lines.append(f"| **Duration** | {_format_duration(total_duration)} |")
        if results:
            rate = passed / len(results) * 100
            lines.append(f"| **Pass Rate** | {rate:.1f}% |")
        lines.append("")

        # Results table
        lines.append("## Results")
        lines.append("")
        lines.append("| Status | Test | Duration | Cost |")
        lines.append("|:------:|------|----------|------|")

        for r in results:
            status = getattr(r, "status", "unknown")
            name = getattr(r, "name", "unknown")
            duration = getattr(r, "duration_ms", 0.0)
            cost = getattr(r, "cost_usd", 0.0)
            icon = _STATUS_EMOJI.get(status, "\u2753")
            lines.append(f"| {icon} | `{name}` | {_format_duration(duration)} | {_format_cost(cost)} |")

        lines.append("")

        # Failures detail
        failures = [r for r in results if getattr(r, "status", "") in ("fail", "error")]
        if failures:
            lines.append("## Failures")
            lines.append("")
            for r in failures:
                name = getattr(r, "name", "unknown")
                error_msg = getattr(r, "error_message", "No details")
                error_type = getattr(r, "error_type", None)
                lines.append(f"### \u274c `{name}`")
                lines.append("")
                if error_type:
                    lines.append(f"**{error_type}**")
                    lines.append("")
                lines.append("```")
                lines.append(str(error_msg))
                lines.append("```")
                lines.append("")

                # Add trace summary if recording is available
                recording: AgentRecording | None = getattr(r, "recording", None)
                if recording:
                    lines.append(f"<details><summary>Trace ({recording.step_count} steps, "
                                 f"{len(recording.llm_steps)} LLM calls, "
                                 f"{len(recording.tool_steps)} tool calls)</summary>")
                    lines.append("")
                    lines.append("| # | Type | Detail | Duration |")
                    lines.append("|---|------|--------|----------|")
                    for step in recording.steps[:20]:
                        step_type = step.type.value
                        detail = ""
                        if step.llm_call:
                            detail = f"{step.llm_call.model} ({step.llm_call.input_tokens}+{step.llm_call.output_tokens} tok)"
                        elif step.tool_call:
                            success = "\u2713" if step.tool_call.success else "\u2717"
                            detail = f"{success} {step.tool_call.tool_name}"
                        elif step.decision:
                            detail = f"{step.decision.type.value}: {step.decision.reason[:50]}"
                        lines.append(f"| {step.step_number} | {step_type} | {detail} | {_format_duration(step.duration_ms)} |")
                    if recording.step_count > 20:
                        lines.append(f"| ... | | {recording.step_count - 20} more steps | |")
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")

        # Cost breakdown
        if len(results) > 1:
            lines.append("## Cost Breakdown")
            lines.append("")
            sorted_by_cost = sorted(results, key=lambda r: getattr(r, "cost_usd", 0.0), reverse=True)
            lines.append("| Test | Cost | % of Total |")
            lines.append("|------|------|-----------|")
            for r in sorted_by_cost:
                name = getattr(r, "name", "unknown")
                cost = getattr(r, "cost_usd", 0.0)
                pct = (cost / total_cost * 100) if total_cost > 0 else 0
                bar_len = int(pct / 5)  # Max 20 chars
                bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
                lines.append(f"| `{name}` | {_format_cost(cost)} | {bar} {pct:.1f}% |")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Generated by [AgentProbe](https://github.com/agentprobe/agentprobe) "
                      f"-- pytest for AI Agents*")
        lines.append("")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
