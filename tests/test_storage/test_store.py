"""Tests for agentprobe.storage.store."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentprobe.core.models import AgentRecording, RecordingMetadata
from agentprobe.storage.store import RecordingStore


@pytest.fixture
def store(tmp_path: Path) -> RecordingStore:
    """Create a RecordingStore backed by a temp SQLite database."""
    db_path = tmp_path / "test_index.db"
    return RecordingStore(db_path=db_path)


@pytest.fixture
def indexed_store(
    store: RecordingStore, sample_recording: AgentRecording, tmp_recording_dir: Path
) -> tuple[RecordingStore, AgentRecording, Path]:
    """A store with one recording already indexed."""
    filepath = tmp_recording_dir / "indexed.aprobe"
    sample_recording.save(filepath)
    store.index(sample_recording, filepath)
    return store, sample_recording, filepath


class TestCreateStore:
    def test_create_store(self, store: RecordingStore) -> None:
        assert store.count() == 0
        assert store.list_all() == []


class TestIndexAndGetRecording:
    def test_index_and_get_recording(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, recording, filepath = indexed_store
        result = store.get(recording.metadata.id)
        assert result is not None
        assert result["name"] == "weather-agent-test"
        assert result["id"] == recording.metadata.id
        assert result["framework"] == "custom"

    def test_get_nonexistent(self, store: RecordingStore) -> None:
        assert store.get("nonexistent-id") is None


class TestSearchByName:
    def test_search_by_name(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, recording, _ = indexed_store
        results = store.search(name="weather")
        assert len(results) == 1
        assert results[0]["name"] == "weather-agent-test"

    def test_search_by_name_no_match(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        results = store.search(name="nonexistent")
        assert len(results) == 0


class TestSearchByTags:
    def test_search_by_tags(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        results = store.search(tags=["weather"])
        assert len(results) == 1

    def test_search_by_tags_no_match(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        results = store.search(tags=["nonexistent"])
        assert len(results) == 0


class TestSearchByFramework:
    def test_search_by_framework(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        results = store.search(framework="custom")
        assert len(results) == 1

    def test_search_by_framework_no_match(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        results = store.search(framework="langchain")
        assert len(results) == 0


class TestDeleteRecording:
    def test_delete_recording(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, recording, _ = indexed_store
        assert store.count() == 1

        store.delete(recording.metadata.id)
        assert store.count() == 0
        assert store.get(recording.metadata.id) is None

    def test_delete_nonexistent_is_noop(self, store: RecordingStore) -> None:
        # Should not raise
        store.delete("nonexistent-id")
        assert store.count() == 0


class TestListAll:
    def test_list_all(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        results = store.list_all()
        assert len(results) == 1
        assert results[0]["name"] == "weather-agent-test"

    def test_list_all_with_multiple(
        self, store: RecordingStore, tmp_recording_dir: Path
    ) -> None:
        for i in range(5):
            rec = AgentRecording(
                metadata=RecordingMetadata(name=f"agent-{i}", agent_framework="custom")
            )
            filepath = tmp_recording_dir / f"rec_{i}.aprobe"
            rec.save(filepath)
            store.index(rec, filepath)

        results = store.list_all()
        assert len(results) == 5

    def test_list_all_with_limit(
        self, store: RecordingStore, tmp_recording_dir: Path
    ) -> None:
        for i in range(5):
            rec = AgentRecording(
                metadata=RecordingMetadata(name=f"agent-{i}", agent_framework="custom")
            )
            filepath = tmp_recording_dir / f"rec_{i}.aprobe"
            rec.save(filepath)
            store.index(rec, filepath)

        results = store.list_all(limit=3)
        assert len(results) == 3


class TestCount:
    def test_count(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        assert store.count() == 1

    def test_count_empty(self, store: RecordingStore) -> None:
        assert store.count() == 0


class TestStats:
    def test_stats(
        self, indexed_store: tuple[RecordingStore, AgentRecording, Path]
    ) -> None:
        store, _, _ = indexed_store
        stats = store.stats()

        assert stats["total_recordings"] == 1
        assert stats["total_cost_usd"] >= 0
        assert stats["total_tokens"] >= 0
        assert "by_framework" in stats
        assert "by_model" in stats
        assert "by_status" in stats
        assert "custom" in stats["by_framework"]
        assert stats["earliest_recording"] is not None
        assert stats["latest_recording"] is not None

    def test_stats_empty(self, store: RecordingStore) -> None:
        stats = store.stats()
        assert stats["total_recordings"] == 0
        assert stats["total_cost_usd"] == 0
        assert stats["total_tokens"] == 0
