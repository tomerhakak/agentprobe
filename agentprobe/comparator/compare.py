"""Model Comparator -- compare 2-5 models side-by-side on the same task.

Works from recorded ``AgentRecording`` traces to produce a rich terminal
comparison table with per-metric winners, overall winner calculation,
and cost-savings estimations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from agentprobe.core.models import AgentRecording

# ---------------------------------------------------------------------------
# Default scoring weights (must sum to 1.0)
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS: Dict[str, float] = {
    "quality": 0.35,
    "cost": 0.25,
    "speed": 0.20,
    "hallucination": 0.10,
    "tokens": 0.10,
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ModelMetrics:
    """Metrics for a single model extracted from a recording."""

    model: str
    cost_usd: float = 0.0
    latency_s: float = 0.0
    quality_pct: float = 0.0
    tokens_out: int = 0
    hallucination_pct: float = 0.0
    composite_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "cost_usd": self.cost_usd,
            "latency_s": self.latency_s,
            "quality_pct": self.quality_pct,
            "tokens_out": self.tokens_out,
            "hallucination_pct": self.hallucination_pct,
            "composite_score": self.composite_score,
        }


@dataclass
class ComparisonResult:
    """Full comparison across models."""

    task_description: str
    models: List[ModelMetrics] = field(default_factory=list)
    winner: str = ""
    savings_per_run: float = 0.0
    savings_per_year: float = 0.0
    savings_vs: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_description": self.task_description,
            "models": [m.to_dict() for m in self.models],
            "winner": self.winner,
            "savings_per_run": self.savings_per_run,
            "savings_per_year": self.savings_per_year,
            "savings_vs": self.savings_vs,
        }


# ---------------------------------------------------------------------------
# ModelComparator
# ---------------------------------------------------------------------------


class ModelComparator:
    """Compare 2-5 models side-by-side from recorded traces.

    Parameters
    ----------
    weights:
        Optional dict overriding the default metric weights for overall
        winner calculation.
    runs_per_year:
        Estimated number of runs per year for savings calculation.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        runs_per_year: int = 36_500,
    ) -> None:
        self.weights = weights or dict(_DEFAULT_WEIGHTS)
        self.runs_per_year = runs_per_year
        self._result: Optional[ComparisonResult] = None

    # -- Public API ---------------------------------------------------------

    def compare_from_recordings(
        self,
        recordings: List[AgentRecording],
        task_description: str = "",
        quality_scores: Optional[Dict[str, float]] = None,
        hallucination_rates: Optional[Dict[str, float]] = None,
    ) -> ComparisonResult:
        """Build a comparison from a list of recordings (one per model).

        Parameters
        ----------
        recordings:
            List of 2-5 ``AgentRecording`` objects, each from a different
            model / configuration.
        task_description:
            Human-readable description of the task being compared.
        quality_scores:
            Optional mapping ``{model_name: quality_pct}`` (0-100).
            If not provided, quality is estimated from output status and
            output length.
        hallucination_rates:
            Optional mapping ``{model_name: hallucination_pct}`` (0-100).
            If not provided, defaults to 0 for all models.
        """
        if len(recordings) < 2:
            raise ValueError("Need at least 2 recordings to compare.")
        if len(recordings) > 5:
            raise ValueError("Maximum 5 recordings for comparison.")

        quality_scores = quality_scores or {}
        hallucination_rates = hallucination_rates or {}

        metrics_list: List[ModelMetrics] = []

        for rec in recordings:
            model_name = rec.environment.model or f"unknown-{len(metrics_list)}"
            cost = rec.total_cost
            latency = rec.total_duration / 1000.0 if rec.total_duration else 0.0

            # Output tokens
            tokens_out = sum(
                step.llm_call.output_tokens
                for step in rec.steps
                if step.llm_call is not None
            )

            # Quality estimation
            quality = quality_scores.get(model_name, 0.0)
            if quality == 0.0:
                if rec.output.status.value == "success":
                    content_len = len(str(rec.output.content)) if rec.output.content else 0
                    quality = min(95.0, 70.0 + content_len * 0.05)
                else:
                    quality = 30.0

            hallucination = hallucination_rates.get(model_name, 0.0)

            metrics_list.append(
                ModelMetrics(
                    model=model_name,
                    cost_usd=cost,
                    latency_s=round(latency, 2),
                    quality_pct=round(quality, 1),
                    tokens_out=tokens_out,
                    hallucination_pct=round(hallucination, 1),
                )
            )

        # Compute composite scores
        self._compute_composite_scores(metrics_list)

        # Determine winner
        winner = max(metrics_list, key=lambda m: m.composite_score)

        # Savings calculation
        costs_sorted = sorted(metrics_list, key=lambda m: m.cost_usd)
        most_expensive = costs_sorted[-1]
        cheapest_good = winner  # the overall winner
        savings_per_run = most_expensive.cost_usd - cheapest_good.cost_usd
        savings_per_year = savings_per_run * self.runs_per_year

        task_desc = task_description or "Agent task comparison"

        self._result = ComparisonResult(
            task_description=task_desc,
            models=metrics_list,
            winner=winner.model,
            savings_per_run=round(savings_per_run, 6),
            savings_per_year=round(savings_per_year, 2),
            savings_vs=most_expensive.model if most_expensive.model != winner.model else "",
        )

        return self._result

    def format_comparison_table(self, result: Optional[ComparisonResult] = None) -> str:
        """Generate a beautiful terminal comparison table.

        Parameters
        ----------
        result:
            A ``ComparisonResult``. If ``None``, uses the result from the
            most recent ``compare_from_recordings`` call.
        """
        result = result or self._result
        if result is None:
            return "  No comparison data. Run compare_from_recordings() first."

        models = result.models
        if not models:
            return "  No models to compare."

        # Column widths
        label_w = 16
        col_w = max(16, max(len(m.model) for m in models) + 4)

        lines: List[str] = []
        lines.append("")
        lines.append(f'  Model Comparison -- "{result.task_description}"')
        lines.append("=" * (label_w + col_w * len(models) + 4))

        # Header row
        header = f"  {'':>{label_w}}"
        for m in models:
            header += f"{m.model:>{col_w}}"
        lines.append(header)
        lines.append("-" * (label_w + col_w * len(models) + 4))

        # Per-metric rows
        rows: List[Dict[str, Any]] = [
            {
                "label": "Cost",
                "values": [f"${m.cost_usd:.4f}" if m.cost_usd < 0.01 else f"${m.cost_usd:.3f}" for m in models],
                "best_idx": self._best_index(models, "cost_usd", lower_is_better=True),
            },
            {
                "label": "Speed",
                "values": [f"{m.latency_s:.1f}s" for m in models],
                "best_idx": self._best_index(models, "latency_s", lower_is_better=True),
            },
            {
                "label": "Quality",
                "values": [f"{m.quality_pct:.0f}%" for m in models],
                "best_idx": self._best_index(models, "quality_pct", lower_is_better=False),
            },
            {
                "label": "Tokens Out",
                "values": [str(m.tokens_out) for m in models],
                "best_idx": self._best_index(models, "tokens_out", lower_is_better=True),
            },
            {
                "label": "Hallucination",
                "values": [f"{m.hallucination_pct:.0f}%" for m in models],
                "best_idx": self._best_index(models, "hallucination_pct", lower_is_better=True),
            },
        ]

        crown = " \U0001f451"

        for row_info in rows:
            row_str = f"  {row_info['label']:>{label_w}}"
            for idx, val in enumerate(row_info["values"]):
                marker = crown if idx == row_info["best_idx"] else ""
                cell = f"{val}{marker}"
                row_str += f"{cell:>{col_w}}"
            lines.append(row_str)

        lines.append("-" * (label_w + col_w * len(models) + 4))

        # Winner line
        winner_metrics = next((m for m in models if m.model == result.winner), None)
        reason = ""
        if winner_metrics:
            reason = "best quality/cost ratio"
        lines.append(f"  Winner: {result.winner} ({reason})")

        # Savings line
        if result.savings_per_run > 0 and result.savings_vs:
            lines.append(
                f"  Save: ${result.savings_per_run:.4f}/run "
                f"-> ${result.savings_per_year:.0f}/year "
                f"by switching from {result.savings_vs}"
            )
        lines.append("")

        return "\n".join(lines)

    # -- Private helpers ----------------------------------------------------

    def _compute_composite_scores(self, metrics: List[ModelMetrics]) -> None:
        """Compute normalised composite scores for each model."""
        if not metrics:
            return

        # Collect raw values
        costs = [m.cost_usd for m in metrics]
        speeds = [m.latency_s for m in metrics]
        qualities = [m.quality_pct for m in metrics]
        hallucinations = [m.hallucination_pct for m in metrics]
        tokens = [m.tokens_out for m in metrics]

        for m in metrics:
            # Normalise each metric to 0-100 (higher = better)
            cost_score = self._normalise_inverse(m.cost_usd, costs)
            speed_score = self._normalise_inverse(m.latency_s, speeds)
            quality_score = m.quality_pct  # already 0-100
            halluc_score = self._normalise_inverse(m.hallucination_pct, hallucinations)
            token_score = self._normalise_inverse(m.tokens_out, tokens)

            composite = (
                quality_score * self.weights.get("quality", 0.35)
                + cost_score * self.weights.get("cost", 0.25)
                + speed_score * self.weights.get("speed", 0.20)
                + halluc_score * self.weights.get("hallucination", 0.10)
                + token_score * self.weights.get("tokens", 0.10)
            )
            m.composite_score = round(composite, 2)

    @staticmethod
    def _normalise_inverse(value: float, all_values: Sequence[float]) -> float:
        """Normalise where lower is better -> higher score."""
        mn = min(all_values)
        mx = max(all_values)
        if mx == mn:
            return 100.0
        # Invert: the minimum value gets 100, the maximum gets 0
        return ((mx - value) / (mx - mn)) * 100.0

    @staticmethod
    def _best_index(
        models: List[ModelMetrics],
        attr: str,
        lower_is_better: bool,
    ) -> int:
        """Return the index of the best model for a given metric."""
        values = [getattr(m, attr) for m in models]
        if lower_is_better:
            return values.index(min(values))
        return values.index(max(values))
