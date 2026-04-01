"""AgentProbe Brain — opt-in learning system for anonymized agent insights."""

from __future__ import annotations

from agentprobe.brain.brain import Brain, BrainConfig
from agentprobe.brain.recommender import Recommendation as BrainInsight

__all__ = [
    "Brain",
    "BrainConfig",
    "BrainInsight",
]
