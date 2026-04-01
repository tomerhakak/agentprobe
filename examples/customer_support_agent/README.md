# Customer Support Agent — AgentProbe Example

A complete example showing how to record, test, and fuzz an AI agent with AgentProbe.

## What's included

| File | Description |
|------|-------------|
| `agent.py` | A customer support agent that searches a knowledge base and responds to queries. No API keys needed — the search tool is simulated. |
| `test_agent.py` | Tests using AgentProbe assertions: output quality, tool usage, cost, safety, and prompt injection resistance. |

## Run the agent

```bash
cd examples/customer_support_agent
python agent.py
```

## Run the tests

```bash
# From the repo root
pytest examples/customer_support_agent/test_agent.py -v

# Or using the AgentProbe CLI
agentprobe test
```

## What the tests cover

- **Basic response** — Output contains expected keywords, reasonable length, completion status
- **Tool usage** — Agent calls `search_kb` and `format_response` in the right order
- **Cost and performance** — Total cost under $0.10, latency under 10s, token count under 5000
- **Safety** — No PII in output, no internal data leaked, no errors
- **Prompt injection** — Fuzzes the agent with 10 injection variants, asserts <30% failure rate
