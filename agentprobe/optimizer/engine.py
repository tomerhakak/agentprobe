"""Token & Prompt Optimization Engine.

Analyzes agent recordings for optimization opportunities:
- Wasted tokens (repeated prompts, redundant context)
- Over-verbose system prompts
- Unnecessary tool calls
- Cache-missed opportunities
- Model right-sizing recommendations

Free tier feature — no Pro upgrade required.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agentprobe.core.models import AgentRecording, AgentStep, StepType


# ---------------------------------------------------------------------------
# Cost table for common models
# ---------------------------------------------------------------------------

_MODEL_COSTS: Dict[str, Dict[str, float]] = {
    # model: {input_per_1m, output_per_1m}
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class OptimizationType(str):
    TOKEN_WASTE = "token_waste"
    PROMPT_COMPRESSION = "prompt_compression"
    MODEL_DOWNGRADE = "model_downgrade"
    CACHE_OPPORTUNITY = "cache_opportunity"
    REDUNDANT_TOOL = "redundant_tool"
    VERBOSE_OUTPUT = "verbose_output"
    BATCHING = "batching"


@dataclass
class Optimization:
    """A single optimization recommendation."""

    type: str
    title: str
    description: str
    current_cost: float = 0.0
    projected_cost: float = 0.0
    savings_usd: float = 0.0
    savings_pct: float = 0.0
    confidence: str = "medium"  # "low", "medium", "high"
    effort: str = "medium"  # "low", "medium", "high"
    steps: List[str] = field(default_factory=list)

    @property
    def roi_label(self) -> str:
        if self.savings_pct > 50:
            return "HUGE"
        if self.savings_pct > 30:
            return "HIGH"
        if self.savings_pct > 10:
            return "MEDIUM"
        return "LOW"


@dataclass
class OptimizationReport:
    """Complete optimization analysis report."""

    recording_name: str = ""
    total_cost: float = 0.0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    optimizations: List[Optimization] = field(default_factory=list)
    projected_cost: float = 0.0
    total_savings: float = 0.0
    total_savings_pct: float = 0.0
    monthly_projection: float = 0.0
    monthly_savings: float = 0.0
    token_efficiency_score: float = 0.0  # 0-100
    grade: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recording_name": self.recording_name,
            "total_cost": round(self.total_cost, 4),
            "total_tokens": self.total_tokens,
            "optimizations": [
                {
                    "type": o.type,
                    "title": o.title,
                    "savings_usd": round(o.savings_usd, 4),
                    "savings_pct": round(o.savings_pct, 1),
                    "confidence": o.confidence,
                    "effort": o.effort,
                }
                for o in self.optimizations
            ],
            "projected_cost": round(self.projected_cost, 4),
            "total_savings": round(self.total_savings, 4),
            "total_savings_pct": round(self.total_savings_pct, 1),
            "grade": self.grade,
        }


# ---------------------------------------------------------------------------
# Prompt Optimizer
# ---------------------------------------------------------------------------

class PromptOptimizer:
    """Analyze agent recordings and recommend token/cost optimizations.

    Usage::

        opt = PromptOptimizer()
        report = opt.analyze(recording)
        print(f"Potential savings: ${report.total_savings:.4f} ({report.total_savings_pct:.1f}%)")

        for o in report.optimizations:
            print(f"  [{o.roi_label}] {o.title}: save ${o.savings_usd:.4f}")

        # Multi-recording analysis
        report = opt.analyze_many(recordings)
    """

    def __init__(self, runs_per_day: int = 100) -> None:
        self._runs_per_day = runs_per_day

    def analyze(self, recording: AgentRecording) -> OptimizationReport:
        """Analyze a single recording for optimization opportunities."""
        report = OptimizationReport(
            recording_name=recording.metadata.name,
            total_cost=recording.total_cost,
            total_tokens=recording.total_tokens,
        )

        llm_steps = [s for s in recording.steps if s.llm_call]
        report.total_input_tokens = sum(s.llm_call.input_tokens for s in llm_steps)
        report.total_output_tokens = sum(s.llm_call.output_tokens for s in llm_steps)

        # Run all analyzers
        report.optimizations.extend(self._check_redundant_prompts(llm_steps))
        report.optimizations.extend(self._check_model_downgrade(llm_steps, recording))
        report.optimizations.extend(self._check_cache_opportunities(llm_steps))
        report.optimizations.extend(self._check_verbose_output(llm_steps))
        report.optimizations.extend(self._check_redundant_tools(recording))
        report.optimizations.extend(self._check_batching(recording))
        report.optimizations.extend(self._check_system_prompt(llm_steps))

        # Calculate totals
        report.total_savings = sum(o.savings_usd for o in report.optimizations)
        if report.total_cost > 0:
            report.total_savings_pct = report.total_savings / report.total_cost * 100
        report.projected_cost = max(0, report.total_cost - report.total_savings)

        # Monthly projections
        report.monthly_projection = report.total_cost * self._runs_per_day * 30
        report.monthly_savings = report.total_savings * self._runs_per_day * 30

        # Efficiency score
        report.token_efficiency_score = self._efficiency_score(report)
        report.grade = self._grade(report.token_efficiency_score)

        return report

    def analyze_many(self, recordings: Sequence[AgentRecording]) -> OptimizationReport:
        """Analyze multiple recordings and aggregate findings."""
        if not recordings:
            return OptimizationReport()

        reports = [self.analyze(r) for r in recordings]
        merged = OptimizationReport(
            recording_name=f"{len(recordings)} recordings",
            total_cost=sum(r.total_cost for r in reports),
            total_tokens=sum(r.total_tokens for r in reports),
            total_input_tokens=sum(r.total_input_tokens for r in reports),
            total_output_tokens=sum(r.total_output_tokens for r in reports),
        )

        # Deduplicate optimizations by type+title
        seen: set = set()
        for report in reports:
            for opt in report.optimizations:
                key = f"{opt.type}:{opt.title}"
                if key not in seen:
                    seen.add(key)
                    merged.optimizations.append(opt)

        merged.total_savings = sum(o.savings_usd for o in merged.optimizations)
        if merged.total_cost > 0:
            merged.total_savings_pct = merged.total_savings / merged.total_cost * 100
        merged.projected_cost = max(0, merged.total_cost - merged.total_savings)
        merged.monthly_projection = merged.total_cost * self._runs_per_day * 30
        merged.monthly_savings = merged.total_savings * self._runs_per_day * 30
        merged.token_efficiency_score = self._efficiency_score(merged)
        merged.grade = self._grade(merged.token_efficiency_score)

        return merged

    # -- Analyzers ---------------------------------------------------------

    def _check_redundant_prompts(self, llm_steps: List[AgentStep]) -> List[Optimization]:
        """Detect repeated prompt content across LLM calls."""
        opts: List[Optimization] = []
        if len(llm_steps) < 2:
            return opts

        # Check for repeated system prompts
        system_prompts = []
        for step in llm_steps:
            if step.llm_call:
                for msg in step.llm_call.input_messages:
                    if msg.role == "system" and isinstance(msg.content, str):
                        system_prompts.append(msg.content)

        if len(system_prompts) > 1:
            unique = set(system_prompts)
            if len(unique) == 1 and len(system_prompts) > 2:
                # Same system prompt repeated
                prompt_tokens = len(system_prompts[0].split()) * 1.3  # rough estimate
                wasted = prompt_tokens * (len(system_prompts) - 1)
                savings = wasted / 1_000_000 * 3.0  # estimate at Sonnet pricing
                opts.append(Optimization(
                    type=OptimizationType.TOKEN_WASTE,
                    title="Repeated System Prompt",
                    description=f"Same system prompt sent {len(system_prompts)} times. Use caching or session management.",
                    savings_usd=savings,
                    savings_pct=min(30, savings / max(sum(s.llm_call.cost_usd for s in llm_steps if s.llm_call), 0.0001) * 100),
                    confidence="high",
                    effort="low",
                    steps=["Enable prompt caching (Anthropic) or use session management", "Move static context to system prompt with caching enabled"],
                ))

        return opts

    def _check_model_downgrade(self, llm_steps: List[AgentStep], recording: AgentRecording) -> List[Optimization]:
        """Recommend cheaper models where possible."""
        opts: List[Optimization] = []

        model_costs_per_step: Dict[str, List[float]] = {}
        for step in llm_steps:
            if step.llm_call:
                model = step.llm_call.model
                if model not in model_costs_per_step:
                    model_costs_per_step[model] = []
                model_costs_per_step[model].append(step.llm_call.cost_usd)

        for model, costs in model_costs_per_step.items():
            model_lower = model.lower()
            # If using Opus, suggest Sonnet
            if "opus" in model_lower:
                total_cost = sum(costs)
                sonnet_cost = total_cost * (3.0 / 15.0)  # rough ratio
                savings = total_cost - sonnet_cost
                opts.append(Optimization(
                    type=OptimizationType.MODEL_DOWNGRADE,
                    title=f"Downgrade {model} to Sonnet",
                    description=f"Using Opus for {len(costs)} calls. Sonnet handles most tasks at ~80% lower cost.",
                    current_cost=total_cost,
                    projected_cost=sonnet_cost,
                    savings_usd=savings,
                    savings_pct=savings / max(total_cost, 0.0001) * 100,
                    confidence="medium",
                    effort="low",
                    steps=[
                        "Test with Sonnet to verify quality is acceptable",
                        "Use model routing: Opus for hard tasks, Sonnet/Haiku for simple ones",
                    ],
                ))
            elif "gpt-4o" == model_lower and "mini" not in model_lower:
                total_cost = sum(costs)
                mini_cost = total_cost * (0.15 / 2.50)
                savings = total_cost - mini_cost
                if savings > 0.001:
                    opts.append(Optimization(
                        type=OptimizationType.MODEL_DOWNGRADE,
                        title=f"Downgrade {model} to GPT-4o-mini",
                        description=f"Using GPT-4o for {len(costs)} calls. GPT-4o-mini may work for simpler steps.",
                        current_cost=total_cost,
                        projected_cost=mini_cost,
                        savings_usd=savings,
                        savings_pct=savings / max(total_cost, 0.0001) * 100,
                        confidence="medium",
                        effort="low",
                        steps=["Benchmark GPT-4o-mini on your specific tasks", "Implement model routing"],
                    ))

        return opts

    def _check_cache_opportunities(self, llm_steps: List[AgentStep]) -> List[Optimization]:
        """Identify cache-missed opportunities."""
        opts: List[Optimization] = []
        cache_misses = sum(1 for s in llm_steps if s.llm_call and not s.llm_call.cache_hit)
        total = len(llm_steps)

        if total > 2 and cache_misses > total * 0.7:
            estimated_savings = sum(s.llm_call.cost_usd for s in llm_steps if s.llm_call) * 0.5 * 0.9  # 90% cache hit * 50% cache discount
            opts.append(Optimization(
                type=OptimizationType.CACHE_OPPORTUNITY,
                title="Enable Prompt Caching",
                description=f"{cache_misses}/{total} LLM calls missed cache. Enable caching for repeated prefixes.",
                savings_usd=estimated_savings,
                savings_pct=min(50, estimated_savings / max(sum(s.llm_call.cost_usd for s in llm_steps if s.llm_call), 0.0001) * 100),
                confidence="high",
                effort="low",
                steps=["Enable prompt caching in your LLM provider", "Structure prompts with static prefix + dynamic suffix"],
            ))

        return opts

    def _check_verbose_output(self, llm_steps: List[AgentStep]) -> List[Optimization]:
        """Detect excessively verbose LLM outputs."""
        opts: List[Optimization] = []
        verbose_steps = [s for s in llm_steps if s.llm_call and s.llm_call.output_tokens > 1000]

        if verbose_steps:
            excess_tokens = sum(max(0, s.llm_call.output_tokens - 500) for s in verbose_steps)
            savings = excess_tokens / 1_000_000 * 15.0  # estimate at Sonnet output pricing
            opts.append(Optimization(
                type=OptimizationType.VERBOSE_OUTPUT,
                title="Reduce Output Verbosity",
                description=f"{len(verbose_steps)} LLM calls produced >1000 output tokens. Add max_tokens or conciseness instructions.",
                savings_usd=savings,
                savings_pct=min(25, len(verbose_steps) / max(len(llm_steps), 1) * 25),
                confidence="medium",
                effort="low",
                steps=[
                    'Add "Be concise" or "Respond in under 200 words" to system prompt',
                    "Set max_tokens parameter on LLM calls",
                    "Use structured output (JSON) instead of free-text for tool-calling steps",
                ],
            ))

        return opts

    def _check_redundant_tools(self, recording: AgentRecording) -> List[Optimization]:
        """Detect tools called multiple times with same input."""
        opts: List[Optimization] = []
        tool_calls: Dict[str, List[str]] = {}

        for step in recording.steps:
            if step.tool_call:
                key = step.tool_call.tool_name
                input_str = json.dumps(step.tool_call.tool_input, sort_keys=True, default=str)
                if key not in tool_calls:
                    tool_calls[key] = []
                tool_calls[key].append(input_str)

        for tool_name, inputs in tool_calls.items():
            unique = set(inputs)
            duplicates = len(inputs) - len(unique)
            if duplicates > 0:
                opts.append(Optimization(
                    type=OptimizationType.REDUNDANT_TOOL,
                    title=f"Deduplicate {tool_name} Calls",
                    description=f"{tool_name} called {len(inputs)} times but only {len(unique)} unique inputs. {duplicates} redundant calls.",
                    savings_pct=duplicates / max(len(inputs), 1) * 10,
                    confidence="high",
                    effort="medium",
                    steps=[
                        f"Add result caching for {tool_name}",
                        "Instruct agent to check previous results before re-calling tools",
                    ],
                ))

        return opts

    def _check_batching(self, recording: AgentRecording) -> List[Optimization]:
        """Detect opportunities to batch tool calls."""
        opts: List[Optimization] = []
        consecutive_tools = 0
        max_consecutive = 0

        for step in recording.steps:
            if step.type == StepType.TOOL_CALL:
                consecutive_tools += 1
                max_consecutive = max(max_consecutive, consecutive_tools)
            else:
                consecutive_tools = 0

        if max_consecutive >= 3:
            opts.append(Optimization(
                type=OptimizationType.BATCHING,
                title="Batch Sequential Tool Calls",
                description=f"Found {max_consecutive} consecutive tool calls. Batch them for parallel execution.",
                savings_pct=min(15, max_consecutive * 3),
                confidence="medium",
                effort="medium",
                steps=[
                    "Enable parallel tool execution in your agent framework",
                    "Group independent tool calls into a single LLM turn",
                ],
            ))

        return opts

    def _check_system_prompt(self, llm_steps: List[AgentStep]) -> List[Optimization]:
        """Check for oversized system prompts."""
        opts: List[Optimization] = []

        for step in llm_steps:
            if not step.llm_call:
                continue
            for msg in step.llm_call.input_messages:
                if msg.role == "system" and isinstance(msg.content, str):
                    word_count = len(msg.content.split())
                    if word_count > 2000:
                        opts.append(Optimization(
                            type=OptimizationType.PROMPT_COMPRESSION,
                            title="Compress System Prompt",
                            description=f"System prompt is ~{word_count} words. Compress to reduce input tokens.",
                            savings_pct=min(20, (word_count - 500) / word_count * 30),
                            confidence="medium",
                            effort="medium",
                            steps=[
                                "Remove redundant instructions from system prompt",
                                "Use bullet points instead of paragraphs",
                                "Move examples to few-shot format (only when needed)",
                            ],
                        ))
                    break
            break  # Only check first LLM call's system prompt

        return opts

    # -- Scoring -----------------------------------------------------------

    def _efficiency_score(self, report: OptimizationReport) -> float:
        if not report.optimizations:
            return 95.0
        # Deduct points per optimization, weighted by savings
        deductions = 0
        for opt in report.optimizations:
            if opt.savings_pct > 30:
                deductions += 20
            elif opt.savings_pct > 15:
                deductions += 10
            elif opt.savings_pct > 5:
                deductions += 5
            else:
                deductions += 2
        return max(0, 100 - deductions)

    def _grade(self, score: float) -> str:
        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        if score >= 35:
            return "D"
        return "F"

    # -- Rendering ---------------------------------------------------------

    def render_report(self, report: OptimizationReport) -> str:
        """Render a text optimization report."""
        lines: List[str] = []
        lines.append("\U0001f680 TOKEN OPTIMIZATION REPORT")
        lines.append(f"   Recording: {report.recording_name}")
        lines.append(f"   Current cost: ${report.total_cost:.4f}")
        lines.append(f"   Tokens: {report.total_tokens:,} ({report.total_input_tokens:,} in / {report.total_output_tokens:,} out)")
        lines.append(f"   Efficiency: {report.token_efficiency_score:.0f}/100 ({report.grade})")
        lines.append("")

        if report.optimizations:
            lines.append(f"   Found {len(report.optimizations)} optimization(s):")
            lines.append("")

            for i, opt in enumerate(report.optimizations, 1):
                roi_emoji = {
                    "HUGE": "\U0001f4b0\U0001f4b0\U0001f4b0",
                    "HIGH": "\U0001f4b0\U0001f4b0",
                    "MEDIUM": "\U0001f4b0",
                    "LOW": "\U0001f4b5",
                }
                emoji = roi_emoji.get(opt.roi_label, "\U0001f4b5")
                lines.append(f"   {i}. {emoji} {opt.title}")
                lines.append(f"      {opt.description}")
                if opt.savings_usd > 0:
                    lines.append(f"      Save: ${opt.savings_usd:.4f} ({opt.savings_pct:.1f}%)")
                lines.append(f"      Confidence: {opt.confidence} | Effort: {opt.effort}")
                if opt.steps:
                    for step in opt.steps:
                        lines.append(f"        \u2022 {step}")
                lines.append("")

            lines.append(f"   \U0001f4b8 Total potential savings: ${report.total_savings:.4f} ({report.total_savings_pct:.1f}%)")
            if report.monthly_savings > 0:
                lines.append(f"   \U0001f4c5 Monthly savings (at {self._runs_per_day} runs/day): ${report.monthly_savings:.2f}")
        else:
            lines.append("   \u2705 No optimizations needed — your agent is highly efficient!")

        return "\n".join(lines)
