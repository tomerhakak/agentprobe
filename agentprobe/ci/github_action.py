"""GitHub Action integration — generates workflow configs and runs AgentProbe tests in CI.

This module provides:
- ``GitHubActionConfig``: typed configuration matching the action.yml inputs.
- ``GitHubActionRunner``: orchestrates test execution, result formatting,
  and PR comment posting inside a GitHub Actions environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_cost(cost: float) -> str:
    """Format a USD cost value for display."""
    return f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}"


def _fmt_duration(ms: float) -> str:
    """Format milliseconds into a human-friendly string."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    secs = ms / 1000
    if secs < 60:
        return f"{secs:.1f}s"
    return f"{secs / 60:.1f}m"


def _status_icon(passed: bool) -> str:
    return "\u2705" if passed else "\u274c"


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Retrieve an attribute from an object or dict uniformly."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _gh_output(name: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_OUTPUT (Actions output file).

    Falls back to the deprecated ``::set-output`` command when the env var
    is not available (e.g. local testing).
    """
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        try:
            with open(output_file, "a", encoding="utf-8") as fh:
                fh.write(f"{name}={value}\n")
            return
        except OSError:
            pass
    # Fallback for older runners / local testing
    print(f"::set-output name={name}::{value}")


def _gh_summary(markdown: str) -> None:
    """Append Markdown content to $GITHUB_STEP_SUMMARY.

    Silently no-ops when the env var is absent (local runs).
    """
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as fh:
                fh.write(markdown + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class GitHubActionConfig:
    """Typed representation of the action.yml inputs.

    Each field maps 1:1 to an input declared in ``action.yml``.  When
    running inside GitHub Actions the values are read from environment
    variables (``INPUT_<NAME>``); otherwise sensible defaults are used.
    """

    test_dir: str = "tests/"
    assertions: str = ""
    cost_limit: float = 5.0
    fail_on_warning: bool = False
    model: str = ""

    # Internal / derived
    workspace: str = ""
    event_name: str = ""
    repository: str = ""
    pr_number: int = 0
    github_token: str = ""

    @classmethod
    def from_environment(cls) -> GitHubActionConfig:
        """Build configuration from GitHub Actions ``INPUT_*`` environment variables."""
        cost_raw = os.environ.get("INPUT_COST-LIMIT", os.environ.get("INPUT_COST_LIMIT", "5.0"))
        try:
            cost_limit = float(cost_raw)
        except (ValueError, TypeError):
            cost_limit = 5.0

        fail_on_warning_raw = os.environ.get(
            "INPUT_FAIL-ON-WARNING",
            os.environ.get("INPUT_FAIL_ON_WARNING", "false"),
        )
        fail_on_warning = fail_on_warning_raw.lower() in ("true", "1", "yes")

        pr_number = 0
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        if event_path:
            try:
                with open(event_path, "r", encoding="utf-8") as fh:
                    event_data = json.load(fh)
                pr_number = int(
                    event_data.get("pull_request", {}).get("number", 0)
                )
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass

        return cls(
            test_dir=os.environ.get("INPUT_TEST-DIR", os.environ.get("INPUT_TEST_DIR", "tests/")),
            assertions=os.environ.get("INPUT_ASSERTIONS", ""),
            cost_limit=cost_limit,
            fail_on_warning=fail_on_warning,
            model=os.environ.get("INPUT_MODEL", ""),
            workspace=os.environ.get("GITHUB_WORKSPACE", os.getcwd()),
            event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            pr_number=pr_number,
            github_token=os.environ.get("INPUT_GITHUB-TOKEN", os.environ.get("INPUT_GITHUB_TOKEN", "")),
        )


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """Lightweight container for a single test outcome."""

    name: str = "unknown"
    passed: bool = False
    status: str = "fail"
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    error: str = ""
    assertions_run: int = 0
    assertions_passed: int = 0


@dataclass
class RunSummary:
    """Aggregate results for a full AgentProbe test run."""

    results: List[TestResult] = field(default_factory=list)
    total_cost: float = 0.0
    total_duration_ms: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    exit_code: int = 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class GitHubActionRunner:
    """Orchestrates AgentProbe test execution inside a GitHub Actions workflow.

    Typical usage from the action's ``entrypoint``::

        config = GitHubActionConfig.from_environment()
        runner = GitHubActionRunner(config)
        exit_code = runner.run()
        sys.exit(exit_code)
    """

    def __init__(self, config: GitHubActionConfig) -> None:
        self.config = config

    # -- Public API ---------------------------------------------------------

    def run(self) -> int:
        """Execute the full CI pipeline and return an exit code (0 = success)."""
        print("::group::AgentProbe Setup")
        self._log_config()
        print("::endgroup::")

        print("::group::AgentProbe Test Execution")
        summary = self._run_tests()
        print("::endgroup::")

        print("::group::AgentProbe Results")
        self._emit_annotations(summary)
        self._set_outputs(summary)
        comment_body = self._build_pr_comment(summary)
        _gh_summary(comment_body)
        print("::endgroup::")

        # Post PR comment when running on a pull_request event
        if self.config.pr_number and self.config.github_token:
            self._post_pr_comment(comment_body)

        # Write report artifacts
        self._write_artifacts(summary, comment_body)

        return summary.exit_code

    # -- Internals ----------------------------------------------------------

    def _log_config(self) -> None:
        """Print the resolved configuration for debugging."""
        print(f"  test-dir:        {self.config.test_dir}")
        print(f"  assertions:      {self.config.assertions or '(all)'}")
        print(f"  cost-limit:      ${self.config.cost_limit:.2f}")
        print(f"  fail-on-warning: {self.config.fail_on_warning}")
        print(f"  model:           {self.config.model or '(default)'}")
        print(f"  workspace:       {self.config.workspace}")

    def _run_tests(self) -> RunSummary:
        """Invoke ``agentprobe test`` as a subprocess and parse results."""
        started_at = datetime.now(timezone.utc).isoformat()

        cmd: List[str] = [
            sys.executable, "-m", "agentprobe", "test",
            "--test-dir", self.config.test_dir,
            "--ci",
            "--json-report", "/tmp/agentprobe-results.json",
        ]

        if self.config.model:
            cmd.extend(["--model", self.config.model])

        if self.config.assertions:
            for assertion in self.config.assertions.split(","):
                assertion = assertion.strip()
                if assertion:
                    cmd.extend(["--assertion", assertion])

        if self.config.cost_limit > 0:
            cmd.extend(["--cost-budget", str(self.config.cost_limit)])

        env = {**os.environ, "AGENTPROBE_CI": "true"}

        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute hard cap
                cwd=self.config.workspace,
                env=env,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = "AgentProbe test run timed out after 30 minutes."
            returncode = 2
        except FileNotFoundError:
            stdout = ""
            stderr = (
                "agentprobe CLI not found. Ensure agentprobe is installed:\n"
                "  pip install agentprobe"
            )
            returncode = 2

        elapsed_ms = (time.monotonic() - start_time) * 1000
        finished_at = datetime.now(timezone.utc).isoformat()

        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)

        # Parse JSON report if available
        results = self._parse_json_report("/tmp/agentprobe-results.json")

        # Fallback: synthesise a single result when no JSON report was produced
        if not results:
            results = [
                TestResult(
                    name="agentprobe-run",
                    passed=returncode == 0,
                    status="pass" if returncode == 0 else "error",
                    duration_ms=elapsed_ms,
                    error=stderr if returncode != 0 else "",
                ),
            ]

        total_cost = sum(r.cost_usd for r in results)
        total_duration = sum(r.duration_ms for r in results)
        has_failures = any(not r.passed for r in results)
        has_warnings = any(r.status == "warn" for r in results)

        # Determine exit code
        exit_code = 0
        if has_failures:
            exit_code = 1
        elif has_warnings and self.config.fail_on_warning:
            exit_code = 1
        if total_cost > self.config.cost_limit > 0:
            print(
                f"::warning::AgentProbe cost ${total_cost:.4f} exceeded "
                f"limit ${self.config.cost_limit:.2f}"
            )
            exit_code = max(exit_code, 1)

        return RunSummary(
            results=results,
            total_cost=total_cost,
            total_duration_ms=total_duration,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
        )

    def _parse_json_report(self, path: str) -> List[TestResult]:
        """Parse the JSON report file emitted by ``agentprobe test --json-report``."""
        report_path = Path(path)
        if not report_path.is_file():
            return []

        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"::warning::Failed to parse AgentProbe JSON report: {exc}")
            return []

        raw_results: Sequence[Dict[str, Any]] = []
        if isinstance(data, list):
            raw_results = data
        elif isinstance(data, dict):
            raw_results = data.get("results", data.get("tests", []))

        results: List[TestResult] = []
        for item in raw_results:
            name = _get(item, "test_name", _get(item, "name", "unknown"))
            status = _get(item, "status", "")
            passed = _get(item, "passed", status == "pass")
            if isinstance(passed, str):
                passed = passed.lower() in ("true", "1", "yes")

            results.append(
                TestResult(
                    name=str(name),
                    passed=bool(passed),
                    status=str(status) or ("pass" if passed else "fail"),
                    duration_ms=float(_get(item, "duration_ms", 0.0)),
                    cost_usd=float(_get(item, "cost_usd", 0.0)),
                    error=str(_get(item, "error", _get(item, "error_message", "")) or ""),
                    assertions_run=int(_get(item, "assertions_run", 0)),
                    assertions_passed=int(_get(item, "assertions_passed", 0)),
                )
            )
        return results

    # -- Annotations & outputs ----------------------------------------------

    def _emit_annotations(self, summary: RunSummary) -> None:
        """Emit GitHub Actions annotations for failures and warnings."""
        for result in summary.results:
            if not result.passed:
                safe_error = result.error.replace("\n", " ").replace("\r", " ")[:500]
                print(f"::error::AgentProbe: {result.name} failed - {safe_error}")
            elif result.status == "warn":
                print(f"::warning::AgentProbe: {result.name} - {result.error[:300]}")

    def _set_outputs(self, summary: RunSummary) -> None:
        """Write step outputs consumed by downstream workflow steps."""
        total = len(summary.results)
        passed = sum(1 for r in summary.results if r.passed)
        failed = total - passed

        _gh_output("total-tests", str(total))
        _gh_output("passed-tests", str(passed))
        _gh_output("failed-tests", str(failed))
        _gh_output("pass-rate", f"{(passed / total * 100) if total else 0:.1f}")
        _gh_output("total-cost", f"{summary.total_cost:.6f}")
        _gh_output("total-duration-ms", f"{summary.total_duration_ms:.0f}")
        _gh_output("exit-code", str(summary.exit_code))
        _gh_output("result", "pass" if summary.exit_code == 0 else "fail")

    # -- PR comment ---------------------------------------------------------

    def _build_pr_comment(self, summary: RunSummary) -> str:
        """Build a Markdown PR comment body from the run summary."""
        total = len(summary.results)
        passed = sum(1 for r in summary.results if r.passed)
        failed = total - passed
        rate = (passed / total * 100) if total else 0
        overall_icon = _status_icon(failed == 0)

        lines: List[str] = []

        # Header
        lines.append(f"## {overall_icon} AgentProbe Test Results")
        lines.append("")

        # Summary table
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Tests | {total} |")
        lines.append(f"| Passed | {passed} \u2705 |")
        if failed:
            lines.append(f"| Failed | {failed} \u274c |")
        else:
            lines.append(f"| Failed | {failed} |")
        lines.append(f"| Pass Rate | **{rate:.1f}%** |")
        lines.append(f"| Total Cost | {_fmt_cost(summary.total_cost)} |")
        lines.append(f"| Duration | {_fmt_duration(summary.total_duration_ms)} |")
        if self.config.cost_limit > 0:
            budget_pct = (summary.total_cost / self.config.cost_limit * 100) if self.config.cost_limit else 0
            lines.append(f"| Cost Budget | {_fmt_cost(summary.total_cost)} / {_fmt_cost(self.config.cost_limit)} ({budget_pct:.0f}%) |")
        lines.append("")

        # Cost budget warning
        if self.config.cost_limit > 0 and summary.total_cost > self.config.cost_limit:
            lines.append(
                f"> **Warning:** Total cost {_fmt_cost(summary.total_cost)} "
                f"exceeded budget {_fmt_cost(self.config.cost_limit)}"
            )
            lines.append("")

        # Assertion results (collapsible)
        has_assertions = any(r.assertions_run > 0 for r in summary.results)
        if has_assertions:
            total_assertions = sum(r.assertions_run for r in summary.results)
            passed_assertions = sum(r.assertions_passed for r in summary.results)
            lines.append(f"<details><summary>Assertions: {passed_assertions}/{total_assertions} passed</summary>")
            lines.append("")
            lines.append("| Test | Assertions | Passed |")
            lines.append("|------|-----------|--------|")
            for r in summary.results:
                if r.assertions_run > 0:
                    a_icon = _status_icon(r.assertions_passed == r.assertions_run)
                    lines.append(f"| `{r.name}` | {r.assertions_run} | {r.assertions_passed} {a_icon} |")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        # Test details (collapsible)
        lines.append("<details><summary>Test Details</summary>")
        lines.append("")
        lines.append("| Status | Test | Duration | Cost |")
        lines.append("|:------:|------|----------|------|")
        for r in summary.results:
            icon = _status_icon(r.passed)
            lines.append(
                f"| {icon} | `{r.name}` | {_fmt_duration(r.duration_ms)} | {_fmt_cost(r.cost_usd)} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

        # Failure details
        failures = [r for r in summary.results if not r.passed]
        if failures:
            lines.append(
                f"<details open><summary>\u274c Failures ({len(failures)} test"
                f"{'s' if len(failures) > 1 else ''})</summary>"
            )
            lines.append("")
            for r in failures:
                lines.append(f"### `{r.name}`")
                lines.append("")
                lines.append("```")
                lines.append(r.error or "No error details available.")
                lines.append("```")
                lines.append("")
            lines.append("</details>")
            lines.append("")

        # Cost breakdown (only when multiple tests)
        if len(summary.results) > 1 and summary.total_cost > 0:
            lines.append("<details><summary>Cost Breakdown</summary>")
            lines.append("")
            lines.append("| Test | Cost | % of Total |")
            lines.append("|------|------|-----------|")
            sorted_by_cost = sorted(summary.results, key=lambda r: r.cost_usd, reverse=True)
            for r in sorted_by_cost:
                pct = (r.cost_usd / summary.total_cost * 100) if summary.total_cost else 0
                lines.append(f"| `{r.name}` | {_fmt_cost(r.cost_usd)} | {pct:.1f}% |")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(
            "*Generated by [AgentProbe](https://github.com/agentprobe/agentprobe) "
            "-- pytest for AI Agents*"
        )
        lines.append("")

        return "\n".join(lines)

    def _post_pr_comment(self, body: str) -> None:
        """Post or update a PR comment via the GitHub API using ``gh`` CLI."""
        repo = self.config.repository
        pr = self.config.pr_number
        if not repo or not pr:
            return

        marker = "<!-- agentprobe-results -->"
        full_body = f"{marker}\n{body}"

        # Try to find and update an existing comment first
        try:
            list_proc = subprocess.run(
                [
                    "gh", "api",
                    f"repos/{repo}/issues/{pr}/comments",
                    "--jq", f'[.[] | select(.body | startswith("{marker}")) | .id] | first',
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "GH_TOKEN": self.config.github_token},
            )
            existing_id = list_proc.stdout.strip()

            if existing_id and existing_id != "null":
                # Update existing comment
                subprocess.run(
                    [
                        "gh", "api",
                        f"repos/{repo}/issues/comments/{existing_id}",
                        "--method", "PATCH",
                        "--field", f"body={full_body}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env={**os.environ, "GH_TOKEN": self.config.github_token},
                )
                print(f"Updated existing AgentProbe comment on PR #{pr}")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Create new comment
        try:
            subprocess.run(
                [
                    "gh", "api",
                    f"repos/{repo}/issues/{pr}/comments",
                    "--method", "POST",
                    "--field", f"body={full_body}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "GH_TOKEN": self.config.github_token},
            )
            print(f"Posted AgentProbe results comment on PR #{pr}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            print(f"::warning::Failed to post PR comment: {exc}")

    # -- Artifacts ----------------------------------------------------------

    def _write_artifacts(self, summary: RunSummary, comment_body: str) -> None:
        """Write report files to the workspace for upload as build artifacts."""
        reports_dir = Path(self.config.workspace) / "agentprobe-reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Markdown report
        (reports_dir / "report.md").write_text(comment_body, encoding="utf-8")

        # JSON summary
        json_data = {
            "started_at": summary.started_at,
            "finished_at": summary.finished_at,
            "total_tests": len(summary.results),
            "passed": sum(1 for r in summary.results if r.passed),
            "failed": sum(1 for r in summary.results if not r.passed),
            "total_cost_usd": summary.total_cost,
            "total_duration_ms": summary.total_duration_ms,
            "cost_limit_usd": self.config.cost_limit,
            "exit_code": summary.exit_code,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "cost_usd": r.cost_usd,
                    "error": r.error,
                    "assertions_run": r.assertions_run,
                    "assertions_passed": r.assertions_passed,
                }
                for r in summary.results
            ],
        }
        (reports_dir / "results.json").write_text(
            json.dumps(json_data, indent=2), encoding="utf-8"
        )

        print(f"Reports written to {reports_dir}")


# ---------------------------------------------------------------------------
# Workflow YAML generation
# ---------------------------------------------------------------------------

def generate_workflow_yaml(
    *,
    test_dir: str = "tests/",
    model: str = "",
    cost_limit: float = 5.0,
    fail_on_warning: bool = False,
    assertions: str = "",
    python_version: str = "3.11",
    agentprobe_version: str = "",
) -> str:
    """Generate a complete GitHub Actions workflow YAML string.

    This is a convenience helper that produces a ready-to-commit workflow
    file.  It is also used by ``agentprobe init --ci`` and the dashboard's
    "Export Workflow" button.
    """
    ap_install = "agentprobe" if not agentprobe_version else f"agentprobe=={agentprobe_version}"

    model_input = f"\n          model: '{model}'" if model else ""
    assertions_input = f"\n          assertions: '{assertions}'" if assertions else ""

    return textwrap.dedent(f"""\
    name: AgentProbe Tests

    on:
      pull_request:
        branches: [main, develop]
      push:
        branches: [main]
      workflow_dispatch:
        inputs:
          cost-limit:
            description: 'Maximum cost per run in USD'
            required: false
            default: '{cost_limit}'

    permissions:
      contents: read
      pull-requests: write

    env:
      AGENTPROBE_CI: "true"

    jobs:
      agentprobe:
        name: Agent Tests
        runs-on: ubuntu-latest
        timeout-minutes: 30

        steps:
          - name: Checkout code
            uses: actions/checkout@v4

          - name: Run AgentProbe
            uses: tomerhakak/agentprobe@v1
            with:
              test-dir: '{test_dir}'
              cost-limit: '${{{{ github.event.inputs.cost-limit || '{cost_limit}' }}}}'
              fail-on-warning: '{str(fail_on_warning).lower()}'{model_input}{assertions_input}
              github-token: '${{{{ secrets.GITHUB_TOKEN }}}}'
            env:
              OPENAI_API_KEY: '${{{{ secrets.OPENAI_API_KEY }}}}'
              ANTHROPIC_API_KEY: '${{{{ secrets.ANTHROPIC_API_KEY }}}}'

          - name: Upload reports
            if: always()
            uses: actions/upload-artifact@v4
            with:
              name: agentprobe-results
              path: agentprobe-reports/
    """)


# ---------------------------------------------------------------------------
# CLI entry-point (called from action.yml)
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry-point invoked by the GitHub Action's ``runs.main`` step."""
    config = GitHubActionConfig.from_environment()
    runner = GitHubActionRunner(config)
    exit_code = runner.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
