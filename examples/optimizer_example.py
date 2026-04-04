"""Example: Token & Cost Optimizer.

Analyze agent recordings for optimization opportunities
and project cost savings.
"""

from agentprobe import AgentRecording
from agentprobe.optimizer import PromptOptimizer


def main():
    recording = AgentRecording.load("recordings/my-agent.aprobe")

    optimizer = PromptOptimizer(runs_per_day=200)
    report = optimizer.analyze(recording)

    print(optimizer.render_report(report))
    # 🚀 TOKEN OPTIMIZATION REPORT
    #    Current cost: $0.0847
    #    Efficiency: 65/100 (B)
    #
    #    1. 💰💰 Downgrade claude-opus to Sonnet
    #       Save: $0.0523 (61.7%)
    #
    #    2. 💰 Enable Prompt Caching
    #       Save: $0.0089 (10.5%)
    #
    #    💸 Total potential savings: $0.0612 (72.2%)
    #    📅 Monthly savings (at 200 runs/day): $367.20


if __name__ == "__main__":
    main()
