"""Snapshot Testing Manager for AI Agents.

Capture agent behavior as snapshots and automatically detect regressions.
Like Jest snapshots, but for AI agent outputs and decision patterns.

Workflow:
1. First run: captures a snapshot (output, tools used, cost, pattern)
2. Next runs: compares against saved snapshot
3. If drift detected: shows diff, lets you update or fail

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from agentprobe.core.models import AgentRecording, StepType


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class SnapshotStatus(str, Enum):
    MATCH = "match"
    DRIFT = "drift"
    NEW = "new"
    UPDATED = "updated"


@dataclass
class SnapshotData:
    """The captured behavioral snapshot of an agent run."""

    name: str
    output_hash: str = ""
    output_preview: str = ""
    tools_used: List[str] = field(default_factory=list)
    tools_sequence: str = ""
    step_count: int = 0
    llm_calls: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    step_pattern: str = ""
    decision_summary: List[str] = field(default_factory=list)
    model: str = ""
    captured_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "output_hash": self.output_hash,
            "output_preview": self.output_preview,
            "tools_used": self.tools_used,
            "tools_sequence": self.tools_sequence,
            "step_count": self.step_count,
            "llm_calls": self.llm_calls,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "step_pattern": self.step_pattern,
            "decision_summary": self.decision_summary,
            "model": self.model,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SnapshotData:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SnapshotDiff:
    """Differences between two snapshots."""

    field_name: str
    expected: Any
    actual: Any
    severity: str = "info"  # "info", "warning", "breaking"


@dataclass
class SnapshotResult:
    """Result of comparing a recording against a snapshot."""

    name: str
    status: SnapshotStatus
    diffs: List[SnapshotDiff] = field(default_factory=list)
    snapshot: Optional[SnapshotData] = None
    previous: Optional[SnapshotData] = None

    @property
    def passed(self) -> bool:
        return self.status in (SnapshotStatus.MATCH, SnapshotStatus.NEW, SnapshotStatus.UPDATED)

    @property
    def has_breaking_diffs(self) -> bool:
        return any(d.severity == "breaking" for d in self.diffs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "passed": self.passed,
            "diffs": [
                {"field": d.field_name, "expected": str(d.expected), "actual": str(d.actual), "severity": d.severity}
                for d in self.diffs
            ],
        }


# ---------------------------------------------------------------------------
# Snapshot Manager
# ---------------------------------------------------------------------------

class SnapshotManager:
    """Manage behavioral snapshots for agent recordings.

    Usage::

        mgr = SnapshotManager(snapshot_dir=".agentprobe/snapshots")

        # First run — creates snapshot
        result = mgr.assert_snapshot("my_agent_test", recording)
        assert result.status == SnapshotStatus.NEW

        # Subsequent runs — compares against snapshot
        result = mgr.assert_snapshot("my_agent_test", recording2)
        if result.status == SnapshotStatus.DRIFT:
            print("Agent behavior changed!")
            for diff in result.diffs:
                print(f"  {diff.field_name}: {diff.expected} -> {diff.actual}")

        # Update snapshot
        mgr.update("my_agent_test", recording3)
    """

    def __init__(
        self,
        snapshot_dir: str = ".agentprobe/snapshots",
        cost_tolerance: float = 0.20,
        token_tolerance: float = 0.30,
        step_tolerance: int = 3,
    ) -> None:
        self._dir = Path(snapshot_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cost_tolerance = cost_tolerance
        self._token_tolerance = token_tolerance
        self._step_tolerance = step_tolerance

    def capture(self, name: str, recording: AgentRecording) -> SnapshotData:
        """Capture a snapshot from a recording."""
        output_content = str(recording.output.content) if recording.output else ""
        output_hash = hashlib.sha256(output_content.encode()).hexdigest()[:16]

        tools_used = []
        tools_sequence_parts = []
        for step in recording.steps:
            if step.tool_call:
                tools_sequence_parts.append(step.tool_call.tool_name)
                if step.tool_call.tool_name not in tools_used:
                    tools_used.append(step.tool_call.tool_name)

        decisions = []
        for step in recording.steps:
            if step.decision:
                decisions.append(f"{step.decision.type.value}: {step.decision.reason[:60]}")

        pattern_map = {
            StepType.LLM_CALL: "L", StepType.TOOL_CALL: "T",
            StepType.TOOL_RESULT: "R", StepType.DECISION: "D",
            StepType.HANDOFF: "H", StepType.MEMORY_READ: "M",
            StepType.MEMORY_WRITE: "W",
        }

        return SnapshotData(
            name=name,
            output_hash=output_hash,
            output_preview=output_content[:200],
            tools_used=tools_used,
            tools_sequence=" -> ".join(tools_sequence_parts),
            step_count=len(recording.steps),
            llm_calls=len(recording.llm_steps),
            total_cost=recording.total_cost,
            total_tokens=recording.total_tokens,
            step_pattern="".join(pattern_map.get(s.type, "?") for s in recording.steps),
            decision_summary=decisions,
            model=recording.environment.model,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    def assert_snapshot(self, name: str, recording: AgentRecording) -> SnapshotResult:
        """Compare a recording against a saved snapshot, creating if missing."""
        current = self.capture(name, recording)
        snap_path = self._dir / f"{name}.snap.json"

        if not snap_path.exists():
            self._save(snap_path, current)
            return SnapshotResult(name=name, status=SnapshotStatus.NEW, snapshot=current)

        saved = self._load(snap_path)
        diffs = self._compare(saved, current)

        if not diffs:
            return SnapshotResult(name=name, status=SnapshotStatus.MATCH, snapshot=current, previous=saved)

        return SnapshotResult(name=name, status=SnapshotStatus.DRIFT, diffs=diffs, snapshot=current, previous=saved)

    def update(self, name: str, recording: AgentRecording) -> SnapshotResult:
        """Update a snapshot with new recording data."""
        current = self.capture(name, recording)
        snap_path = self._dir / f"{name}.snap.json"
        self._save(snap_path, current)
        return SnapshotResult(name=name, status=SnapshotStatus.UPDATED, snapshot=current)

    def delete(self, name: str) -> bool:
        """Delete a snapshot."""
        snap_path = self._dir / f"{name}.snap.json"
        if snap_path.exists():
            snap_path.unlink()
            return True
        return False

    def list_snapshots(self) -> List[str]:
        """List all saved snapshot names."""
        return sorted(
            p.stem.replace(".snap", "") for p in self._dir.glob("*.snap.json")
        )

    # -- Comparison --------------------------------------------------------

    def _compare(self, saved: SnapshotData, current: SnapshotData) -> List[SnapshotDiff]:
        """Compare two snapshots and return differences."""
        diffs: List[SnapshotDiff] = []

        # Output change
        if saved.output_hash != current.output_hash:
            diffs.append(SnapshotDiff("output_hash", saved.output_hash, current.output_hash, "breaking"))

        # Tool set change
        if saved.tools_used != current.tools_used:
            diffs.append(SnapshotDiff("tools_used", saved.tools_used, current.tools_used, "breaking"))

        # Tool sequence change
        if saved.tools_sequence != current.tools_sequence:
            diffs.append(SnapshotDiff("tools_sequence", saved.tools_sequence, current.tools_sequence, "warning"))

        # Step count change
        if abs(saved.step_count - current.step_count) > self._step_tolerance:
            diffs.append(SnapshotDiff("step_count", saved.step_count, current.step_count, "warning"))

        # Step pattern change
        if saved.step_pattern != current.step_pattern:
            diffs.append(SnapshotDiff("step_pattern", saved.step_pattern, current.step_pattern, "warning"))

        # Cost change
        if saved.total_cost > 0:
            cost_change = abs(current.total_cost - saved.total_cost) / saved.total_cost
            if cost_change > self._cost_tolerance:
                severity = "breaking" if cost_change > 1.0 else "warning"
                diffs.append(SnapshotDiff("total_cost", f"${saved.total_cost:.4f}", f"${current.total_cost:.4f}", severity))

        # Token change
        if saved.total_tokens > 0:
            token_change = abs(current.total_tokens - saved.total_tokens) / saved.total_tokens
            if token_change > self._token_tolerance:
                diffs.append(SnapshotDiff("total_tokens", saved.total_tokens, current.total_tokens, "warning"))

        # Model change
        if saved.model and current.model and saved.model != current.model:
            diffs.append(SnapshotDiff("model", saved.model, current.model, "info"))

        return diffs

    # -- Persistence -------------------------------------------------------

    def _save(self, path: Path, snapshot: SnapshotData) -> None:
        path.write_text(json.dumps(snapshot.to_dict(), indent=2))

    def _load(self, path: Path) -> SnapshotData:
        return SnapshotData.from_dict(json.loads(path.read_text()))

    # -- Rendering ---------------------------------------------------------

    def render_result(self, result: SnapshotResult) -> str:
        """Render a snapshot comparison result."""
        status_emoji = {
            SnapshotStatus.MATCH: "\u2705", SnapshotStatus.DRIFT: "\U0001f534",
            SnapshotStatus.NEW: "\U0001f195", SnapshotStatus.UPDATED: "\U0001f504",
        }
        emoji = status_emoji.get(result.status, "\u2753")
        lines: List[str] = [f"{emoji} Snapshot: {result.name} — {result.status.value.upper()}"]

        if result.diffs:
            for diff in result.diffs:
                sev_emoji = {
                    "breaking": "\U0001f534", "warning": "\U0001f7e1", "info": "\U0001f535"
                }
                e = sev_emoji.get(diff.severity, "")
                lines.append(f"   {e} {diff.field_name}: {diff.expected} \u2192 {diff.actual}")

        return "\n".join(lines)
