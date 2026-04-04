"""Example: Chaos Engineering for AI Agents.

Inject failures, latency, and adversarial conditions to stress-test
your agent's resilience.
"""

from agentprobe import AgentRecording
from agentprobe.chaos import ChaosEngine, ChaosScenario, ChaosResult


def main():
    recording = AgentRecording.load("recordings/my-agent.aprobe")

    # Run with default scenarios (5 random from 12 built-in)
    engine = ChaosEngine(seed=42)
    result = engine.run(recording)

    print(engine.render_report(result))
    # Output:
    # 🌀 CHAOS ENGINEERING REPORT
    #    Resilience: 73/100 (B)
    #    Recovered: 3/5 injections

    # Run specific scenarios
    result = engine.run(recording, scenarios=[
        "Tool Timeout Storm",
        "Hallucination Station",
        "Domino Effect",
    ])

    print(f"\nResilience: {result.resilience_score:.0f}/100 ({result.grade})")
    for rec in result.recommendations:
        print(f"  - {rec}")


if __name__ == "__main__":
    main()
