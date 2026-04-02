"""Using AgentProbe with CrewAI.

AgentProbe plugs into CrewAI via AgentProbeCrewHandler, giving you full
visibility into every agent step, delegation, tool call, and LLM
interaction inside a Crew.

Run:
    pip install agentprobe crewai crewai-tools
    python crewai_example.py
"""
from __future__ import annotations

from crewai import Agent, Crew, Task, Process
from crewai_tools import SerperDevTool

from agentprobe.plugins.crewai import AgentProbeCrewHandler


# ---------------------------------------------------------------------------
# 1. Create the AgentProbe handler for CrewAI
# ---------------------------------------------------------------------------
# The handler hooks into CrewAI's callback system and records every
# agent action, delegation event, tool call, and final output.

handler = AgentProbeCrewHandler(
    session_name="crewai-research-demo",
    track_delegations=True,     # record agent-to-agent delegations
    track_tool_calls=True,      # record each tool invocation
)


# ---------------------------------------------------------------------------
# 2. Define agents
# ---------------------------------------------------------------------------

researcher = Agent(
    role="Senior Research Analyst",
    goal="Find accurate, up-to-date information on the given topic.",
    backstory=(
        "You are a meticulous researcher who always verifies facts "
        "from multiple sources before reporting."
    ),
    tools=[SerperDevTool()],
    verbose=True,
    allow_delegation=False,
)

writer = Agent(
    role="Technical Writer",
    goal="Turn raw research into a clear, concise briefing (under 200 words).",
    backstory=(
        "You are an expert at distilling complex topics into plain English "
        "without losing accuracy."
    ),
    verbose=True,
    allow_delegation=False,
)


# ---------------------------------------------------------------------------
# 3. Define tasks
# ---------------------------------------------------------------------------

research_task = Task(
    description="Research the current state of AI agent testing frameworks in 2026.",
    expected_output="A bullet-point list of the top 5 frameworks with one-line descriptions.",
    agent=researcher,
)

writing_task = Task(
    description=(
        "Write a short executive briefing based on the research. "
        "Include a recommendation for engineering teams."
    ),
    expected_output="A 150-200 word briefing in Markdown format.",
    agent=writer,
)


# ---------------------------------------------------------------------------
# 4. Assemble and run the Crew with AgentProbe
# ---------------------------------------------------------------------------

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process=Process.sequential,
    callbacks=[handler],         # <-- attach AgentProbe here
    verbose=True,
)

result = crew.kickoff()
print(f"\n{'='*60}")
print("CREW OUTPUT:")
print(f"{'='*60}")
print(result)


# ---------------------------------------------------------------------------
# 5. Run assertions
# ---------------------------------------------------------------------------

# Cost — the full crew run should stay under budget
handler.assert_cost_under(0.50)
print("\nCost assertion passed.")

# Errors — no agent should have crashed
handler.assert_no_errors()
print("No-error assertion passed.")

# Output quality — the final briefing should mention AI agents
handler.assert_final_output_contains("agent")
print("Output quality assertion passed.")

# Task completion — both tasks should have completed successfully
handler.assert_all_tasks_completed()
print("Task completion assertion passed.")


# ---------------------------------------------------------------------------
# 6. Inspect per-agent metrics
# ---------------------------------------------------------------------------

recording = handler.get_recording()

print(f"\n--- Per-Agent Breakdown ---")
for agent_report in recording.agent_reports:
    print(f"  {agent_report.role}:")
    print(f"    LLM calls:   {agent_report.llm_call_count}")
    print(f"    Tool calls:  {agent_report.tool_call_count}")
    print(f"    Tokens:      {agent_report.total_tokens}")
    print(f"    Cost:        ${agent_report.cost:.4f}")
    print(f"    Duration:    {agent_report.duration_seconds:.2f}s")

print(f"\n  Total crew cost: ${recording.total_cost:.4f}")
print(f"  Total duration:  {recording.duration_seconds:.2f}s")


# ---------------------------------------------------------------------------
# 7. Save and explore
# ---------------------------------------------------------------------------

recording.save("crewai_recording.json")
print(f"\nRecording saved. Run `agentprobe serve` to explore in the dashboard.")
