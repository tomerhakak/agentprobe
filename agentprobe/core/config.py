"""Configuration system for AgentProbe."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

class RecordingSettings(BaseModel):
    """Settings that control what gets captured in recordings."""

    auto_record: bool = True
    storage_dir: str = ".agentprobe/recordings"
    max_size_mb: float = 50.0
    capture_inputs: bool = True
    capture_outputs: bool = True
    capture_tool_calls: bool = True
    capture_llm_calls: bool = True
    capture_decisions: bool = True
    capture_system_prompt: bool = True
    redaction_patterns: List[str] = Field(default_factory=list)


class TestingSettings(BaseModel):
    """Settings for the test runner."""

    test_dir: str = "tests/agent_tests"
    default_max_cost_usd: float = 1.0
    default_max_latency_ms: float = 30000.0
    default_max_steps: int = 50
    parallel: int = 4
    timeout_seconds: float = 120.0


class LocalModelSettings(BaseModel):
    """Settings for local model evaluation."""

    provider: str = "none"  # "ollama" | "llamacpp" | "none"
    eval_model: str = ""
    embedding_model: str = ""
    ollama_url: str = "http://localhost:11434"


class DashboardSettings(BaseModel):
    """Settings for the local dashboard server."""

    port: int = 8484
    host: str = "127.0.0.1"


class CISettings(BaseModel):
    """Settings for CI/CD integration."""

    fail_on_regression: bool = True
    thresholds: Dict[str, float] = Field(default_factory=lambda: {
        "cost_increase_pct": 20.0,
        "latency_increase_pct": 20.0,
        "quality_decrease_pct": 5.0,
    })
    report_format: str = "markdown"  # "markdown" | "json" | "junit"


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------

_CONFIG_FILENAME = "agentprobe.yaml"


class ProjectSettings(BaseModel):
    """Project metadata."""

    name: str = "my-agent"
    description: str = ""


class AgentProbeConfig(BaseModel):
    """Root configuration for an AgentProbe project.

    Loads from ``agentprobe.yaml`` by searching the current directory and its
    parents.  All fields have sensible defaults so a config file is optional.
    """

    project: ProjectSettings = Field(default_factory=ProjectSettings)
    project_name: str = "my-agent"
    description: str = ""
    framework: str = "auto"  # auto/langchain/crewai/openai/anthropic/custom
    default_model: str = "claude-sonnet-4-6"

    recording: RecordingSettings = Field(default_factory=RecordingSettings)
    testing: TestingSettings = Field(default_factory=TestingSettings)
    local_model: LocalModelSettings = Field(default_factory=LocalModelSettings)
    cost_estimation: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom per-model pricing overrides: {model: {input_per_1k: float, output_per_1k: float}}",
    )
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)
    ci: CISettings = Field(default_factory=CISettings)

    # -- I/O ----------------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[Union[str, Path]] = None) -> AgentProbeConfig:
        """Load configuration from a YAML file.

        If *path* is ``None`` the method walks from the current working
        directory upward looking for ``agentprobe.yaml``.  If no file is found,
        the default configuration is returned.
        """
        if path is not None:
            resolved = Path(path)
            if resolved.is_file():
                return cls._from_yaml(resolved)
            raise FileNotFoundError(f"Config file not found: {resolved}")

        candidate = Path.cwd()
        while True:
            config_file = candidate / _CONFIG_FILENAME
            if config_file.is_file():
                return cls._from_yaml(config_file)
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent

        return cls.default()

    def save(self, path: Union[str, Path]) -> None:
        """Save configuration to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def default(cls) -> AgentProbeConfig:
        """Return the default configuration."""
        return cls()

    # -- Internal -----------------------------------------------------------

    @classmethod
    def _from_yaml(cls, path: Path) -> AgentProbeConfig:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
