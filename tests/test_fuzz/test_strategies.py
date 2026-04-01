"""Tests for agentprobe.fuzz.strategies."""

from __future__ import annotations

import pytest

from agentprobe.fuzz.strategies import (
    BoundaryTesting,
    EdgeCases,
    PromptInjection,
    ToolFailures,
)


class TestPromptInjectionGeneratesVariants:
    def test_prompt_injection_generates_variants(self) -> None:
        strategy = PromptInjection(num_variants=20)
        variants = strategy.generate_variants("What is the weather?")
        assert isinstance(variants, list)
        assert len(variants) > 0
        assert len(variants) <= 20
        assert all(isinstance(v, str) for v in variants)

    def test_prompt_injection_all_techniques(self) -> None:
        strategy = PromptInjection(num_variants=200)
        variants = strategy.generate_variants("Hello world")
        assert len(variants) > 10  # should generate many variants

    def test_prompt_injection_single_technique(self) -> None:
        strategy = PromptInjection(
            techniques=["ignore_instructions"], num_variants=100
        )
        variants = strategy.generate_variants("Test input")
        assert len(variants) > 0
        # All should contain instruction-override patterns
        assert any("ignore" in v.lower() or "disregard" in v.lower() for v in variants)

    def test_prompt_injection_contains_base_input(self) -> None:
        base = "Summarize this document"
        strategy = PromptInjection(
            techniques=["ignore_instructions"], num_variants=100
        )
        variants = strategy.generate_variants(base)
        # Many variants should include the base input
        assert any(base in v for v in variants)


class TestEdgeCasesGeneratesVariants:
    def test_edge_cases_generates_variants(self) -> None:
        strategy = EdgeCases()
        variants = strategy.generate_variants("Hello")
        assert isinstance(variants, list)
        assert len(variants) > 0
        assert all(isinstance(v, str) for v in variants)

    def test_edge_cases_includes_empty(self) -> None:
        strategy = EdgeCases(techniques=["empty_input"])
        variants = strategy.generate_variants("test")
        # Should include empty and whitespace-only strings
        assert "" in variants or any(v.strip() == "" for v in variants)

    def test_edge_cases_includes_long_input(self) -> None:
        strategy = EdgeCases(techniques=["very_long_input"])
        variants = strategy.generate_variants("x")
        assert any(len(v) > 1000 for v in variants)

    def test_edge_cases_single_technique(self) -> None:
        strategy = EdgeCases(techniques=["contradictory_input"])
        variants = strategy.generate_variants("do this")
        assert len(variants) > 0
        assert any("don't" in v or "opposite" in v.lower() or "not" in v.lower() for v in variants)


class TestToolFailuresGeneratesConfigs:
    def test_tool_failures_generates_configs(self) -> None:
        strategy = ToolFailures()
        configs = strategy.generate_failure_configs()
        assert isinstance(configs, list)
        assert len(configs) > 0
        # Each config should have a type
        assert all("type" in c for c in configs)

    def test_tool_failures_includes_timeout(self) -> None:
        strategy = ToolFailures(techniques=["timeout"])
        configs = strategy.generate_failure_configs()
        assert len(configs) > 0
        assert all(c["type"] == "timeout" for c in configs)
        assert all("delay_ms" in c for c in configs)

    def test_tool_failures_includes_error_500(self) -> None:
        strategy = ToolFailures(techniques=["error_500"])
        configs = strategy.generate_failure_configs()
        assert len(configs) > 0
        assert all("status_code" in c for c in configs)

    def test_tool_failures_generate_variants_passthrough(self) -> None:
        strategy = ToolFailures()
        variants = strategy.generate_variants("input text")
        # ToolFailures does not mutate the input
        assert variants == ["input text"]


class TestBoundaryTesting:
    def test_boundary_testing(self) -> None:
        strategy = BoundaryTesting(
            scope="customer support",
            out_of_scope=["write code", "medical advice"],
            num_variants=50,
        )
        variants = strategy.generate_variants("Help me with my order")
        assert isinstance(variants, list)
        assert len(variants) > 0
        assert all(isinstance(v, str) for v in variants)

    def test_boundary_testing_includes_in_scope(self) -> None:
        strategy = BoundaryTesting(
            scope="weather",
            out_of_scope=["cooking"],
            num_variants=50,
        )
        variants = strategy.generate_variants("What is the weather?")
        # Should include rephrased in-scope requests
        assert any("weather" in v.lower() for v in variants)

    def test_boundary_testing_includes_out_of_scope(self) -> None:
        strategy = BoundaryTesting(
            scope="weather",
            out_of_scope=["cooking recipes"],
            num_variants=50,
        )
        variants = strategy.generate_variants("What is the weather?")
        assert any("cooking" in v.lower() for v in variants)

    def test_boundary_testing_includes_drift(self) -> None:
        strategy = BoundaryTesting(
            scope="math tutoring",
            out_of_scope=["write my essay"],
            num_variants=50,
        )
        variants = strategy.generate_variants("Help me with calculus")
        # Drift variants combine in-scope and out-of-scope
        assert any(
            "calculus" in v.lower() and "essay" in v.lower() for v in variants
        )
