"""Example: Time Travel Debugger for Agent Execution.

Step through your agent's recording like a VCR — forward, backward,
with breakpoints on tools, cost, or errors.
"""

from agentprobe import AgentRecording
from agentprobe.timeline import TimelineDebugger


def main():
    # Load a recording
    recording = AgentRecording.load("recordings/my-agent.aprobe")

    # Create debugger
    dbg = TimelineDebugger(recording)

    # Set breakpoints
    dbg.add_breakpoint_tool("web_search")       # Break when web_search is called
    dbg.add_breakpoint_cost(0.05)                # Break when cost exceeds $0.05
    dbg.add_breakpoint_error()                   # Break on any error

    # Navigate
    state = dbg.current()
    print(f"Position: {state.position}/{state.total_steps}")
    print(f"Cost so far: ${state.cumulative_cost:.4f}")

    # Step forward
    state = dbg.step_forward()
    print(f"\n{dbg.render_step_label()}")

    # Run until breakpoint
    state = dbg.run()
    if state.hit_breakpoints:
        print(f"\nHit breakpoint: {state.hit_breakpoints[0].condition}")

    # Inspect current step
    import json
    info = dbg.inspect_step()
    print(json.dumps(info, indent=2, default=str))

    # Show timeline bar
    print(f"\n{dbg.render_timeline_bar()}")

    # Compare two positions
    diff = dbg.diff(0, state.position)
    print(f"\nCost from step 0 to {state.position}: ${diff['cost_delta']:.4f}")


if __name__ == "__main__":
    main()
