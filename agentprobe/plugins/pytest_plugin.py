"""Pytest plugin for AgentProbe -- provides fixtures, markers, and HTML reporting.

Register this plugin automatically via ``pyproject.toml``::

    [project.entry-points."pytest11"]
    agentprobe = "agentprobe.plugins.pytest_plugin"

Or load it manually in ``conftest.py``::

    pytest_plugins = ["agentprobe.plugins.pytest_plugin"]
"""

from __future__ import annotations

import html
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import pytest

from agentprobe.core.asserter import AssertionError, AssertionResult, Assertions
from agentprobe.core.models import AgentRecording


# ---------------------------------------------------------------------------
# Plugin registration helpers
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers and command-line options."""
    config.addinivalue_line(
        "markers",
        "agentprobe(recording): mark a test as an AgentProbe test with an optional recording path or object",
    )
    config.addinivalue_line(
        "markers",
        "agentprobe_tag(*tags): tag an AgentProbe test for selective execution",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add AgentProbe CLI options."""
    group = parser.getgroup("agentprobe", "AgentProbe options")
    group.addoption(
        "--agentprobe-report",
        action="store",
        default=None,
        metavar="PATH",
        help="Generate an AgentProbe HTML report at PATH",
    )
    group.addoption(
        "--agentprobe-tag",
        action="append",
        default=[],
        metavar="TAG",
        help="Only run AgentProbe tests with the given tag (repeatable)",
    )


# ---------------------------------------------------------------------------
# Collection hook -- auto-discover test_agent_*.py files
# ---------------------------------------------------------------------------

def pytest_collect_file(
    parent: pytest.Collector,
    file_path: Path,
) -> pytest.Module | None:
    """Auto-collect test files matching ``test_agent_*.py``."""
    if file_path.suffix == ".py" and file_path.name.startswith("test_agent_"):
        return pytest.Module.from_parent(parent, path=file_path)
    return None


# ---------------------------------------------------------------------------
# Tag filtering
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Filter tests by ``--agentprobe-tag`` if specified."""
    required_tags = config.getoption("--agentprobe-tag", default=[])
    if not required_tags:
        return

    tag_set = set(required_tags)
    remaining: list[pytest.Item] = []
    deselected: list[pytest.Item] = []

    for item in items:
        marker = item.get_closest_marker("agentprobe_tag")
        if marker is not None:
            item_tags = set(marker.args)
            if item_tags & tag_set:
                remaining.append(item)
            else:
                deselected.append(item)
        else:
            # Non-agentprobe tests are kept
            remaining.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agentprobe_recording(request: pytest.FixtureRequest) -> AgentRecording | None:
    """Provide an :class:`AgentRecording` loaded from the ``@pytest.mark.agentprobe``
    marker, or ``None`` if no recording is specified.

    Usage::

        @pytest.mark.agentprobe(recording="path/to/recording.aprobe")
        def test_my_agent(agentprobe_recording):
            assert agentprobe_recording is not None
    """
    marker = request.node.get_closest_marker("agentprobe")
    if marker is None:
        return None

    recording_arg = marker.kwargs.get("recording", None)
    if recording_arg is None and marker.args:
        recording_arg = marker.args[0]

    if recording_arg is None:
        return None

    if isinstance(recording_arg, AgentRecording):
        return recording_arg

    if isinstance(recording_arg, (str, Path)):
        path = Path(recording_arg)
        if not path.is_absolute():
            # Resolve relative to the test file
            test_dir = Path(request.fspath).parent  # type: ignore[arg-type]
            path = test_dir / path
        return AgentRecording.load(path)

    return None


@pytest.fixture
def A(agentprobe_recording: AgentRecording | None) -> Assertions:
    """Provide a fresh :class:`Assertions` instance pre-loaded with the
    recording from the ``agentprobe`` marker (if any).

    Usage::

        @pytest.mark.agentprobe(recording="recording.aprobe")
        def test_output(A):
            A.output_contains("hello")
            A.completed_successfully()
    """
    a = Assertions()
    if agentprobe_recording is not None:
        a.set_recording(agentprobe_recording)
    return a


# ---------------------------------------------------------------------------
# Session-level result collection for reporting
# ---------------------------------------------------------------------------

_collected_results: list[dict[str, Any]] = []


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any, None]:
    """Collect test results for the AgentProbe HTML report."""
    outcome = yield
    report = outcome.get_result()

    if call.when != "call":
        return

    result_entry: dict[str, Any] = {
        "name": item.nodeid,
        "passed": report.passed,
        "duration_ms": (call.duration if call.duration else 0) * 1000,
        "error": None,
        "assertion_results": [],
    }

    if report.failed:
        result_entry["passed"] = False
        if call.excinfo is not None:
            result_entry["error"] = str(call.excinfo.value)

    _collected_results.append(result_entry)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Generate the HTML report if ``--agentprobe-report`` was specified."""
    report_path = session.config.getoption("--agentprobe-report", default=None)
    if report_path is None:
        return

    _generate_html_report(Path(report_path), _collected_results)
    _collected_results.clear()


# ---------------------------------------------------------------------------
# HTML report generator
# ---------------------------------------------------------------------------

def _generate_html_report(path: Path, results: list[dict[str, Any]]) -> None:
    """Write a self-contained HTML report summarising test results."""
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    total_duration = sum(r["duration_ms"] for r in results)
    timestamp = datetime.now(timezone.utc).isoformat()

    rows = ""
    for r in results:
        status_class = "pass" if r["passed"] else "fail"
        status_label = "PASS" if r["passed"] else "FAIL"
        error_html = f'<pre class="error">{html.escape(r["error"])}</pre>' if r.get("error") else ""
        rows += f"""
        <tr class="{status_class}">
            <td>{html.escape(r['name'])}</td>
            <td class="status">{status_label}</td>
            <td>{r['duration_ms']:.1f}ms</td>
            <td>{error_html}</td>
        </tr>"""

    report_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AgentProbe Test Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
  h1 {{ color: #58a6ff; }}
  .summary {{ display: flex; gap: 24px; margin-bottom: 24px; }}
  .summary .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
                    padding: 16px 24px; }}
  .summary .card .value {{ font-size: 28px; font-weight: bold; }}
  .summary .card .label {{ color: #8b949e; font-size: 13px; }}
  .pass .value {{ color: #3fb950; }}
  .fail .value {{ color: #f85149; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22;
           border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
  th {{ background: #21262d; text-align: left; padding: 12px 16px; color: #8b949e;
        font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }}
  td {{ padding: 12px 16px; border-top: 1px solid #21262d; }}
  tr.pass .status {{ color: #3fb950; font-weight: bold; }}
  tr.fail .status {{ color: #f85149; font-weight: bold; }}
  pre.error {{ background: #1c1017; color: #f85149; padding: 8px 12px; border-radius: 4px;
               font-size: 12px; overflow-x: auto; margin: 4px 0 0; white-space: pre-wrap; }}
  .timestamp {{ color: #484f58; font-size: 12px; margin-top: 16px; }}
</style>
</head>
<body>
<h1>AgentProbe Test Report</h1>

<div class="summary">
  <div class="card">
    <div class="value">{total}</div>
    <div class="label">Total</div>
  </div>
  <div class="card pass">
    <div class="value">{passed}</div>
    <div class="label">Passed</div>
  </div>
  <div class="card fail">
    <div class="value">{failed}</div>
    <div class="label">Failed</div>
  </div>
  <div class="card">
    <div class="value">{total_duration:.0f}ms</div>
    <div class="label">Duration</div>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>Test</th>
      <th>Status</th>
      <th>Duration</th>
      <th>Details</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>

<p class="timestamp">Generated at {timestamp} by AgentProbe</p>
</body>
</html>
"""
    path.write_text(report_html, encoding="utf-8")
