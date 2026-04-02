"""AgentProbe CLI — polished Click-based interface with Rich formatting."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

import agentprobe
from agentprobe.core.config import AgentProbeConfig
from agentprobe.core.models import AgentRecording, StepType

console = Console()
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRAMEWORKS = ["auto", "langchain", "crewai", "openai", "anthropic", "custom"]


def _load_config() -> AgentProbeConfig:
    """Load the project config or return defaults."""
    try:
        return AgentProbeConfig.load()
    except Exception:
        return AgentProbeConfig.default()


def _resolve_store():
    """Lazily import and return a RecordingStore instance."""
    from agentprobe.storage.store import RecordingStore

    cfg = _load_config()
    return RecordingStore(cfg.recording.storage_dir)


def _find_recordings(pattern: str | None = None, tag: str | None = None) -> list[Path]:
    """Find .aprobe recording files in the storage directory."""
    cfg = _load_config()
    storage_dir = Path(cfg.recording.storage_dir)
    if not storage_dir.exists():
        return []
    glob_pattern = pattern or "**/*.aprobe"
    results = sorted(storage_dir.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if tag:
        filtered = []
        for p in results:
            try:
                rec = AgentRecording.load(p)
                if tag in rec.metadata.tags:
                    filtered.append(p)
            except Exception:
                continue
        return filtered
    return results


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


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential output.")
@click.pass_context
def cli(ctx: click.Context, quiet: bool) -> None:
    """AgentProbe — pytest for AI Agents.

    Test, record, replay, and monitor AI agents locally.
    """
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

@cli.command()
def version() -> None:
    """Show AgentProbe version."""
    console.print(Panel(
        f"[bold cyan]AgentProbe[/bold cyan] v{agentprobe.__version__}",
        subtitle="pytest for AI Agents",
        border_style="cyan",
    ))


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--interactive", "-i", is_flag=True, help="Run interactive setup wizard.")
def init(interactive: bool) -> None:
    """Initialize an AgentProbe project in the current directory."""
    config_path = Path.cwd() / "agentprobe.yaml"
    if config_path.exists():
        if not click.confirm("agentprobe.yaml already exists. Overwrite?", default=False):
            console.print("[yellow]Aborted.[/yellow]")
            return

    if interactive:
        project_name = click.prompt("Project name", default=Path.cwd().name)
        description = click.prompt("Description", default="")
        framework = click.prompt(
            "Agent framework",
            type=click.Choice(_FRAMEWORKS),
            default="auto",
        )
        default_model = click.prompt("Default model", default="claude-sonnet-4-6")
        test_dir = click.prompt("Test directory", default="tests/agent_tests")
        max_cost = click.prompt("Max cost per test (USD)", default=1.0, type=float)

        cfg = AgentProbeConfig(
            project_name=project_name,
            description=description,
            framework=framework,
            default_model=default_model,
            testing={"test_dir": test_dir, "default_max_cost_usd": max_cost},
        )
    else:
        cfg = AgentProbeConfig(project_name=Path.cwd().name)

    cfg.save(config_path)

    # Create directory structure
    dirs = [
        Path(cfg.recording.storage_dir),
        Path(cfg.testing.test_dir),
        Path(".agentprobe/snapshots"),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Create example test file if test dir is empty
    test_dir = Path(cfg.testing.test_dir)
    example_test = test_dir / "test_example.py"
    if not example_test.exists():
        example_test.write_text(
            '"""Example AgentProbe test."""\n\n'
            'from agentprobe import assertions\n\n\n'
            'def test_agent_responds(recording):\n'
            '    """Verify the agent produces a non-empty response."""\n'
            '    assertions.output_is_not_empty(recording)\n'
            '    assertions.cost_below(recording, max_cost_usd=0.50)\n'
            '    assertions.latency_below(recording, max_ms=10000)\n',
        )

    console.print(Panel(
        "[bold green]AgentProbe initialized successfully![/bold green]\n\n"
        f"  Config:     {config_path}\n"
        f"  Recordings: {cfg.recording.storage_dir}/\n"
        f"  Tests:      {cfg.testing.test_dir}/\n"
        f"  Snapshots:  .agentprobe/snapshots/\n\n"
        "Next steps:\n"
        "  1. [cyan]agentprobe record[/cyan] <your-agent-command>\n"
        "  2. [cyan]agentprobe test[/cyan]\n"
        "  3. [cyan]agentprobe dashboard[/cyan]",
        title="[bold]Setup Complete[/bold]",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("command", nargs=-1, required=True)
@click.option("--name", "-n", default=None, help="Name for this recording.")
@click.option("--tags", "-t", default=None, help="Comma-separated tags.")
@click.option("--framework", "-f", type=click.Choice(_FRAMEWORKS), default=None, help="Agent framework.")
def record(command: tuple[str, ...], name: str | None, tags: str | None, framework: str | None) -> None:
    """Record an agent execution.

    COMMAND is the shell command to run the agent (e.g. 'python run_agent.py').
    """
    cfg = _load_config()
    cmd_str = " ".join(command)
    recording_name = name or f"recording-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    fw = framework or cfg.framework

    console.print(Panel(
        f"[bold]Recording:[/bold] {cmd_str}\n"
        f"[bold]Name:[/bold]      {recording_name}\n"
        f"[bold]Framework:[/bold] {fw}\n"
        f"[bold]Tags:[/bold]      {', '.join(tag_list) or '(none)'}",
        title="[bold cyan]Recording Agent Execution[/bold cyan]",
        border_style="cyan",
    ))

    env = os.environ.copy()
    env["AGENTPROBE_RECORDING"] = "1"
    env["AGENTPROBE_RECORDING_NAME"] = recording_name
    if tag_list:
        env["AGENTPROBE_RECORDING_TAGS"] = ",".join(tag_list)
    if fw:
        env["AGENTPROBE_FRAMEWORK"] = fw

    start = time.monotonic()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Running agent...", total=None)
            result = subprocess.run(
                cmd_str,
                shell=True,
                env=env,
                capture_output=False,
            )
            progress.update(task, completed=True)
    except KeyboardInterrupt:
        console.print("\n[yellow]Recording interrupted by user.[/yellow]")
        return

    elapsed = time.monotonic() - start
    exit_code = result.returncode

    if exit_code == 0:
        console.print(f"\n[green]Agent exited successfully[/green] ({elapsed:.1f}s)")
    else:
        console.print(f"\n[red]Agent exited with code {exit_code}[/red] ({elapsed:.1f}s)")

    # Check if a recording was saved
    storage_dir = Path(cfg.recording.storage_dir)
    recordings = sorted(storage_dir.glob("*.aprobe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if recordings:
        latest = recordings[0]
        console.print(f"[green]Recording saved:[/green] {latest}")
        try:
            rec = AgentRecording.load(latest)
            console.print(
                f"  Steps: {rec.step_count}  |  "
                f"Cost: {_format_cost(rec.total_cost)}  |  "
                f"Duration: {_format_duration(rec.total_duration)}"
            )
        except Exception:
            pass
    else:
        console.print(
            "[yellow]No recording file found.[/yellow] "
            "Make sure your agent uses an AgentProbe adapter."
        )


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", required=False, default=None)
@click.option("-k", "--filter", "filter_expr", default=None, help="Filter tests by name expression.")
@click.option("--parallel", "-p", default=None, type=int, help="Number of parallel workers.")
@click.option("--max-cost", default=None, type=float, help="Maximum allowed cost in USD.")
@click.option("--ci", is_flag=True, help="Run in CI mode (non-interactive, strict).")
@click.option("--report", "report_format", type=click.Choice(["terminal", "html", "json", "markdown"]), default="terminal", help="Report format.")
@click.option("--output", "-o", "output_path", default=None, help="Output path for report file.")
@click.option("--tag", default=None, help="Only run tests matching this tag.")
def test(
    path: str | None,
    filter_expr: str | None,
    parallel: int | None,
    max_cost: float | None,
    ci: bool,
    report_format: str,
    output_path: str | None,
    tag: str | None,
) -> None:
    """Run agent tests.

    PATH is an optional path to a test file or directory. Defaults to the
    configured test directory.
    """
    cfg = _load_config()
    test_path = path or cfg.testing.test_dir
    n_workers = parallel or cfg.testing.parallel
    cost_limit = max_cost or cfg.testing.default_max_cost_usd

    if not Path(test_path).exists():
        console.print(f"[red]Test path not found:[/red] {test_path}")
        console.print("Run [cyan]agentprobe init[/cyan] first.")
        raise SystemExit(1)

    console.print(Panel(
        f"[bold]Path:[/bold]     {test_path}\n"
        f"[bold]Workers:[/bold]  {n_workers}\n"
        f"[bold]Max cost:[/bold] {_format_cost(cost_limit)}\n"
        f"[bold]Filter:[/bold]   {filter_expr or '(all)'}\n"
        f"[bold]Tag:[/bold]      {tag or '(all)'}",
        title="[bold cyan]Running Agent Tests[/bold cyan]",
        border_style="cyan",
    ))

    # Build pytest-style arguments for the test runner
    try:
        from agentprobe.core.test_runner import TestRunner
        runner = TestRunner(config=cfg)
        results = runner.run(
            path=test_path,
            filter_expr=filter_expr,
            parallel=n_workers,
            max_cost_usd=cost_limit,
            tag=tag,
        )
    except ImportError:
        # Fallback: delegate to pytest with agentprobe plugin
        console.print("[dim]Delegating to pytest...[/dim]\n")
        args = [sys.executable, "-m", "pytest", test_path, "-v"]
        if filter_expr:
            args.extend(["-k", filter_expr])
        if n_workers and n_workers > 1:
            args.extend(["-n", str(n_workers)])
        env = os.environ.copy()
        env["AGENTPROBE_MAX_COST"] = str(cost_limit)
        if ci:
            env["AGENTPROBE_CI"] = "1"
        if tag:
            env["AGENTPROBE_TAG"] = tag
        result = subprocess.run(args, env=env)
        raise SystemExit(result.returncode)

    # Generate report
    from agentprobe.reporters.terminal import TerminalReporter

    if report_format == "terminal" and not output_path:
        reporter = TerminalReporter()
        reporter.report_test_results(results)
    else:
        if report_format == "html":
            from agentprobe.reporters.html import HTMLReporter
            out = output_path or "agentprobe-report.html"
            HTMLReporter().generate_test_report(results, out)
            console.print(f"[green]HTML report written to:[/green] {out}")
        elif report_format == "json":
            from agentprobe.reporters.json_reporter import JSONReporter
            out = output_path or "agentprobe-report.json"
            JSONReporter().generate_test_report(results, out)
            console.print(f"[green]JSON report written to:[/green] {out}")
        elif report_format == "markdown":
            from agentprobe.reporters.markdown import MarkdownReporter
            out = output_path or "agentprobe-report.md"
            MarkdownReporter().generate_test_report(results, out)
            console.print(f"[green]Markdown report written to:[/green] {out}")
        else:
            reporter = TerminalReporter()
            reporter.report_test_results(results)
            if output_path:
                from agentprobe.reporters.terminal import TerminalReporter as TR
                tr = TR()
                tr.report_test_results(results)

    # Exit code
    failed = sum(1 for r in results if r.status == "fail")
    if failed > 0:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("recording")
@click.option("--model", "-m", default=None, help="Model to use for replay.")
@click.option("--system-prompt", default=None, help="Override system prompt.")
@click.option("--mock-tools", is_flag=True, help="Mock tool calls instead of executing them.")
@click.option("--compare", is_flag=True, help="Show comparison between original and replay.")
def replay(recording: str, model: str | None, system_prompt: str | None, mock_tools: bool, compare: bool) -> None:
    """Replay a recording, optionally with different settings.

    RECORDING is the path or ID of a recording file.
    """
    rec_path = Path(recording)
    if not rec_path.exists():
        # Try to find by name in storage dir
        cfg = _load_config()
        candidates = list(Path(cfg.recording.storage_dir).glob(f"**/*{recording}*"))
        if not candidates:
            console.print(f"[red]Recording not found:[/red] {recording}")
            raise SystemExit(1)
        rec_path = candidates[0]

    console.print(Panel(
        f"[bold]Recording:[/bold]    {rec_path}\n"
        f"[bold]Model:[/bold]        {model or '(original)'}\n"
        f"[bold]Mock tools:[/bold]   {'yes' if mock_tools else 'no'}\n"
        f"[bold]System prompt:[/bold] {'(override)' if system_prompt else '(original)'}",
        title="[bold cyan]Replaying Recording[/bold cyan]",
        border_style="cyan",
    ))

    original = AgentRecording.load(rec_path)

    try:
        from agentprobe.core.replayer import Replayer, ReplayConfig

        replay_cfg = ReplayConfig(
            model=model or original.environment.model,
            system_prompt=system_prompt or original.environment.system_prompt,
            mock_tools=mock_tools,
        )
        replayer = Replayer(config=replay_cfg)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Replaying...", total=None)
            replay_result = replayer.replay(original)
            progress.update(task, completed=True)

        from agentprobe.reporters.terminal import TerminalReporter
        reporter = TerminalReporter()

        if compare:
            reporter.report_comparison({
                "original": original,
                "replay": replay_result,
            })
        else:
            reporter.report_recording(replay_result)

    except ImportError:
        console.print("[yellow]Replayer module not available.[/yellow]")
        console.print("Showing original recording instead:\n")
        from agentprobe.reporters.terminal import TerminalReporter
        TerminalReporter().report_recording(original)


# ---------------------------------------------------------------------------
# recordings (group)
# ---------------------------------------------------------------------------

@cli.group()
def recordings() -> None:
    """Manage agent recordings."""
    pass


@recordings.command("list")
@click.option("--tag", default=None, help="Filter by tag.")
@click.option("--after", default=None, help="Show recordings after this date (YYYY-MM-DD).")
@click.option("--before", default=None, help="Show recordings before this date (YYYY-MM-DD).")
@click.option("--limit", "-n", default=20, help="Maximum number of recordings to show.")
def recordings_list(tag: str | None, after: str | None, before: str | None, limit: int) -> None:
    """List recorded agent executions."""
    cfg = _load_config()
    storage_dir = Path(cfg.recording.storage_dir)
    if not storage_dir.exists():
        console.print("[yellow]No recordings directory found.[/yellow] Run [cyan]agentprobe init[/cyan] first.")
        return

    paths = sorted(storage_dir.glob("**/*.aprobe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not paths:
        console.print("[yellow]No recordings found.[/yellow]")
        return

    recordings_data: list[dict[str, Any]] = []
    for p in paths:
        try:
            rec = AgentRecording.load(p)
            meta = rec.metadata
            ts = meta.timestamp

            # Date filters
            if after:
                after_dt = datetime.fromisoformat(after).replace(tzinfo=timezone.utc)
                if ts < after_dt:
                    continue
            if before:
                before_dt = datetime.fromisoformat(before).replace(tzinfo=timezone.utc)
                if ts > before_dt:
                    continue
            # Tag filter
            if tag and tag not in meta.tags:
                continue

            recordings_data.append({
                "id": meta.id[:8],
                "name": meta.name or p.stem,
                "framework": meta.agent_framework or "-",
                "model": rec.environment.model or "-",
                "status": rec.output.status.value if rec.output else "-",
                "cost": rec.total_cost,
                "duration": rec.total_duration,
                "date": ts.strftime("%Y-%m-%d %H:%M"),
                "tags": meta.tags,
                "path": str(p),
            })
        except Exception:
            continue

    if not recordings_data:
        console.print("[yellow]No recordings match the given filters.[/yellow]")
        return

    recordings_data = recordings_data[:limit]

    from agentprobe.reporters.terminal import TerminalReporter
    TerminalReporter().report_recordings_list(recordings_data)


@recordings.command("inspect")
@click.argument("recording")
def recordings_inspect(recording: str) -> None:
    """Inspect a recording in detail."""
    rec_path = Path(recording)
    if not rec_path.exists():
        cfg = _load_config()
        candidates = list(Path(cfg.recording.storage_dir).glob(f"**/*{recording}*"))
        if not candidates:
            console.print(f"[red]Recording not found:[/red] {recording}")
            raise SystemExit(1)
        rec_path = candidates[0]

    rec = AgentRecording.load(rec_path)
    from agentprobe.reporters.terminal import TerminalReporter
    TerminalReporter().report_recording(rec)


@recordings.command("export")
@click.argument("recording")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml"]), default="json", help="Export format.")
def recordings_export(recording: str, fmt: str) -> None:
    """Export a recording to JSON or YAML."""
    rec_path = Path(recording)
    if not rec_path.exists():
        cfg = _load_config()
        candidates = list(Path(cfg.recording.storage_dir).glob(f"**/*{recording}*"))
        if not candidates:
            console.print(f"[red]Recording not found:[/red] {recording}")
            raise SystemExit(1)
        rec_path = candidates[0]

    rec = AgentRecording.load(rec_path)
    data = rec.to_dict()

    if fmt == "json":
        output = json.dumps(data, indent=2, default=str)
    else:
        import yaml
        output = yaml.safe_dump(data, default_flow_style=False, sort_keys=False)

    console.print(output)


# ---------------------------------------------------------------------------
# analyze (group)
# ---------------------------------------------------------------------------

@cli.group()
def analyze() -> None:
    """Analyze recordings for cost, latency, and failures."""
    pass


@analyze.command("cost")
@click.option("--group-by", "group_by", type=click.Choice(["model", "framework", "tag", "date"]), default="model", help="Group cost analysis by dimension.")
def analyze_cost(group_by: str) -> None:
    """Analyze cost across recordings."""
    cfg = _load_config()
    storage_dir = Path(cfg.recording.storage_dir)
    paths = sorted(storage_dir.glob("**/*.aprobe"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not paths:
        console.print("[yellow]No recordings found.[/yellow]")
        return

    groups: dict[str, list[float]] = {}
    total_cost = 0.0

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Analyzing costs...", total=len(paths))
        for p in paths:
            try:
                rec = AgentRecording.load(p)
                cost = rec.total_cost
                total_cost += cost

                if group_by == "model":
                    key = rec.environment.model or "unknown"
                elif group_by == "framework":
                    key = rec.metadata.agent_framework or "unknown"
                elif group_by == "tag":
                    for t in (rec.metadata.tags or ["untagged"]):
                        groups.setdefault(t, []).append(cost)
                    progress.advance(task)
                    continue
                else:  # date
                    key = rec.metadata.timestamp.strftime("%Y-%m-%d")

                groups.setdefault(key, []).append(cost)
            except Exception:
                pass
            progress.advance(task)

    table = Table(title=f"Cost Analysis (grouped by {group_by})")
    table.add_column("Group", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Total Cost", justify="right", style="yellow")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")

    for key in sorted(groups):
        costs = groups[key]
        table.add_row(
            key,
            str(len(costs)),
            _format_cost(sum(costs)),
            _format_cost(sum(costs) / len(costs)),
            _format_cost(min(costs)),
            _format_cost(max(costs)),
        )

    console.print(table)
    console.print(f"\n[bold]Total cost across all recordings:[/bold] [yellow]{_format_cost(total_cost)}[/yellow]")


@analyze.command("latency")
@click.option("--percentiles", default="50,90,95,99", help="Comma-separated percentiles to calculate.")
def analyze_latency(percentiles: str) -> None:
    """Analyze latency across recordings."""
    cfg = _load_config()
    storage_dir = Path(cfg.recording.storage_dir)
    paths = sorted(storage_dir.glob("**/*.aprobe"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not paths:
        console.print("[yellow]No recordings found.[/yellow]")
        return

    pcts = [int(p.strip()) for p in percentiles.split(",")]
    durations: list[float] = []
    step_durations: list[float] = []
    llm_latencies: list[float] = []

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Analyzing latency...", total=len(paths))
        for p in paths:
            try:
                rec = AgentRecording.load(p)
                durations.append(rec.total_duration)
                for step in rec.steps:
                    step_durations.append(step.duration_ms)
                    if step.llm_call:
                        llm_latencies.append(step.llm_call.latency_ms)
            except Exception:
                pass
            progress.advance(task)

    def calc_percentile(data: list[float], p: int) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    table = Table(title="Latency Analysis")
    table.add_column("Metric", style="cyan")
    for p in pcts:
        table.add_column(f"p{p}", justify="right")
    table.add_column("Mean", justify="right", style="yellow")

    for label, data in [
        ("Total Duration", durations),
        ("Step Duration", step_durations),
        ("LLM Latency", llm_latencies),
    ]:
        if not data:
            continue
        row = [label]
        for p in pcts:
            row.append(_format_duration(calc_percentile(data, p)))
        mean = sum(data) / len(data)
        row.append(_format_duration(mean))
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[bold]Recordings analyzed:[/bold] {len(durations)}")


@analyze.command("failures")
@click.option("--classify", is_flag=True, help="Classify failures by type.")
def analyze_failures(classify: bool) -> None:
    """Analyze failures across recordings."""
    cfg = _load_config()
    storage_dir = Path(cfg.recording.storage_dir)
    paths = sorted(storage_dir.glob("**/*.aprobe"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not paths:
        console.print("[yellow]No recordings found.[/yellow]")
        return

    failures: list[dict[str, Any]] = []
    total = 0

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Analyzing failures...", total=len(paths))
        for p in paths:
            try:
                rec = AgentRecording.load(p)
                total += 1
                if rec.output.status.value != "success":
                    error_type = "unknown"
                    error_msg = rec.output.error or ""
                    if classify:
                        if "timeout" in error_msg.lower():
                            error_type = "timeout"
                        elif "rate" in error_msg.lower() or "429" in error_msg:
                            error_type = "rate_limit"
                        elif "auth" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
                            error_type = "auth_error"
                        elif "tool" in error_msg.lower():
                            error_type = "tool_error"
                        elif "context" in error_msg.lower() or "token" in error_msg.lower():
                            error_type = "context_overflow"
                        else:
                            error_type = "other"
                    failures.append({
                        "name": rec.metadata.name or p.stem,
                        "id": rec.metadata.id[:8],
                        "error": error_msg[:100] or rec.output.status.value,
                        "type": error_type,
                        "date": rec.metadata.timestamp.strftime("%Y-%m-%d %H:%M"),
                        "model": rec.environment.model or "-",
                    })
            except Exception:
                pass
            progress.advance(task)

    if not failures:
        console.print(f"[green]No failures found across {total} recordings.[/green]")
        return

    if classify:
        # Show classification summary first
        type_counts: dict[str, int] = {}
        for f in failures:
            type_counts[f["type"]] = type_counts.get(f["type"], 0) + 1

        summary_table = Table(title="Failure Classification")
        summary_table.add_column("Type", style="cyan")
        summary_table.add_column("Count", justify="right", style="red")
        summary_table.add_column("Percentage", justify="right")
        for ftype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            pct = count / len(failures) * 100
            summary_table.add_row(ftype, str(count), f"{pct:.1f}%")
        console.print(summary_table)
        console.print()

    table = Table(title=f"Failures ({len(failures)}/{total} recordings)")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Model")
    if classify:
        table.add_column("Type", style="yellow")
    table.add_column("Error", style="red")
    table.add_column("Date", style="dim")

    for f in failures:
        row = [f["id"], f["name"], f["model"]]
        if classify:
            row.append(f["type"])
        row.extend([f["error"], f["date"]])
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[bold]Failure rate:[/bold] [red]{len(failures)}/{total}[/red] ({len(failures)/total*100:.1f}%)")


# ---------------------------------------------------------------------------
# snapshot (group)
# ---------------------------------------------------------------------------

@cli.group()
def snapshot() -> None:
    """Manage performance snapshots for regression detection."""
    pass


@snapshot.command("create")
@click.option("--name", required=True, help="Name for this snapshot.")
@click.option("--recordings", "recordings_glob", default=None, help="Glob pattern to select recordings.")
def snapshot_create(name: str, recordings_glob: str | None) -> None:
    """Create a performance snapshot from current recordings."""
    cfg = _load_config()
    storage_dir = Path(cfg.recording.storage_dir)
    snapshot_dir = Path(".agentprobe/snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    pattern = recordings_glob or "**/*.aprobe"
    paths = list(storage_dir.glob(pattern))

    if not paths:
        console.print("[yellow]No recordings match the pattern.[/yellow]")
        return

    snapshot_data: dict[str, Any] = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recording_count": len(paths),
        "metrics": {
            "costs": [],
            "durations": [],
            "step_counts": [],
            "models": {},
        },
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        console=console,
    ) as progress:
        task = progress.add_task("Building snapshot...", total=len(paths))
        for p in paths:
            try:
                rec = AgentRecording.load(p)
                snapshot_data["metrics"]["costs"].append(rec.total_cost)
                snapshot_data["metrics"]["durations"].append(rec.total_duration)
                snapshot_data["metrics"]["step_counts"].append(rec.step_count)
                model = rec.environment.model or "unknown"
                snapshot_data["metrics"]["models"][model] = snapshot_data["metrics"]["models"].get(model, 0) + 1
            except Exception:
                pass
            progress.advance(task)

    # Compute summary stats
    costs = snapshot_data["metrics"]["costs"]
    durations = snapshot_data["metrics"]["durations"]
    snapshot_data["summary"] = {
        "avg_cost": sum(costs) / len(costs) if costs else 0,
        "avg_duration": sum(durations) / len(durations) if durations else 0,
        "total_cost": sum(costs),
        "p95_cost": sorted(costs)[int(len(costs) * 0.95)] if costs else 0,
        "p95_duration": sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
    }

    snapshot_path = snapshot_dir / f"{name}.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot_data, f, indent=2, default=str)

    console.print(Panel(
        f"[bold green]Snapshot created:[/bold green] {snapshot_path}\n"
        f"  Recordings: {len(paths)}\n"
        f"  Avg cost:   {_format_cost(snapshot_data['summary']['avg_cost'])}\n"
        f"  Avg time:   {_format_duration(snapshot_data['summary']['avg_duration'])}\n"
        f"  p95 cost:   {_format_cost(snapshot_data['summary']['p95_cost'])}\n"
        f"  p95 time:   {_format_duration(snapshot_data['summary']['p95_duration'])}",
        title=f"[bold]Snapshot: {name}[/bold]",
        border_style="green",
    ))


@snapshot.command("check")
@click.option("--baseline", required=True, help="Path to baseline snapshot for comparison.")
def snapshot_check(baseline: str) -> None:
    """Check current recordings against a baseline snapshot."""
    baseline_path = Path(baseline)
    if not baseline_path.exists():
        baseline_path = Path(".agentprobe/snapshots") / f"{baseline}.json"
    if not baseline_path.exists():
        console.print(f"[red]Baseline not found:[/red] {baseline}")
        raise SystemExit(1)

    with open(baseline_path) as f:
        baseline_data = json.load(f)

    cfg = _load_config()
    thresholds = cfg.ci.thresholds

    # Build current snapshot
    storage_dir = Path(cfg.recording.storage_dir)
    paths = list(storage_dir.glob("**/*.aprobe"))
    current_costs: list[float] = []
    current_durations: list[float] = []

    for p in paths:
        try:
            rec = AgentRecording.load(p)
            current_costs.append(rec.total_cost)
            current_durations.append(rec.total_duration)
        except Exception:
            continue

    if not current_costs:
        console.print("[yellow]No current recordings to compare.[/yellow]")
        return

    current_avg_cost = sum(current_costs) / len(current_costs)
    current_avg_dur = sum(current_durations) / len(current_durations)
    baseline_avg_cost = baseline_data["summary"]["avg_cost"]
    baseline_avg_dur = baseline_data["summary"]["avg_duration"]

    cost_change_pct = ((current_avg_cost - baseline_avg_cost) / baseline_avg_cost * 100) if baseline_avg_cost > 0 else 0
    dur_change_pct = ((current_avg_dur - baseline_avg_dur) / baseline_avg_dur * 100) if baseline_avg_dur > 0 else 0

    cost_threshold = thresholds.get("cost_increase_pct", 20.0)
    latency_threshold = thresholds.get("latency_increase_pct", 20.0)

    cost_ok = cost_change_pct <= cost_threshold
    dur_ok = dur_change_pct <= latency_threshold

    table = Table(title="Snapshot Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Status", justify="center")

    cost_style = "green" if cost_ok else "red"
    dur_style = "green" if dur_ok else "red"

    table.add_row(
        "Avg Cost",
        _format_cost(baseline_avg_cost),
        _format_cost(current_avg_cost),
        f"[{cost_style}]{cost_change_pct:+.1f}%[/{cost_style}]",
        f"+{cost_threshold:.0f}%",
        "[green]PASS[/green]" if cost_ok else "[red]FAIL[/red]",
    )
    table.add_row(
        "Avg Duration",
        _format_duration(baseline_avg_dur),
        _format_duration(current_avg_dur),
        f"[{dur_style}]{dur_change_pct:+.1f}%[/{dur_style}]",
        f"+{latency_threshold:.0f}%",
        "[green]PASS[/green]" if dur_ok else "[red]FAIL[/red]",
    )

    console.print(table)

    if not cost_ok or not dur_ok:
        console.print("\n[red bold]Regression detected![/red bold]")
        raise SystemExit(1)
    else:
        console.print("\n[green bold]All metrics within thresholds.[/green bold]")


@snapshot.command("list")
def snapshot_list() -> None:
    """List available snapshots."""
    snapshot_dir = Path(".agentprobe/snapshots")
    if not snapshot_dir.exists():
        console.print("[yellow]No snapshots directory found.[/yellow]")
        return

    paths = sorted(snapshot_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not paths:
        console.print("[yellow]No snapshots found.[/yellow]")
        return

    table = Table(title="Performance Snapshots")
    table.add_column("Name", style="cyan")
    table.add_column("Created", style="dim")
    table.add_column("Recordings", justify="right")
    table.add_column("Avg Cost", justify="right", style="yellow")
    table.add_column("Avg Duration", justify="right")

    for p in paths:
        try:
            with open(p) as f:
                data = json.load(f)
            table.add_row(
                data.get("name", p.stem),
                data.get("created_at", "-")[:19],
                str(data.get("recording_count", 0)),
                _format_cost(data.get("summary", {}).get("avg_cost", 0)),
                _format_duration(data.get("summary", {}).get("avg_duration", 0)),
            )
        except Exception:
            table.add_row(p.stem, "-", "-", "-", "-")

    console.print(table)


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--port", "-p", default=None, type=int, help="Port to run the dashboard on.")
def dashboard(port: int | None) -> None:
    """Launch the local AgentProbe dashboard."""
    cfg = _load_config()
    dash_port = port or cfg.dashboard.port
    dash_host = cfg.dashboard.host

    console.print(Panel(
        f"[bold cyan]AgentProbe Dashboard[/bold cyan]\n\n"
        f"  URL: [link]http://{dash_host}:{dash_port}[/link]\n\n"
        "  Press [bold]Ctrl+C[/bold] to stop.",
        border_style="cyan",
    ))

    try:
        from agentprobe.dashboard.server import create_app
        app = create_app(cfg)
        import uvicorn
        uvicorn.run(app, host=dash_host, port=dash_port, log_level="info")
    except ImportError:
        console.print(
            "[yellow]Dashboard dependencies not installed.[/yellow]\n"
            "Install with: [cyan]pip install agentprobe[dashboard][/cyan]"
        )
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# roast
# ---------------------------------------------------------------------------

from agentprobe.roast.cli import roast_command  # noqa: E402

cli.add_command(roast_command, "roast")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the agentprobe CLI."""
    cli()


if __name__ == "__main__":
    main()
