"""Using AgentProbe with LangChain.

AgentProbe integrates with LangChain via a callback handler that captures
every LLM call, chain step, tool invocation, and error — automatically.

Run:
    pip install agentprobe langchain langchain-openai
    python langchain_example.py
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agentprobe.plugins.langchain import AgentProbeCallbackHandler


# ---------------------------------------------------------------------------
# 1. Create the AgentProbe callback handler
# ---------------------------------------------------------------------------
# Attach this to any LangChain chain or agent.  It records every event
# (LLM start/end, tool start/end, chain start/end, errors) with zero
# changes to your existing code.

handler = AgentProbeCallbackHandler(
    session_name="langchain-demo",   # optional — label for the dashboard
    record_prompts=True,             # capture full prompts (disable for PII)
)


# ---------------------------------------------------------------------------
# 2. Define a simple tool and agent
# ---------------------------------------------------------------------------

@tool
def lookup_population(country: str) -> str:
    """Look up the approximate population of a country."""
    populations = {
        "france": "68 million",
        "germany": "84 million",
        "japan": "125 million",
        "brazil": "214 million",
    }
    return populations.get(country.lower(), "Unknown")


prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful geography assistant. Use the tools available."),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

llm = ChatOpenAI(model="gpt-4o", temperature=0)
agent = create_openai_tools_agent(llm, [lookup_population], prompt)
executor = AgentExecutor(agent=agent, tools=[lookup_population], verbose=True)


# ---------------------------------------------------------------------------
# 3. Run the agent with AgentProbe recording
# ---------------------------------------------------------------------------
# Pass the handler via the `callbacks` keyword — that's it.

result = executor.invoke(
    {"input": "What's the population of France and Germany combined?"},
    config={"callbacks": [handler]},
)

print(f"\nAgent output: {result['output']}")


# ---------------------------------------------------------------------------
# 4. Run assertions on the recorded session
# ---------------------------------------------------------------------------

# Cost — make sure this chain didn't burn through budget
handler.assert_cost_under(0.10)
print("Cost assertion passed.")

# Errors — fail if any LLM call or tool raised an unhandled exception
handler.assert_no_errors()
print("No-error assertion passed.")

# Latency — end-to-end should be under 15 seconds
handler.assert_total_latency_under(15.0)
print("Latency assertion passed.")

# Step count — the agent shouldn't need more than 5 reasoning steps
handler.assert_steps_under(5)
print("Step-count assertion passed.")


# ---------------------------------------------------------------------------
# 5. Inspect the recording
# ---------------------------------------------------------------------------

recording = handler.get_recording()

print(f"\n--- Recording Summary ---")
print(f"  Session:      {recording.session_name}")
print(f"  LLM calls:    {recording.llm_call_count}")
print(f"  Tool calls:   {recording.tool_call_count}")
print(f"  Total tokens:  {recording.total_tokens}")
print(f"  Total cost:    ${recording.total_cost:.4f}")
print(f"  Duration:      {recording.duration_seconds:.2f}s")


# ---------------------------------------------------------------------------
# 6. Export for CI or the web dashboard
# ---------------------------------------------------------------------------

recording.save("langchain_recording.json")
print(f"\nRecording saved to langchain_recording.json")
print("Run `agentprobe serve` then import the file to explore visually.")
