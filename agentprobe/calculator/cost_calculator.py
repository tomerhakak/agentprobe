"""Cost Calculator -- True cost analysis for AI agents.

Projects per-run costs into daily / monthly / yearly figures, compares
across models, detects token waste, and generates actionable savings
recommendations.

Free tier feature -- no Pro upgrade required.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Model pricing  (USD per 1 000 000 tokens — industry standard unit)
# ---------------------------------------------------------------------------

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic
    "claude-opus-4-6":          {"input_per_1m": 15.00,  "output_per_1m": 75.00},
    "claude-sonnet-4-6":        {"input_per_1m": 3.00,   "output_per_1m": 15.00},
    "claude-haiku-4-5":         {"input_per_1m": 1.00,   "output_per_1m": 5.00},
    "claude-3-5-sonnet-latest": {"input_per_1m": 3.00,   "output_per_1m": 15.00},
    "claude-3-5-haiku-latest":  {"input_per_1m": 1.00,   "output_per_1m": 5.00},
    "claude-3-opus-latest":     {"input_per_1m": 15.00,  "output_per_1m": 75.00},
    # OpenAI
    "gpt-4o":                   {"input_per_1m": 2.50,   "output_per_1m": 10.00},
    "gpt-4o-mini":              {"input_per_1m": 0.15,   "output_per_1m": 0.60},
    "gpt-4-turbo":              {"input_per_1m": 10.00,  "output_per_1m": 30.00},
    "gpt-4":                    {"input_per_1m": 30.00,  "output_per_1m": 60.00},
    "gpt-3.5-turbo":            {"input_per_1m": 0.50,   "output_per_1m": 1.50},
    "o1":                       {"input_per_1m": 15.00,  "output_per_1m": 60.00},
    "o1-mini":                  {"input_per_1m": 3.00,   "output_per_1m": 12.00},
    "o3-mini":                  {"input_per_1m": 1.10,   "output_per_1m": 4.40},
    # Google
    "gemini-1.5-pro":           {"input_per_1m": 1.25,   "output_per_1m": 5.00},
    "gemini-1.5-flash":         {"input_per_1m": 0.075,  "output_per_1m": 0.30},
    "gemini-2.0-flash":         {"input_per_1m": 0.10,   "output_per_1m": 0.40},
    # Meta (typical hosted pricing)
    "llama-3.1-70b":            {"input_per_1m": 0.59,   "output_per_1m": 0.79},
    "llama-3.1-8b":             {"input_per_1m": 0.06,   "output_per_1m": 0.06},
    # Mistral
    "mistral-large":            {"input_per_1m": 2.00,   "output_per_1m": 6.00},
    "mistral-small":            {"input_per_1m": 0.20,   "output_per_1m": 0.60},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ModelComparison:
    """Cost comparison for a single alternative model."""

    model: str
    yearly_cost: float
    savings_usd: float
    savings_pct: float


@dataclass
class SavingsRecommendation:
    """A single actionable savings recommendation."""

    rank: int
    description: str
    estimated_yearly_savings: float


@dataclass
class TokenWasteAnalysis:
    """Results of the token waste analysis."""

    system_prompt_pct: float = 0.0
    redundant_tool_calls: int = 0
    estimated_yearly_savings: float = 0.0
    details: List[str] = field(default_factory=list)


@dataclass
class CostReport:
    """Complete cost analysis report."""

    # Per run
    per_run_llm_cost: float = 0.0
    per_run_tool_cost: float = 0.0
    per_run_total: float = 0.0

    # Projections
    daily_cost: float = 0.0
    monthly_cost: float = 0.0
    yearly_cost: float = 0.0
    runs_per_day: int = 100

    # Current model
    current_model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    # Comparisons
    model_comparisons: List[ModelComparison] = field(default_factory=list)

    # Waste
    waste: Optional[TokenWasteAnalysis] = None

    # Recommendations
    recommendations: List[SavingsRecommendation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cost_for_model(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: Dict[str, Dict[str, float]] | None = None,
) -> float:
    """Calculate cost in USD for a given model and token counts."""
    pricing = pricing or MODEL_PRICING
    entry = _resolve_model(model, pricing)
    if entry is None:
        return 0.0
    return (
        (input_tokens / 1_000_000) * entry["input_per_1m"]
        + (output_tokens / 1_000_000) * entry["output_per_1m"]
    )


def _resolve_model(
    model: str,
    pricing: Dict[str, Dict[str, float]],
) -> Dict[str, float] | None:
    """Exact then prefix match for model pricing."""
    if model in pricing:
        return pricing[model]
    for known in sorted(pricing, key=len, reverse=True):
        if model.startswith(known):
            return pricing[known]
    return None


def _fmt_cost(cost: float) -> str:
    if cost < 0.01:
        return f"${cost:.4f}"
    if cost < 1.0:
        return f"${cost:.2f}"
    return f"${cost:,.2f}"


def _fmt_pct(pct: float) -> str:
    return f"{pct:.0f}%"


# ---------------------------------------------------------------------------
# CostProjector
# ---------------------------------------------------------------------------

class CostProjector:
    """Analyze agent recordings and project the true cost of operation.

    Usage::

        from agentprobe.calculator import CostProjector

        projector = CostProjector()
        report = projector.analyze(recording, runs_per_day=200)
        print(projector.format_terminal_report(report))
    """

    def __init__(
        self,
        custom_pricing: Dict[str, Dict[str, float]] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        custom_pricing:
            Optional overrides merged on top of ``MODEL_PRICING``.
        """
        self._pricing: Dict[str, Dict[str, float]] = dict(MODEL_PRICING)
        if custom_pricing:
            self._pricing.update(custom_pricing)

    # -- Main analysis ------------------------------------------------------

    def analyze(
        self,
        recording: AgentRecording,
        *,
        runs_per_day: int = 100,
        tool_api_cost_per_call: float = 0.0001,
    ) -> CostReport:
        """Produce a full cost report from a recording.

        Parameters
        ----------
        recording:
            An ``AgentRecording`` to analyse.
        runs_per_day:
            How many times per day this agent runs (for projections).
        tool_api_cost_per_call:
            Estimated third-party API cost per tool call (default $0.0001).

        Returns
        -------
        CostReport
        """
        model = recording.environment.model or "unknown"
        input_tokens = 0
        output_tokens = 0
        llm_cost = 0.0
        tool_calls = 0
        system_prompt_tokens = 0

        for step in recording.steps:
            if step.type == StepType.LLM_CALL and step.llm_call:
                llm = step.llm_call
                input_tokens += llm.input_tokens
                output_tokens += llm.output_tokens
                llm_cost += llm.cost_usd
            elif step.type == StepType.TOOL_CALL:
                tool_calls += 1

        # If recorded cost is zero, estimate from pricing table
        if llm_cost == 0.0 and (input_tokens or output_tokens):
            llm_cost = _cost_for_model(model, input_tokens, output_tokens, self._pricing)

        tool_cost = tool_calls * tool_api_cost_per_call
        per_run_total = llm_cost + tool_cost

        # Projections
        daily = per_run_total * runs_per_day
        monthly = daily * 30
        yearly = daily * 365

        # Estimate system prompt token share
        if recording.environment.system_prompt and input_tokens > 0:
            # Rough estimate: ~4 chars per token
            sp_token_est = len(recording.environment.system_prompt) // 4
            system_prompt_pct = min((sp_token_est / max(input_tokens, 1)) * 100, 100)
        else:
            system_prompt_pct = 0.0

        # Token waste analysis
        waste = self._analyze_waste(
            recording, system_prompt_pct, yearly,
        )

        # Model comparisons
        comparisons = self._compare_models(
            model, input_tokens, output_tokens, runs_per_day,
        )

        # Recommendations
        recommendations = self._generate_recommendations(
            waste, comparisons, yearly, recording,
        )

        return CostReport(
            per_run_llm_cost=llm_cost,
            per_run_tool_cost=tool_cost,
            per_run_total=per_run_total,
            daily_cost=daily,
            monthly_cost=monthly,
            yearly_cost=yearly,
            runs_per_day=runs_per_day,
            current_model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_comparisons=comparisons,
            waste=waste,
            recommendations=recommendations,
        )

    # -- Model comparison ---------------------------------------------------

    def _compare_models(
        self,
        current_model: str,
        input_tokens: int,
        output_tokens: int,
        runs_per_day: int,
    ) -> List[ModelComparison]:
        """Compare current model cost against alternatives."""
        current_yearly = (
            _cost_for_model(current_model, input_tokens, output_tokens, self._pricing)
            * runs_per_day
            * 365
        )
        if current_yearly == 0:
            return []

        comparisons: List[ModelComparison] = []
        for alt_model in sorted(self._pricing.keys()):
            if alt_model == current_model:
                continue
            alt_cost = (
                _cost_for_model(alt_model, input_tokens, output_tokens, self._pricing)
                * runs_per_day
                * 365
            )
            savings = current_yearly - alt_cost
            pct = (savings / current_yearly) * 100 if current_yearly else 0
            comparisons.append(ModelComparison(
                model=alt_model,
                yearly_cost=alt_cost,
                savings_usd=savings,
                savings_pct=pct,
            ))

        # Sort by savings descending
        comparisons.sort(key=lambda c: c.savings_usd, reverse=True)
        return comparisons

    # -- Waste detection ----------------------------------------------------

    def _analyze_waste(
        self,
        recording: AgentRecording,
        system_prompt_pct: float,
        yearly_cost: float,
    ) -> TokenWasteAnalysis:
        """Detect token waste patterns."""
        details: List[str] = []
        estimated_savings = 0.0

        # System prompt analysis
        if system_prompt_pct > 30:
            sp_savings = yearly_cost * (system_prompt_pct / 100) * 0.3  # 30% of SP cost recoverable
            estimated_savings += sp_savings
            details.append(
                f"System prompt uses {system_prompt_pct:.0f}% of input tokens. "
                f"Consider shortening it to save ~{_fmt_cost(sp_savings)}/year."
            )

        # Redundant tool calls
        tool_names: List[str] = []
        for step in recording.steps:
            if step.type == StepType.TOOL_CALL and step.tool_call:
                tool_names.append(step.tool_call.tool_name)

        redundant = 0
        seen: Dict[str, int] = {}
        for name in tool_names:
            seen[name] = seen.get(name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                redundant += count - 1
        if redundant:
            # Rough estimate: each redundant call costs ~20% of per-run cost
            dup_savings = yearly_cost * 0.05 * redundant
            estimated_savings += dup_savings
            details.append(
                f"{redundant} redundant tool call(s) detected that could be merged. "
                f"Estimated savings: ~{_fmt_cost(dup_savings)}/year."
            )

        return TokenWasteAnalysis(
            system_prompt_pct=system_prompt_pct,
            redundant_tool_calls=redundant,
            estimated_yearly_savings=estimated_savings,
            details=details,
        )

    # -- Recommendations ----------------------------------------------------

    def _generate_recommendations(
        self,
        waste: TokenWasteAnalysis,
        comparisons: List[ModelComparison],
        yearly_cost: float,
        recording: AgentRecording,
    ) -> List[SavingsRecommendation]:
        """Generate the top actionable savings recommendations."""
        recs: List[SavingsRecommendation] = []

        # 1. System prompt optimization
        if waste.system_prompt_pct > 25:
            sp_save = yearly_cost * (waste.system_prompt_pct / 100) * 0.3
            recs.append(SavingsRecommendation(
                rank=0,
                description=f"Shorten system prompt ({waste.system_prompt_pct:.0f}% of tokens)",
                estimated_yearly_savings=sp_save,
            ))

        # 2. Caching
        cache_save = yearly_cost * 0.15  # conservative 15%
        recs.append(SavingsRecommendation(
            rank=0,
            description="Cache repeated queries and tool results",
            estimated_yearly_savings=cache_save,
        ))

        # 3. Batch tool calls
        tool_count = len(recording.tool_steps)
        if tool_count >= 2:
            batch_save = yearly_cost * 0.05
            recs.append(SavingsRecommendation(
                rank=0,
                description="Batch sequential tool calls into parallel",
                estimated_yearly_savings=batch_save,
            ))

        # 4. Model switch (pick the best savings option)
        if comparisons:
            best = comparisons[0]
            if best.savings_usd > 0:
                recs.append(SavingsRecommendation(
                    rank=0,
                    description=f"Switch to {best.model} (save {_fmt_pct(best.savings_pct)})",
                    estimated_yearly_savings=best.savings_usd,
                ))

        # Sort by savings and assign ranks
        recs.sort(key=lambda r: r.estimated_yearly_savings, reverse=True)
        for i, rec in enumerate(recs):
            rec.rank = i + 1

        return recs[:5]

    # -- Formatters ---------------------------------------------------------

    def format_terminal_report(self, report: CostReport) -> str:
        """Render a cost report as a beautiful terminal string.

        Parameters
        ----------
        report:
            The ``CostReport`` from :meth:`analyze`.

        Returns
        -------
        str
            Multi-line terminal-ready string.
        """
        lines: List[str] = []

        lines.append("")
        lines.append("\U0001f4b0 AgentProbe Cost Calculator")
        lines.append("\u2550" * 55)
        lines.append("")

        # Per Run
        lines.append("Per Run:")
        lines.append(f"  LLM calls:     {_fmt_cost(report.per_run_llm_cost)}")
        lines.append(f"  Tool calls:    {_fmt_cost(report.per_run_tool_cost)} (API fees)")
        lines.append(f"  Total:         {_fmt_cost(report.per_run_total)}")
        lines.append("")

        # Projections
        lines.append(f"Projections ({report.runs_per_day} runs/day):")
        lines.append(f"  Daily:    {_fmt_cost(report.daily_cost)}")
        lines.append(f"  Monthly:  {_fmt_cost(report.monthly_cost)}")
        lines.append(f"  Yearly:   {_fmt_cost(report.yearly_cost)}")
        lines.append("")

        # Model comparison (top 5)
        if report.model_comparisons:
            lines.append("Model Comparison:")
            lines.append(f"  Current ({report.current_model}): {_fmt_cost(report.yearly_cost)}/year")
            shown = 0
            for mc in report.model_comparisons:
                if mc.savings_usd <= 0:
                    continue
                lines.append(
                    f"  Switch to {mc.model}: "
                    f"{_fmt_cost(mc.yearly_cost)}/year  "
                    f"(save {_fmt_cost(mc.savings_usd)} \u2014 {_fmt_pct(mc.savings_pct)})"
                )
                shown += 1
                if shown >= 5:
                    break
            lines.append("")

        # Token waste
        if report.waste and report.waste.details:
            lines.append("Token Waste Analysis:")
            if report.waste.system_prompt_pct > 0:
                lines.append(
                    f"  System prompt:    {report.waste.system_prompt_pct:.0f}% of tokens"
                    + (" (optimize this!)" if report.waste.system_prompt_pct > 30 else "")
                )
            if report.waste.redundant_tool_calls:
                lines.append(
                    f"  Redundant calls:  {report.waste.redundant_tool_calls} call(s) could be merged"
                )
            lines.append(f"  Est. savings:     {_fmt_cost(report.waste.estimated_yearly_savings)}/year with optimization")
            lines.append("")

        # Recommendations
        if report.recommendations:
            lines.append("\U0001f4a1 Top Savings:")
            for rec in report.recommendations[:3]:
                lines.append(
                    f"  {rec.rank}. {rec.description} "
                    f"\u2192 save {_fmt_cost(rec.estimated_yearly_savings)}/year"
                )
            lines.append("")

        return "\n".join(lines)

    def format_json(self, report: CostReport) -> str:
        """Render the cost report as a JSON string.

        Parameters
        ----------
        report:
            The ``CostReport`` from :meth:`analyze`.

        Returns
        -------
        str
            Pretty-printed JSON.
        """
        data: Dict[str, Any] = {
            "per_run": {
                "llm_cost": report.per_run_llm_cost,
                "tool_cost": report.per_run_tool_cost,
                "total": report.per_run_total,
            },
            "projections": {
                "runs_per_day": report.runs_per_day,
                "daily": report.daily_cost,
                "monthly": report.monthly_cost,
                "yearly": report.yearly_cost,
            },
            "current_model": report.current_model,
            "tokens": {
                "input": report.input_tokens,
                "output": report.output_tokens,
            },
            "model_comparisons": [
                {
                    "model": mc.model,
                    "yearly_cost": mc.yearly_cost,
                    "savings_usd": mc.savings_usd,
                    "savings_pct": round(mc.savings_pct, 1),
                }
                for mc in report.model_comparisons
            ],
            "waste": {
                "system_prompt_pct": report.waste.system_prompt_pct,
                "redundant_tool_calls": report.waste.redundant_tool_calls,
                "estimated_yearly_savings": report.waste.estimated_yearly_savings,
                "details": report.waste.details,
            } if report.waste else None,
            "recommendations": [
                {
                    "rank": r.rank,
                    "description": r.description,
                    "estimated_yearly_savings": r.estimated_yearly_savings,
                }
                for r in report.recommendations
            ],
        }
        return json.dumps(data, indent=2)
