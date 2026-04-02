# Changelog

All notable changes to AgentProbe are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
