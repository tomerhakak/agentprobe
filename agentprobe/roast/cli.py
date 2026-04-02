"""CLI command for ``agentprobe roast``."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from agentprobe.roast.roaster import (
    Roaster,
    RoastLevel,
    RoastReport,
    format_terminal_report,
)

console = Console()
err_console = Console(stderr=True)


def _run_agent_script(script_path: str) -> Path:
    """Execute an agent script and capture an AgentProbe recording.

    If the script itself produces a ``.aprobe`` or ``.json`` recording file, we
    use that.  Otherwise we attempt to run the script via ``agentprobe record``
    and capture output.
    """
    script = Path(script_path).resolve()
    if not script.exists():
        raise click.BadParameter(f"Agent script not found: {script}")

    # Convention: look for a recording file produced in the same directory.
    possible_recording = script.with_suffix(".aprobe")
    if possible_recording.exists():
        return possible_recording

    # Attempt to run via agentprobe record (best-effort).
    tmp_dir = Path(tempfile.mkdtemp(prefix="agentprobe_roast_"))
    output_path = tmp_dir / "recording.aprobe"

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "agentprobe",
                "record",
                str(script),
                "--output",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise click.ClickException(
            f"Could not produce a recording from '{script}'. "
            f"Please provide a pre-recorded trace via --recording instead.\n"
            f"Error: {exc}"
        ) from exc

    if not output_path.exists():
        raise click.ClickException(
            f"Recording was not created at {output_path}. "
            f"Try providing a pre-recorded trace via --recording."
        )
    return output_path


@click.command("roast")
@click.argument("target", required=False, default=None)
@click.option(
    "--recording",
    "-r",
    type=click.Path(exists=True),
    default=None,
    help="Path to a pre-recorded trace (.aprobe or .json).",
)
@click.option(
    "--level",
    "-l",
    type=click.Choice(["mild", "medium", "savage"], case_sensitive=False),
    default="medium",
    help="Roast severity level (default: medium).",
)
@click.option(
    "--json-output",
    "-j",
    is_flag=True,
    default=False,
    help="Output the roast report as JSON instead of the terminal report.",
)
@click.pass_context
def roast_command(
    ctx: click.Context,
    target: Optional[str],
    recording: Optional[str],
    level: str,
    json_output: bool,
) -> None:
    """Roast your AI agent with a brutally honest (and funny) evaluation.

    \b
    Examples:
      agentprobe roast my_agent.py
      agentprobe roast my_agent.py --level savage
      agentprobe roast --recording trace.json
      agentprobe roast --recording trace.aprobe --level mild --json-output
    """
    roast_level = RoastLevel(level.lower())

    # Resolve the recording path.
    recording_path: Optional[Path] = None

    if recording:
        recording_path = Path(recording).resolve()
    elif target:
        target_path = Path(target).resolve()
        # If the target is already a recording file, use it directly.
        if target_path.suffix in (".aprobe", ".json"):
            if not target_path.exists():
                raise click.ClickException(f"File not found: {target_path}")
            recording_path = target_path
        else:
            # Treat it as an agent script to run.
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]Running agent script..."),
                console=err_console,
                transient=True,
            ) as progress:
                progress.add_task("run", total=None)
                recording_path = _run_agent_script(target)
    else:
        raise click.UsageError(
            "Provide an agent script or use --recording to specify a trace file.\n"
            "Example: agentprobe roast my_agent.py\n"
            "         agentprobe roast --recording trace.json"
        )

    # Run the roast.
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Roasting your agent..."),
        console=err_console,
        transient=True,
    ) as progress:
        progress.add_task("roast", total=None)
        report = Roaster.roast_recording_file(recording_path, level=roast_level)

    # Output.
    if json_output:
        console.print_json(json.dumps(report.to_dict(), indent=2))
    else:
        console.print(format_terminal_report(report))
