# Changelog

All notable changes to AgentProbe are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-04-04

### Added
- **Timeline** — Time Travel Debugger: step forward/backward through agent execution, set breakpoints on tools/cost/errors, inspect state at each point, interactive TUI mode (`agentprobe timeline`)
- **DNA** — Agent Behavioral Fingerprinting: generate unique multi-dimensional behavioral fingerprints, detect drift, compare agents, visual DNA helix rendering (`agentprobe dna`)
- **Chaos** — Chaos Engineering for Agents: 12 built-in chaos scenarios (tool timeouts, LLM hallucinations, cascading failures, cost spikes), resilience scoring, recovery analysis (`agentprobe chaos`)
- **Coverage** — Agent Path Coverage: track tool coverage, branch coverage, step pattern diversity, error path testing across recordings — like code coverage for AI agents (`agentprobe coverage`)
- **Snapshot** — Snapshot Testing: capture and compare behavioral snapshots (output, tools, cost, patterns) to detect regressions — like Jest snapshots for agents (`agentprobe snapshot`)
- **Optimizer** — Token & Prompt Optimization: detect wasted tokens, recommend model downgrades, identify caching opportunities, project monthly savings (`agentprobe optimize`)
- **Watch** — Live Monitoring Mode: auto-run tests when recordings or test files change — like nodemon for AI agents (`agentprobe watch`)
- **NLTest** — Natural Language Test Writer: write tests in plain English, auto-translate to executable pytest code with proper assertions (`agentprobe nltest`)

## [0.4.0] - 2026-04-02

### Added
- 🔥 Agent Roast: funny brutal analysis with 450 jokes, 3 severity levels (mild/medium/savage)
- 🔬 X-Ray Mode: live tree visualization of agent thinking with per-step costs
- 💰 Cost Calculator: true cost projections (daily/monthly/yearly) + savings recommendations
- 🏥 Health Check: 5-dimension scoring (reliability, speed, cost, security, quality)
- 🎮 Injection Playground: 55 prompt injection attacks across 5 categories
- 🏆 Leaderboard: SQLite-backed agent rankings with composite scoring and sparkline trends
- ⚖️ Model Comparator: side-by-side model comparison with winner detection

## [0.3.0] - 2026-04-02

### Added
- GitHub Action: test AI agents on every PR with cost limits and regression checks
- LangChain plugin with `AgentProbeCallbackHandler` for automatic recording
- CrewAI plugin with `AgentProbeCrewHandler` for multi-agent visibility
- CI module with PR comment reporting (`agentprobe ci report`)
- `--compare-baseline` flag for regression testing against a branch
- `--fail-on-cost-exceeded` flag for hard cost ceilings in CI

## [0.2.0] - 2026-04-01

### Added
- Local web platform at `localhost:9700` with interactive dashboard
- 35+ testing modules across 5 domains
- **Security**: prompt injection fuzzing (5 attack categories), PII detection (27 types), threat modeling
- **Compliance**: SOC2, HIPAA, GDPR, PCI-DSS, CCPA automated checks (53 controls)
- **Monitoring**: cost tracking with budget alerts, drift detection, latency histograms
- **Intelligence**: hallucination detection, model recommender, token-level cost attribution (X-Ray)
- **Arena**: agent-vs-agent battles with ELO rating system and LLM judge (Pro)
- Autopsy module for failure root-cause analysis
- Benchmark module for multi-dimensional agent evaluation
- Model comparison with automatic replay across providers
- HTML and JSON export for all reports

## [0.1.0] - 2026-03-31

### Added
- Initial release
- Core `@record` decorator for capturing LLM calls
- Recording and replay engine with model swapping
- Basic assertions: `assert_cost_under`, `assert_latency_under`, `assert_output_contains`, `assert_total_tokens_under`
- CLI interface (`agentprobe test`, `agentprobe serve`)
- JSON recording format for portability
