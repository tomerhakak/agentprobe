<p align="center">
  <h1 align="center">AgentProbe</h1>
  <p align="center">
    <strong>pytest for AI Agents</strong> — Record, test, and monitor AI agents locally.
  </p>
</p>

<p align="center">
  <a href="https://pypi.org/project/agentprobe/"><img src="https://img.shields.io/pypi/v/agentprobe?color=blue" alt="PyPI"></a>
  <a href="https://github.com/agentprobe/agentprobe/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://pypi.org/project/agentprobe/"><img src="https://img.shields.io/pypi/pyversions/agentprobe" alt="Python 3.10+"></a>
  <a href="https://github.com/agentprobe/agentprobe/stargazers"><img src="https://img.shields.io/github/stars/agentprobe/agentprobe?style=social" alt="GitHub Stars"></a>
</p>

---

## The Problem

AI agents are black boxes. They call LLMs, invoke tools, make routing decisions — and you have no idea why one run costs $0.12 and the next costs $2.40. When something breaks in production, you can't reproduce it. When you swap models, you can't tell if behavior changed. **There is no `pytest` for agents.**

## The Solution

AgentProbe records every LLM call, tool invocation, and decision your agent makes into a portable trace. You write tests against those traces using 35+ built-in assertions — for output quality, cost, latency, safety, and behavior. Replay recordings with different models or prompts. Fuzz your agent with prompt injections. View everything in a local dashboard. All offline, all private, all in your CI pipeline.

```
$ agentprobe test

 tests/test_agent.py
  PASS  test_basic_response .................. 0.8s
  PASS  test_uses_search_tool ................ 0.3s
  PASS  test_cost_within_budget .............. 0.1s
  PASS  test_no_pii_leakage .................. 0.2s
  FAIL  test_prompt_injection_resistance ..... 0.4s
        AssertionError: Output contains forbidden pattern: 'IGNORE PREVIOUS'

 4 passed, 1 failed in 1.8s
 Total cost: $0.0034 | Tokens: 1,247 | Traces: .agentprobe/
```

## Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/tomerhakak/agentprobe/main/install.sh | bash
```

Or with pip:
```bash
pip install agentprobe
```

Then:
```bash
agentprobe init
agentprobe test
agentprobe platform start   # local web dashboard
```

## Features

### Record — Capture every LLM call, tool call, and decision

```python
from agentprobe import record, RecordingSession

@record("customer-support")
def run_agent(query: str, session: RecordingSession) -> str:
    session.set_input(query)
    # Your agent logic here — AgentProbe captures everything
    session.add_llm_call(model="gpt-4o", input_messages=[...], output_message=...)
    session.add_tool_call(tool_name="search_kb", tool_input={"q": query}, tool_output=results)
    session.set_output(answer)
    return answer
```

### Assert — 35+ built-in assertions for output, behavior, cost, and safety

```python
from agentprobe import assertions as A

def test_agent_response(recording):
    A.set_recording(recording)

    # Output quality
    A.output_contains("refund policy")
    A.output_length_less_than(500)

    # Behavior
    A.called_tool("search_kb")
    A.called_tools_in_order(["search_kb", "format_response"])
    A.steps_less_than(10)

    # Cost and performance
    A.total_cost_less_than(0.05)
    A.total_tokens_less_than(4000)
    A.total_latency_less_than(5000)

    # Safety
    A.no_pii_in_output()
    A.output_not_contains("internal use only")
```

### Replay — Test with different models, prompts, or tools

```python
from agentprobe import Replayer, ReplayConfig

replayer = Replayer()
result = replayer.replay(
    "recordings/customer-support.aprobe",
    config=ReplayConfig(model="claude-sonnet-4-20250514", mock_tools=True),
)
comparison = replayer.compare(original_recording, result)
print(comparison.summary)
# Steps: 5 -> 4 (delta: -1)
# Output Similarity: 94.2%
# Cost: $0.0180 -> $0.0095 (-47.2%)
```

Or from the CLI:

```bash
agentprobe replay recordings/customer-support.aprobe --model claude-sonnet-4-20250514
agentprobe replay recordings/customer-support.aprobe --diff
```

### Fuzz — Automatic prompt injection and edge case testing

```python
from agentprobe.fuzz import Fuzzer, PromptInjection, EdgeCases

fuzzer = Fuzzer()
result = fuzzer.run(
    agent_fn=run_agent,
    strategies=[PromptInjection(), EdgeCases()],
    assertions=lambda A: [
        A.no_pii_in_output(),
        A.output_not_contains("IGNORE PREVIOUS"),
        A.completed_successfully(),
    ],
)
print(result.summary())
# Strategy: PromptInjection
#   Variants tested: 47
#   Passed:  45
#   Failed:  2
#   Failure rate: 4.3%
```

### Mock — Mock tools and LLMs for fast, free, deterministic tests

```python
from agentprobe.mock import MockLLM, MockTool

mock_llm = MockLLM(responses=["Your order #1234 has been shipped."])
mock_search = MockTool(responses=[{"results": ["Order shipped on March 15"]}])

result = replayer.replay(
    recording,
    config=ReplayConfig(
        mock_llm=mock_llm,
        tool_mocks={"search_orders": mock_search},
    ),
)
# Zero API calls. Zero cost. Deterministic output.
```

### Dashboard — Local web UI for traces, costs, and trends

```bash
agentprobe dashboard
# Opens http://localhost:9700
```

```
+------------------------------------------------------------------+
|  AgentProbe Dashboard                              localhost:9700 |
+------------------------------------------------------------------+
|                                                                   |
|  Recent Traces                          Cost Trend (7d)           |
|  +---------------------------------+   +---------------------+   |
|  | customer-support  0.3s  $0.003  |   |          __/        |   |
|  | order-lookup      1.2s  $0.018  |   |      ___/           |   |
|  | refund-agent      0.8s  $0.007  |   |  ___/               |   |
|  | billing-qa        0.5s  $0.004  |   | /                   |   |
|  +---------------------------------+   +---------------------+   |
|                                                                   |
|  Assertions: 142 passed, 3 failed     Avg cost/run: $0.008       |
|  Models: gpt-4o (67%), claude-sonnet (33%)   Drift: LOW          |
+------------------------------------------------------------------+
```

### Analyze — Cost, latency, drift, and failure analysis

```bash
agentprobe analyze --recordings .agentprobe/recordings/
# Cost breakdown by model, tool usage patterns, latency percentiles,
# drift detection across runs, failure clustering
```

### Framework Agnostic

AgentProbe works with any agent framework. Use the adapters or record manually:

| Framework | Status |
|-----------|--------|
| OpenAI SDK | Supported |
| Anthropic SDK | Supported |
| LangChain | Supported |
| CrewAI | Supported |
| Custom agents | Supported (manual recording) |

## CI/CD Integration

Add AgentProbe to your GitHub Actions pipeline:

```yaml
# .github/workflows/agent-tests.yml
name: Agent Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install agentprobe[all]
      - run: agentprobe test --ci --report report.html
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: agentprobe-report
          path: report.html
```

## Why AgentProbe?

| | AgentProbe | Promptfoo | DeepEval | Ragas |
|---|---|---|---|---|
| Record agent traces | Yes | No | No | No |
| Replay with model swap | Yes | No | No | No |
| 35+ built-in assertions | Yes | Custom only | 14 metrics | 8 metrics |
| Prompt injection fuzzing | Yes | Basic | No | No |
| Tool call assertions | Yes | No | No | No |
| Cost/latency assertions | Yes | No | Partial | No |
| PII detection | Yes | No | No | No |
| Local dashboard | Yes | Yes | Yes | No |
| pytest integration | Native | No | Plugin | No |
| Framework agnostic | Yes | LLM-only | LLM-only | RAG-only |
| Fully offline | Yes | Partial | No | No |
| Mock LLMs and tools | Yes | No | No | No |

## Architecture

```
Your Agent Code
      |
      v
  @record decorator / Recorder
      |
      v
  RecordingSession ──> .aprobe trace files
      |                       |
      v                       v
  Assertions (35+)      Replayer
      |                       |
      v                       v
  pytest runner         Compare & Diff
      |                       |
      v                       v
  CI/CD pipeline        Dashboard (local web UI)
      |
      v
  Fuzzer (PromptInjection, EdgeCases, ToolFailures)
```

## Installation

### One-line install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/tomerhakak/agentprobe/main/install.sh | bash
```

This will:
- Check that Python 3.10+ is installed
- Create an isolated environment at `~/.agentprobe/`
- Install the latest AgentProbe release from GitHub
- Add the `agentprobe` command to your PATH automatically
- Works on macOS, Linux, and WSL

After install, reload your shell and you're ready:
```bash
source ~/.zshrc   # or ~/.bashrc
agentprobe init
agentprobe test
agentprobe platform start   # launch the local web dashboard
```

### With pip

```bash
# Core
pip install agentprobe

# With specific framework support
pip install agentprobe[openai]
pip install agentprobe[anthropic]
pip install agentprobe[langchain]

# With local dashboard
pip install agentprobe[dashboard]

# Everything
pip install agentprobe[all]
```

### From source

```bash
git clone https://github.com/tomerhakak/agentprobe.git
cd agentprobe
pip install -e ".[all]"
```

## AgentProbe Pro

Take your agent testing to the next level with Pro-exclusive features:

| Feature | Description |
|---------|-------------|
| **Agent Battle Arena** | Head-to-head agent comparison with battle reports |
| **Agent Autopsy** | Forensic failure analysis with cause-of-death detection |
| **Security Scorer** | 71 checks, 0-100 score, A-F grade across 4 categories |
| **Cost X-Ray** | Per-step cost visualization with waste detection |
| **Agent Diff** | Behavioral comparison between agent versions |
| **Agent Changelog** | Auto-generated behavioral changelog |
| **Agent Benchmark** | 6-dimension scoring: accuracy, cost, speed, safety, consistency, tool mastery |
| **Full Fuzzer** | 47+ prompt injection variants, edge cases, tool failures |
| **Brain** | Learns from your tests — recommends optimizations over time |
| **Dashboard** | Local web UI with traces, costs, and trends |

```python
from agentprobe.arena import Arena
from agentprobe.autopsy import AgentAutopsy
from agentprobe.security import SecurityScorer
from agentprobe.benchmark import AgentBenchmark

# Battle two agents head-to-head
arena = Arena()
report = arena.battle(agent_a, agent_b, inputs=["Handle a refund", "Reset password"])

# Forensic failure analysis
autopsy = AgentAutopsy()
report = autopsy.analyze(failed_recording)
print(report.cause_of_death)  # "infinite_loop" | "cost_explosion" | "tool_misuse" | ...

# Security score your agent
scorer = SecurityScorer()
score = scorer.score(recording)
print(f"{score.grade}: {score.total}/100")  # "B+: 82/100"

# Benchmark across 6 dimensions
bench = AgentBenchmark()
scorecard = bench.run(agent_fn)
print(scorecard.overall_grade)  # "A-"
```

Learn more at [agentprobe.dev/pro](https://agentprobe.dev/pro)

## Examples

See the [`examples/`](examples/) directory:

- **[Customer Support Agent](examples/customer_support_agent/)** — A complete example with agent, tests, and fuzzing

## Contributing

We welcome contributions. See our development setup:

```bash
git clone https://github.com/agentprobe/agentprobe.git
cd agentprobe
pip install -e ".[dev,all]"
pytest
ruff check .
```

## License

MIT License. See [LICENSE](LICENSE) for details.
