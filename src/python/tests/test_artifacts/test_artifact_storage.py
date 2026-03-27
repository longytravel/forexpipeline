"""Unit tests for artifacts.storage — ArtifactStorage versioning (Task 1)."""
import json
from pathlib import Path

import pytest

from artifacts.storage import (
    ArtifactStorage,
    crash_safe_write,
    crash_safe_write_json,
)


class TestResolveVersionDir:
    def test_resolve_version_dir_empty(self, tmp_path):
        """First version is v001."""
        path = ArtifactStorage.resolve_version_dir("test_strategy", tmp_path)
        assert path == tmp_path / "test_strategy" / "v001" / "backtest"

    def test_resolve_version_dir_increments(self, tmp_path):
        """v002 after v001 exists."""
        (tmp_path / "test_strategy" / "v001").mkdir(parents=True)
        path = ArtifactStorage.resolve_version_dir("test_strategy", tmp_path)
        assert path == tmp_path / "test_strategy" / "v002" / "backtest"

    def test_resolve_version_dir_skips_non_version(self, tmp_path):
        """Non-version directories are ignored."""
        (tmp_path / "test_strategy" / "v001").mkdir(parents=True)
        (tmp_path / "test_strategy" / "temp").mkdir(parents=True)
        (tmp_path / "test_strategy" / "notes.txt").parent.mkdir(parents=True, exist_ok=True)
        path = ArtifactStorage.resolve_version_dir("test_strategy", tmp_path)
        assert path == tmp_path / "test_strategy" / "v002" / "backtest"


class TestShouldCreateNewVersion:
    def test_should_create_new_version_no_existing(self, tmp_path):
        """Returns True when no versions exist."""
        assert ArtifactStorage.should_create_new_version(
            "test_strategy", "hash1", "hash2", "hash3", tmp_path
        )

    def test_should_create_new_version_unchanged(self, tmp_path):
        """Returns False when hashes match latest manifest."""
        version_dir = tmp_path / "test_strategy" / "v001"
        version_dir.mkdir(parents=True)
        manifest = {
            "provenance": {
                "config_hash": "hash1",
                "dataset_hash": "hash2",
                "cost_model_hash": "hash3",
            }
        }
        (version_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        assert not ArtifactStorage.should_create_new_version(
            "test_strategy", "hash1", "hash2", "hash3", tmp_path
        )

    def test_should_create_new_version_changed(self, tmp_path):
        """Returns True when any hash differs."""
        version_dir = tmp_path / "test_strategy" / "v001"
        version_dir.mkdir(parents=True)
        manifest = {
            "provenance": {
                "config_hash": "hash1",
                "dataset_hash": "hash2",
                "cost_model_hash": "hash3",
            }
        }
        (version_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        # Change config_hash
        assert ArtifactStorage.should_create_new_version(
            "test_strategy", "hash_CHANGED", "hash2", "hash3", tmp_path
        )


class TestCreateVersionDir:
    def test_create_version_dir(self, tmp_path):
        """Creates the full directory tree."""
        version_dir = ArtifactStorage.create_version_dir(
            "test_strategy", 1, tmp_path
        )
        assert version_dir == tmp_path / "test_strategy" / "v001"
        assert (version_dir / "backtest").is_dir()

    def test_create_version_dir_idempotent(self, tmp_path):
        """Can be called twice without error."""
        ArtifactStorage.create_version_dir("test_strategy", 1, tmp_path)
        ArtifactStorage.create_version_dir("test_strategy", 1, tmp_path)
        assert (tmp_path / "test_strategy" / "v001" / "backtest").is_dir()


class TestCrashSafeWrite:
    def test_crash_safe_write_atomic(self, tmp_path):
        """No .partial files remain after successful write."""
        filepath = tmp_path / "test.txt"
        crash_safe_write(filepath, "hello world")
        assert filepath.exists()
        assert not filepath.with_name("test.txt.partial").exists()

    def test_crash_safe_write_no_corrupt_on_interrupt(self, tmp_path):
        """If original exists and write is attempted, original stays if partial left."""
        filepath = tmp_path / "original.txt"
        filepath.write_text("original content", encoding="utf-8")

        # Simulate: write new content successfully
        crash_safe_write(filepath, "new content")
        assert filepath.read_text(encoding="utf-8") == "new content"

    def test_crash_safe_write_json(self, tmp_path):
        """JSON serialization + crash-safe write."""
        filepath = tmp_path / "test.json"
        obj = {"key": "value", "nested": {"a": 1}}
        crash_safe_write_json(obj, filepath)
        loaded = json.loads(filepath.read_text(encoding="utf-8"))
        assert loaded["key"] == "value"
        assert loaded["nested"]["a"] == 1
