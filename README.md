<p align="center">
  <h1 align="center">🧪 AgentProbe</h1>
  <p align="center">
    <strong>pytest for AI Agents</strong>
  </p>
  <p align="center">
    Record, test, replay, and secure your AI agents — locally, privately, in your CI pipeline.
  </p>
</p>

<p align="center">
  <a href="https://github.com/tomerhakak/agentprobe/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"></a>
  <a href="https://pypi.org/project/agentprobe/"><img src="https://img.shields.io/pypi/v/agentprobe?color=green" alt="PyPI version"></a>
  <a href="https://pypi.org/project/agentprobe/"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="https://github.com/tomerhakak/agentprobe/actions"><img src="https://img.shields.io/github/actions/workflow/status/tomerhakak/agentprobe/ci.yml?label=CI" alt="GitHub Actions"></a>
  <a href="https://github.com/tomerhakak/agentprobe/stargazers"><img src="https://img.shields.io/github/stars/tomerhakak/agentprobe?style=social" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="https://agentprobe.dev/docs">Docs</a> &middot;
  <a href="https://agentprobe.dev/pro">Pro</a> &middot;
  <a href="https://github.com/tomerhakak/agentprobe/tree/main/examples">Examples</a> &middot;
  <a href="https://discord.gg/agentprobe">Discord</a>
</p>

---

> Your agents call LLMs, invoke tools, and make routing decisions — yet you have no way to test them, no way to catch regressions, and no idea why one run costs $0.12 while the next costs $2.40. **AgentProbe fixes that.**

---

## Quick Install

```bash
# pip (recommended)
pip install agentprobe

# or one-line installer (macOS, Linux, WSL)
curl -fsSL https://raw.githubusercontent.com/tomerhakak/agentprobe/main/install.sh | bash
```

Then get started:

```bash
agentprobe init        # scaffold config + example tests
agentprobe test        # run your agent tests
agentprobe platform    # local web dashboard at localhost:9700
```

---

## 30-Second Demo

**Record** your agent, then **test** it — just like pytest.

```python
from agentprobe import record, RecordingSession
from agentprobe import assertions as A

# 1. Record a run
@record("my-agent")
def run_agent(query: str, session: RecordingSession) -> str:
    session.set_input(query)
    session.add_llm_call(model="gpt-4o", input_messages=[...], output_message=response)
    session.add_tool_call(tool_name="search", tool_input={"q": query}, tool_output=results)
    session.set_output(answer)
    return answer

# 2. Test the recording
def test_agent_works(recording):
    A.set_recording(recording)
    A.output_contains("refund policy")
    A.called_tool("search")
    A.total_cost_less_than(0.05)
    A.no_pii_in_output()
```

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

---

## Features

<table>
<tr>
<td width="50%" valign="top">

### 🔴 Recording
Capture every LLM call, tool invocation, and routing decision into portable `.aprobe` trace files. Framework-agnostic — works with any agent.

</td>
<td width="50%" valign="top">

### ✅ Testing
**35+ built-in assertions** — output quality, tool usage, cost, latency, safety. Property-based, parameterized, regression, and snapshot testing.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### ⏪ Replay
Swap models, change prompts, compare results side-by-side. See exact cost and behavior differences between `gpt-4o` and `claude-sonnet`.

</td>
<td width="50%" valign="top">

### 🛡️ Security
Prompt injection fuzzing (47+ variants), PII detection (27 entity types), threat modeling, and security scoring.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📊 Monitoring
Cost tracking per run, budget alerts, behavioral drift detection, anomaly detection, latency percentiles.

</td>
<td width="50%" valign="top">

### 🧠 Intelligence
Hallucination detection, auto-optimizer, model recommender, and A/B testing across agent configurations.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### ⚔️ Arena <sup>Pro</sup>
Agent vs. agent battles with ELO ratings. Head-to-head comparison across any dimension — cost, accuracy, speed, safety.

</td>
<td width="50%" valign="top">

### 🔬 Autopsy <sup>Pro</sup>
Forensic failure analysis. Automatic root-cause detection: infinite loops, cost explosions, tool misuse, hallucination spirals.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔍 X-Ray
Token-level cost attribution. See exactly which step, which tool call, which LLM request is burning your budget. Beautiful tree visualization.

</td>
<td width="50%" valign="top">

### 📋 Compliance <sup>Pro</sup>
**53 automated checks** across SOC2, HIPAA, GDPR, PCI-DSS, and CCPA. Generate audit-ready reports.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔥 Agent Roast
Get a brutally honest (and funny) analysis of your agent. 450 jokes, 3 severity levels. *"Your agent spends money like a drunk sailor at a token store."*

</td>
<td width="50%" valign="top">

### 💰 Cost Calculator
Find out what your agent REALLY costs. Per-run, monthly, yearly projections. Model comparison with savings recommendations.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🏥 Health Check
5-dimension health score (reliability, speed, cost, security, quality) with progress bars and actionable tips.

</td>
<td width="50%" valign="top">

### 🎮 Injection Playground
**55 prompt injection attacks** across 5 categories. Test your agent's defenses interactively.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🏆 Leaderboard
Rank your agents by composite score. Track improvements over time. SQLite-backed, fully local.

</td>
<td width="50%" valign="top">

### ⚖️ Model Comparator
Side-by-side model comparison. Cost, speed, quality, hallucination rate. Crown emoji for the winner.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### ⏳ Timeline <sup>NEW</sup>
Time-travel debugger for agent execution. Step forward/backward, set breakpoints on tools/cost/errors, inspect state at every point. Interactive TUI mode.

</td>
<td width="50%" valign="top">

### 🧬 Agent DNA <sup>NEW</sup>
Behavioral fingerprinting. Generate a unique multi-dimensional DNA profile for any agent. Detect drift, compare identities, visual helix rendering.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🌀 Chaos Engineering <sup>NEW</sup>
12 built-in chaos scenarios: tool timeouts, LLM hallucinations, cascading failures, cost explosions. Resilience scoring with recovery analysis.

</td>
<td width="50%" valign="top">

### 📊 Agent Coverage <sup>NEW</sup>
Like code coverage, but for agents. Track tool coverage, branch coverage, step pattern diversity, and error path testing across recordings.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📸 Snapshot Testing <sup>NEW</sup>
Jest-style snapshots for agent behavior. Capture output, tools, cost, and patterns — automatically detect regressions on re-runs.

</td>
<td width="50%" valign="top">

### 🚀 Token Optimizer <sup>NEW</sup>
Automatic optimization analysis. Detects wasted tokens, recommends model downgrades, identifies caching opportunities, projects monthly savings.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 👀 Watch Mode <sup>NEW</sup>
Auto-run tests when files change. Like nodemon for AI agents — monitors recordings and test files, triggers analysis on save.

</td>
<td width="50%" valign="top">

### 🧪 NL Test Writer <sup>NEW</sup>
Write tests in plain English: *"respond in under 5 seconds"*, *"cost below $0.10"*. Auto-translates to executable pytest code.

</td>
</tr>
</table>

---

## Integrations

AgentProbe is framework-agnostic. Use it with anything.

<table>
<tr>
<th>Framework</th>
<th>Integration</th>
</tr>
<tr><td>OpenAI SDK</td><td>Auto-instrumentation</td></tr>
<tr><td>Anthropic SDK</td><td>Auto-instrumentation</td></tr>
<tr><td>LangChain</td><td>Callback handler</td></tr>
<tr><td>CrewAI</td><td>Callback handler</td></tr>
<tr><td>AutoGen</td><td>Adapter</td></tr>
<tr><td>Custom agents</td><td>Manual recording API</td></tr>
</table>

### GitHub Action

```yaml
- uses: tomerhakak/agentprobe@v1
  with:
    args: test --ci --report report.html
```

### LangChain

```python
from agentprobe.adapters.langchain import AgentProbeCallbackHandler

handler = AgentProbeCallbackHandler(session_name="my-chain")
chain.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### CrewAI

```python
from agentprobe.adapters.crewai import AgentProbeCrewHandler

handler = AgentProbeCrewHandler(session_name="my-crew")
crew.kickoff(callbacks=[handler])
```

### CI/CD

<details>
<summary><strong>GitHub Actions</strong></summary>

```yaml
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

</details>

<details>
<summary><strong>GitLab CI</strong></summary>

```yaml
agent-tests:
  image: python:3.12
  script:
    - pip install agentprobe[all]
    - agentprobe test --ci --report report.html
  artifacts:
    paths:
      - report.html
    when: always
```

</details>

<details>
<summary><strong>Jenkins</strong></summary>

```groovy
pipeline {
    agent { docker { image 'python:3.12' } }
    stages {
        stage('Agent Tests') {
            steps {
                sh 'pip install agentprobe[all]'
                sh 'agentprobe test --ci --report report.html'
            }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'report.html' }
    }
}
```

</details>

---

## CLI Reference

```
agentprobe record     Record an agent run into a .aprobe trace
agentprobe test       Run agent tests (pytest-compatible)
agentprobe replay     Replay a recording with a different model or config
agentprobe fuzz       Fuzz your agent with prompt injections & edge cases
agentprobe scan       Security scan — PII detection, injection resistance
agentprobe roast      Get a funny brutal analysis of your agent
agentprobe xray       Visualize agent thinking step-by-step
agentprobe health     5-dimension health check with scores
agentprobe cost       Calculate true cost projections & savings
agentprobe compare    Side-by-side model comparison
agentprobe playground Interactive prompt injection lab (55 attacks)
agentprobe leaderboard Rank and track your agents over time
agentprobe analyze    Cost breakdown, drift detection, failure clustering
agentprobe platform   Launch the local web dashboard (localhost:9700)
agentprobe init       Scaffold config file and example tests
agentprobe diff       Compare two recordings or agent versions
agentprobe timeline   Time-travel debugger — step through execution
agentprobe dna        Generate behavioral DNA fingerprint
agentprobe chaos      Run chaos engineering scenarios
agentprobe coverage   Agent path coverage report
agentprobe snapshot   Capture/compare behavioral snapshots
agentprobe optimize   Token & cost optimization analysis
agentprobe watch      Auto-run tests on file changes
agentprobe nltest     Generate tests from plain English
```

Run `agentprobe --help` for the full list.

---

## Platform

AgentProbe ships with a **local web dashboard** — no cloud, no accounts, no data leaves your machine.

```bash
agentprobe platform start
# Opens http://localhost:9700
```

```
+------------------------------------------------------------------+
|  AgentProbe Platform                           localhost:9700     |
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

Traces, cost breakdowns, assertion results, drift detection, and failure analysis — all in one place.

---

## Free vs. Pro

<table>
<tr>
<th>Feature</th>
<th align="center">Free</th>
<th align="center">Pro</th>
</tr>
<tr><td><strong>Recording & Replay</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>35+ Assertions</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>pytest Integration</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>Mock LLMs & Tools</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>CI/CD & GitHub Action</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>Cost & Latency Tracking</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>PII Detection (27 types)</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>Basic Fuzzing</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>Local Dashboard</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🔥 Agent Roast (450 jokes)</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🔬 X-Ray Visualization</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>💰 Cost Calculator & Projections</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🏥 Health Check (5 dimensions)</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🎮 Injection Playground (55 attacks)</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🏆 Agent Leaderboard</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>⚖️ Model Comparator</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>⏳ Timeline (Time Travel Debugger)</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🧬 Agent DNA (Behavioral Fingerprinting)</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🌀 Chaos Engineering (12 scenarios)</strong></td><td align="center">✅ (5 max)</td><td align="center">✅</td></tr>
<tr><td><strong>📊 Agent Path Coverage</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>📸 Snapshot Testing</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🚀 Token Optimizer</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>👀 Watch Mode</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td><strong>🧪 NL Test Writer</strong></td><td align="center">✅</td><td align="center">✅</td></tr>
<tr><td colspan="3"></td></tr>
<tr><td><strong>⚔️ Agent Battle Arena</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>🔬 Agent Autopsy</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>📋 Compliance (53 checks)</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>🛡️ Security Scorer (71 checks)</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>🧠 Agent Benchmark (6D)</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>🔀 Agent Diff & Changelog</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>🧠 Brain (auto-optimizer)</strong></td><td align="center">-</td><td align="center">✅</td></tr>
<tr><td><strong>Full Fuzzer (47+ variants)</strong></td><td align="center">-</td><td align="center">✅</td></tr>
</table>

<p align="center">
  <a href="https://agentprobe.dev/pro"><strong>Learn more about Pro &rarr;</strong></a>
</p>

---

## Why AgentProbe?

| | AgentProbe | Promptfoo | DeepEval | Ragas |
|---|:---:|:---:|:---:|:---:|
| Record agent traces | ✅ | - | - | - |
| Replay with model swap | ✅ | - | - | - |
| 35+ built-in assertions | ✅ | Custom | 14 | 8 |
| Prompt injection fuzzing | ✅ | Basic | - | - |
| Tool call assertions | ✅ | - | - | - |
| Cost & latency assertions | ✅ | - | Partial | - |
| PII detection | ✅ | - | - | - |
| Mock LLMs & tools | ✅ | - | - | - |
| pytest native | ✅ | - | Plugin | - |
| Framework agnostic | ✅ | LLM-only | LLM-only | RAG-only |
| Fully offline | ✅ | Partial | - | - |
| Local dashboard | ✅ | ✅ | ✅ | - |

---

## Examples

### Replay with a different model

```python
from agentprobe import Replayer, ReplayConfig

replayer = Replayer()
result = replayer.replay(
    "recordings/customer-support.aprobe",
    config=ReplayConfig(model="claude-sonnet-4-20250514", mock_tools=True),
)
comparison = replayer.compare(original, result)
print(comparison.summary)
# Output Similarity: 94.2%
# Cost: $0.0180 -> $0.0095 (-47.2%)
```

### Fuzz for prompt injections

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
# Strategy: PromptInjection | Tested: 47 | Failed: 2 | Failure rate: 4.3%
```

### Mock for fast, free, deterministic tests

```python
from agentprobe.mock import MockLLM, MockTool

mock_llm = MockLLM(responses=["Your order #1234 has been shipped."])
mock_search = MockTool(responses=[{"results": ["Order shipped on March 15"]}])

result = replayer.replay(
    recording,
    config=ReplayConfig(mock_llm=mock_llm, tool_mocks={"search_orders": mock_search}),
)
# Zero API calls. Zero cost. Deterministic.
```

### Time-travel through execution

```python
from agentprobe.timeline import TimelineDebugger

dbg = TimelineDebugger(recording)
dbg.add_breakpoint_tool("web_search")
dbg.add_breakpoint_cost(0.10)

state = dbg.step_forward()    # advance one step
state = dbg.run()             # run until breakpoint
print(state.cumulative_cost)  # $0.0847
print(dbg.render_timeline_bar())
# ██▒██▒▒▒▼██▒◆██
```

### Chaos-test your agent

```python
from agentprobe.chaos import ChaosEngine

engine = ChaosEngine(seed=42)
result = engine.run(recording)
print(f"Resilience: {result.resilience_score:.0f}/100 ({result.grade})")
# Resilience: 73/100 (B)
# Recommendations: Add retry logic for tool failures
```

### Write tests in English

```bash
agentprobe nltest \
  "respond in under 5 seconds" \
  "cost below $0.10" \
  "call the search tool at least once" \
  "no PII in output" \
  -o tests/test_generated.py
```

```python
# Auto-generated:
def test_agent(recording):
    assertions.latency_below(recording, max_ms=5000)
    assertions.cost_below(recording, max_cost_usd=0.10)
    assertions.called_tool(recording, tool_name="search")
    assertions.no_pii_in_output(recording)
```

### Agent DNA fingerprinting

```python
from agentprobe.dna import AgentDNA

dna = AgentDNA()
fp = dna.fingerprint(recording)
print(fp.signature)  # "CeSp-VbTf-DeDp"
print(dna.render_helix(fp))
# 🧬 Agent DNA Helix
#  💬 verbosity        ████████████░░░░░░░░ 0.62
#  🧰 tool_diversity   ██████████████░░░░░░ 0.71
#  ⚡ speed            ████████████████░░░░ 0.83
```

See more in the [`examples/`](examples/) directory.

---

## Contributing

Contributions are welcome. Here is how to get started:

```bash
git clone https://github.com/tomerhakak/agentprobe.git
cd agentprobe
pip install -e ".[dev,all]"
pytest
ruff check .
```

Please open an issue before submitting large PRs so we can discuss the approach.

---

## License

[MIT](LICENSE) — use it however you want.

---

<p align="center">
  <sub>Built by <a href="https://github.com/tomerhakak">@tomerhakak</a> &middot; <a href="https://agentprobe.dev">agentprobe.dev</a></sub>
</p>
