"""Track and optimize your agent's costs.

AgentProbe records the exact token count and dollar cost of every LLM call.
Use this data to set budgets, get alerts, and compare costs across models.

Run:
    pip install agentprobe
    python cost_tracking.py
"""
from __future__ import annotations

from agentprobe import AgentProbe, record
from agentprobe.monitoring import CostTracker, BudgetAlert


# ---------------------------------------------------------------------------
# 1. Record costs automatically with the @record decorator
# ---------------------------------------------------------------------------

@record
def summarize_document(text: str) -> str:
    """Agent that summarizes long documents."""
    import openai

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Summarize the following document in 3 bullet points."},
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# 2. Set up cost tracking with budget alerts
# ---------------------------------------------------------------------------
# CostTracker aggregates costs across all @record-decorated calls and
# fires alerts when thresholds are crossed.

tracker = CostTracker(
    session_name="cost-demo",
    alerts=[
        BudgetAlert(threshold=0.50, action="warn"),     # print warning at $0.50
        BudgetAlert(threshold=2.00, action="warn"),     # print warning at $2.00
        BudgetAlert(threshold=5.00, action="stop"),     # raise exception at $5.00
    ],
)

# Simulate processing several documents
sample_docs = [
    "Artificial intelligence has transformed software engineering..." * 100,
    "The quarterly revenue report shows a 15% increase..." * 100,
    "New regulations require all AI systems to undergo..." * 100,
]

print("Processing documents...\n")
for i, doc in enumerate(sample_docs, 1):
    result = summarize_document(doc)
    recording = summarize_document.last_recording  # type: ignore[attr-defined]
    tracker.add(recording)

    print(f"  Doc {i}: {recording.total_tokens} tokens, ${recording.total_cost:.4f}")

print(f"\n  Running total: ${tracker.total_cost:.4f}")


# ---------------------------------------------------------------------------
# 3. Get a cost breakdown
# ---------------------------------------------------------------------------

breakdown = tracker.breakdown()

print("\n--- Cost Breakdown ---")
print(f"  Total cost:         ${breakdown.total_cost:.4f}")
print(f"  Input tokens:       {breakdown.input_tokens:,}")
print(f"  Output tokens:      {breakdown.output_tokens:,}")
print(f"  Input cost:         ${breakdown.input_cost:.4f}")
print(f"  Output cost:        ${breakdown.output_cost:.4f}")
print(f"  Calls:              {breakdown.call_count}")
print(f"  Avg cost per call:  ${breakdown.avg_cost_per_call:.4f}")


# ---------------------------------------------------------------------------
# 4. Compare costs across models
# ---------------------------------------------------------------------------
# Replay the same prompts through different models to find the cheapest
# option that still produces acceptable results.

print("\n--- Model Cost Comparison ---")

recordings = tracker.get_recordings()
models_to_compare = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-20250514", "claude-haiku-4-20250414"]

comparison = tracker.compare_models(
    recordings=recordings,
    models=models_to_compare,
)

print(f"  {'Model':<30} {'Cost':>8} {'Tokens':>10} {'Latency':>10} {'Quality':>8}")
print(f"  {'-'*30} {'-'*8} {'-'*10} {'-'*10} {'-'*8}")

for row in comparison.rows:
    print(
        f"  {row.model:<30} "
        f"${row.total_cost:>7.4f} "
        f"{row.total_tokens:>10,} "
        f"{row.avg_latency:>9.2f}s "
        f"{row.quality_score:>7.0%}"
    )

print(f"\n  Recommended: {comparison.recommendation.model}")
print(f"  Reason:      {comparison.recommendation.reason}")


# ---------------------------------------------------------------------------
# 5. Project monthly costs
# ---------------------------------------------------------------------------

projection = tracker.project_monthly(
    daily_calls=500,                # expected calls per day
    avg_tokens_per_call=breakdown.avg_tokens_per_call,
)

print(f"\n--- Monthly Cost Projection ---")
print(f"  Daily calls:        {projection.daily_calls}")
print(f"  Avg tokens/call:    {projection.avg_tokens_per_call:,}")
print(f"  Projected monthly:  ${projection.monthly_cost:.2f}")
print(f"  With gpt-4o-mini:   ${projection.monthly_cost_alternative('gpt-4o-mini'):.2f}")


# ---------------------------------------------------------------------------
# 6. Export cost data
# ---------------------------------------------------------------------------

tracker.save("cost_report.json")
tracker.export_csv("cost_data.csv")     # for spreadsheet analysis
print(f"\nCost data exported. Run `agentprobe serve` to view in dashboard.")
