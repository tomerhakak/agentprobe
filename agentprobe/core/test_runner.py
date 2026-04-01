"""Test runner for AgentProbe -- discovers and executes agent test functions."""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from agentprobe.core.asserter import AssertionResult, Assertions, assertions
from agentprobe.core.models import AgentRecording


# ---------------------------------------------------------------------------
# @test decorator
# ---------------------------------------------------------------------------

def test(
    recording: str | AgentRecording | None = None,
    mocks: dict[str, Any] | None = None,
    llm: str | None = None,
    tags: list[str] | None = None,
) -> Callable[..., Any]:
    """Decorator that marks a function as an AgentProbe test.

    Parameters
    ----------
    recording:
        Path to a ``.aprobe`` file or an :class:`AgentRecording` instance.
        If ``None``, the test must load or create its own recording.
    mocks:
        Dictionary of tool-name -> mock-return-value pairs to inject.
    llm:
        Override the LLM model name for replay.
    tags:
        Tags for filtering during test runs (e.g. ``["regression", "fast"]``).
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        # Attach metadata to the function
        wrapper._agentprobe_test = True  # type: ignore[attr-defined]
        wrapper._agentprobe_recording = recording  # type: ignore[attr-defined]
        wrapper._agentprobe_mocks = mocks  # type: ignore[attr-defined]
        wrapper._agentprobe_llm = llm  # type: ignore[attr-defined]
        wrapper._agentprobe_tags = tags or []  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _is_agentprobe_test(obj: Any) -> bool:
    """Check whether *obj* is a function decorated with ``@test``."""
    return callable(obj) and getattr(obj, "_agentprobe_test", False) is True


# ---------------------------------------------------------------------------
# TestResult
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """Result of running a single AgentProbe test."""

    test_name: str
    passed: bool
    assertion_results: list[AssertionResult] = field(default_factory=list)
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# TestSuite
# ---------------------------------------------------------------------------

class TestSuite:
    """Discovers and runs AgentProbe tests.

    Parameters
    ----------
    config:
        Optional configuration dict.  Reserved for future use (e.g.
        default recording path, default LLM, cost budgets).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._discovered: list[Callable[..., Any]] = []

    # -- discovery ----------------------------------------------------------

    def discover(self, path: str = "tests/agentprobe") -> list[Callable[..., Any]]:
        """Discover all AgentProbe test functions in *path*.

        Scans Python files matching ``test_*.py`` or ``*_test.py`` in the
        given directory (recursively).  Functions decorated with ``@test``
        are collected.

        Returns the list of discovered test callables (also stored internally).
        """
        root = Path(path).resolve()
        tests: list[Callable[..., Any]] = []

        if root.is_file() and root.suffix == ".py":
            files = [root]
        elif root.is_dir():
            files = sorted(
                p
                for p in root.rglob("*.py")
                if p.name.startswith("test_") or p.name.endswith("_test.py")
            )
        else:
            self._discovered = []
            return []

        for filepath in files:
            module = self._load_module(filepath)
            if module is None:
                continue
            for name, obj in inspect.getmembers(module):
                if _is_agentprobe_test(obj):
                    tests.append(obj)

        self._discovered = tests
        return tests

    @staticmethod
    def _load_module(filepath: Path) -> Any | None:
        """Dynamically import a Python file as a module."""
        module_name = f"agentprobe_test_{filepath.stem}_{id(filepath)}"
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Make sure the module's directory is on sys.path so relative imports work
        parent = str(filepath.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception:
            # If a test file has import errors, skip it but don't crash
            traceback.print_exc()
            return None
        return module

    # -- execution ----------------------------------------------------------

    def run(
        self,
        tests: list[Callable[..., Any]] | None = None,
        parallel: int = 1,
        max_cost: float | None = None,
        tags: list[str] | None = None,
    ) -> list[TestResult]:
        """Run a list of AgentProbe tests and return their results.

        Parameters
        ----------
        tests:
            Test callables to run.  Defaults to whatever was last discovered.
        parallel:
            Max number of tests to run concurrently.
        max_cost:
            If the cumulative cost of completed tests exceeds this, stop early.
        tags:
            Only run tests whose tags overlap with this list.  ``None`` means
            run all.
        """
        targets = tests if tests is not None else self._discovered
        if not targets:
            return []

        # Filter by tags if specified
        if tags:
            tag_set = set(tags)
            targets = [
                t for t in targets
                if tag_set & set(getattr(t, "_agentprobe_tags", []))
            ]

        results: list[TestResult] = []
        cumulative_cost = 0.0

        if parallel <= 1:
            for t in targets:
                result = self.run_single(t)
                results.append(result)
                cumulative_cost += result.cost_usd
                if max_cost is not None and cumulative_cost >= max_cost:
                    break
        else:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_to_test = {executor.submit(self.run_single, t): t for t in targets}
                for future in as_completed(future_to_test):
                    result = future.result()
                    results.append(result)
                    cumulative_cost += result.cost_usd
                    if max_cost is not None and cumulative_cost >= max_cost:
                        # Cancel remaining futures (best effort)
                        for f in future_to_test:
                            f.cancel()
                        break

        return results

    def run_single(self, test_func: Callable[..., Any]) -> TestResult:
        """Run a single AgentProbe test function and return its result."""
        test_name = getattr(test_func, "__qualname__", None) or getattr(test_func, "__name__", str(test_func))

        # Create a fresh Assertions instance for this test
        test_assertions = Assertions()

        # Resolve the recording
        recording_ref = getattr(test_func, "_agentprobe_recording", None)
        recording: AgentRecording | None = None

        if isinstance(recording_ref, AgentRecording):
            recording = recording_ref
        elif isinstance(recording_ref, str):
            try:
                recording = AgentRecording.load(recording_ref)
            except Exception as exc:
                return TestResult(
                    test_name=test_name,
                    passed=False,
                    error=f"Failed to load recording {recording_ref!r}: {exc}",
                )

        if recording is not None:
            test_assertions.set_recording(recording)

        # Determine what arguments the test function expects
        sig = inspect.signature(test_func)
        kwargs: dict[str, Any] = {}
        for param_name in sig.parameters:
            if param_name in ("assertions", "A", "a"):
                kwargs[param_name] = test_assertions
            elif param_name == "recording":
                kwargs[param_name] = recording

        start = time.perf_counter_ns()
        error: str | None = None
        passed = True

        try:
            test_func(**kwargs)
        except Exception as exc:
            passed = False
            # If it's our assertion error, that's expected flow
            from agentprobe.core.asserter import AssertionError as APAssertionError
            if not isinstance(exc, APAssertionError):
                error = f"{type(exc).__name__}: {exc}"
            else:
                error = str(exc)
        finally:
            duration_ms = (time.perf_counter_ns() - start) / 1_000_000

        assertion_results = test_assertions.get_results()
        if not passed and error is None:
            # Might have failed assertions
            pass

        cost = recording.total_cost if recording is not None else 0.0

        return TestResult(
            test_name=test_name,
            passed=passed and test_assertions.all_passed(),
            assertion_results=assertion_results,
            duration_ms=duration_ms,
            cost_usd=cost,
            error=error,
        )
