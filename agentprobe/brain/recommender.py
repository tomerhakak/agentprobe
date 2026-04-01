"""The brain's recommendation engine -- suggests improvements based on learned patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from agentprobe.brain.store import BrainStore


# ---------------------------------------------------------------------------
# Cost bucket ordering for comparison
# ---------------------------------------------------------------------------

_COST_BUCKET_ORDER = ["<$0.01", "$0.01-$0.05", "$0.05-$0.10", "$0.10-$0.50", ">$0.50"]
_COST_BUCKET_MIDPOINTS = {
    "<$0.01": 0.005,
    "$0.01-$0.05": 0.03,
    "$0.05-$0.10": 0.075,
    "$0.10-$0.50": 0.30,
    ">$0.50": 0.75,
}


def _weighted_avg_cost(buckets: Dict[str, int]) -> float:
    """Estimate average cost from bucket distribution."""
    total_count = sum(buckets.values())
    if total_count == 0:
        return 0.0
    weighted = sum(
        _COST_BUCKET_MIDPOINTS.get(b, 0) * count for b, count in buckets.items()
    )
    return weighted / total_count


def _dominant_bucket(buckets: Dict[str, int]) -> str:
    """Return the bucket with the highest count."""
    if not buckets:
        return "<$0.01"
    return max(buckets.items(), key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# Recommendation dataclass
# ---------------------------------------------------------------------------


@dataclass
class Recommendation:
    """A single actionable recommendation from the brain."""

    type: str  # "cost", "safety", "performance", "testing", "model"
    priority: str  # "high", "medium", "low"
    title: str
    description: str
    action: str  # specific actionable step


# ---------------------------------------------------------------------------
# Recommender engine
# ---------------------------------------------------------------------------


class BrainRecommender:
    """Generates recommendations based on collected patterns."""

    # Minimum insights needed before we start giving advice
    MIN_INSIGHTS = 3

    def __init__(self, store: BrainStore) -> None:
        self.store = store

    def get_recommendations(self) -> List[Recommendation]:
        """Analyze patterns and generate all recommendations."""
        if self.store.insight_count() < self.MIN_INSIGHTS:
            return [
                Recommendation(
                    type="testing",
                    priority="low",
                    title="Run more tests to unlock recommendations",
                    description=(
                        f"The brain needs at least {self.MIN_INSIGHTS} recorded insights "
                        f"to generate meaningful recommendations. You currently have "
                        f"{self.store.insight_count()}."
                    ),
                    action="Run more agent tests with `agentprobe test` to build up the brain's knowledge.",
                )
            ]

        patterns = self.store.get_patterns()
        model_stats = self.store.get_model_stats()
        assertion_eff = self.store.get_assertion_effectiveness()

        recs: list[Recommendation] = []
        recs.extend(self._cost_recommendations(patterns, model_stats))
        recs.extend(self._safety_recommendations(patterns, assertion_eff))
        recs.extend(self._performance_recommendations(patterns, model_stats))
        recs.extend(self._testing_recommendations(patterns, assertion_eff))
        recs.extend(self._model_recommendations(patterns, model_stats))

        # Sort by priority: high > medium > low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda r: priority_order.get(r.priority, 3))

        return recs

    # ------------------------------------------------------------------
    # Cost recommendations
    # ------------------------------------------------------------------

    def _cost_recommendations(
        self, patterns: Dict[str, Any], model_stats: Dict[str, Any]
    ) -> List[Recommendation]:
        recs: list[Recommendation] = []

        cost_by_model = patterns.get("cost_by_model", {})

        # Check for expensive models — suggest cheaper alternatives
        for model, buckets in cost_by_model.items():
            avg_cost = _weighted_avg_cost(buckets)
            dominant = _dominant_bucket(buckets)

            if avg_cost > 0.10:
                # Find cheaper models with decent pass rates
                cheaper_alternatives: list[str] = []
                for other_model, other_buckets in cost_by_model.items():
                    if other_model == model:
                        continue
                    other_avg = _weighted_avg_cost(other_buckets)
                    other_pass = model_stats.get(other_model, {}).get(
                        "pass_rate", 0
                    )
                    if other_avg < avg_cost * 0.6 and other_pass > 80:
                        cheaper_alternatives.append(
                            f"{other_model} (~${other_avg:.2f}/run, {other_pass}% pass rate)"
                        )

                if cheaper_alternatives:
                    alts_str = ", ".join(cheaper_alternatives[:3])
                    recs.append(
                        Recommendation(
                            type="cost",
                            priority="high",
                            title=f"High cost detected with {model}",
                            description=(
                                f"Your {model} agent's dominant cost bucket is {dominant} "
                                f"(est. ~${avg_cost:.2f}/run). Cheaper alternatives with "
                                f"good pass rates: {alts_str}."
                            ),
                            action=(
                                f"Try replaying your recordings with a cheaper model: "
                                f"`agentprobe replay --model {cheaper_alternatives[0].split()[0]}`"
                            ),
                        )
                    )
                else:
                    recs.append(
                        Recommendation(
                            type="cost",
                            priority="medium",
                            title=f"High cost detected with {model}",
                            description=(
                                f"Your {model} agent's dominant cost bucket is {dominant} "
                                f"(est. ~${avg_cost:.2f}/run). Consider testing with "
                                f"smaller or cached prompts."
                            ),
                            action=(
                                "Review your system prompts for unnecessary length. "
                                "Consider adding `total_cost_less_than()` assertions "
                                "to catch cost regressions."
                            ),
                        )
                    )

        # Token usage warnings
        token_bucket_counts: dict[str, int] = {}
        for ins in self.store.get_insights(limit=10000):
            tb = ins["token_bucket"]
            token_bucket_counts[tb] = token_bucket_counts.get(tb, 0) + 1
        total_ins = sum(token_bucket_counts.values())
        high_token_count = token_bucket_counts.get(">10K", 0) + token_bucket_counts.get(
            "5K-10K", 0
        )
        if total_ins > 0 and high_token_count / total_ins > 0.3:
            recs.append(
                Recommendation(
                    type="cost",
                    priority="medium",
                    title="High token consumption detected",
                    description=(
                        f"{round(high_token_count / total_ins * 100)}% of your runs "
                        f"use 5K+ tokens. This drives up cost and latency."
                    ),
                    action=(
                        "Review system prompts for unnecessary verbosity. Consider "
                        "prompt caching, shorter instructions, or moving context to "
                        "tool descriptions."
                    ),
                )
            )

        return recs

    # ------------------------------------------------------------------
    # Safety recommendations
    # ------------------------------------------------------------------

    def _safety_recommendations(
        self, patterns: Dict[str, Any], assertion_eff: Dict[str, Any]
    ) -> List[Recommendation]:
        recs: list[Recommendation] = []
        assertions_used = set(patterns.get("assertions_used", {}).keys())
        failure_types = patterns.get("failure_types", {})

        # Check if PII assertion is missing
        pii_assertions = {"no_pii_in_output", "no_pii", "pii_check", "no_pii_leaked"}
        if not assertions_used & pii_assertions:
            recs.append(
                Recommendation(
                    type="safety",
                    priority="high",
                    title="No PII detection assertions found",
                    description=(
                        "Your test suite does not include any PII detection assertions. "
                        "Agents can inadvertently leak sensitive data like emails, phone "
                        "numbers, or SSNs in their outputs."
                    ),
                    action=(
                        "Add `no_pii_in_output()` to your test assertions. Example:\n"
                        "  assert rec | no_pii_in_output()"
                    ),
                )
            )

        # Check if prompt injection tests are missing
        injection_assertions = {
            "prompt_injection",
            "no_prompt_injection",
            "injection_safe",
            "fuzz",
        }
        if not assertions_used & injection_assertions:
            recs.append(
                Recommendation(
                    type="safety",
                    priority="high",
                    title="No prompt injection testing detected",
                    description=(
                        "Your tests don't include prompt injection defenses. "
                        "Adversarial inputs can manipulate agent behavior."
                    ),
                    action=(
                        "Add prompt injection fuzz testing:\n"
                        "  `agentprobe fuzz --strategy prompt-injection`"
                    ),
                )
            )

        # If PII failures are already happening
        if "pii_detected" in failure_types or "pii_leaked" in failure_types:
            count = failure_types.get("pii_detected", 0) + failure_types.get(
                "pii_leaked", 0
            )
            recs.append(
                Recommendation(
                    type="safety",
                    priority="high",
                    title="PII leaks detected in agent outputs",
                    description=(
                        f"PII was detected in {count} test run(s). This is a serious "
                        f"safety concern that needs immediate attention."
                    ),
                    action=(
                        "Review your agent's system prompt to explicitly instruct it "
                        "not to include PII. Add output filtering as a post-processing step."
                    ),
                )
            )

        # Check for tool-safety assertions
        tool_safety = {
            "no_dangerous_tool_calls",
            "tool_call_safe",
            "safe_tool_usage",
            "no_destructive_actions",
        }
        tools_used = set(patterns.get("tool_usage", {}).keys())
        if tools_used and not assertions_used & tool_safety:
            recs.append(
                Recommendation(
                    type="safety",
                    priority="medium",
                    title="Tool calls lack safety assertions",
                    description=(
                        f"Your agent uses {len(tools_used)} tool(s) but has no "
                        f"safety assertions on tool usage. Agents can misuse tools "
                        f"in unexpected ways."
                    ),
                    action=(
                        "Add tool-safety assertions to verify your agent only calls "
                        "expected tools with valid arguments."
                    ),
                )
            )

        return recs

    # ------------------------------------------------------------------
    # Performance recommendations
    # ------------------------------------------------------------------

    def _performance_recommendations(
        self, patterns: Dict[str, Any], model_stats: Dict[str, Any]
    ) -> List[Recommendation]:
        recs: list[Recommendation] = []

        step_dist = patterns.get("step_distribution", {})
        avg_steps = step_dist.get("avg", 0)
        max_steps = step_dist.get("max", 0)
        error_rate = patterns.get("error_rate", 0)

        # High step count
        if avg_steps > 6:
            recs.append(
                Recommendation(
                    type="performance",
                    priority="medium",
                    title="High average step count",
                    description=(
                        f"Your agents average {avg_steps} steps per run (max: {max_steps}). "
                        f"This increases cost and latency. Well-optimized agents often "
                        f"complete in 3-5 steps."
                    ),
                    action=(
                        "Review your agent's tool selection and prompt design. "
                        "Check for unnecessary retries or redundant tool calls. "
                        "Add `total_steps_less_than(6)` assertions to catch step bloat."
                    ),
                )
            )

        # High error rate
        if error_rate > 20:
            recs.append(
                Recommendation(
                    type="performance",
                    priority="high",
                    title="High error rate in agent runs",
                    description=(
                        f"{error_rate}% of your agent runs encounter errors. "
                        f"This indicates reliability issues."
                    ),
                    action=(
                        "Examine the most common failure types and address root causes. "
                        "Consider adding retry logic or improving error handling in "
                        "your agent's tool implementations."
                    ),
                )
            )

        # High latency
        for model, stats in model_stats.items():
            latency_dist = stats.get("latency_distribution", {})
            slow_count = latency_dist.get(">10s", 0) + latency_dist.get("5-10s", 0)
            total = sum(latency_dist.values()) if latency_dist else 0
            if total > 0 and slow_count / total > 0.4:
                recs.append(
                    Recommendation(
                        type="performance",
                        priority="medium",
                        title=f"Slow responses with {model}",
                        description=(
                            f"{round(slow_count / total * 100)}% of {model} runs take "
                            f"5+ seconds. This may impact user experience."
                        ),
                        action=(
                            f"Consider adding `step_latency_less_than(3000)` assertions. "
                            f"Review if parallel tool calls could reduce total time. "
                            f"Try a faster model for time-sensitive use cases."
                        ),
                    )
                )

        # Large step variance
        min_steps = step_dist.get("min", 0)
        if max_steps > 0 and min_steps > 0 and max_steps > min_steps * 4:
            recs.append(
                Recommendation(
                    type="performance",
                    priority="low",
                    title="High variance in step counts",
                    description=(
                        f"Step counts range from {min_steps} to {max_steps}, indicating "
                        f"inconsistent agent behavior. Some runs may be getting stuck "
                        f"in loops or unnecessary retries."
                    ),
                    action=(
                        "Add `total_steps_less_than()` assertions to catch runaway "
                        "executions. Review high-step recordings for unnecessary loops."
                    ),
                )
            )

        return recs

    # ------------------------------------------------------------------
    # Testing recommendations
    # ------------------------------------------------------------------

    def _testing_recommendations(
        self, patterns: Dict[str, Any], assertion_eff: Dict[str, Any]
    ) -> List[Recommendation]:
        recs: list[Recommendation] = []

        assertions_used = patterns.get("assertions_used", {})
        total_insights = patterns.get("total_insights", 0)

        # Too few assertion types
        assertion_types = list(assertions_used.keys())
        if 0 < len(assertion_types) < 4:
            recs.append(
                Recommendation(
                    type="testing",
                    priority="medium",
                    title="Limited assertion diversity",
                    description=(
                        f"You're only using {len(assertion_types)} assertion type(s): "
                        f"{', '.join(assertion_types)}. A robust test suite typically "
                        f"covers output correctness, cost, safety, and behavioral checks."
                    ),
                    action=(
                        "Add more assertion types. Consider:\n"
                        "  - `total_cost_less_than()` for cost control\n"
                        "  - `no_pii_in_output()` for safety\n"
                        "  - `called_tool()` for behavioral verification\n"
                        "  - `total_steps_less_than()` for efficiency"
                    ),
                )
            )

        # Tests that always pass might be too lenient
        pass_rates = patterns.get("pass_rates_by_framework", {})
        for fw, rate in pass_rates.items():
            if rate == 100.0 and total_insights >= 5:
                recs.append(
                    Recommendation(
                        type="testing",
                        priority="medium",
                        title=f"Tests always pass for {fw} agents",
                        description=(
                            f"Your {fw} tests have a 100% pass rate across all runs. "
                            f"While this may be correct, it could indicate tests are "
                            f"too lenient and not catching real issues."
                        ),
                        action=(
                            "Consider tightening thresholds on cost and latency assertions. "
                            "Add edge-case tests. Run `agentprobe fuzz` to stress-test "
                            "your agent with adversarial inputs."
                        ),
                    )
                )

        # Assertions that always pass (and are used often enough to judge)
        always_passing: list[str] = []
        for name, stats in assertion_eff.items():
            if stats.get("always_passing", False):
                always_passing.append(name)

        if always_passing:
            recs.append(
                Recommendation(
                    type="testing",
                    priority="low",
                    title="Some assertions may be too lenient",
                    description=(
                        f"The following assertions have never caught a failure despite "
                        f"being used 5+ times: {', '.join(always_passing)}. They may "
                        f"have thresholds that are too generous."
                    ),
                    action=(
                        "Review and tighten the thresholds for these assertions. "
                        "If they're genuinely always correct, consider if they still "
                        "add value to your test suite."
                    ),
                )
            )

        # Low overall pass rate
        for fw, rate in pass_rates.items():
            if rate < 50 and total_insights >= 3:
                recs.append(
                    Recommendation(
                        type="testing",
                        priority="high",
                        title=f"Very low pass rate for {fw} agents",
                        description=(
                            f"Your {fw} agents have only a {rate}% assertion pass rate. "
                            f"This suggests fundamental issues with either the agent "
                            f"or the test expectations."
                        ),
                        action=(
                            "Review the most common failure types and determine if "
                            "the agent needs fixing or if test expectations are unrealistic. "
                            "Start by examining the highest-frequency failure type."
                        ),
                    )
                )

        return recs

    # ------------------------------------------------------------------
    # Model recommendations
    # ------------------------------------------------------------------

    def _model_recommendations(
        self, patterns: Dict[str, Any], model_stats: Dict[str, Any]
    ) -> List[Recommendation]:
        recs: list[Recommendation] = []

        if len(model_stats) < 2:
            # Need at least 2 models to compare
            models_used = list(patterns.get("models_used", {}).keys())
            if len(models_used) == 1:
                recs.append(
                    Recommendation(
                        type="model",
                        priority="low",
                        title="Only one model tested",
                        description=(
                            f"You've only tested with {models_used[0]}. Replaying "
                            f"your recordings with other models can reveal cost savings "
                            f"or quality improvements."
                        ),
                        action=(
                            f"Try replaying with different models:\n"
                            f"  `agentprobe replay --model gpt-4o`\n"
                            f"  `agentprobe replay --model claude-sonnet-4-6`\n"
                            f"  `agentprobe replay --model claude-haiku-4`"
                        ),
                    )
                )
            return recs

        # Compare models: find best cost/quality tradeoff
        best_pass_rate = 0.0
        best_pass_model = ""
        cheapest_model = ""
        cheapest_cost = float("inf")

        for model, stats in model_stats.items():
            pr = stats.get("pass_rate", 0)
            if pr > best_pass_rate:
                best_pass_rate = pr
                best_pass_model = model

            cost_dist = stats.get("cost_distribution", {})
            avg_cost = _weighted_avg_cost(cost_dist)
            if avg_cost < cheapest_cost:
                cheapest_cost = avg_cost
                cheapest_model = model

        # If cheapest model has good pass rate and is different from most-used
        most_used_model = ""
        most_used_count = 0
        for model, count in patterns.get("models_used", {}).items():
            if count > most_used_count:
                most_used_count = count
                most_used_model = model

        if (
            cheapest_model
            and cheapest_model != most_used_model
            and most_used_model in model_stats
        ):
            cheap_pass = model_stats[cheapest_model].get("pass_rate", 0)
            main_pass = model_stats[most_used_model].get("pass_rate", 0)
            main_cost_dist = model_stats[most_used_model].get(
                "cost_distribution", {}
            )
            main_avg_cost = _weighted_avg_cost(main_cost_dist)

            if cheap_pass >= main_pass * 0.9 and cheapest_cost < main_avg_cost * 0.7:
                savings_pct = round((1 - cheapest_cost / main_avg_cost) * 100)
                recs.append(
                    Recommendation(
                        type="model",
                        priority="high",
                        title=f"Consider switching to {cheapest_model}",
                        description=(
                            f"Based on replay data, {cheapest_model} achieves "
                            f"{cheap_pass}% pass rate (vs {main_pass}% for "
                            f"{most_used_model}) at ~{savings_pct}% lower cost."
                        ),
                        action=(
                            f"Switch your default model to {cheapest_model}:\n"
                            f"  Update `default_model: {cheapest_model}` in agentprobe.yaml"
                        ),
                    )
                )

        # If a model has notably higher pass rate
        if (
            best_pass_model
            and best_pass_model != most_used_model
            and most_used_model in model_stats
        ):
            main_pass = model_stats[most_used_model].get("pass_rate", 0)
            if best_pass_rate > main_pass + 10:
                recs.append(
                    Recommendation(
                        type="model",
                        priority="medium",
                        title=f"{best_pass_model} has higher quality",
                        description=(
                            f"{best_pass_model} has a {best_pass_rate}% pass rate vs "
                            f"{main_pass}% for your primary model {most_used_model}. "
                            f"If quality is more important than cost, consider switching."
                        ),
                        action=(
                            f"For high-quality use cases, use {best_pass_model}:\n"
                            f"  `agentprobe replay --model {best_pass_model}`"
                        ),
                    )
                )

        # Model with high error rate
        for model, stats in model_stats.items():
            if stats.get("error_rate", 0) > 30 and stats.get("run_count", 0) >= 3:
                recs.append(
                    Recommendation(
                        type="model",
                        priority="high",
                        title=f"Frequent errors with {model}",
                        description=(
                            f"{model} has a {stats['error_rate']}% error rate across "
                            f"{stats['run_count']} runs. Common failures: "
                            f"{', '.join(list(stats.get('common_failures', {}).keys())[:3]) or 'unknown'}."
                        ),
                        action=(
                            f"Investigate whether {model} supports all tools and "
                            f"features your agent requires. Consider switching to a "
                            f"more reliable model."
                        ),
                    )
                )

        return recs
