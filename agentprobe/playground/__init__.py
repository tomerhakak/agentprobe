"""Prompt Injection Playground -- interactive terminal lab for testing agent security."""

from __future__ import annotations

from agentprobe.playground.injection_lab import AttackResult, InjectionLab
from agentprobe.playground.attacks import ATTACK_DATABASE, ALL_CATEGORIES

__all__ = [
    "AttackResult",
    "InjectionLab",
    "ATTACK_DATABASE",
    "ALL_CATEGORIES",
]
