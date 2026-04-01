# AgentProbe Launch Content Kit

> **Copy-paste ready content for every platform.**
> GitHub: https://github.com/tomerhakak/agentprobe
> Tagline: "pytest for AI Agents -- Record, test, and monitor AI agents locally."

---

## 1. Hacker News

**Title (78 chars):**

```
Show HN: AgentProbe – pytest for AI agents. Record, test, fuzz, replay locally
```

**URL to submit:**

```
https://github.com/tomerhakak/agentprobe
```

**Best time to post:** Tuesday, 6:00 AM PT

**First comment (paste immediately after submitting):**

```
Hi HN, I built AgentProbe because I kept shipping AI agents with no way to test them properly.

We have pytest for code. We have Lighthouse for web performance. But for AI agents — systems that call LLMs, invoke tools, make multi-step decisions, and cost real money per run — there's nothing. When my support agent suddenly started costing $2.40 per query instead of $0.12, I had no way to catch that before production. When I swapped from GPT-4o to Claude, I couldn't tell if behavior actually changed. I was flying blind.

AgentProbe fixes this. You add a `@record` decorator to your agent, and it captures every LLM call, tool invocation, and routing decision into a portable trace file. Then you write tests against those traces using 35+ built-in assertions — things like `total_cost_less_than(0.05)`, `called_tools_in_order(["search", "respond"])`, `no_pii_in_output()`, and `output_contains("refund policy")`. You can replay recordings with different models to compare cost and quality. You can fuzz your agent with 47+ prompt injection variants automatically. Everything runs locally, offline, in your CI pipeline. No data leaves your machine.

It's framework-agnostic (works with OpenAI, Anthropic, LangChain, CrewAI, or any custom agent), has native pytest integration, includes a local dashboard, and the entire thing is MIT licensed. `pip install agentprobe` to get started. Would love feedback from anyone building agents — what assertions would you want that don't exist yet?
```

---

## 2. Reddit Posts

---

### r/MachineLearning

**Title:**

```
[P] AgentProbe: pytest for AI Agents — Record, test, fuzz, and replay AI agent traces locally
```

**Body:**

```
I've been building AI agents for the past year and the testing story is terrible. We have mature testing for APIs, for frontends, for data pipelines — but for agents that make multi-step LLM calls, invoke tools, and cost real money per execution? Nothing.

**AgentProbe** is an open-source Python library that brings real testing to AI agents:

- **Record** every LLM call, tool invocation, and decision into portable trace files
- **Assert** with 35+ built-in checks: output quality, cost budgets, latency, tool usage order, PII detection, safety
- **Replay** recordings with different models/prompts and compare cost, quality, and behavior
- **Fuzz** with 47+ prompt injection variants to find safety holes automatically
- **Mock** LLMs and tools for fast, free, deterministic tests
- **Dashboard** — local web UI showing traces, cost trends, and drift detection

It integrates natively with pytest, works with any framework (OpenAI, Anthropic, LangChain, CrewAI), runs fully offline, and fits directly into CI/CD.

Quick example:

    from agentprobe import assertions as A

    def test_support_agent(recording):
        A.set_recording(recording)
        A.output_contains("refund policy")
        A.called_tool("search_kb")
        A.total_cost_less_than(0.05)
        A.no_pii_in_output()

Install: `pip install agentprobe`

GitHub: https://github.com/tomerhakak/agentprobe

MIT licensed. Feedback welcome — especially on what assertions or features you'd want for your agent workflows.
```

---

### r/artificial

**Title:**

```
I built an open-source testing framework for AI agents — like pytest but for LLM-powered systems
```

**Body:**

```
AI agents are hard to test. They call LLMs, invoke tools, make routing decisions — and when something breaks or costs spike, you have no reproducible way to catch it.

I built **AgentProbe** to fix this. It records every LLM call, tool invocation, and decision your agent makes. Then you write tests against those traces:

- Assert output quality, cost budgets, latency, tool call order
- Replay with different models and compare behavior
- Fuzz with prompt injections automatically
- Detect PII leakage
- Run in CI/CD with native pytest integration

Works with OpenAI, Anthropic, LangChain, CrewAI, or any custom agent. Fully local and offline.

`pip install agentprobe`

GitHub: https://github.com/tomerhakak/agentprobe

Open source (MIT). Would love to hear what testing challenges you're facing with agents.
```

---

### r/LocalLLaMA

**Title:**

```
AgentProbe: open-source tool to test AI agents locally — record traces, assert cost/quality, fuzz for injections
```

**Body:**

```
If you're running agents locally, you probably care about testing them properly. I built AgentProbe to make that easy.

**What it does:**

- Records every LLM call and tool invocation into trace files
- 35+ assertions for output quality, cost, latency, safety, and tool usage
- Replay recordings with a different model — swap GPT-4o for a local Llama and compare quality, cost, and behavior side by side
- Fuzz testing with prompt injection variants
- Mock LLMs for deterministic, zero-cost test runs
- Local dashboard at localhost:9700

**Why LocalLLaMA folks will care:** The replay feature is killer for model comparison. Record a trace with GPT-4o, replay with your local model, and get an instant comparison:

    Steps: 5 -> 4 (delta: -1)
    Output Similarity: 94.2%
    Cost: $0.0180 -> $0.0095 (-47.2%)

Everything runs locally. No data sent anywhere. MIT licensed.

`pip install agentprobe`

GitHub: https://github.com/tomerhakak/agentprobe
```

---

### r/Python

**Title:**

```
AgentProbe: pytest for AI agents — record, test, and replay LLM agent traces with 35+ built-in assertions
```

**Body:**

```
I built a Python testing library specifically for AI agents. If you've tried to write tests for systems that call LLMs, invoke tools, and make multi-step decisions, you know how painful it is. AgentProbe makes it feel like regular pytest.

**Install:**

    pip install agentprobe

**Record your agent:**

    from agentprobe import record

    @record("customer-support")
    def run_agent(query, session):
        session.set_input(query)
        # your agent logic
        session.set_output(answer)

**Write tests:**

    from agentprobe import assertions as A

    def test_agent(recording):
        A.set_recording(recording)
        A.output_contains("refund policy")
        A.called_tools_in_order(["search_kb", "format_response"])
        A.total_cost_less_than(0.05)
        A.total_tokens_less_than(4000)
        A.no_pii_in_output()

**Run:**

    agentprobe test

**Key features:**

- 35+ built-in assertions (cost, latency, output quality, tool usage, PII, safety)
- Native pytest plugin — just `pip install` and your fixtures work
- Replay traces with different models and compare results
- Fuzz with prompt injection variants
- Mock LLMs and tools for zero-cost deterministic tests
- Local dashboard for trace inspection
- Framework agnostic: OpenAI, Anthropic, LangChain, CrewAI, custom

Built with Click, Rich, Pydantic, and FastAPI. Python 3.10+. MIT licensed.

GitHub: https://github.com/tomerhakak/agentprobe

Happy to answer questions about the design or take feature requests.
```

---

### r/programming

**Title:**

```
AgentProbe: A testing framework for AI agents — record traces, assert behavior, fuzz for prompt injections
```

**Body:**

```
We have mature testing tools for APIs (Postman), web apps (Cypress), and services (pytest, JUnit). But AI agents — systems that call LLMs, invoke tools, and make multi-step decisions — have nothing comparable.

AgentProbe is an open-source Python library that brings proper testing to AI agents:

1. **Record** — Capture every LLM call, tool invocation, and decision into portable trace files
2. **Assert** — 35+ built-in assertions: output quality, cost budgets, latency caps, tool call ordering, PII detection
3. **Replay** — Re-run traces with different models/prompts, compare output similarity, cost delta, and behavior changes
4. **Fuzz** — Automatically test 47+ prompt injection variants and report failure rates
5. **Mock** — Replace LLMs and tools with deterministic mocks for fast CI runs
6. **Dashboard** — Local web UI for trace inspection and cost trends

It integrates as a native pytest plugin, runs fully offline, and works with any agent framework.

Example test:

    def test_agent(recording):
        A.set_recording(recording)
        A.output_contains("refund policy")
        A.called_tool("search_kb")
        A.total_cost_less_than(0.05)
        A.no_pii_in_output()

GitHub: https://github.com/tomerhakak/agentprobe

MIT licensed. `pip install agentprobe`
```

---

### r/SideProject

**Title:**

```
I built pytest for AI agents — record, test, and monitor your agents locally
```

**Body:**

```
**Problem:** AI agents are untestable black boxes. When one run costs $0.12 and the next costs $2.40, there's no way to catch it. When you swap models, no way to compare behavior.

**Solution:** AgentProbe records everything your agent does into trace files. You write tests against those traces — output quality, cost, latency, tool usage, safety. Run them in CI like any other test suite.

**Features:**
- 35+ built-in assertions
- Replay with different models and compare
- Prompt injection fuzzing (47+ variants)
- Mock LLMs for free deterministic tests
- Local dashboard
- Native pytest integration
- Works with OpenAI, Anthropic, LangChain, CrewAI

**Stack:** Python, Click, Rich, Pydantic, FastAPI

**Status:** v0.1.0, MIT licensed, on PyPI

`pip install agentprobe`

GitHub: https://github.com/tomerhakak/agentprobe

Would love feedback from anyone building agents!
```

---

## 3. Twitter/X Thread

**Tweet 1 (Hook):**

```
I built pytest for AI agents.

Record every LLM call, tool invocation, and decision.
Test with 35+ assertions.
Fuzz for prompt injections.
Replay with different models.

All local. All offline. All in your CI pipeline.

It's called AgentProbe, and it's open source.

github.com/tomerhakak/agentprobe
```

**Tweet 2 (The problem):**

```
The problem:

AI agents are black boxes.

One run costs $0.12. The next costs $2.40.
You swap models — did behavior change?
A prompt injection slips through — how do you catch it?
PII leaks into a response — when did that start?

There is no pytest for agents. Until now.
```

**Tweet 3 (Features + terminal mockup):**

```
What it looks like:

$ agentprobe test

 test_basic_response .............. PASS
 test_uses_search_tool ........... PASS
 test_cost_within_budget ......... PASS
 test_no_pii_leakage ............. PASS
 test_injection_resistance ....... FAIL

 4 passed, 1 failed in 1.8s
 Total cost: $0.0034 | Tokens: 1,247
```

**Tweet 4 (Code example):**

```
Write agent tests like regular pytest:

from agentprobe import assertions as A

def test_agent(recording):
    A.output_contains("refund policy")
    A.called_tool("search_kb")
    A.total_cost_less_than(0.05)
    A.no_pii_in_output()

That's it. pip install agentprobe.
```

**Tweet 5 (CTA):**

```
AgentProbe is:

- MIT licensed
- Framework agnostic (OpenAI, Anthropic, LangChain, CrewAI)
- Fully offline
- On PyPI right now

pip install agentprobe

Star it if this is useful:
github.com/tomerhakak/agentprobe

What assertions would you want? Reply and I'll add them.
```

---

## 4. LinkedIn Post

```
We have pytest for code. Lighthouse for web performance. k6 for load testing.

But for AI agents — systems that call LLMs, invoke tools, route decisions, and cost real money per execution — we've had nothing.

I just open-sourced AgentProbe: a testing framework that treats AI agents as first-class testable systems.

Here's what it does:

Record every LLM call, tool invocation, and routing decision your agent makes into portable trace files. Write tests against those traces using 35+ built-in assertions — for output quality, cost budgets, latency, tool usage patterns, PII detection, and safety. Replay recordings with different models to compare behavior and cost. Fuzz your agent with prompt injection variants to find vulnerabilities before production does.

The key insight: agent testing isn't just about "does the output look right." It's about cost control, behavioral consistency, safety guarantees, and reproducibility. AgentProbe gives you all of these in a single pip install.

It integrates natively with pytest, works with any agent framework (OpenAI, Anthropic, LangChain, CrewAI), runs fully offline, and drops straight into your CI/CD pipeline. No data leaves your machine.

We're at v0.1.0 and looking for feedback from teams building production agents.

pip install agentprobe
https://github.com/tomerhakak/agentprobe

MIT licensed. If you're shipping AI agents without tests, you're shipping bugs you can't see.

#AI #MachineLearning #LLM #Testing #OpenSource #Python #AIAgents
```

---

## 5. Dev.to Article

```
---
title: "I Built pytest for AI Agents — Here's Why Agent Testing Is Broken"
published: true
tags: ai, python, testing, opensource
cover_image: https://raw.githubusercontent.com/tomerhakak/agentprobe/main/docs/assets/cover.png
---

We test our APIs. We test our frontends. We test our data pipelines. But AI agents? We cross our fingers and ship.

That needs to change.

## The Problem Nobody Talks About

AI agents are fundamentally different from traditional software. A REST endpoint returns the same response for the same input. An AI agent calls an LLM (non-deterministic), picks tools based on the response (branching), calls more LLMs (compounding non-determinism), and produces a final output that might be completely different on the next run.

And every single step costs money.

I've been building production agents for the past year, and here's what kept happening:

- **Cost spikes with no explanation.** One run costs $0.12, the next costs $2.40. Which LLM call caused it? No idea.
- **Model swaps break things silently.** Switching from GPT-4o to Claude changed tool-calling behavior in subtle ways I didn't catch for weeks.
- **Prompt injections slip through.** A user input like "ignore previous instructions" made my support agent leak internal documentation.
- **No reproducibility.** When something failed, I couldn't replay the exact sequence of calls to debug it.

I looked for a pytest equivalent for agents. I found prompt evaluation tools (Promptfoo, DeepEval, Ragas) — but they test LLM outputs, not agent behavior. None of them could tell me "did my agent call the right tools in the right order and stay under budget?"

So I built one.

## What Is AgentProbe?

AgentProbe is an open-source Python library that records, tests, replays, and monitors AI agents. Think of it as pytest specifically designed for agentic systems.

Install it:

```bash
pip install agentprobe
```

## Quick Start

### Step 1: Record your agent

Add the `@record` decorator to capture everything:

```python
from agentprobe import record, RecordingSession

@record("customer-support")
def run_agent(query: str, session: RecordingSession) -> str:
    session.set_input(query)
    # Your existing agent logic here
    session.add_llm_call(model="gpt-4o", input_messages=[...], output_message=response)
    session.add_tool_call(tool_name="search_kb", tool_input={"q": query}, tool_output=results)
    session.set_output(answer)
    return answer
```

Every LLM call, tool invocation, and decision gets captured into a portable `.aprobe` trace file.

### Step 2: Write tests

Use 35+ built-in assertions:

```python
from agentprobe import assertions as A

def test_customer_support(recording):
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

### Step 3: Run

```bash
$ agentprobe test

 tests/test_agent.py
  PASS  test_basic_response .................. 0.8s
  PASS  test_uses_search_tool ................ 0.3s
  PASS  test_cost_within_budget .............. 0.1s
  PASS  test_no_pii_leakage .................. 0.2s
  FAIL  test_prompt_injection_resistance ..... 0.4s

 4 passed, 1 failed in 1.8s
 Total cost: $0.0034 | Tokens: 1,247
```

## Key Features

### Replay with Model Swap

Record a trace with GPT-4o, replay it with Claude, and compare:

```python
from agentprobe import Replayer, ReplayConfig

result = replayer.replay(
    "recordings/customer-support.aprobe",
    config=ReplayConfig(model="claude-sonnet-4-20250514", mock_tools=True),
)
comparison = replayer.compare(original, result)
print(comparison.summary)
# Output Similarity: 94.2%
# Cost: $0.0180 -> $0.0095 (-47.2%)
```

This is how you make data-driven model decisions instead of guessing.

### Prompt Injection Fuzzing

Automatically test your agent against 47+ injection variants:

```python
from agentprobe.fuzz import Fuzzer, PromptInjection

result = Fuzzer().run(
    agent_fn=run_agent,
    strategies=[PromptInjection()],
    assertions=lambda A: [
        A.no_pii_in_output(),
        A.output_not_contains("IGNORE PREVIOUS"),
    ],
)
# Variants tested: 47 | Passed: 45 | Failed: 2 | Failure rate: 4.3%
```

### Mock Everything

For CI, mock LLMs and tools so tests are fast, free, and deterministic:

```python
from agentprobe.mock import MockLLM, MockTool

mock_llm = MockLLM(responses=["Your order has been shipped."])
mock_search = MockTool(responses=[{"results": ["Order shipped March 15"]}])
# Zero API calls. Zero cost. Deterministic output.
```

### Local Dashboard

```bash
agentprobe dashboard
# Opens localhost:9700 — trace viewer, cost trends, drift detection
```

## Why It Matters

The AI agent ecosystem is moving fast. Teams are shipping agents to production that handle customer support, code generation, data analysis, and financial decisions. These systems need the same testing rigor as any production software.

AgentProbe brings that rigor without requiring you to change your agent architecture, send data to a third party, or learn a new paradigm. If you know pytest, you already know AgentProbe.

## Framework Support

AgentProbe is framework-agnostic. It works with:

- OpenAI SDK
- Anthropic SDK
- LangChain
- CrewAI
- Any custom agent (manual recording)

## Get Started

```bash
pip install agentprobe
agentprobe init
agentprobe test
```

GitHub: [github.com/tomerhakak/agentprobe](https://github.com/tomerhakak/agentprobe)

MIT licensed. Star the repo if it's useful, open an issue if it's not. I'm actively building based on community feedback — what assertions or features would make this useful for your agents?
```

---

## 6. Product Hunt

**Tagline (under 60 chars):**

```
pytest for AI Agents — test, record, replay, fuzz
```

**Description (under 260 chars):**

```
AgentProbe records every LLM call and tool invocation your AI agent makes. Write tests with 35+ assertions for cost, quality, safety, and behavior. Replay with different models. Fuzz for prompt injections. All local, all offline, all in your CI pipeline.
```

**5 Key Features:**

```
- Record every LLM call, tool invocation, and routing decision into portable trace files
- 35+ built-in assertions for output quality, cost budgets, latency, tool usage, and PII detection
- Replay recordings with different models and compare cost, quality, and behavior side by side
- Automatic prompt injection fuzzing with 47+ attack variants and failure rate reporting
- Local dashboard with trace viewer, cost trends, and behavioral drift detection
```

**First Comment from Maker:**

```
Hi Product Hunt! I'm the maker of AgentProbe.

I built this because I was shipping AI agents to production with zero testing infrastructure. We had pytest for code, Lighthouse for web perf, but nothing for agents — systems that call LLMs, invoke tools, and cost real money per execution.

The breaking point was when my support agent's cost spiked 20x overnight. I had no traces, no assertions, no way to reproduce the issue. I realized we needed a dedicated testing framework that understands agent-specific concerns: cost budgets, tool call ordering, prompt injection resistance, PII leakage, and behavioral consistency across model changes.

AgentProbe captures everything into portable traces, gives you 35+ assertions to test against, lets you replay with different models, and fuzzes for safety vulnerabilities — all locally, no data sent anywhere.

It's MIT licensed, on PyPI (`pip install agentprobe`), and works with OpenAI, Anthropic, LangChain, CrewAI, or any custom agent.

I'd love to hear what testing challenges you're facing with AI agents — that's what drives the roadmap. Thanks for checking it out!
```

---

## 7. Discord Messages

---

### LangChain Discord

```
Hey everyone! I just open-sourced AgentProbe — a testing framework for AI agents. Think "pytest for agents."

It records every LLM call and tool invocation into traces, then lets you write assertions like:
- `A.called_tools_in_order(["retriever", "summarizer"])`
- `A.total_cost_less_than(0.05)`
- `A.no_pii_in_output()`

It has a LangChain adapter built in. Works as a native pytest plugin.

You can also replay recordings with different models and compare output similarity + cost, and fuzz for prompt injections automatically.

pip install agentprobe[langchain]
https://github.com/tomerhakak/agentprobe

MIT licensed. Would love feedback from LangChain builders!
```

---

### OpenAI Discord

```
Just released AgentProbe — an open-source testing framework for AI agents.

If you're building agents with the OpenAI SDK, AgentProbe records every API call, tool invocation, and decision into trace files. Then you test against them:

- Assert cost < $0.05 per run
- Assert tool call order
- Assert no PII in output
- Fuzz for prompt injections (47+ variants)
- Replay with different models and compare

Has a built-in OpenAI adapter. Native pytest integration.

pip install agentprobe[openai]
https://github.com/tomerhakak/agentprobe

Feedback welcome!
```

---

### Anthropic Discord

```
Hey! I built AgentProbe — pytest for AI agents. Just open-sourced it.

Records agent traces (LLM calls, tool invocations, routing decisions), then you write tests with 35+ assertions for cost, quality, safety, and behavior.

Has a built-in Anthropic SDK adapter. The replay feature is great for comparing Claude models — record with Sonnet, replay with Haiku, see the cost/quality tradeoff instantly.

pip install agentprobe[anthropic]
https://github.com/tomerhakak/agentprobe

MIT licensed. Would love feedback from folks building Claude-powered agents!
```

---

### Python Discord

```
Just released AgentProbe v0.1.0 — a pytest plugin for testing AI agents.

If you're building anything that calls LLMs and tools, this gives you:
- `@record` decorator to capture traces
- 35+ assertions (cost, latency, output quality, tool usage, PII detection)
- Replay with model swap + comparison
- Prompt injection fuzzing
- Mock LLMs and tools for fast deterministic tests
- Local dashboard

Built with Click, Rich, Pydantic, FastAPI. Python 3.10+. Native pytest integration.

pip install agentprobe
https://github.com/tomerhakak/agentprobe

MIT licensed. PRs welcome!
```

---

## 8. Email to AI Newsletters

**Target newsletters:** The Batch, TLDR AI, Ben's Bites, AI Breakfast, The Neuron

**Subject line:**

```
Open-source launch: AgentProbe — pytest for AI agents (record, test, fuzz, replay)
```

**Email body:**

```
Hi [Newsletter Name] team,

I just open-sourced AgentProbe, a Python testing framework for AI agents. The one-line pitch: it's pytest for AI agents — record every LLM call and tool invocation, test with 35+ assertions, fuzz for prompt injections, and replay with different models. All local, all offline.

THE PROBLEM: AI agents are shipping to production untested. We have mature testing tools for APIs, frontends, and data pipelines — but nothing for agentic systems that make multi-step LLM calls, invoke tools, and cost real money per execution. When an agent's cost spikes 20x or a prompt injection leaks internal data, teams have no way to catch it before users do.

WHAT AGENTPROBE DOES: It captures everything an agent does into portable trace files, then provides 35+ built-in assertions for output quality, cost budgets, latency, tool usage patterns, PII detection, and safety. Developers can replay recordings with different models to make data-driven model decisions (e.g., "switching from GPT-4o to Claude Sonnet reduces cost 47% with 94% output similarity"). The fuzzer automatically tests agents against 47+ prompt injection variants. It integrates as a native pytest plugin and runs in CI/CD pipelines. Framework-agnostic: works with OpenAI, Anthropic, LangChain, CrewAI, or any custom agent.

WHY NOW: The agent ecosystem is exploding — LangChain, CrewAI, OpenAI Agents SDK, Anthropic tool use — but testing infrastructure hasn't kept up. AgentProbe fills that gap. It's MIT licensed, on PyPI (pip install agentprobe), and the GitHub repo is at https://github.com/tomerhakak/agentprobe.

Happy to provide additional details, screenshots, or a demo. Thank you for considering it for inclusion.

Best,
Tomer Hakak
https://github.com/tomerhakak/agentprobe
```

---

*End of Launch Kit. Copy, paste, ship.*
