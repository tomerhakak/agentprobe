"""Natural Language Test Generator.

Write agent tests in plain English — AgentProbe translates them to
executable Python test code with proper assertions.

Examples:
    "The agent should respond in under 5 seconds"
    "The agent must not use more than $0.10"
    "The agent should call the search tool at least once"
    "The agent must not leak PII in the output"
    "The output should contain a JSON object"

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Pattern matchers — NL to assertion mapping
# ---------------------------------------------------------------------------

@dataclass
class AssertionPattern:
    """Maps a natural language pattern to an assertion function."""

    pattern: str  # regex pattern
    assertion_func: str
    args_extractor: str  # how to extract args from regex groups
    description: str


_PATTERNS: List[AssertionPattern] = [
    # Cost assertions
    AssertionPattern(
        pattern=r"(?:cost|spend|price)\s+(?:less|under|below|at most|max|maximum)\s+\$?(\d+\.?\d*)",
        assertion_func="assertions.cost_below",
        args_extractor="max_cost_usd={0}",
        description="Assert total cost is below a threshold",
    ),
    AssertionPattern(
        pattern=r"(?:cost|spend)\s+(?:more|above|over|at least|minimum)\s+\$?(\d+\.?\d*)",
        assertion_func="assertions.cost_above",
        args_extractor="min_cost_usd={0}",
        description="Assert total cost is above a threshold",
    ),

    # Latency assertions
    AssertionPattern(
        pattern=r"(?:respond|finish|complete|run)\s+(?:in|within|under)\s+(\d+\.?\d*)\s*(s|sec|seconds?|ms|milliseconds?|m|min|minutes?)",
        assertion_func="assertions.latency_below",
        args_extractor="max_ms={ms}",
        description="Assert total latency is below a threshold",
    ),
    AssertionPattern(
        pattern=r"(?:faster|quicker)\s+than\s+(\d+\.?\d*)\s*(s|sec|seconds?|ms|milliseconds?)",
        assertion_func="assertions.latency_below",
        args_extractor="max_ms={ms}",
        description="Assert total latency is below a threshold",
    ),

    # Tool assertions
    AssertionPattern(
        pattern=r"(?:call|use|invoke)\s+(?:the\s+)?(\w+)\s+tool\s+(?:at least\s+)?(\d+)\s+times?",
        assertion_func="assertions.called_tool_n_times",
        args_extractor='tool_name="{0}", min_times={1}',
        description="Assert a specific tool was called N times",
    ),
    AssertionPattern(
        pattern=r"(?:call|use|invoke)\s+(?:the\s+)?(\w+)\s+tool",
        assertion_func="assertions.called_tool",
        args_extractor='tool_name="{0}"',
        description="Assert a specific tool was called",
    ),
    AssertionPattern(
        pattern=r"(?:not|never|don'?t)\s+(?:call|use|invoke)\s+(?:the\s+)?(\w+)\s+tool",
        assertion_func="assertions.did_not_call_tool",
        args_extractor='tool_name="{0}"',
        description="Assert a specific tool was NOT called",
    ),

    # Output assertions
    AssertionPattern(
        pattern=r"(?:output|response|result)\s+(?:should\s+)?(?:contain|include|have)\s+['\"](.+?)['\"]",
        assertion_func="assertions.output_contains",
        args_extractor='substring="{0}"',
        description="Assert output contains a substring",
    ),
    AssertionPattern(
        pattern=r"(?:output|response|result)\s+(?:should\s+)?(?:not\s+)?(?:be\s+)?empty",
        assertion_func="assertions.output_is_not_empty",
        args_extractor="",
        description="Assert output is not empty",
    ),
    AssertionPattern(
        pattern=r"(?:output|response|result)\s+(?:should\s+)?(?:contain|be|have|include)\s+(?:a\s+)?(?:valid\s+)?json",
        assertion_func="assertions.output_is_valid_json",
        args_extractor="",
        description="Assert output is valid JSON",
    ),

    # Step count
    AssertionPattern(
        pattern=r"(?:use|take|require)\s+(?:less|fewer|under|at most|max)\s+(?:than\s+)?(\d+)\s+steps?",
        assertion_func="assertions.max_steps",
        args_extractor="max_steps={0}",
        description="Assert maximum number of steps",
    ),

    # Token assertions
    AssertionPattern(
        pattern=r"(?:use|consume|spend)\s+(?:less|under|below|at most|max)\s+(?:than\s+)?(\d+[kK]?)\s+tokens?",
        assertion_func="assertions.max_tokens",
        args_extractor="max_tokens={tokens}",
        description="Assert maximum token usage",
    ),

    # Security assertions
    AssertionPattern(
        pattern=r"(?:not|never|don'?t|no)\s+(?:leak|expose|reveal|contain|include|have)\s+(?:any\s+)?(?:PII|pii|personal\s+information|sensitive\s+data)",
        assertion_func="assertions.no_pii_in_output",
        args_extractor="",
        description="Assert no PII in output",
    ),

    # Success assertion
    AssertionPattern(
        pattern=r"(?:succeed|complete|finish)\s+(?:successfully|without\s+errors?)",
        assertion_func="assertions.succeeded",
        args_extractor="",
        description="Assert agent completed successfully",
    ),
    AssertionPattern(
        pattern=r"(?:no|not?|zero|don'?t\s+have)\s+errors?",
        assertion_func="assertions.no_errors",
        args_extractor="",
        description="Assert no errors occurred",
    ),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GeneratedAssertion:
    """A single generated assertion from natural language."""

    nl_input: str
    assertion_code: str
    assertion_func: str
    confidence: float = 0.0  # 0.0-1.0
    description: str = ""


@dataclass
class GeneratedTest:
    """A complete generated test function."""

    name: str
    nl_inputs: List[str]
    assertions: List[GeneratedAssertion] = field(default_factory=list)
    code: str = ""
    unmatched: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nl_inputs": self.nl_inputs,
            "code": self.code,
            "assertions": [
                {
                    "nl": a.nl_input,
                    "code": a.assertion_code,
                    "confidence": a.confidence,
                }
                for a in self.assertions
            ],
            "unmatched": self.unmatched,
        }


# ---------------------------------------------------------------------------
# NL Test Generator
# ---------------------------------------------------------------------------

class NLTestGenerator:
    """Generate executable test code from natural language descriptions.

    Usage::

        gen = NLTestGenerator()

        # Single assertion
        assertion = gen.translate("The agent should respond in under 5 seconds")
        print(assertion.assertion_code)
        # -> assertions.latency_below(recording, max_ms=5000)

        # Full test
        test = gen.generate_test("test_my_agent", [
            "The agent should respond in under 5 seconds",
            "The agent must not use more than $0.10",
            "The agent should call the search tool at least once",
            "The output should not be empty",
        ])
        print(test.code)  # Complete pytest function

        # Write to file
        gen.write_test_file("tests/test_generated.py", [test])
    """

    def __init__(self) -> None:
        self._patterns = list(_PATTERNS)

    def add_pattern(self, pattern: AssertionPattern) -> None:
        """Add a custom NL pattern."""
        self._patterns.append(pattern)

    def translate(self, nl_input: str) -> Optional[GeneratedAssertion]:
        """Translate a single natural language assertion to code."""
        cleaned = nl_input.strip().lower()
        cleaned = re.sub(r"^(the\s+agent\s+)?(should|must|has\s+to|needs\s+to|ought\s+to)\s+", "", cleaned)

        for pattern in self._patterns:
            match = re.search(pattern.pattern, cleaned, re.IGNORECASE)
            if match:
                args = self._extract_args(pattern, match, cleaned)
                code = f"{pattern.assertion_func}(recording, {args})" if args else f"{pattern.assertion_func}(recording)"
                return GeneratedAssertion(
                    nl_input=nl_input,
                    assertion_code=code,
                    assertion_func=pattern.assertion_func,
                    confidence=0.9 if len(match.group(0)) > len(cleaned) * 0.5 else 0.7,
                    description=pattern.description,
                )

        return None

    def generate_test(self, test_name: str, nl_descriptions: List[str]) -> GeneratedTest:
        """Generate a complete test function from NL descriptions."""
        if not test_name.startswith("test_"):
            test_name = f"test_{test_name}"

        test = GeneratedTest(name=test_name, nl_inputs=nl_descriptions)

        for desc in nl_descriptions:
            assertion = self.translate(desc)
            if assertion:
                test.assertions.append(assertion)
            else:
                test.unmatched.append(desc)

        # Generate code
        lines: List[str] = []
        lines.append(f"def {test_name}(recording):")
        lines.append(f'    """Generated from natural language descriptions.')
        lines.append(f"")
        for desc in nl_descriptions:
            lines.append(f"    - {desc}")
        lines.append(f'    """')

        for assertion in test.assertions:
            lines.append(f"    {assertion.assertion_code}")

        if test.unmatched:
            lines.append("")
            lines.append("    # The following could not be auto-translated:")
            for u in test.unmatched:
                lines.append(f"    # TODO: {u}")

        if not test.assertions and not test.unmatched:
            lines.append("    pass")

        test.code = "\n".join(lines)
        return test

    def generate_test_file(self, tests: List[GeneratedTest]) -> str:
        """Generate a complete test file with imports and multiple tests."""
        lines: List[str] = []
        lines.append('"""Auto-generated agent tests from natural language descriptions."""')
        lines.append("")
        lines.append("from agentprobe import assertions")
        lines.append("")
        lines.append("")

        for test in tests:
            lines.append(test.code)
            lines.append("")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def write_test_file(self, path: str, tests: List[GeneratedTest]) -> str:
        """Write generated tests to a file."""
        content = self.generate_test_file(tests)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return content

    # -- Args extraction ---------------------------------------------------

    def _extract_args(self, pattern: AssertionPattern, match: re.Match, cleaned: str) -> str:
        """Extract assertion arguments from regex match groups."""
        args = pattern.args_extractor
        if not args:
            return ""

        groups = match.groups()

        # Handle time conversion
        if "{ms}" in args:
            value = float(groups[0])
            unit = groups[1].lower() if len(groups) > 1 else "s"
            if unit.startswith("ms") or unit.startswith("milli"):
                ms = value
            elif unit.startswith("m") and not unit.startswith("ms"):
                ms = value * 60 * 1000
            else:
                ms = value * 1000
            args = args.replace("{ms}", str(int(ms)))
        elif "{tokens}" in args:
            raw = groups[0]
            if raw.lower().endswith("k"):
                tokens = int(float(raw[:-1]) * 1000)
            else:
                tokens = int(raw)
            args = args.replace("{tokens}", str(tokens))
        else:
            for i, group in enumerate(groups):
                args = args.replace(f"{{{i}}}", group)

        return args

    # -- Rendering ---------------------------------------------------------

    def render_translation(self, assertion: GeneratedAssertion) -> str:
        """Render a single translation result."""
        conf_bar = "\u2588" * int(assertion.confidence * 10) + "\u2591" * (10 - int(assertion.confidence * 10))
        return (
            f"   \U0001f4dd \"{assertion.nl_input}\"\n"
            f"   \u2192  {assertion.assertion_code}\n"
            f"      Confidence: [{conf_bar}] {assertion.confidence:.0%}"
        )

    def render_test(self, test: GeneratedTest) -> str:
        """Render a generated test summary."""
        lines: List[str] = []
        lines.append(f"\U0001f9ea Generated Test: {test.name}")
        lines.append(f"   Assertions: {len(test.assertions)}")
        if test.unmatched:
            lines.append(f"   Unmatched: {len(test.unmatched)}")
        lines.append("")
        lines.append(test.code)
        return "\n".join(lines)
