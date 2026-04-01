"""Cost calculator for LLM API calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class _ModelPricing:
    """Per-token pricing for a single model.

    Prices are expressed as USD per 1 000 tokens.
    """

    input_per_1k: float
    output_per_1k: float


# ---------------------------------------------------------------------------
# Built-in pricing  (USD per 1 000 tokens, as of early 2026)
# ---------------------------------------------------------------------------

_BUILTIN_PRICING: dict[str, _ModelPricing] = {
    # Anthropic
    "claude-opus-4-6":          _ModelPricing(input_per_1k=0.015,  output_per_1k=0.075),
    "claude-sonnet-4-6":        _ModelPricing(input_per_1k=0.003,  output_per_1k=0.015),
    "claude-haiku-4-5":         _ModelPricing(input_per_1k=0.001,  output_per_1k=0.005),
    "claude-3-5-sonnet-latest": _ModelPricing(input_per_1k=0.003,  output_per_1k=0.015),
    "claude-3-5-haiku-latest":  _ModelPricing(input_per_1k=0.001,  output_per_1k=0.005),
    "claude-3-opus-latest":     _ModelPricing(input_per_1k=0.015,  output_per_1k=0.075),
    # OpenAI
    "gpt-4o":                   _ModelPricing(input_per_1k=0.0025, output_per_1k=0.010),
    "gpt-4o-mini":              _ModelPricing(input_per_1k=0.00015,output_per_1k=0.0006),
    "gpt-4-turbo":              _ModelPricing(input_per_1k=0.010,  output_per_1k=0.030),
    "gpt-4":                    _ModelPricing(input_per_1k=0.030,  output_per_1k=0.060),
    "gpt-3.5-turbo":            _ModelPricing(input_per_1k=0.0005, output_per_1k=0.0015),
    "o1":                       _ModelPricing(input_per_1k=0.015,  output_per_1k=0.060),
    "o1-mini":                  _ModelPricing(input_per_1k=0.003,  output_per_1k=0.012),
    "o3-mini":                  _ModelPricing(input_per_1k=0.0011, output_per_1k=0.0044),
    # Google
    "gemini-1.5-pro":           _ModelPricing(input_per_1k=0.00125,output_per_1k=0.005),
    "gemini-1.5-flash":         _ModelPricing(input_per_1k=0.000075,output_per_1k=0.0003),
    "gemini-2.0-flash":         _ModelPricing(input_per_1k=0.0001, output_per_1k=0.0004),
    # Meta (via API providers — typical hosted pricing)
    "llama-3.1-70b":            _ModelPricing(input_per_1k=0.00059,output_per_1k=0.00079),
    "llama-3.1-8b":             _ModelPricing(input_per_1k=0.00006,output_per_1k=0.00006),
    # Mistral
    "mistral-large":            _ModelPricing(input_per_1k=0.002,  output_per_1k=0.006),
    "mistral-small":            _ModelPricing(input_per_1k=0.0002, output_per_1k=0.0006),
}


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

@dataclass
class CostCalculator:
    """Calculate the cost of LLM API calls.

    Parameters
    ----------
    custom_pricing:
        Optional overrides keyed by model name.  Each value should be a dict
        with ``input_per_1k`` and ``output_per_1k`` (USD per 1 000 tokens).
    """

    custom_pricing: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._pricing: dict[str, _ModelPricing] = dict(_BUILTIN_PRICING)
        for model, prices in self.custom_pricing.items():
            self._pricing[model] = _ModelPricing(
                input_per_1k=prices.get("input_per_1k", 0.0),
                output_per_1k=prices.get("output_per_1k", 0.0),
            )

    def calculate(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Return estimated cost in USD for the given token counts.

        If the model is not found in built-in or custom pricing, the method
        attempts a prefix match (e.g. ``gpt-4o-2024-05-13`` will match
        ``gpt-4o``).  If no match is found, returns ``0.0``.
        """
        pricing = self._resolve(model)
        if pricing is None:
            return 0.0
        return (
            (input_tokens / 1000.0) * pricing.input_per_1k
            + (output_tokens / 1000.0) * pricing.output_per_1k
        )

    def get_pricing(self, model: str) -> dict[str, float] | None:
        """Return the pricing entry for *model*, or ``None``."""
        pricing = self._resolve(model)
        if pricing is None:
            return None
        return {
            "input_per_1k": pricing.input_per_1k,
            "output_per_1k": pricing.output_per_1k,
        }

    @property
    def supported_models(self) -> list[str]:
        """List of all models with known pricing."""
        return sorted(self._pricing.keys())

    # -- Internal -----------------------------------------------------------

    def _resolve(self, model: str) -> _ModelPricing | None:
        """Resolve a model name to its pricing, trying exact then prefix match."""
        if model in self._pricing:
            return self._pricing[model]
        # Prefix / contains match (e.g. "gpt-4o-2024-05-13" -> "gpt-4o")
        for known in sorted(self._pricing, key=len, reverse=True):
            if model.startswith(known):
                return self._pricing[known]
        return None
