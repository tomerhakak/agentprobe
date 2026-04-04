"""Optimizer — Token & Prompt Optimization Engine.

Analyzes agent recordings for wasted tokens, redundant prompts,
over-verbose outputs, and suggests actionable optimizations with
projected cost savings.

Free tier feature — no Pro upgrade required.
"""

from agentprobe.optimizer.engine import PromptOptimizer, OptimizationReport

__all__ = ["PromptOptimizer", "OptimizationReport"]
