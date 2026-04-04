"""Example: Agent DNA Behavioral Fingerprinting.

Generate a unique behavioral fingerprint for your agent and detect drift.
"""

from agentprobe import AgentRecording
from agentprobe.dna import AgentDNA


def main():
    recording = AgentRecording.load("recordings/my-agent.aprobe")

    dna = AgentDNA()
    fp = dna.fingerprint(recording)

    # Print DNA helix visualization
    print(dna.render_helix(fp))
    # 🧬 Agent DNA Helix
    #  💬 verbosity        ████████████░░░░░░░░ 0.62
    #  🧰 tool_diversity   ██████████████░░░░░░ 0.71
    #  ⚡ speed            ████████████████░░░░ 0.83

    print(f"\nSignature: {fp.signature}")
    print(f"Hash: {fp.hash[:24]}...")
    print(f"Pattern: {fp.step_pattern}")

    # Compare two recordings
    recording2 = AgentRecording.load("recordings/my-agent-v2.aprobe")
    fp2 = dna.fingerprint(recording2)
    comparison = dna.compare(fp, fp2)

    print(dna.render_comparison(comparison))
    # ✅ Verdict: SIMILAR (similarity: 89.2%)
    #    Pattern similarity: 85.0%
    #    ⚠️ Drifted traits:
    #      ↑ verbosity: +0.18
    #    ✔️ Stable traits: tool_diversity, speed, ...


if __name__ == "__main__":
    main()
