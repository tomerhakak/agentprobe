"""Comprehensive assertion framework for AgentProbe recordings."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from agentprobe.core.models import AgentRecording, AgentStep, OutputStatus, StepType


# ---------------------------------------------------------------------------
# Matchers — small helper classes for JSON schema-like assertions
# ---------------------------------------------------------------------------

class _Matcher:
    """Base class for all matchers."""

    def matches(self, value: Any) -> bool:
        raise NotImplementedError

    def description(self) -> str:
        raise NotImplementedError


class _AnyString(_Matcher):
    def matches(self, value: Any) -> bool:
        return isinstance(value, str)

    def description(self) -> str:
        return "any_string()"


class _AnyInt(_Matcher):
    def matches(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def description(self) -> str:
        return "any_int()"


class _AnyFloat(_Matcher):
    def matches(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def description(self) -> str:
        return "any_float()"


class _Contains(_Matcher):
    def __init__(self, text: str) -> None:
        self._text = text

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and self._text in value

    def description(self) -> str:
        return f"contains({self._text!r})"


class _LessThan(_Matcher):
    def __init__(self, threshold: float) -> None:
        self._threshold = threshold

    def matches(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and value < self._threshold

    def description(self) -> str:
        return f"less_than({self._threshold})"


class _GreaterThan(_Matcher):
    def __init__(self, threshold: float) -> None:
        self._threshold = threshold

    def matches(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and value > self._threshold

    def description(self) -> str:
        return f"greater_than({self._threshold})"


class _ListOf(_Matcher):
    def __init__(self, item_matcher: Any, min_length: int = 0) -> None:
        self._item_matcher = item_matcher
        self._min_length = min_length

    def matches(self, value: Any) -> bool:
        if not isinstance(value, list):
            return False
        if len(value) < self._min_length:
            return False
        for item in value:
            if isinstance(self._item_matcher, _Matcher):
                if not self._item_matcher.matches(item):
                    return False
            elif isinstance(self._item_matcher, dict):
                if not _match_schema(item, self._item_matcher):
                    return False
            elif isinstance(self._item_matcher, type):
                if not isinstance(item, self._item_matcher):
                    return False
            else:
                if item != self._item_matcher:
                    return False
        return True

    def description(self) -> str:
        return f"list_of(..., min_length={self._min_length})"


# ---------------------------------------------------------------------------
# Schema matching helper
# ---------------------------------------------------------------------------

def _match_schema(actual: Any, schema: Any) -> bool:
    """Recursively match a value against a schema-like structure.

    The schema can contain:
    - _Matcher instances (checked via .matches())
    - dict (recursively matched key-by-key; extra keys in actual are allowed)
    - list (each schema element matched against corresponding actual element)
    - Literal values (compared with ==)
    """
    if isinstance(schema, _Matcher):
        return schema.matches(actual)
    if isinstance(schema, dict):
        if not isinstance(actual, dict):
            return False
        for key, expected in schema.items():
            if key not in actual:
                return False
            if not _match_schema(actual[key], expected):
                return False
        return True
    if isinstance(schema, list):
        if not isinstance(actual, list):
            return False
        if len(actual) < len(schema):
            return False
        for s_item, a_item in zip(schema, actual):
            if not _match_schema(a_item, s_item):
                return False
        return True
    return actual == schema


# ---------------------------------------------------------------------------
# PII regex patterns
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("phone_us", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ip_address", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]


# ---------------------------------------------------------------------------
# AssertionResult & AssertionError
# ---------------------------------------------------------------------------

@dataclass
class AssertionResult:
    """Result of a single assertion check."""

    passed: bool
    assertion_name: str
    message: str
    expected: Any = None
    actual: Any = None


class AssertionError(Exception):
    """Raised when an assertion fails."""

    def __init__(self, result: AssertionResult) -> None:
        self.result = result
        super().__init__(result.message)


# ---------------------------------------------------------------------------
# Text similarity helpers
# ---------------------------------------------------------------------------

def _simple_similarity(a: str, b: str) -> float:
    """Compute text similarity using SequenceMatcher (0..1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _embedding_similarity(a: str, b: str) -> float | None:
    """Try to compute cosine similarity using sentence-transformers.

    Returns None if the library is not available.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]
    except ImportError:
        return None

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode([a, b])
    cos_sim = float(
        np.dot(embeddings[0], embeddings[1])
        / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]) + 1e-10)
    )
    return cos_sim


# ---------------------------------------------------------------------------
# Assertions class
# ---------------------------------------------------------------------------

class Assertions:
    """Main assertions class -- used as ``assertions`` or ``A`` in tests.

    Collects assertion results during a test run and evaluates them against
    an :class:`AgentRecording`.
    """

    def __init__(self) -> None:
        self._recording: AgentRecording | None = None
        self._results: list[AssertionResult] = []

    # -- setup --------------------------------------------------------------

    def set_recording(self, recording: AgentRecording) -> None:
        """Set the recording to assert against and reset prior results."""
        self._recording = recording
        self._results = []

    def reset(self) -> None:
        """Clear the recording and all results."""
        self._recording = None
        self._results = []

    # -- internal helpers ---------------------------------------------------

    def _require_recording(self) -> AgentRecording:
        if self._recording is None:
            raise RuntimeError(
                "No recording set. Call assertions.set_recording(recording) first."
            )
        return self._recording

    def _output_text(self) -> str:
        """Return the final output content as a string."""
        rec = self._require_recording()
        content = rec.output.content
        if isinstance(content, str):
            return content
        return str(content)

    def _record(self, result: AssertionResult) -> AssertionResult:
        self._results.append(result)
        if not result.passed:
            raise AssertionError(result)
        return result

    def _pass(self, name: str, message: str, expected: Any = None, actual: Any = None) -> AssertionResult:
        return self._record(AssertionResult(
            passed=True, assertion_name=name, message=message,
            expected=expected, actual=actual,
        ))

    def _fail(self, name: str, message: str, expected: Any = None, actual: Any = None) -> AssertionResult:
        return self._record(AssertionResult(
            passed=False, assertion_name=name, message=message,
            expected=expected, actual=actual,
        ))

    # ===================================================================
    # Output Assertions
    # ===================================================================

    def output_contains(self, text: str, case_sensitive: bool = True) -> AssertionResult:
        output = self._output_text()
        haystack = output if case_sensitive else output.lower()
        needle = text if case_sensitive else text.lower()
        if needle in haystack:
            return self._pass("output_contains", f"Output contains {text!r}", text, output)
        return self._fail("output_contains", f"Output does not contain {text!r}", text, output)

    def output_not_contains(self, text: str, case_sensitive: bool = True) -> AssertionResult:
        output = self._output_text()
        haystack = output if case_sensitive else output.lower()
        needle = text if case_sensitive else text.lower()
        if needle not in haystack:
            return self._pass("output_not_contains", f"Output does not contain {text!r}", text, output)
        return self._fail("output_not_contains", f"Output unexpectedly contains {text!r}", text, output)

    def output_contains_any(self, texts: list[str], case_sensitive: bool = True) -> AssertionResult:
        output = self._output_text()
        haystack = output if case_sensitive else output.lower()
        for t in texts:
            needle = t if case_sensitive else t.lower()
            if needle in haystack:
                return self._pass("output_contains_any", f"Output contains {t!r}", texts, output)
        return self._fail("output_contains_any", f"Output contains none of {texts!r}", texts, output)

    def output_contains_all(self, texts: list[str], case_sensitive: bool = True) -> AssertionResult:
        output = self._output_text()
        haystack = output if case_sensitive else output.lower()
        missing = [t for t in texts if (t if case_sensitive else t.lower()) not in haystack]
        if not missing:
            return self._pass("output_contains_all", "Output contains all expected texts", texts, output)
        return self._fail("output_contains_all", f"Output missing: {missing!r}", texts, output)

    def output_matches(self, pattern: str) -> AssertionResult:
        output = self._output_text()
        if re.search(pattern, output):
            return self._pass("output_matches", f"Output matches pattern {pattern!r}", pattern, output)
        return self._fail("output_matches", f"Output does not match pattern {pattern!r}", pattern, output)

    def output_not_matches(self, pattern: str) -> AssertionResult:
        output = self._output_text()
        if not re.search(pattern, output):
            return self._pass("output_not_matches", f"Output does not match pattern {pattern!r}", pattern, output)
        return self._fail("output_not_matches", f"Output unexpectedly matches pattern {pattern!r}", pattern, output)

    def output_equals(self, expected: str) -> AssertionResult:
        output = self._output_text()
        if output == expected:
            return self._pass("output_equals", "Output equals expected", expected, output)
        return self._fail("output_equals", "Output does not equal expected", expected, output)

    def output_json_valid(self) -> AssertionResult:
        output = self._output_text()
        try:
            json.loads(output)
            return self._pass("output_json_valid", "Output is valid JSON", "valid JSON", output)
        except (json.JSONDecodeError, TypeError) as exc:
            return self._fail("output_json_valid", f"Output is not valid JSON: {exc}", "valid JSON", output)

    def output_json_matches(self, schema: dict[str, Any]) -> AssertionResult:
        output = self._output_text()
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, TypeError) as exc:
            return self._fail("output_json_matches", f"Output is not valid JSON: {exc}", schema, output)
        if _match_schema(parsed, schema):
            return self._pass("output_json_matches", "Output JSON matches schema", schema, parsed)
        return self._fail("output_json_matches", "Output JSON does not match schema", schema, parsed)

    def output_length_less_than(self, max_length: int) -> AssertionResult:
        output = self._output_text()
        length = len(output)
        if length < max_length:
            return self._pass("output_length_less_than", f"Output length {length} < {max_length}", max_length, length)
        return self._fail("output_length_less_than", f"Output length {length} >= {max_length}", max_length, length)

    def output_length_greater_than(self, min_length: int) -> AssertionResult:
        output = self._output_text()
        length = len(output)
        if length > min_length:
            return self._pass("output_length_greater_than", f"Output length {length} > {min_length}", min_length, length)
        return self._fail("output_length_greater_than", f"Output length {length} <= {min_length}", min_length, length)

    def output_similar_to(self, text: str, threshold: float = 0.8) -> AssertionResult:
        output = self._output_text()
        # Try embedding similarity first, fall back to SequenceMatcher
        similarity = _embedding_similarity(output, text)
        method = "embedding"
        if similarity is None:
            similarity = _simple_similarity(output, text)
            method = "sequence_matcher"
        if similarity >= threshold:
            return self._pass(
                "output_similar_to",
                f"Output similar to expected (similarity={similarity:.3f}, method={method}, threshold={threshold})",
                text, output,
            )
        return self._fail(
            "output_similar_to",
            f"Output not similar enough (similarity={similarity:.3f}, method={method}, threshold={threshold})",
            text, output,
        )

    # ===================================================================
    # Behavioral Assertions
    # ===================================================================

    def _tool_calls(self) -> list[AgentStep]:
        rec = self._require_recording()
        return [s for s in rec.steps if s.type == StepType.TOOL_CALL and s.tool_call is not None]

    def called_tool(self, tool_name: str, times: int | None = None) -> AssertionResult:
        calls = [s for s in self._tool_calls() if s.tool_call and s.tool_call.tool_name == tool_name]
        count = len(calls)
        if times is not None:
            if count == times:
                return self._pass("called_tool", f"Tool {tool_name!r} called {times} time(s)", times, count)
            return self._fail("called_tool", f"Tool {tool_name!r} called {count} time(s), expected {times}", times, count)
        if count > 0:
            return self._pass("called_tool", f"Tool {tool_name!r} was called ({count} time(s))", f">= 1", count)
        return self._fail("called_tool", f"Tool {tool_name!r} was never called", f">= 1", 0)

    def not_called_tool(self, tool_name: str) -> AssertionResult:
        calls = [s for s in self._tool_calls() if s.tool_call and s.tool_call.tool_name == tool_name]
        if not calls:
            return self._pass("not_called_tool", f"Tool {tool_name!r} was not called", 0, 0)
        return self._fail("not_called_tool", f"Tool {tool_name!r} was called {len(calls)} time(s)", 0, len(calls))

    def called_tools_in_order(self, tool_names: list[str]) -> AssertionResult:
        actual_names = [
            s.tool_call.tool_name for s in self._tool_calls()
            if s.tool_call is not None
        ]
        # Check that tool_names appear as a subsequence of actual_names
        it = iter(actual_names)
        remaining: list[str] = []
        for name in tool_names:
            found = False
            for actual in it:
                if actual == name:
                    found = True
                    break
            if not found:
                remaining.append(name)
        if not remaining:
            return self._pass("called_tools_in_order", f"Tools called in order: {tool_names}", tool_names, actual_names)
        return self._fail(
            "called_tools_in_order",
            f"Tools not called in expected order. Missing in sequence: {remaining}",
            tool_names, actual_names,
        )

    def tool_called_with(self, tool_name: str, expected_input: dict[str, Any]) -> AssertionResult:
        calls = [
            s for s in self._tool_calls()
            if s.tool_call and s.tool_call.tool_name == tool_name
        ]
        if not calls:
            return self._fail("tool_called_with", f"Tool {tool_name!r} was never called", expected_input, None)
        for step in calls:
            assert step.tool_call is not None
            actual_input = step.tool_call.tool_input
            if isinstance(actual_input, dict) and _match_schema(actual_input, expected_input):
                return self._pass("tool_called_with", f"Tool {tool_name!r} called with matching input", expected_input, actual_input)
        # None matched
        all_inputs = [s.tool_call.tool_input for s in calls if s.tool_call]
        return self._fail("tool_called_with", f"Tool {tool_name!r} never called with matching input", expected_input, all_inputs)

    def tool_returned(self, tool_name: str, expected_output: Any) -> AssertionResult:
        calls = [
            s for s in self._tool_calls()
            if s.tool_call and s.tool_call.tool_name == tool_name
        ]
        if not calls:
            return self._fail("tool_returned", f"Tool {tool_name!r} was never called", expected_output, None)
        for step in calls:
            assert step.tool_call is not None
            actual_output = step.tool_call.tool_output
            if isinstance(expected_output, _Matcher):
                if expected_output.matches(actual_output):
                    return self._pass("tool_returned", f"Tool {tool_name!r} returned matching output", expected_output.description(), actual_output)
            elif isinstance(expected_output, dict):
                if _match_schema(actual_output, expected_output):
                    return self._pass("tool_returned", f"Tool {tool_name!r} returned matching output", expected_output, actual_output)
            elif actual_output == expected_output:
                return self._pass("tool_returned", f"Tool {tool_name!r} returned expected output", expected_output, actual_output)
        all_outputs = [s.tool_call.tool_output for s in calls if s.tool_call]
        return self._fail("tool_returned", f"Tool {tool_name!r} never returned expected output", expected_output, all_outputs)

    def steps_less_than(self, max_steps: int) -> AssertionResult:
        rec = self._require_recording()
        count = rec.step_count
        if count < max_steps:
            return self._pass("steps_less_than", f"Step count {count} < {max_steps}", max_steps, count)
        return self._fail("steps_less_than", f"Step count {count} >= {max_steps}", max_steps, count)

    def steps_greater_than(self, min_steps: int) -> AssertionResult:
        rec = self._require_recording()
        count = rec.step_count
        if count > min_steps:
            return self._pass("steps_greater_than", f"Step count {count} > {min_steps}", min_steps, count)
        return self._fail("steps_greater_than", f"Step count {count} <= {min_steps}", min_steps, count)

    def steps_between(self, min_steps: int, max_steps: int) -> AssertionResult:
        rec = self._require_recording()
        count = rec.step_count
        if min_steps <= count <= max_steps:
            return self._pass("steps_between", f"Step count {count} in [{min_steps}, {max_steps}]", (min_steps, max_steps), count)
        return self._fail("steps_between", f"Step count {count} not in [{min_steps}, {max_steps}]", (min_steps, max_steps), count)

    def no_repeated_tool_calls(self, max_repeats: int = 3) -> AssertionResult:
        tool_names = [
            s.tool_call.tool_name for s in self._tool_calls()
            if s.tool_call is not None
        ]
        counts = Counter(tool_names)
        offenders = {name: cnt for name, cnt in counts.items() if cnt > max_repeats}
        if not offenders:
            return self._pass("no_repeated_tool_calls", f"No tool called more than {max_repeats} time(s)", max_repeats, dict(counts))
        return self._fail("no_repeated_tool_calls", f"Tools called too many times: {offenders}", max_repeats, offenders)

    def used_model(self, model_name: str) -> AssertionResult:
        rec = self._require_recording()
        models_used: set[str] = set()
        for step in rec.steps:
            if step.llm_call is not None:
                models_used.add(step.llm_call.model)
        if not models_used:
            # Fall back to environment
            if rec.environment.model:
                models_used.add(rec.environment.model)
        if model_name in models_used:
            return self._pass("used_model", f"Model {model_name!r} was used", model_name, models_used)
        return self._fail("used_model", f"Model {model_name!r} was not used", model_name, models_used)

    def no_errors(self) -> AssertionResult:
        rec = self._require_recording()
        errors: list[str] = []
        for step in rec.steps:
            if step.tool_call and step.tool_call.error:
                errors.append(f"Step {step.step_number}: tool error: {step.tool_call.error}")
            if step.tool_call and not step.tool_call.success:
                errors.append(f"Step {step.step_number}: tool call failed")
        if not errors:
            return self._pass("no_errors", "No errors in any step", "no errors", [])
        return self._fail("no_errors", f"Found {len(errors)} error(s)", "no errors", errors)

    def completed_successfully(self) -> AssertionResult:
        rec = self._require_recording()
        status = rec.output.status
        if status == OutputStatus.SUCCESS:
            return self._pass("completed_successfully", "Agent completed successfully", OutputStatus.SUCCESS.value, status.value)
        return self._fail("completed_successfully", f"Agent status: {status.value}", OutputStatus.SUCCESS.value, status.value)

    # ===================================================================
    # Performance Assertions
    # ===================================================================

    def total_cost_less_than(self, max_cost: float) -> AssertionResult:
        rec = self._require_recording()
        cost = rec.total_cost
        if cost < max_cost:
            return self._pass("total_cost_less_than", f"Total cost ${cost:.6f} < ${max_cost:.6f}", max_cost, cost)
        return self._fail("total_cost_less_than", f"Total cost ${cost:.6f} >= ${max_cost:.6f}", max_cost, cost)

    def total_cost_greater_than(self, min_cost: float) -> AssertionResult:
        rec = self._require_recording()
        cost = rec.total_cost
        if cost > min_cost:
            return self._pass("total_cost_greater_than", f"Total cost ${cost:.6f} > ${min_cost:.6f}", min_cost, cost)
        return self._fail("total_cost_greater_than", f"Total cost ${cost:.6f} <= ${min_cost:.6f}", min_cost, cost)

    def cost_per_step_less_than(self, max_cost: float) -> AssertionResult:
        rec = self._require_recording()
        llm_steps = rec.llm_steps
        if not llm_steps:
            return self._pass("cost_per_step_less_than", "No LLM steps to evaluate", max_cost, 0)
        for step in llm_steps:
            assert step.llm_call is not None
            if step.llm_call.cost_usd >= max_cost:
                return self._fail(
                    "cost_per_step_less_than",
                    f"Step {step.step_number} cost ${step.llm_call.cost_usd:.6f} >= ${max_cost:.6f}",
                    max_cost, step.llm_call.cost_usd,
                )
        return self._pass("cost_per_step_less_than", f"All step costs < ${max_cost:.6f}", max_cost, None)

    def total_latency_less_than(self, max_ms: int) -> AssertionResult:
        rec = self._require_recording()
        total = rec.total_duration
        if total < max_ms:
            return self._pass("total_latency_less_than", f"Total latency {total:.1f}ms < {max_ms}ms", max_ms, total)
        return self._fail("total_latency_less_than", f"Total latency {total:.1f}ms >= {max_ms}ms", max_ms, total)

    def step_latency_less_than(self, max_ms: int) -> AssertionResult:
        rec = self._require_recording()
        for step in rec.steps:
            if step.duration_ms >= max_ms:
                return self._fail(
                    "step_latency_less_than",
                    f"Step {step.step_number} latency {step.duration_ms:.1f}ms >= {max_ms}ms",
                    max_ms, step.duration_ms,
                )
        return self._pass("step_latency_less_than", f"All step latencies < {max_ms}ms", max_ms, None)

    def total_tokens_less_than(self, max_tokens: int) -> AssertionResult:
        rec = self._require_recording()
        tokens = rec.total_tokens
        if tokens < max_tokens:
            return self._pass("total_tokens_less_than", f"Total tokens {tokens} < {max_tokens}", max_tokens, tokens)
        return self._fail("total_tokens_less_than", f"Total tokens {tokens} >= {max_tokens}", max_tokens, tokens)

    def input_tokens_less_than(self, max_tokens: int) -> AssertionResult:
        rec = self._require_recording()
        tokens = sum(s.llm_call.input_tokens for s in rec.steps if s.llm_call is not None)
        if tokens < max_tokens:
            return self._pass("input_tokens_less_than", f"Input tokens {tokens} < {max_tokens}", max_tokens, tokens)
        return self._fail("input_tokens_less_than", f"Input tokens {tokens} >= {max_tokens}", max_tokens, tokens)

    def output_tokens_less_than(self, max_tokens: int) -> AssertionResult:
        rec = self._require_recording()
        tokens = sum(s.llm_call.output_tokens for s in rec.steps if s.llm_call is not None)
        if tokens < max_tokens:
            return self._pass("output_tokens_less_than", f"Output tokens {tokens} < {max_tokens}", max_tokens, tokens)
        return self._fail("output_tokens_less_than", f"Output tokens {tokens} >= {max_tokens}", max_tokens, tokens)

    # ===================================================================
    # Safety Assertions
    # ===================================================================

    def output_not_contains_any(self, patterns: list[str], case_sensitive: bool = True) -> AssertionResult:
        output = self._output_text()
        haystack = output if case_sensitive else output.lower()
        found: list[str] = []
        for p in patterns:
            needle = p if case_sensitive else p.lower()
            if needle in haystack:
                found.append(p)
        if not found:
            return self._pass("output_not_contains_any", "Output does not contain any forbidden patterns", patterns, output)
        return self._fail("output_not_contains_any", f"Output contains forbidden patterns: {found!r}", patterns, found)

    def no_pii_in_output(self) -> AssertionResult:
        output = self._output_text()
        detections: list[str] = []
        for label, pattern in _PII_PATTERNS:
            matches = pattern.findall(output)
            if matches:
                detections.append(f"{label}: {len(matches)} match(es)")
        if not detections:
            return self._pass("no_pii_in_output", "No PII detected in output", "no PII", [])
        return self._fail("no_pii_in_output", f"PII detected: {'; '.join(detections)}", "no PII", detections)

    def output_relevant_to(self, input_text: str, threshold: float = 0.6) -> AssertionResult:
        output = self._output_text()
        similarity = _embedding_similarity(output, input_text)
        method = "embedding"
        if similarity is None:
            similarity = _simple_similarity(output, input_text)
            method = "sequence_matcher"
        if similarity >= threshold:
            return self._pass(
                "output_relevant_to",
                f"Output relevant to input (similarity={similarity:.3f}, method={method}, threshold={threshold})",
                input_text, output,
            )
        return self._fail(
            "output_relevant_to",
            f"Output not relevant to input (similarity={similarity:.3f}, method={method}, threshold={threshold})",
            input_text, output,
        )

    # ===================================================================
    # Static matcher factories
    # ===================================================================

    @staticmethod
    def any_string() -> _AnyString:
        return _AnyString()

    @staticmethod
    def any_int() -> _AnyInt:
        return _AnyInt()

    @staticmethod
    def any_float() -> _AnyFloat:
        return _AnyFloat()

    @staticmethod
    def contains(text: str) -> _Contains:
        return _Contains(text)

    @staticmethod
    def less_than(value: float) -> _LessThan:
        return _LessThan(value)

    @staticmethod
    def greater_than(value: float) -> _GreaterThan:
        return _GreaterThan(value)

    @staticmethod
    def list_of(item_matcher: Any, min_length: int = 0) -> _ListOf:
        return _ListOf(item_matcher, min_length)

    # ===================================================================
    # Results
    # ===================================================================

    def get_results(self) -> list[AssertionResult]:
        return list(self._results)

    def all_passed(self) -> bool:
        return all(r.passed for r in self._results)

    def summary(self) -> str:
        """Return a formatted summary of all assertion results."""
        if not self._results:
            return "No assertions recorded."

        lines: list[str] = []
        passed = sum(1 for r in self._results if r.passed)
        failed = sum(1 for r in self._results if not r.passed)
        total = len(self._results)

        lines.append(f"Assertion Summary: {passed}/{total} passed, {failed} failed")
        lines.append("-" * 60)

        for r in self._results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.assertion_name}: {r.message}")

        lines.append("-" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

assertions = Assertions()
A = assertions
