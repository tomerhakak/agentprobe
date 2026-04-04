"""Coverage — Agent Path Coverage Reporting.

Like code coverage, but for agent decision paths. Tracks which tools,
branches, and strategies an agent has exercised across test runs.

Free tier feature — no Pro upgrade required.
"""

from agentprobe.coverage.tracker import CoverageTracker, CoverageReport

__all__ = ["CoverageTracker", "CoverageReport"]
