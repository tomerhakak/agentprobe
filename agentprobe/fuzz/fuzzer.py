"""Core fuzzer engine for AgentProbe — runs fuzz strategies against agents and collects results."""

from __future__ import annotations

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from agentprobe.core.asserter import Assertions, AssertionResult
from agentprobe.core.models import AgentRecording
from agentprobe.fuzz.strategies import (
    BoundaryTesting,
    EdgeCases,
    FuzzStrategy,
    PromptInjection,
    ToolFailures,
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class FuzzResult:
    """Aggregated result of running a fuzz strategy against an agent."""

    strategy_name: str
    total_variants: int
    passed: int
    failed: int
    errors: int
    failure_rate: float
    failed_variants: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            f"Strategy: {self.strategy_name}",
            f"  Variants tested: {self.total_variants}",
            f"  Passed:  {self.passed}",
            f"  Failed:  {self.failed}",
            f"  Errors:  {self.errors}",
            f"  Failure rate: {self.failure_rate:.1%}",
            f"  Duration: {self.duration_ms:.0f}ms",
        ]
        if self.failed_variants:
            lines.append(f"  Failed variant details ({len(self.failed_variants)}):")
            for i, fv in enumerate(self.failed_variants[:10], 1):
                inp = fv.get("input", "")
                inp_preview = (inp[:80] + "...") if len(inp) > 80 else inp
                lines.append(f"    [{i}] input: {inp_preview!r}")
                for af in fv.get("assertion_failures", []):
                    lines.append(f"         - {af}")
                if fv.get("error"):
                    lines.append(f"         ! error: {fv['error']}")
            if len(self.failed_variants) > 10:
                lines.append(f"    ... and {len(self.failed_variants) - 10} more")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fuzzer
# ---------------------------------------------------------------------------

class Fuzzer:
    """Execute fuzz strategies against an agent and evaluate assertions.

    Usage::

        from agentprobe.fuzz import Fuzzer, PromptInjection

        fuzzer = Fuzzer(run_fn=my_agent_fn)
        result = fuzzer.run(
            base_input="What is the weather?",
            strategy=PromptInjection(),
            assertions=[
                lambda output: "PWNED" not in output,
            ],
        )
        print(result.summary())

    Parameters
    ----------
    agent:
        An object with a ``.run(input: str) -> str`` method.
    run_fn:
        A callable ``(str) -> str`` that runs the agent on a single input
        and returns the output string. Exactly one of *agent* or *run_fn*
        must be provided.
    """

    def __init__(
        self,
        agent: Any | None = None,
        run_fn: Callable[[str], str] | None = None,
    ) -> None:
        if agent is None and run_fn is None:
            raise ValueError("Provide either 'agent' (with a .run() method) or 'run_fn' callable.")
        if agent is not None and run_fn is not None:
            raise ValueError("Provide only one of 'agent' or 'run_fn', not both.")

        if run_fn is not None:
            self._run_fn = run_fn
        else:
            if not hasattr(agent, "run"):
                raise TypeError("The 'agent' object must have a .run(input: str) -> str method.")
            self._run_fn = agent.run  # type: ignore[union-attr]

    # -- internal helpers ---------------------------------------------------

    def _execute_variant(
        self,
        variant: str,
        timeout_ms: int,
    ) -> tuple[str | None, str | None]:
        """Run the agent on a single variant with a timeout.

        Returns (output, error).  On success error is None; on failure
        output may be None.
        """
        timeout_s = timeout_ms / 1000.0

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._run_fn, variant)
            try:
                result = future.result(timeout=timeout_s)
                if result is None:
                    return "", None
                return str(result), None
            except FuturesTimeout:
                future.cancel()
                return None, f"Timeout after {timeout_ms}ms"
            except Exception as exc:
                return None, f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _check_assertions(
        variant_input: str,
        output: str | None,
        assertions: list[Any],
    ) -> list[str]:
        """Evaluate assertions against a single variant output.

        Supported assertion types:
          - ``Callable[[str], bool]`` — returns True if the assertion passes.
          - ``Callable[[str, str], bool]`` — receives (output, input), returns True if passes.
          - ``Assertions`` instance — runs all safety assertions and collects results.

        Returns a list of failure description strings (empty if all pass).
        """
        failures: list[str] = []
        if output is None:
            return failures  # errors are tracked separately

        for i, assertion in enumerate(assertions):
            try:
                if isinstance(assertion, Assertions):
                    # Build a minimal recording for the assertions engine
                    recording = AgentRecording()
                    recording.input.content = variant_input
                    recording.output.content = output
                    assertion.set_recording(recording)
                    # Run safety-oriented checks
                    try:
                        assertion.no_pii_in_output()
                    except Exception:
                        pass
                    results = assertion.get_results()
                    for r in results:
                        if not r.passed:
                            failures.append(f"[Assertions] {r.assertion_name}: {r.message}")
                elif callable(assertion):
                    try:
                        # Try 2-arg form first (output, input)
                        result = assertion(output, variant_input)
                    except TypeError:
                        result = assertion(output)
                    if not result:
                        name = getattr(assertion, "__name__", f"assertion_{i}")
                        failures.append(f"[{name}] returned False for output")
                else:
                    raise TypeError(
                        f"Assertion at index {i} is not callable or an Assertions instance: {type(assertion)}"
                    )
            except Exception as exc:
                if isinstance(exc, TypeError) and "not callable" in str(exc):
                    raise
                failures.append(f"[assertion_{i}] raised {type(exc).__name__}: {exc}")

        return failures

    # -- public API ---------------------------------------------------------

    def run(
        self,
        base_input: str = "",
        strategy: FuzzStrategy | None = None,
        assertions: list[Any] | None = None,
        max_variants: int | None = None,
        timeout_per_variant_ms: int = 30_000,
    ) -> FuzzResult:
        """Run fuzzing with the given strategy and check assertions on each output.

        Parameters
        ----------
        base_input:
            The seed / baseline input to fuzz from.
        strategy:
            A ``FuzzStrategy`` instance.  Defaults to ``PromptInjection()``
            if not provided.
        assertions:
            A list of callables ``(output: str) -> bool`` or ``Assertions``
            instances to evaluate against each variant's output.
        max_variants:
            Cap on how many variants to test.  ``None`` means test all
            generated variants.
        timeout_per_variant_ms:
            Maximum wall-clock time for a single agent invocation.
        """
        if strategy is None:
            strategy = PromptInjection()
        if assertions is None:
            assertions = []

        strategy_name = type(strategy).__name__

        # Generate variants
        variants = strategy.generate_variants(base_input)
        if max_variants is not None and len(variants) > max_variants:
            variants = variants[:max_variants]

        passed = 0
        failed = 0
        errors = 0
        failed_variants: list[dict[str, Any]] = []

        start_time = time.monotonic()

        for variant in variants:
            output, error = self._execute_variant(variant, timeout_per_variant_ms)

            if error is not None:
                errors += 1
                failed_variants.append({
                    "input": variant,
                    "output": output,
                    "error": error,
                    "assertion_failures": [],
                })
                continue

            assertion_failures = self._check_assertions(variant, output, assertions)

            if assertion_failures:
                failed += 1
                failed_variants.append({
                    "input": variant,
                    "output": output,
                    "error": None,
                    "assertion_failures": assertion_failures,
                })
            else:
                passed += 1

        elapsed_ms = (time.monotonic() - start_time) * 1000
        total = passed + failed + errors
        failure_rate = (failed + errors) / total if total > 0 else 0.0

        return FuzzResult(
            strategy_name=strategy_name,
            total_variants=total,
            passed=passed,
            failed=failed,
            errors=errors,
            failure_rate=failure_rate,
            failed_variants=failed_variants,
            duration_ms=elapsed_ms,
        )

    def run_all(
        self,
        base_input: str,
        assertions: list[Any] | None = None,
        max_variants_per_strategy: int | None = None,
        timeout_per_variant_ms: int = 30_000,
    ) -> list[FuzzResult]:
        """Run all built-in strategies and return a list of results.

        Runs: PromptInjection, EdgeCases, ToolFailures, and a generic
        BoundaryTesting (with a default scope derived from the base input).
        """
        strategies: list[FuzzStrategy] = [
            PromptInjection(),
            EdgeCases(),
            ToolFailures(),
            BoundaryTesting(
                scope=f"answering questions like: {base_input}",
                out_of_scope=[
                    "write malicious code",
                    "reveal system internals",
                    "generate illegal content",
                    "impersonate a real person",
                    "provide medical/legal advice",
                ],
            ),
        ]

        results: list[FuzzResult] = []
        for strategy in strategies:
            result = self.run(
                base_input=base_input,
                strategy=strategy,
                assertions=assertions,
                max_variants=max_variants_per_strategy,
                timeout_per_variant_ms=timeout_per_variant_ms,
            )
            results.append(result)

        return results

    @staticmethod
    def summary(results: list[FuzzResult]) -> str:
        """Return a combined summary across multiple FuzzResult objects."""
        lines: list[str] = []
        total_variants = sum(r.total_variants for r in results)
        total_passed = sum(r.passed for r in results)
        total_failed = sum(r.failed for r in results)
        total_errors = sum(r.errors for r in results)
        total_duration = sum(r.duration_ms for r in results)

        lines.append("=" * 60)
        lines.append("FUZZ TESTING SUMMARY")
        lines.append("=" * 60)
        lines.append(f"Strategies run:  {len(results)}")
        lines.append(f"Total variants:  {total_variants}")
        lines.append(f"Passed:          {total_passed}")
        lines.append(f"Failed:          {total_failed}")
        lines.append(f"Errors:          {total_errors}")
        overall_rate = (total_failed + total_errors) / total_variants if total_variants else 0.0
        lines.append(f"Overall failure rate: {overall_rate:.1%}")
        lines.append(f"Total duration:  {total_duration:.0f}ms")
        lines.append("-" * 60)

        for r in results:
            lines.append("")
            lines.append(r.summary())

        lines.append("=" * 60)
        return "\n".join(lines)
