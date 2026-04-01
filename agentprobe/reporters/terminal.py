"""Terminal reporter — Rich-based output for AgentProbe results."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# TestResult protocol — compatible with any test runner implementation
# ---------------------------------------------------------------------------

@runtime_checkable
class TestResult(Protocol):
    """Minimal interface for a test result object."""

    name: str
    status: str  # "pass" | "fail" | "warn" | "skip" | "error"
    duration_ms: float
    cost_usd: float
    error_message: str | None
    error_type: str | None
    recording: AgentRecording | None


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
    minutes = seconds / 60
    return f"{minutes:.1f}m"


_STATUS_ICONS = {
    "pass": ("[green]PASS[/green]", "[green]  [pass] [/green]"),
    "fail": ("[red]FAIL[/red]", "[red]  [fail] [/red]"),
    "warn": ("[yellow]WARN[/yellow]", "[yellow]  [warn] [/yellow]"),
    "skip": ("[dim]SKIP[/dim]", "[dim]  [skip] [/dim]"),
    "error": ("[red bold]ERROR[/red bold]", "[red]  [err]  [/red]"),
}


# ---------------------------------------------------------------------------
# TerminalReporter
# ---------------------------------------------------------------------------

class TerminalReporter:
    """Rich-based terminal reporter for AgentProbe."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    # -- Test results -------------------------------------------------------

    def report_test_results(self, results: list[Any]) -> None:
        """Display test results with pass/fail indicators, cost, and timing.

        Each result must have at minimum: name, status, duration_ms, cost_usd.
        Optional: error_message, error_type.
        """
        if not results:
            self.console.print("[yellow]No test results to display.[/yellow]")
            return

        self.console.print()

        passed = 0
        failed = 0
        warned = 0
        skipped = 0
        errored = 0
        total_cost = 0.0
        total_duration = 0.0

        for r in results:
            status = getattr(r, "status", "pass")
            name = getattr(r, "name", "unknown")
            duration = getattr(r, "duration_ms", 0.0)
            cost = getattr(r, "cost_usd", 0.0)
            error_msg = getattr(r, "error_message", None)
            error_type = getattr(r, "error_type", None)

            total_cost += cost
            total_duration += duration

            status_label, status_icon = _STATUS_ICONS.get(status, _STATUS_ICONS["error"])

            timing_info = f"({_format_duration(duration)}, {_format_cost(cost)})"
            line = Text()

            if status == "pass":
                passed += 1
                line.append("  \u2705 ", style="green")
                line.append(name, style="bold")
                line.append(f"    {status_label}  ", style="green")
                line.append(timing_info, style="dim")
            elif status == "fail":
                failed += 1
                line.append("  \u274c ", style="red")
                line.append(name, style="bold red")
                line.append(f"    {status_label}  ", style="red")
                line.append(timing_info, style="dim")
            elif status == "warn":
                warned += 1
                line.append("  \u26a0\ufe0f  ", style="yellow")
                line.append(name, style="bold yellow")
                line.append(f"    {status_label}  ", style="yellow")
                line.append(timing_info, style="dim")
            elif status == "skip":
                skipped += 1
                line.append("  \u23ed\ufe0f  ", style="dim")
                line.append(name, style="dim")
                line.append(f"    {status_label}  ", style="dim")
                line.append(timing_info, style="dim")
            else:
                errored += 1
                line.append("  \u274c ", style="red")
                line.append(name, style="bold red")
                line.append(f"    {status_label}  ", style="red")
                line.append(timing_info, style="dim")

            self.console.print(line)

            if error_msg:
                err_text = Text()
                err_text.append("     \u2514\u2500 ", style="dim")
                if error_type:
                    err_text.append(f"{error_type}: ", style="red bold")
                err_text.append(error_msg, style="red")
                self.console.print(err_text)

        # Summary
        self.console.print()
        summary_parts: list[str] = []
        if passed:
            summary_parts.append(f"[green]{passed} passed[/green]")
        if failed:
            summary_parts.append(f"[red]{failed} failed[/red]")
        if warned:
            summary_parts.append(f"[yellow]{warned} warnings[/yellow]")
        if skipped:
            summary_parts.append(f"[dim]{skipped} skipped[/dim]")
        if errored:
            summary_parts.append(f"[red]{errored} errors[/red]")

        summary_line = ", ".join(summary_parts) + f" in {_format_duration(total_duration)}"

        border = "green" if failed == 0 and errored == 0 else "red"
        self.console.print(Panel(
            f"{summary_line}\n"
            f"Total cost: [yellow]{_format_cost(total_cost)}[/yellow]",
            title="[bold]Test Summary[/bold]",
            border_style=border,
        ))

    # -- Recording view -----------------------------------------------------

    def report_recording(self, recording: AgentRecording) -> None:
        """Display a detailed view of a recording with trace steps."""
        meta = recording.metadata
        env = recording.environment

        # Header panel
        header_lines = [
            f"[bold]Name:[/bold]       {meta.name or meta.id}",
            f"[bold]ID:[/bold]         {meta.id}",
            f"[bold]Framework:[/bold]  {meta.agent_framework or '-'}",
            f"[bold]Model:[/bold]      {env.model or '-'}",
            f"[bold]Timestamp:[/bold]  {meta.timestamp.isoformat() if meta.timestamp else '-'}",
            f"[bold]Tags:[/bold]       {', '.join(meta.tags) if meta.tags else '(none)'}",
        ]
        self.console.print(Panel(
            "\n".join(header_lines),
            title="[bold cyan]Recording Details[/bold cyan]",
            border_style="cyan",
        ))

        # Metrics
        metrics_table = Table(show_header=False, box=None, padding=(0, 2))
        metrics_table.add_column("Label", style="bold")
        metrics_table.add_column("Value")
        metrics_table.add_row("Steps", str(recording.step_count))
        metrics_table.add_row("LLM Calls", str(len(recording.llm_steps)))
        metrics_table.add_row("Tool Calls", str(len(recording.tool_steps)))
        metrics_table.add_row("Total Cost", f"[yellow]{_format_cost(recording.total_cost)}[/yellow]")
        metrics_table.add_row("Total Tokens", f"{recording.total_tokens:,}")
        metrics_table.add_row("Duration", _format_duration(recording.total_duration))
        metrics_table.add_row("Status", self._colorize_status(recording.output.status.value))
        self.console.print(Panel(metrics_table, title="[bold]Metrics[/bold]", border_style="blue"))

        # Input
        input_content = recording.input.content
        if isinstance(input_content, str) and input_content:
            self.console.print(Panel(
                input_content[:500] + ("..." if len(str(input_content)) > 500 else ""),
                title="[bold]Input[/bold]",
                border_style="green",
            ))

        # Execution trace
        if recording.steps:
            tree = Tree("[bold]Execution Trace[/bold]")
            for step in recording.steps:
                self._add_step_to_tree(tree, step)
            self.console.print(Panel(tree, border_style="blue"))

        # Output
        output_content = recording.output.content
        if isinstance(output_content, str) and output_content:
            out_style = "green" if recording.output.status.value == "success" else "red"
            self.console.print(Panel(
                output_content[:500] + ("..." if len(str(output_content)) > 500 else ""),
                title="[bold]Output[/bold]",
                border_style=out_style,
            ))

        if recording.output.error:
            self.console.print(Panel(
                f"[red]{recording.output.error}[/red]",
                title="[bold red]Error[/bold red]",
                border_style="red",
            ))

        # System prompt
        if env.system_prompt:
            self.console.print(Panel(
                env.system_prompt[:300] + ("..." if len(env.system_prompt) > 300 else ""),
                title="[bold]System Prompt[/bold]",
                border_style="dim",
            ))

        # Tools available
        if env.tools_available:
            tool_names = ", ".join(t.name for t in env.tools_available)
            self.console.print(f"\n[bold]Available Tools:[/bold] {tool_names}")

    # -- Comparison ---------------------------------------------------------

    def report_comparison(self, comparison: dict[str, Any] | Any) -> None:
        """Display a side-by-side comparison of original vs replay."""
        if isinstance(comparison, dict):
            original = comparison.get("original")
            replay = comparison.get("replay")
        else:
            original = getattr(comparison, "original", None)
            replay = getattr(comparison, "replay", None)

        if original is None or replay is None:
            self.console.print("[yellow]Incomplete comparison data.[/yellow]")
            return

        table = Table(title="Recording Comparison")
        table.add_column("Metric", style="cyan")
        table.add_column("Original", justify="right")
        table.add_column("Replay", justify="right")
        table.add_column("Delta", justify="right")

        # Costs
        orig_cost = original.total_cost if isinstance(original, AgentRecording) else 0
        rep_cost = replay.total_cost if isinstance(replay, AgentRecording) else 0
        cost_delta = rep_cost - orig_cost
        cost_style = "green" if cost_delta <= 0 else "red"
        table.add_row(
            "Cost",
            _format_cost(orig_cost),
            _format_cost(rep_cost),
            f"[{cost_style}]{'+' if cost_delta >= 0 else ''}{_format_cost(cost_delta)}[/{cost_style}]",
        )

        # Duration
        orig_dur = original.total_duration if isinstance(original, AgentRecording) else 0
        rep_dur = replay.total_duration if isinstance(replay, AgentRecording) else 0
        dur_delta = rep_dur - orig_dur
        dur_style = "green" if dur_delta <= 0 else "red"
        table.add_row(
            "Duration",
            _format_duration(orig_dur),
            _format_duration(rep_dur),
            f"[{dur_style}]{'+' if dur_delta >= 0 else ''}{_format_duration(abs(dur_delta))}[/{dur_style}]",
        )

        # Steps
        orig_steps = original.step_count if isinstance(original, AgentRecording) else 0
        rep_steps = replay.step_count if isinstance(replay, AgentRecording) else 0
        step_delta = rep_steps - orig_steps
        step_style = "green" if step_delta <= 0 else "yellow"
        table.add_row(
            "Steps",
            str(orig_steps),
            str(rep_steps),
            f"[{step_style}]{'+' if step_delta >= 0 else ''}{step_delta}[/{step_style}]",
        )

        # Tokens
        orig_tokens = original.total_tokens if isinstance(original, AgentRecording) else 0
        rep_tokens = replay.total_tokens if isinstance(replay, AgentRecording) else 0
        token_delta = rep_tokens - orig_tokens
        token_style = "green" if token_delta <= 0 else "yellow"
        table.add_row(
            "Tokens",
            f"{orig_tokens:,}",
            f"{rep_tokens:,}",
            f"[{token_style}]{'+' if token_delta >= 0 else ''}{token_delta:,}[/{token_style}]",
        )

        # Status
        orig_status = original.output.status.value if isinstance(original, AgentRecording) else "-"
        rep_status = replay.output.status.value if isinstance(replay, AgentRecording) else "-"
        table.add_row(
            "Status",
            self._colorize_status(orig_status),
            self._colorize_status(rep_status),
            "[green]same[/green]" if orig_status == rep_status else "[red]changed[/red]",
        )

        # Model
        orig_model = original.environment.model if isinstance(original, AgentRecording) else "-"
        rep_model = replay.environment.model if isinstance(replay, AgentRecording) else "-"
        table.add_row("Model", orig_model, rep_model, "")

        self.console.print(table)

        # Output comparison
        if isinstance(original, AgentRecording) and isinstance(replay, AgentRecording):
            orig_out = str(original.output.content)[:200]
            rep_out = str(replay.output.content)[:200]
            if orig_out != rep_out:
                self.console.print(Panel(
                    f"[bold]Original:[/bold]\n{orig_out}\n\n[bold]Replay:[/bold]\n{rep_out}",
                    title="[bold]Output Differences[/bold]",
                    border_style="yellow",
                ))

    # -- Recordings list ----------------------------------------------------

    def report_recordings_list(self, recordings: list[dict[str, Any]]) -> None:
        """Display a table of recordings."""
        table = Table(title=f"Agent Recordings ({len(recordings)})")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Name", style="cyan", max_width=30)
        table.add_column("Framework", width=12)
        table.add_column("Model", width=20)
        table.add_column("Status", width=8, justify="center")
        table.add_column("Cost", justify="right", style="yellow")
        table.add_column("Duration", justify="right")
        table.add_column("Date", style="dim", width=16)

        for rec in recordings:
            status_str = self._colorize_status(rec.get("status", "-"))
            table.add_row(
                rec.get("id", "-"),
                rec.get("name", "-"),
                rec.get("framework", "-"),
                rec.get("model", "-"),
                status_str,
                _format_cost(rec.get("cost", 0)),
                _format_duration(rec.get("duration", 0)),
                rec.get("date", "-"),
            )

        self.console.print(table)

    # -- Helpers ------------------------------------------------------------

    def _colorize_status(self, status: str) -> str:
        """Return a Rich-styled status string."""
        mapping = {
            "success": "[green]success[/green]",
            "pass": "[green]pass[/green]",
            "error": "[red]error[/red]",
            "fail": "[red]fail[/red]",
            "timeout": "[yellow]timeout[/yellow]",
            "cancelled": "[dim]cancelled[/dim]",
            "warn": "[yellow]warn[/yellow]",
            "skip": "[dim]skip[/dim]",
        }
        return mapping.get(status, status)

    def _add_step_to_tree(self, tree: Tree, step: AgentStep) -> None:
        """Add a step node to a Rich tree."""
        duration = _format_duration(step.duration_ms)

        if step.type == StepType.LLM_CALL and step.llm_call:
            llm = step.llm_call
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"[cyan]LLM Call[/cyan] "
                f"({llm.model}, {llm.input_tokens}+{llm.output_tokens} tok, "
                f"{_format_cost(llm.cost_usd)}, {duration})"
            )
            node = tree.add(label)
            if llm.finish_reason:
                node.add(f"[dim]finish_reason: {llm.finish_reason}[/dim]")
            if llm.cache_hit:
                node.add("[green]cache hit[/green]")

        elif step.type == StepType.TOOL_CALL and step.tool_call:
            tc = step.tool_call
            success_icon = "[green]\u2713[/green]" if tc.success else "[red]\u2717[/red]"
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"{success_icon} [magenta]Tool: {tc.tool_name}[/magenta] ({duration})"
            )
            node = tree.add(label)
            if tc.tool_input is not None:
                input_str = json.dumps(tc.tool_input, default=str)
                if len(input_str) > 120:
                    input_str = input_str[:120] + "..."
                node.add(f"[dim]input: {input_str}[/dim]")
            if tc.error:
                node.add(f"[red]error: {tc.error}[/red]")
            if tc.side_effects:
                node.add(f"[yellow]side effects: {', '.join(tc.side_effects)}[/yellow]")

        elif step.type == StepType.TOOL_RESULT:
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"[dim]Tool Result[/dim] ({duration})"
            )
            tree.add(label)

        elif step.type == StepType.DECISION and step.decision:
            dec = step.decision
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"[yellow]Decision: {dec.type.value}[/yellow] ({duration})"
            )
            node = tree.add(label)
            if dec.reason:
                node.add(f"[dim]{dec.reason}[/dim]")
            if dec.alternatives_considered:
                node.add(f"[dim]alternatives: {', '.join(dec.alternatives_considered)}[/dim]")

        elif step.type == StepType.HANDOFF:
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"[bold yellow]Handoff[/bold yellow] ({duration})"
            )
            tree.add(label)

        elif step.type in (StepType.MEMORY_READ, StepType.MEMORY_WRITE):
            op = "Read" if step.type == StepType.MEMORY_READ else "Write"
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"[dim]Memory {op}[/dim] ({duration})"
            )
            tree.add(label)

        else:
            label = (
                f"[bold blue]#{step.step_number}[/bold blue] "
                f"{step.type.value} ({duration})"
            )
            tree.add(label)
