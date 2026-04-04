"""Example: Agent Path Coverage Reporting.

Like code coverage, but for agent behavior — track which tools,
branches, and patterns have been exercised.
"""

from pathlib import Path

from agentprobe import AgentRecording
from agentprobe.coverage import CoverageTracker


def main():
    tracker = CoverageTracker()

    # Set tools available to the agent
    tracker.set_available_tools([
        "web_search", "calculator", "file_read", "file_write",
        "send_email", "database_query",
    ])

    # Add all recordings from directory
    recordings_dir = Path("recordings")
    for path in recordings_dir.glob("*.aprobe"):
        rec = AgentRecording.load(path)
        tracker.add(rec)

    # Generate report
    report = tracker.report()
    print(tracker.render_report(report))
    # 📊 AGENT COVERAGE REPORT
    #    Recordings analyzed: 12
    #    🔧 Tool Coverage: 83% (5/6)
    #       Uncovered: send_email
    #    🔀 Branch Coverage: 75% (3/4)
    #    🧬 Unique Patterns: 8
    #    🎯 Overall Coverage: 78% (B)


if __name__ == "__main__":
    main()
