"""Health Check -- "Is your agent healthy?"

Quick five-dimension health assessment with scores, progress bars,
and actionable recommendations.  Free tier feature.
"""

from agentprobe.health.checker import (
    HealthChecker,
    HealthDimension,
    HealthReport,
)

__all__ = [
    "HealthChecker",
    "HealthDimension",
    "HealthReport",
]
