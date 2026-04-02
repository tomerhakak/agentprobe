"""AgentProbe Quickstart — Record, Test, Replay in 30 seconds.

This example shows the three core operations of AgentProbe:
  1. Record — capture every LLM call your agent makes
  2. Test   — run assertions on cost, latency, and output quality
  3. Replay — re-run the same conversation with a different model

Run:
    pip install agentprobe
    python quickstart.py
"""
from __future__ import annotations

from agentprobe import AgentProbe, record


# ---------------------------------------------------------------------------
# Step 1 — Define your agent
# ---------------------------------------------------------------------------
# The @record decorator captures every LLM call made inside the function,
# including the prompt, completion, token counts, latency, and cost.

@record
def my_qa_agent(question: str) -> str:
    """A minimal agent that answers questions via OpenAI."""
    import openai

    client = openai.OpenAI()  # uses OPENAI_API_KEY from env
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Be concise."},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Step 2 — Record a session
# ---------------------------------------------------------------------------
# Simply call your decorated function.  AgentProbe records everything in the
# background — no extra code needed.

answer = my_qa_agent("What is the capital of France?")
print(f"Agent answered: {answer}")


# ---------------------------------------------------------------------------
# Step 3 — Run assertions on the recording
# ---------------------------------------------------------------------------
# Retrieve the recording from the decorated function and validate it.

recording = my_qa_agent.last_recording  # type: ignore[attr-defined]

# Cost guard — fail if a single call costs more than $0.05
recording.assert_cost_under(0.05)

# Latency guard — fail if any call takes longer than 5 seconds
recording.assert_latency_under(5.0)

# Output quality — check the answer contains expected content
recording.assert_output_contains("Paris")

# Token budget — make sure we stay within limits
recording.assert_total_tokens_under(500)

print("All assertions passed!")


# ---------------------------------------------------------------------------
# Step 4 — Replay with a different model
# ---------------------------------------------------------------------------
# Replay sends the *exact same prompts* to a different model so you can
# compare cost, latency, and output quality side-by-side.

replay = recording.replay(model="gpt-4o-mini")

print(f"\nOriginal  -> model={recording.model}, cost=${recording.total_cost:.4f}")
print(f"Replay    -> model={replay.model}, cost=${replay.total_cost:.4f}")
print(f"Savings   -> {recording.cost_savings_vs(replay):.0%}")


# ---------------------------------------------------------------------------
# Step 5 — View in the local dashboard (optional)
# ---------------------------------------------------------------------------
# Start the AgentProbe web UI to explore recordings visually:
#
#   agentprobe serve
#
# Then open http://localhost:9700 in your browser.

probe = AgentProbe()
probe.save(recording)
print(f"\nRecording saved. Run `agentprobe serve` to view in dashboard.")
