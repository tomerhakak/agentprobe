"""Agent DNA — Behavioral Fingerprinting Engine.

Generates a unique multi-dimensional behavioral fingerprint for an agent
based on its execution patterns, tool usage, decision paths, cost profile,
and communication style. Enables:

- **Drift detection**: Compare fingerprints over time to spot behavioral changes
- **Identity matching**: Verify an agent behaves consistently across environments
- **Clustering**: Group similar agents by behavioral similarity

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Trait definitions — the dimensions of an agent's DNA
# ---------------------------------------------------------------------------

_TRAIT_NAMES = [
    "verbosity",       # tokens per response
    "tool_diversity",  # unique tools / total tool calls
    "tool_frequency",  # tool calls per LLM call
    "cost_efficiency", # output tokens per dollar
    "speed",           # tokens per second
    "retry_tendency",  # fraction of retries/errors
    "decisiveness",    # decisions per LLM call
    "depth",           # total steps
    "memory_usage",    # memory reads+writes / total steps
    "delegation",      # handoffs / total steps
]

_TRAIT_EMOJI = {
    "verbosity": "\U0001f4ac",       # 💬
    "tool_diversity": "\U0001f9f0",  # 🧰
    "tool_frequency": "\U0001f527",  # 🔧
    "cost_efficiency": "\U0001f4b0", # 💰
    "speed": "\u26a1",               # ⚡
    "retry_tendency": "\U0001f504",  # 🔄
    "decisiveness": "\U0001f9e0",    # 🧠
    "depth": "\U0001f4cf",           # 📏
    "memory_usage": "\U0001f4be",    # 💾
    "delegation": "\U0001f91d",      # 🤝
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DNAFingerprint:
    """A unique behavioral fingerprint for an agent."""

    traits: Dict[str, float] = field(default_factory=dict)  # 0.0 - 1.0 normalized
    raw_values: Dict[str, float] = field(default_factory=dict)
    hash: str = ""
    signature: str = ""  # short human-readable signature like "VbTd-CeSp-ReDe"
    tool_profile: Dict[str, int] = field(default_factory=dict)
    model_profile: Dict[str, int] = field(default_factory=dict)
    step_pattern: str = ""  # e.g. "LTLTTTLDL" (L=LLM, T=Tool, D=Decision)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "traits": self.traits,
            "raw_values": self.raw_values,
            "hash": self.hash,
            "signature": self.signature,
            "tool_profile": self.tool_profile,
            "model_profile": self.model_profile,
            "step_pattern": self.step_pattern,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DNAFingerprint:
        return cls(**data)


@dataclass
class DNAComparison:
    """Result of comparing two agent fingerprints."""

    similarity: float = 0.0  # 0.0 - 1.0 (cosine similarity)
    trait_deltas: Dict[str, float] = field(default_factory=dict)
    drifted_traits: List[str] = field(default_factory=list)
    stable_traits: List[str] = field(default_factory=list)
    verdict: str = ""  # "identical", "similar", "different", "unrelated"
    pattern_similarity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "similarity": round(self.similarity, 4),
            "trait_deltas": {k: round(v, 4) for k, v in self.trait_deltas.items()},
            "drifted_traits": self.drifted_traits,
            "stable_traits": self.stable_traits,
            "verdict": self.verdict,
            "pattern_similarity": round(self.pattern_similarity, 4),
        }


# ---------------------------------------------------------------------------
# AgentDNA — main engine
# ---------------------------------------------------------------------------

class AgentDNA:
    """Generate and compare behavioral fingerprints for AI agents.

    Usage::

        dna = AgentDNA()
        fp = dna.fingerprint(recording)
        print(fp.signature)       # "VbTd-CeSp-ReDe"
        print(fp.traits)          # {"verbosity": 0.72, ...}

        fp2 = dna.fingerprint(other_recording)
        cmp = dna.compare(fp, fp2)
        print(cmp.similarity)     # 0.89
        print(cmp.verdict)        # "similar"

        # Multi-recording fingerprint (averages behavior)
        fp_avg = dna.fingerprint_many(recordings)
    """

    def __init__(self, drift_threshold: float = 0.15) -> None:
        self._drift_threshold = drift_threshold

    def fingerprint(self, recording: AgentRecording) -> DNAFingerprint:
        """Generate a fingerprint from a single recording."""
        raw = self._extract_raw(recording)
        traits = self._normalize(raw)
        tool_profile = self._tool_profile(recording)
        model_profile = self._model_profile(recording)
        pattern = self._step_pattern(recording)
        sig = self._build_signature(traits)
        h = self._compute_hash(traits, pattern)

        return DNAFingerprint(
            traits=traits,
            raw_values=raw,
            hash=h,
            signature=sig,
            tool_profile=tool_profile,
            model_profile=model_profile,
            step_pattern=pattern,
        )

    def fingerprint_many(self, recordings: Sequence[AgentRecording]) -> DNAFingerprint:
        """Generate an averaged fingerprint from multiple recordings."""
        if not recordings:
            return DNAFingerprint()
        fps = [self.fingerprint(r) for r in recordings]
        avg_traits: Dict[str, float] = {}
        avg_raw: Dict[str, float] = {}
        for trait in _TRAIT_NAMES:
            vals = [fp.traits.get(trait, 0.0) for fp in fps]
            avg_traits[trait] = sum(vals) / len(vals)
            raw_vals = [fp.raw_values.get(trait, 0.0) for fp in fps]
            avg_raw[trait] = sum(raw_vals) / len(raw_vals)

        merged_tools: Counter = Counter()
        merged_models: Counter = Counter()
        for fp in fps:
            merged_tools.update(fp.tool_profile)
            merged_models.update(fp.model_profile)

        pattern = fps[0].step_pattern
        sig = self._build_signature(avg_traits)
        h = self._compute_hash(avg_traits, pattern)

        return DNAFingerprint(
            traits=avg_traits,
            raw_values=avg_raw,
            hash=h,
            signature=sig,
            tool_profile=dict(merged_tools),
            model_profile=dict(merged_models),
            step_pattern=pattern,
        )

    def compare(self, a: DNAFingerprint, b: DNAFingerprint) -> DNAComparison:
        """Compare two fingerprints and produce a detailed comparison."""
        # Cosine similarity on trait vectors
        vec_a = [a.traits.get(t, 0.0) for t in _TRAIT_NAMES]
        vec_b = [b.traits.get(t, 0.0) for t in _TRAIT_NAMES]
        sim = _cosine_similarity(vec_a, vec_b)

        deltas: Dict[str, float] = {}
        drifted: List[str] = []
        stable: List[str] = []

        for trait in _TRAIT_NAMES:
            va = a.traits.get(trait, 0.0)
            vb = b.traits.get(trait, 0.0)
            delta = vb - va
            deltas[trait] = delta
            if abs(delta) > self._drift_threshold:
                drifted.append(trait)
            else:
                stable.append(trait)

        pattern_sim = _pattern_similarity(a.step_pattern, b.step_pattern)

        if sim >= 0.95:
            verdict = "identical"
        elif sim >= 0.80:
            verdict = "similar"
        elif sim >= 0.50:
            verdict = "different"
        else:
            verdict = "unrelated"

        return DNAComparison(
            similarity=sim,
            trait_deltas=deltas,
            drifted_traits=drifted,
            stable_traits=stable,
            verdict=verdict,
            pattern_similarity=pattern_sim,
        )

    # -- Rendering ---------------------------------------------------------

    def render_helix(self, fp: DNAFingerprint, width: int = 40) -> str:
        """Render a text-based DNA double-helix visualization."""
        lines: List[str] = []
        lines.append("  \u256d\u2500 Agent DNA Helix \u2500\u256e")
        for trait in _TRAIT_NAMES:
            val = fp.traits.get(trait, 0.0)
            emoji = _TRAIT_EMOJI.get(trait, "\u25cf")
            bar_len = int(val * 20)
            bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
            label = f"{trait:<16s}"
            lines.append(f"  {emoji} {label} {bar} {val:.2f}")
        lines.append(f"  \u256d\u2500 Signature: {fp.signature}")
        lines.append(f"  \u2570\u2500 Hash: {fp.hash[:16]}...")
        return "\n".join(lines)

    def render_comparison(self, cmp: DNAComparison) -> str:
        """Render a comparison report."""
        lines: List[str] = []
        verdict_emoji = {
            "identical": "\u2705",
            "similar": "\U0001f7e1",
            "different": "\U0001f7e0",
            "unrelated": "\U0001f534",
        }
        emoji = verdict_emoji.get(cmp.verdict, "\u2753")
        lines.append(f"{emoji} Verdict: {cmp.verdict.upper()} (similarity: {cmp.similarity:.1%})")
        lines.append(f"   Pattern similarity: {cmp.pattern_similarity:.1%}")

        if cmp.drifted_traits:
            lines.append(f"\n   \u26a0\ufe0f Drifted traits:")
            for trait in cmp.drifted_traits:
                delta = cmp.trait_deltas[trait]
                direction = "\u2191" if delta > 0 else "\u2193"
                lines.append(f"     {direction} {trait}: {delta:+.2f}")

        if cmp.stable_traits:
            lines.append(f"\n   \u2714\ufe0f Stable traits: {', '.join(cmp.stable_traits)}")

        return "\n".join(lines)

    # -- Internal ----------------------------------------------------------

    def _extract_raw(self, recording: AgentRecording) -> Dict[str, float]:
        """Extract raw trait values from a recording."""
        steps = recording.steps
        llm_steps = [s for s in steps if s.type == StepType.LLM_CALL and s.llm_call]
        tool_steps = [s for s in steps if s.type == StepType.TOOL_CALL and s.tool_call]
        decision_steps = [s for s in steps if s.type == StepType.DECISION]
        memory_steps = [s for s in steps if s.type in (StepType.MEMORY_READ, StepType.MEMORY_WRITE)]
        handoff_steps = [s for s in steps if s.type == StepType.HANDOFF]

        total_output_tokens = sum(s.llm_call.output_tokens for s in llm_steps)
        total_tokens = sum(s.llm_call.input_tokens + s.llm_call.output_tokens for s in llm_steps)
        total_cost = sum(s.llm_call.cost_usd for s in llm_steps)
        total_duration_s = sum(s.duration_ms for s in steps) / 1000.0
        unique_tools = len(set(s.tool_call.tool_name for s in tool_steps))
        error_steps = sum(1 for s in tool_steps if not s.tool_call.success)

        n_llm = max(len(llm_steps), 1)
        n_tool = max(len(tool_steps), 1)
        n_total = max(len(steps), 1)

        return {
            "verbosity": total_output_tokens / n_llm,
            "tool_diversity": unique_tools / n_tool if tool_steps else 0.0,
            "tool_frequency": len(tool_steps) / n_llm,
            "cost_efficiency": total_output_tokens / max(total_cost, 0.0001),
            "speed": total_tokens / max(total_duration_s, 0.001),
            "retry_tendency": error_steps / n_total,
            "decisiveness": len(decision_steps) / n_llm,
            "depth": float(len(steps)),
            "memory_usage": len(memory_steps) / n_total,
            "delegation": len(handoff_steps) / n_total,
        }

    def _normalize(self, raw: Dict[str, float]) -> Dict[str, float]:
        """Normalize raw values to 0.0 - 1.0 using sigmoid scaling."""
        scales = {
            "verbosity": (200, 800),
            "tool_diversity": (0, 1),
            "tool_frequency": (0, 5),
            "cost_efficiency": (1000, 100000),
            "speed": (10, 500),
            "retry_tendency": (0, 0.5),
            "decisiveness": (0, 2),
            "depth": (1, 50),
            "memory_usage": (0, 0.5),
            "delegation": (0, 0.3),
        }
        normalized: Dict[str, float] = {}
        for trait in _TRAIT_NAMES:
            val = raw.get(trait, 0.0)
            low, high = scales.get(trait, (0, 1))
            if high == low:
                normalized[trait] = 0.5
            else:
                normalized[trait] = max(0.0, min(1.0, (val - low) / (high - low)))
        return normalized

    def _tool_profile(self, recording: AgentRecording) -> Dict[str, int]:
        counts: Counter = Counter()
        for step in recording.steps:
            if step.tool_call:
                counts[step.tool_call.tool_name] += 1
        return dict(counts.most_common(20))

    def _model_profile(self, recording: AgentRecording) -> Dict[str, int]:
        counts: Counter = Counter()
        for step in recording.steps:
            if step.llm_call:
                counts[step.llm_call.model] += 1
        return dict(counts.most_common(10))

    def _step_pattern(self, recording: AgentRecording) -> str:
        mapping = {
            StepType.LLM_CALL: "L",
            StepType.TOOL_CALL: "T",
            StepType.TOOL_RESULT: "R",
            StepType.DECISION: "D",
            StepType.HANDOFF: "H",
            StepType.MEMORY_READ: "M",
            StepType.MEMORY_WRITE: "W",
        }
        return "".join(mapping.get(s.type, "?") for s in recording.steps)

    def _build_signature(self, traits: Dict[str, float]) -> str:
        """Build a short human-readable signature from trait values."""
        abbreviations = {
            "verbosity": "Vb", "tool_diversity": "Td", "tool_frequency": "Tf",
            "cost_efficiency": "Ce", "speed": "Sp", "retry_tendency": "Re",
            "decisiveness": "De", "depth": "Dp", "memory_usage": "Me",
            "delegation": "Dg",
        }
        # Pick top 6 most distinctive traits (highest values)
        sorted_traits = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:6]
        parts = [abbreviations.get(t, t[:2].title()) for t, _ in sorted_traits]
        # Group in pairs
        groups = [parts[i] + parts[i+1] if i+1 < len(parts) else parts[i] for i in range(0, len(parts), 2)]
        return "-".join(groups)

    def _compute_hash(self, traits: Dict[str, float], pattern: str) -> str:
        """Compute a deterministic hash of the fingerprint."""
        data = json.dumps(
            {"traits": {k: round(v, 4) for k, v in sorted(traits.items())}, "pattern": pattern},
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _pattern_similarity(a: str, b: str) -> float:
    """Simple edit-distance based similarity between step patterns."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    max_len = max(len(a), len(b))
    # Use simple matching character count for speed
    matches = sum(1 for ca, cb in zip(a, b) if ca == cb)
    return matches / max_len
