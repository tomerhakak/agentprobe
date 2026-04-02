"""Cost Calculator -- "How much does your agent REALLY cost?"

Projections, model comparisons, token-waste detection, and actionable
savings recommendations.  Free tier feature.
"""

from agentprobe.calculator.cost_calculator import (
    CostProjector,
    CostReport,
    ModelComparison,
    SavingsRecommendation,
    TokenWasteAnalysis,
)

__all__ = [
    "CostProjector",
    "CostReport",
    "ModelComparison",
    "SavingsRecommendation",
    "TokenWasteAnalysis",
]
