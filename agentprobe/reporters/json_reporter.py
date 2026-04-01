"""JSON reporter — generates machine-readable test reports for CI/CD."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentprobe.core.models import AgentRecording


class JSONReporter:
    """Generates JSON test reports suitable for CI/CD pipelines."""

    def generate_test_report(self, results: list[Any], output_path: str) -> None:
        """Generate a JSON report file.

        Parameters
        ----------
        results:
            List of test result objects with attributes: name, status,
            duration_ms, cost_usd, error_message, error_type, recording.
        output_path:
            File path to write the JSON to.
        """
        now = datetime.now(timezone.utc)

        passed = sum(1 for r in results if getattr(r, "status", "") == "pass")
        failed = sum(1 for r in results if getattr(r, "status", "") == "fail")
        warned = sum(1 for r in results if getattr(r, "status", "") == "warn")
        skipped = sum(1 for r in results if getattr(r, "status", "") == "skip")
        errored = sum(1 for r in results if getattr(r, "status", "") == "error")
        total_cost = sum(getattr(r, "cost_usd", 0.0) for r in results)
        total_duration = sum(getattr(r, "duration_ms", 0.0) for r in results)

        report: dict[str, Any] = {
            "agentprobe_version": self._get_version(),
            "generated_at": now.isoformat(),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "warned": warned,
                "skipped": skipped,
                "errored": errored,
                "total_cost_usd": round(total_cost, 6),
                "total_duration_ms": round(total_duration, 2),
                "success_rate": round(passed / len(results) * 100, 2) if results else 0.0,
            },
            "tests": [],
        }

        for r in results:
            test_entry = self._serialize_result(r)
            report["tests"].append(test_entry)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

    def _serialize_result(self, result: Any) -> dict[str, Any]:
        """Convert a test result to a JSON-serializable dict."""
        status = getattr(result, "status", "unknown")
        name = getattr(result, "name", "unknown")
        duration = getattr(result, "duration_ms", 0.0)
        cost = getattr(result, "cost_usd", 0.0)
        error_msg = getattr(result, "error_message", None)
        error_type = getattr(result, "error_type", None)
        recording: AgentRecording | None = getattr(result, "recording", None)

        entry: dict[str, Any] = {
            "name": name,
            "status": status,
            "duration_ms": round(duration, 2),
            "cost_usd": round(cost, 6),
        }

        if error_msg:
            entry["error"] = {
                "type": error_type or "AssertionError",
                "message": error_msg,
            }

        if recording:
            entry["recording"] = {
                "id": recording.metadata.id,
                "model": recording.environment.model,
                "framework": recording.metadata.agent_framework,
                "step_count": recording.step_count,
                "total_tokens": recording.total_tokens,
                "total_cost_usd": round(recording.total_cost, 6),
                "total_duration_ms": round(recording.total_duration, 2),
                "output_status": recording.output.status.value,
                "llm_calls": len(recording.llm_steps),
                "tool_calls": len(recording.tool_steps),
                "steps": [
                    {
                        "step_number": s.step_number,
                        "type": s.type.value,
                        "duration_ms": round(s.duration_ms, 2),
                        **({"tool_name": s.tool_call.tool_name, "tool_success": s.tool_call.success}
                           if s.tool_call else {}),
                        **({"model": s.llm_call.model, "input_tokens": s.llm_call.input_tokens,
                            "output_tokens": s.llm_call.output_tokens, "cost_usd": round(s.llm_call.cost_usd, 6)}
                           if s.llm_call else {}),
                    }
                    for s in recording.steps
                ],
            }

        return entry

    @staticmethod
    def _get_version() -> str:
        try:
            import agentprobe
            return agentprobe.__version__
        except Exception:
            return "unknown"
