"""Tests for agentprobe.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentprobe.core.config import AgentProbeConfig


class TestDefaultConfig:
    def test_default_config(self, sample_config: AgentProbeConfig) -> None:
        assert sample_config.project_name == "my-agent"
        assert sample_config.framework == "auto"
        assert sample_config.recording.auto_record is True
        assert sample_config.testing.parallel == 4
        assert sample_config.dashboard.port == 8484

    def test_default_config_via_class_method(self) -> None:
        cfg = AgentProbeConfig.default()
        assert cfg.project_name == "my-agent"
        assert cfg.recording.storage_dir == ".agentprobe/recordings"
        assert cfg.testing.default_max_cost_usd == 1.0


class TestConfigSaveAndLoad:
    def test_config_save_and_load(self, tmp_path: Path) -> None:
        cfg = AgentProbeConfig(project_name="test-project", framework="langchain")
        filepath = tmp_path / "agentprobe.yaml"
        cfg.save(filepath)
        assert filepath.exists()

        loaded = AgentProbeConfig.load(filepath)
        assert loaded.project_name == "test-project"
        assert loaded.framework == "langchain"

    def test_config_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        cfg = AgentProbeConfig.default()
        filepath = tmp_path / "deep" / "nested" / "agentprobe.yaml"
        cfg.save(filepath)
        assert filepath.exists()

    def test_config_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            AgentProbeConfig.load(tmp_path / "nonexistent.yaml")

    def test_config_roundtrip_preserves_values(self, tmp_path: Path) -> None:
        cfg = AgentProbeConfig(
            project_name="roundtrip",
            framework="crewai",
            default_model="claude-sonnet-4-6",
        )
        cfg.testing.timeout_seconds = 300.0
        cfg.dashboard.port = 9999

        filepath = tmp_path / "rt.yaml"
        cfg.save(filepath)
        loaded = AgentProbeConfig.load(filepath)

        assert loaded.project_name == "roundtrip"
        assert loaded.framework == "crewai"
        assert loaded.default_model == "claude-sonnet-4-6"
        assert loaded.testing.timeout_seconds == 300.0
        assert loaded.dashboard.port == 9999


class TestConfigProjectName:
    def test_config_project_name(self) -> None:
        cfg = AgentProbeConfig(project_name="my-cool-agent")
        assert cfg.project_name == "my-cool-agent"

    def test_config_project_settings(self) -> None:
        cfg = AgentProbeConfig.default()
        assert cfg.project.name == "my-agent"
        assert cfg.project.description == ""
