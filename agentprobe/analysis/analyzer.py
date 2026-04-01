"""Analyzer — production-ready analysis engine for AgentProbe recordings."""

from __future__ import annotations

import glob as glob_mod
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agentprobe.core.models import AgentRecording, AgentStep, OutputStatus, StepType


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CostReport:
    total_cost: float
    avg_cost: float
    by_group: dict[str, dict]  # group -> {total, avg, count, avg_tokens}
    recordings_count: int


@dataclass
class LatencyReport:
    avg_ms: float
    percentiles: dict[int, float]  # p50, p90, p95, p99
    by_step_type: dict[str, dict]
    slowest_recordings: list[dict]


@dataclass
class FailureReport:
    total_failures: int
    failure_rate: float
    by_type: dict[str, dict]  # type -> {count, percentage, examples}
    common_errors: list[dict]


@dataclass
class DriftReport:
    has_drift: bool
    dimensions: dict[str, dict]  # dimension -> {baseline, current, threshold, drifted}
    severity: str  # LOW, MEDIUM, HIGH
    summary: str


@dataclass
class TokenWasteReport:
    total_waste_tokens: int
    waste_percentage: float
    issues: list[dict]  # {type, description, affected_count, wasted_tokens}


# ---------------------------------------------------------------------------
# Default drift thresholds
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "output_similarity": 0.2,  # flag if similarity drops by more than 20%
    "tool_usage": 0.15,        # flag if tool distribution shifts by more than 15%
    "step_count": 0.25,        # flag if avg step count changes by more than 25%
    "cost": 0.3,               # flag if avg cost changes by more than 30%
}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class Analyzer:
    """Core analysis engine for AgentProbe recordings."""

    def __init__(self) -> None:
        pass

    # -- helpers -----------------------------------------------------------

    def _load_recordings(self, recordings_glob: str) -> list[AgentRecording]:
        """Load recordings from a glob pattern (e.g. 'runs/*.aprobe')."""
        paths = sorted(glob_mod.glob(recordings_glob, recursive=True))
        results: list[AgentRecording] = []
        for p in paths:
            try:
                results.append(AgentRecording.load(p))
            except Exception:
                # Skip files that cannot be parsed — warn in the future.
                continue
        return results

    def _resolve_recordings(
        self, recordings: Union[str, list[AgentRecording]]
    ) -> list[AgentRecording]:
        """Accept either a glob string or a pre-loaded list."""
        if isinstance(recordings, str):
            return self._load_recordings(recordings)
        return list(recordings)

    # -- cost --------------------------------------------------------------

    def cost_analysis(
        self,
        recordings: Union[str, list[AgentRecording]],
        group_by: str = "model",
    ) -> CostReport:
        """Analyze costs across recordings. group_by: model, tool, date, tag."""
        recs = self._resolve_recordings(recordings)
        if not recs:
            return CostReport(
                total_cost=0.0, avg_cost=0.0, by_group={}, recordings_count=0
            )

        total_cost = sum(r.total_cost for r in recs)
        avg_cost = total_cost / len(recs)

        # Build groups
        groups: dict[str, list[AgentRecording]] = defaultdict(list)
        for r in recs:
            keys = self._group_keys(r, group_by)
            for k in keys:
                groups[k].append(r)

        by_group: dict[str, dict] = {}
        for gname, grec in groups.items():
            g_total = sum(r.total_cost for r in grec)
            g_tokens = sum(r.total_tokens for r in grec)
            by_group[gname] = {
                "total": g_total,
                "avg": g_total / len(grec) if grec else 0.0,
                "count": len(grec),
                "avg_tokens": g_tokens / len(grec) if grec else 0,
            }

        return CostReport(
            total_cost=total_cost,
            avg_cost=avg_cost,
            by_group=by_group,
            recordings_count=len(recs),
        )

    def _group_keys(self, recording: AgentRecording, group_by: str) -> list[str]:
        """Return one or more group keys for a recording."""
        if group_by == "model":
            return [recording.environment.model or "unknown"]
        if group_by == "tool":
            tools_used: set[str] = set()
            for step in recording.steps:
                if step.tool_call and step.tool_call.tool_name:
                    tools_used.add(step.tool_call.tool_name)
            return list(tools_used) if tools_used else ["no_tool"]
        if group_by == "date":
            ts = recording.metadata.timestamp
            return [ts.strftime("%Y-%m-%d") if ts else "unknown"]
        if group_by == "tag":
            return recording.metadata.tags if recording.metadata.tags else ["untagged"]
        return ["all"]

    # -- latency -----------------------------------------------------------

    def latency_analysis(
        self,
        recordings: Union[str, list[AgentRecording]],
        percentiles: Optional[list[int]] = None,
    ) -> LatencyReport:
        """Analyze latency across recordings."""
        if percentiles is None:
            percentiles = [50, 90, 95, 99]

        recs = self._resolve_recordings(recordings)
        if not recs:
            return LatencyReport(
                avg_ms=0.0,
                percentiles={p: 0.0 for p in percentiles},
                by_step_type={},
                slowest_recordings=[],
            )

        durations = [r.total_duration for r in recs]
        avg_ms = statistics.mean(durations) if durations else 0.0

        pct_map: dict[int, float] = {}
        for p in percentiles:
            if len(durations) < 2:
                pct_map[p] = durations[0] if durations else 0.0
            else:
                pct_map[p] = _percentile(sorted(durations), p)

        # By step type
        step_durations: dict[str, list[float]] = defaultdict(list)
        for r in recs:
            for step in r.steps:
                step_durations[step.type.value].append(step.duration_ms)

        by_step_type: dict[str, dict] = {}
        for stype, durs in step_durations.items():
            sorted_durs = sorted(durs)
            by_step_type[stype] = {
                "count": len(durs),
                "avg_ms": statistics.mean(durs),
                "min_ms": min(durs),
                "max_ms": max(durs),
                "p50_ms": _percentile(sorted_durs, 50),
                "p95_ms": _percentile(sorted_durs, 95),
            }

        # Slowest recordings (top 5)
        ranked = sorted(recs, key=lambda r: r.total_duration, reverse=True)
        slowest = [
            {
                "id": r.metadata.id,
                "name": r.metadata.name,
                "duration_ms": r.total_duration,
                "step_count": r.step_count,
            }
            for r in ranked[:5]
        ]

        return LatencyReport(
            avg_ms=avg_ms,
            percentiles=pct_map,
            by_step_type=by_step_type,
            slowest_recordings=slowest,
        )

    # -- failure -----------------------------------------------------------

    def failure_analysis(
        self,
        recordings: Union[str, list[AgentRecording]],
        classify: bool = True,
    ) -> FailureReport:
        """Analyze failures. If classify=True, categorize into types."""
        recs = self._resolve_recordings(recordings)
        if not recs:
            return FailureReport(
                total_failures=0, failure_rate=0.0, by_type={}, common_errors=[]
            )

        failed = [r for r in recs if r.output.status != OutputStatus.SUCCESS]
        total_failures = len(failed)
        failure_rate = total_failures / len(recs) if recs else 0.0

        # Classify
        type_buckets: dict[str, list[AgentRecording]] = defaultdict(list)
        for r in failed:
            ftype = self._classify_failure(r) if classify else "unclassified"
            type_buckets[ftype].append(r)

        by_type: dict[str, dict] = {}
        for ftype, frecs in type_buckets.items():
            examples = [
                {
                    "id": r.metadata.id,
                    "name": r.metadata.name,
                    "error": r.output.error or "",
                }
                for r in frecs[:3]
            ]
            by_type[ftype] = {
                "count": len(frecs),
                "percentage": len(frecs) / total_failures if total_failures else 0.0,
                "examples": examples,
            }

        # Common errors — aggregate error messages
        error_counter: Counter[str] = Counter()
        for r in failed:
            msg = (r.output.error or "unknown").strip()
            # Normalise: take the first 120 chars to group similar errors
            normalised = msg[:120]
            error_counter[normalised] += 1

        common_errors = [
            {"error": err, "count": cnt}
            for err, cnt in error_counter.most_common(10)
        ]

        return FailureReport(
            total_failures=total_failures,
            failure_rate=failure_rate,
            by_type=by_type,
            common_errors=common_errors,
        )

    def _classify_failure(self, recording: AgentRecording) -> str:
        """Classify a failed recording into a failure type based on heuristics."""
        # 1. Timeout
        if recording.output.status == OutputStatus.TIMEOUT:
            return "timeout"

        error_text = (recording.output.error or "").lower()

        # 2. Timeout keywords in error
        if any(kw in error_text for kw in ("timeout", "timed out", "deadline exceeded")):
            return "timeout"

        # 3. Tool errors — any step with a failed tool call
        tool_errors = [
            s
            for s in recording.steps
            if s.tool_call is not None and not s.tool_call.success
        ]
        if tool_errors:
            return "tool_error"

        # 4. Infinite loop — same tool called consecutively many times
        if self._detect_loop(recording):
            return "infinite_loop"

        # 5. Wrong tool selection — tool called that produced an error with a
        #    message suggesting it was the wrong tool, or tool called on clearly
        #    unrelated input (heuristic: tool result contains "not found" /
        #    "invalid" and was the last step before failure)
        if self._detect_wrong_tool(recording):
            return "wrong_tool_selection"

        # 6. Hallucination — output contains tool names/calls that don't exist
        #    in tools_available, or output references information not in any
        #    tool result
        if self._detect_hallucination(recording):
            return "hallucination"

        return "other"

    def _detect_loop(self, recording: AgentRecording) -> bool:
        """Return True if the recording exhibits an infinite-loop pattern."""
        tool_names = [
            s.tool_call.tool_name
            for s in recording.steps
            if s.tool_call is not None
        ]
        if len(tool_names) < 4:
            return False
        # Check for 4+ consecutive identical tool calls
        run_length = 1
        for i in range(1, len(tool_names)):
            if tool_names[i] == tool_names[i - 1]:
                run_length += 1
                if run_length >= 4:
                    return True
            else:
                run_length = 1
        return False

    def _detect_wrong_tool(self, recording: AgentRecording) -> bool:
        """Heuristic: the last tool call before failure errored with suggestive message."""
        tool_steps = [s for s in recording.steps if s.tool_call is not None]
        if not tool_steps:
            return False
        last_tool = tool_steps[-1]
        if last_tool.tool_call and not last_tool.tool_call.success:
            err = (last_tool.tool_call.error or "").lower()
            indicators = ("not found", "invalid", "no such", "wrong", "unsupported")
            if any(ind in err for ind in indicators):
                return True
        return False

    def _detect_hallucination(self, recording: AgentRecording) -> bool:
        """Heuristic: agent called a tool that is not in tools_available."""
        available = {t.name for t in recording.environment.tools_available}
        if not available:
            return False  # Cannot determine if we don't know available tools
        for step in recording.steps:
            if step.tool_call and step.tool_call.tool_name not in available:
                return True
        return False

    # -- drift -------------------------------------------------------------

    def detect_drift(
        self,
        baseline: Union[str, list[AgentRecording]],
        current: Union[str, list[AgentRecording]],
        dimensions: Optional[list[str]] = None,
        thresholds: Optional[dict[str, float]] = None,
    ) -> DriftReport:
        """Detect behavioral drift between baseline and current recordings."""
        if dimensions is None:
            dimensions = ["output_similarity", "tool_usage", "step_count", "cost"]

        effective_thresholds = dict(_DEFAULT_THRESHOLDS)
        if thresholds:
            effective_thresholds.update(thresholds)

        base_recs = self._resolve_recordings(baseline)
        curr_recs = self._resolve_recordings(current)

        if not base_recs or not curr_recs:
            return DriftReport(
                has_drift=False,
                dimensions={},
                severity="LOW",
                summary="Insufficient recordings for drift detection.",
            )

        dim_results: dict[str, dict] = {}
        drifted_count = 0

        for dim in dimensions:
            thresh = effective_thresholds.get(dim, 0.2)
            base_val, curr_val = self._compute_dimension(dim, base_recs, curr_recs)
            # Drift is measured as relative change
            if base_val == 0.0 and curr_val == 0.0:
                delta = 0.0
            elif base_val == 0.0:
                delta = 1.0  # went from 0 to something
            else:
                delta = abs(curr_val - base_val) / abs(base_val)

            is_drifted = delta > thresh
            if is_drifted:
                drifted_count += 1

            dim_results[dim] = {
                "baseline": round(base_val, 6),
                "current": round(curr_val, 6),
                "delta": round(delta, 6),
                "threshold": thresh,
                "drifted": is_drifted,
            }

        has_drift = drifted_count > 0
        if drifted_count == 0:
            severity = "LOW"
        elif drifted_count <= len(dimensions) // 2:
            severity = "MEDIUM"
        else:
            severity = "HIGH"

        drifted_names = [d for d, v in dim_results.items() if v["drifted"]]
        if drifted_names:
            summary = f"Drift detected in {len(drifted_names)}/{len(dimensions)} dimensions: {', '.join(drifted_names)}."
        else:
            summary = "No significant drift detected across any dimension."

        return DriftReport(
            has_drift=has_drift,
            dimensions=dim_results,
            severity=severity,
            summary=summary,
        )

    def _compute_dimension(
        self,
        dimension: str,
        base: list[AgentRecording],
        current: list[AgentRecording],
    ) -> tuple[float, float]:
        """Compute a scalar value for both baseline and current sets for a given dimension."""
        if dimension == "output_similarity":
            # Similarity between outputs in baseline vs current
            base_texts = [str(r.output.content) for r in base]
            curr_texts = [str(r.output.content) for r in current]
            # Baseline self-similarity
            base_val = self._calculate_output_similarity(base_texts, base_texts)
            # Cross-similarity
            curr_val = self._calculate_output_similarity(base_texts, curr_texts)
            return base_val, curr_val

        if dimension == "tool_usage":
            # Jaccard similarity of tool sets
            base_tools = self._aggregate_tool_distribution(base)
            curr_tools = self._aggregate_tool_distribution(current)
            base_val = 1.0  # baseline compared to itself
            # Compute cosine-like overlap
            all_tools = set(base_tools.keys()) | set(curr_tools.keys())
            if not all_tools:
                return 1.0, 1.0
            dot = sum(base_tools.get(t, 0) * curr_tools.get(t, 0) for t in all_tools)
            mag_b = sum(v ** 2 for v in base_tools.values()) ** 0.5
            mag_c = sum(v ** 2 for v in curr_tools.values()) ** 0.5
            curr_val = dot / (mag_b * mag_c) if (mag_b * mag_c) > 0 else 0.0
            return base_val, curr_val

        if dimension == "step_count":
            base_val = statistics.mean([r.step_count for r in base]) if base else 0.0
            curr_val = statistics.mean([r.step_count for r in current]) if current else 0.0
            return base_val, curr_val

        if dimension == "cost":
            base_val = statistics.mean([r.total_cost for r in base]) if base else 0.0
            curr_val = statistics.mean([r.total_cost for r in current]) if current else 0.0
            return base_val, curr_val

        return 0.0, 0.0

    def _aggregate_tool_distribution(
        self, recordings: list[AgentRecording]
    ) -> dict[str, float]:
        """Return normalised tool-call frequency across recordings."""
        counter: Counter[str] = Counter()
        for r in recordings:
            for s in r.steps:
                if s.tool_call:
                    counter[s.tool_call.tool_name] += 1
        total = sum(counter.values())
        if total == 0:
            return {}
        return {k: v / total for k, v in counter.items()}

    def _calculate_output_similarity(
        self, texts_a: list[str], texts_b: list[str]
    ) -> float:
        """Calculate average pairwise similarity using SequenceMatcher."""
        if not texts_a or not texts_b:
            return 0.0

        total = 0.0
        count = 0
        for a in texts_a:
            for b in texts_b:
                total += SequenceMatcher(None, a, b).ratio()
                count += 1

        return total / count if count else 0.0

    # -- token waste -------------------------------------------------------

    def token_waste(
        self, recordings: Union[str, list[AgentRecording]]
    ) -> TokenWasteReport:
        """Detect token waste patterns across recordings."""
        recs = self._resolve_recordings(recordings)
        if not recs:
            return TokenWasteReport(
                total_waste_tokens=0, waste_percentage=0.0, issues=[]
            )

        total_tokens = sum(r.total_tokens for r in recs)
        issues: list[dict] = []

        # 1. System prompt repeated in multi-turn conversations
        repeated_sys = self._detect_repeated_system_prompt(recs)
        if repeated_sys["wasted_tokens"] > 0:
            issues.append(repeated_sys)

        # 2. Tool descriptions sent but never used
        unused_tools = self._detect_unused_tool_descriptions(recs)
        if unused_tools["wasted_tokens"] > 0:
            issues.append(unused_tools)

        # 3. Excessive 'thinking' text before tool calls
        excessive_thinking = self._detect_excessive_thinking(recs)
        if excessive_thinking["wasted_tokens"] > 0:
            issues.append(excessive_thinking)

        # 4. Repeated identical messages
        repeated_msgs = self._detect_repeated_messages(recs)
        if repeated_msgs["wasted_tokens"] > 0:
            issues.append(repeated_msgs)

        total_waste = sum(i["wasted_tokens"] for i in issues)
        waste_pct = (total_waste / total_tokens * 100.0) if total_tokens > 0 else 0.0

        return TokenWasteReport(
            total_waste_tokens=total_waste,
            waste_percentage=round(waste_pct, 2),
            issues=issues,
        )

    def _detect_repeated_system_prompt(
        self, recordings: list[AgentRecording]
    ) -> dict:
        """Detect system prompts repeated across LLM calls within a recording."""
        affected = 0
        wasted = 0

        for r in recordings:
            sys_prompt = r.environment.system_prompt
            if not sys_prompt:
                continue
            # Estimate tokens for system prompt (rough: 1 token per 4 chars)
            sys_tokens = len(sys_prompt) // 4
            llm_steps = [s for s in r.steps if s.llm_call is not None]
            if len(llm_steps) <= 1:
                continue
            # Every LLM call after the first re-sends the system prompt
            repeats = len(llm_steps) - 1
            if repeats > 0:
                affected += 1
                wasted += sys_tokens * repeats

        return {
            "type": "repeated_system_prompt",
            "description": "System prompt is re-sent in every LLM call within multi-turn conversations.",
            "affected_count": affected,
            "wasted_tokens": wasted,
        }

    def _detect_unused_tool_descriptions(
        self, recordings: list[AgentRecording]
    ) -> dict:
        """Detect tool definitions sent to the LLM but never invoked."""
        affected = 0
        wasted = 0

        for r in recordings:
            available = {t.name for t in r.environment.tools_available}
            used = {
                s.tool_call.tool_name
                for s in r.steps
                if s.tool_call is not None
            }
            unused = available - used
            if unused:
                affected += 1
                # Estimate wasted tokens from unused tool descriptions
                for tool_def in r.environment.tools_available:
                    if tool_def.name in unused:
                        desc_len = len(tool_def.description) + len(
                            str(tool_def.parameters)
                        )
                        # Count per LLM call
                        llm_count = max(len(r.llm_steps), 1)
                        wasted += (desc_len // 4) * llm_count

        return {
            "type": "unused_tool_descriptions",
            "description": "Tool schemas sent to the LLM but the tools were never called.",
            "affected_count": affected,
            "wasted_tokens": wasted,
        }

    def _detect_excessive_thinking(self, recordings: list[AgentRecording]) -> dict:
        """Detect LLM responses with large text blocks before a tool call."""
        affected = 0
        wasted = 0
        thinking_threshold = 500  # chars of text before a tool call is 'excessive'

        for r in recordings:
            for step in r.steps:
                if step.llm_call and step.llm_call.output_message:
                    msg = step.llm_call.output_message
                    content = msg.content
                    if isinstance(content, list):
                        # Look for text block followed by tool_use
                        text_before_tool = 0
                        found_tool = False
                        for block in content:
                            if block.type.value == "tool_use":
                                found_tool = True
                                break
                            if block.type.value == "text" and block.text:
                                text_before_tool += len(block.text)
                        if found_tool and text_before_tool > thinking_threshold:
                            affected += 1
                            # Excess tokens beyond a reasonable preamble
                            excess_chars = text_before_tool - thinking_threshold
                            wasted += excess_chars // 4

        return {
            "type": "excessive_thinking",
            "description": "Large text output generated before tool calls (verbose reasoning).",
            "affected_count": affected,
            "wasted_tokens": wasted,
        }

    def _detect_repeated_messages(self, recordings: list[AgentRecording]) -> dict:
        """Detect repeated identical messages within recordings."""
        affected = 0
        wasted = 0

        for r in recordings:
            seen: dict[str, int] = {}
            for step in r.steps:
                if step.llm_call:
                    for m in step.llm_call.input_messages:
                        key = f"{m.role}:{str(m.content)[:200]}"
                        if key in seen:
                            affected += 1
                            content_str = str(m.content)
                            wasted += len(content_str) // 4
                        seen[key] = seen.get(key, 0) + 1

        return {
            "type": "repeated_messages",
            "description": "Identical messages sent multiple times across LLM calls.",
            "affected_count": affected,
            "wasted_tokens": wasted,
        }

    # -- compare runs ------------------------------------------------------

    def compare_runs(
        self,
        run_a: Union[str, list[AgentRecording]],
        run_b: Union[str, list[AgentRecording]],
    ) -> dict:
        """Full comparative analysis between two sets of recordings."""
        recs_a = self._resolve_recordings(run_a)
        recs_b = self._resolve_recordings(run_b)

        cost_a = self.cost_analysis(recs_a)
        cost_b = self.cost_analysis(recs_b)
        latency_a = self.latency_analysis(recs_a)
        latency_b = self.latency_analysis(recs_b)
        failure_a = self.failure_analysis(recs_a)
        failure_b = self.failure_analysis(recs_b)
        waste_a = self.token_waste(recs_a)
        waste_b = self.token_waste(recs_b)
        drift = self.detect_drift(recs_a, recs_b)

        def _delta(a: float, b: float) -> dict:
            diff = b - a
            pct = (diff / a * 100.0) if a != 0 else (100.0 if diff != 0 else 0.0)
            return {"a": round(a, 6), "b": round(b, 6), "diff": round(diff, 6), "pct_change": round(pct, 2)}

        return {
            "recordings": {"a": cost_a.recordings_count, "b": cost_b.recordings_count},
            "cost": _delta(cost_a.avg_cost, cost_b.avg_cost),
            "latency_avg_ms": _delta(latency_a.avg_ms, latency_b.avg_ms),
            "latency_p95_ms": _delta(
                latency_a.percentiles.get(95, 0.0),
                latency_b.percentiles.get(95, 0.0),
            ),
            "failure_rate": _delta(failure_a.failure_rate, failure_b.failure_rate),
            "token_waste_pct": _delta(waste_a.waste_percentage, waste_b.waste_percentage),
            "drift": {
                "has_drift": drift.has_drift,
                "severity": drift.severity,
                "summary": drift.summary,
                "dimensions": drift.dimensions,
            },
        }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _percentile(sorted_data: list[float], p: int) -> float:
    """Compute the p-th percentile from pre-sorted data using linear interpolation."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    # Use the 'inclusive' interpolation method
    k = (p / 100.0) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_data[-1]
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])
