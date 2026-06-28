# AgentProbe — Portfolio Overview

## What this project is

AgentProbe is a Python-based testing, recording, replay, and analysis framework for AI agents. The idea is similar to `pytest`, but focused on LLM/AI-agent behavior: every agent run can be recorded, tested, replayed, inspected, compared, and monitored.

The project is designed for teams and developers who build AI agents and need a practical way to answer questions such as:

- Did the agent call the right tools?
- Did the output contain unsafe or sensitive information?
- Did the cost stay below budget?
- Did the agent behavior change after a prompt/model/code update?
- Can we reproduce a failed agent run?
- Can we compare one model or prompt version against another?

## Why I built it

AI agents can look impressive in a demo but fail in production because their behavior is non-deterministic, hard to debug, and expensive to monitor. AgentProbe was built to solve that gap: it gives an AI-agent workflow a more engineering-oriented testing layer.

The project demonstrates my ability to take a real technical problem, break it into product features, design the developer experience, and turn it into a working open-source-style project.

## Core capabilities

### Recording

AgentProbe records LLM calls, tool calls, inputs, outputs, costs, latency, and execution metadata into portable trace files.

### Testing

The framework includes assertions for output quality, tool usage, cost limits, latency, safety checks, and PII leakage.

### Replay

A recorded agent run can be replayed with a different model or configuration to compare behavior, cost, and reliability.

### Security and safety checks

The project includes prompt-injection testing, PII detection, and safety-oriented assertions for AI-agent workflows.

### Cost and monitoring

AgentProbe tracks token usage, cost per run, latency, drift, and failure patterns so agent behavior can be analyzed over time.

### Local dashboard

The project includes a local platform concept for viewing traces, cost trends, test results, and debugging information without sending data to an external service.

## Technical areas demonstrated

- Python package structure and CLI design
- AI-agent testing concepts
- LLM call recording and replay architecture
- Prompt-injection and safety testing
- Cost tracking and token analysis
- Local-first architecture
- CI/CD and GitHub Actions integration concept
- Developer documentation and product positioning
- Open-source project structure

## How to explain this in interviews

A strong way to explain the project:

> I built AgentProbe as a testing and observability framework for AI agents. The goal was to bring a pytest-like workflow to AI-agent systems: record an agent run, test its behavior, replay it, compare versions, track cost, and detect safety issues like prompt injection or PII leakage. The project shows both technical implementation and product thinking around how AI agents should be validated before production.

## What this shows about me

This project shows that I can:

- Understand a real AI/automation problem
- Translate a problem into a product concept
- Design a technical architecture around data, traces, tests, and monitoring
- Work with Python and developer-tooling patterns
- Think like both a technical analyst and a product-oriented builder
- Create documentation that makes a technical project understandable to others

## Notes for employers

This is a personal portfolio project by Tomer Hakak. The repository is intended to demonstrate practical AI-agent, automation, testing, and data-oriented thinking. The project was developed as part of hands-on learning and portfolio building in the AI/automation space.
