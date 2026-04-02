"""Pit two agents against each other in the Arena.

The Arena runs both agents on the same set of prompts and uses an LLM judge
to score each response on accuracy, helpfulness, and safety.  Results
include per-prompt scores, aggregate ELO ratings, and a detailed comparison.

Note: Arena battles require AgentProbe Pro.  Sign up at https://agentprobe.dev/pro

Run:
    pip install agentprobe[pro]
    python arena_battle.py
"""
from __future__ import annotations

from agentprobe.arena import Arena, ArenaConfig, Contestant


# ---------------------------------------------------------------------------
# 1. Define the two agents (contestants)
# ---------------------------------------------------------------------------
# Each contestant wraps a callable that takes a prompt and returns a response.
# You can use any framework — raw API calls, LangChain, CrewAI, etc.

def agent_gpt4o(prompt: str) -> str:
    """Agent powered by GPT-4o."""
    import openai

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful, accurate assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


def agent_claude(prompt: str) -> str:
    """Agent powered by Claude Sonnet."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt},
        ],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# 2. Configure the Arena
# ---------------------------------------------------------------------------

config = ArenaConfig(
    rounds=20,                      # number of prompts to test
    judge_model="gpt-4o",           # LLM used to evaluate responses
    scoring_criteria=[
        "accuracy",                 # factual correctness
        "helpfulness",              # did it actually answer the question?
        "safety",                   # no harmful, biased, or toxic content
        "conciseness",              # shorter is better (when equally correct)
    ],
    prompt_categories=[
        "general_knowledge",        # trivia, facts, definitions
        "reasoning",                # logic puzzles, math, deduction
        "creative_writing",         # stories, poems, humor
        "coding",                   # write/debug/explain code
        "safety_adversarial",       # attempts to elicit harmful content
    ],
    include_cost_analysis=True,     # track cost per response
)


# ---------------------------------------------------------------------------
# 3. Run the battle
# ---------------------------------------------------------------------------

arena = Arena(config)

arena.add_contestant(Contestant(
    name="GPT-4o Agent",
    agent_fn=agent_gpt4o,
    metadata={"provider": "openai", "model": "gpt-4o"},
))

arena.add_contestant(Contestant(
    name="Claude Sonnet Agent",
    agent_fn=agent_claude,
    metadata={"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
))

print("Starting Arena battle — this may take a few minutes...\n")
results = arena.battle()


# ---------------------------------------------------------------------------
# 4. Print results
# ---------------------------------------------------------------------------

print("=" * 60)
print("ARENA RESULTS")
print("=" * 60)

print(f"\n  Winner: {results.winner.name}")
print(f"  Win margin: {results.win_margin:.0%}\n")

print(f"  {'Contestant':<25} {'ELO':>6} {'Win%':>6} {'Avg Score':>10} {'Cost':>8}")
print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*10} {'-'*8}")

for c in results.leaderboard:
    print(
        f"  {c.name:<25} "
        f"{c.elo:>6.0f} "
        f"{c.win_rate:>5.0%} "
        f"{c.avg_score:>10.2f} "
        f"${c.total_cost:>7.4f}"
    )


# ---------------------------------------------------------------------------
# 5. Per-category breakdown
# ---------------------------------------------------------------------------

print(f"\n--- Per-Category Scores ---")
print(f"  {'Category':<25} {'GPT-4o':>10} {'Claude':>10} {'Winner':>15}")
print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*15}")

for cat in results.category_breakdown:
    print(
        f"  {cat.name:<25} "
        f"{cat.scores[0]:.2f}{'':>5} "
        f"{cat.scores[1]:.2f}{'':>5} "
        f"{cat.winner:>15}"
    )


# ---------------------------------------------------------------------------
# 6. Cost efficiency analysis
# ---------------------------------------------------------------------------

print(f"\n--- Cost Efficiency ---")
for c in results.leaderboard:
    print(f"  {c.name}: ${c.total_cost:.4f} total, ${c.cost_per_point:.4f}/quality-point")

if results.cost_efficient_winner != results.winner:
    print(f"\n  Note: {results.cost_efficient_winner.name} wins on cost efficiency,")
    print(f"  even though {results.winner.name} wins on quality.")


# ---------------------------------------------------------------------------
# 7. Save and share
# ---------------------------------------------------------------------------

results.save("arena_results.json")
results.save_html("arena_report.html")
print(f"\nResults saved. Run `agentprobe serve` to view the full battle report.")
print("Share the HTML report with your team: arena_report.html")
