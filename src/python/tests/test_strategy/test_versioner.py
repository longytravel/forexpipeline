"""Tests for strategy versioner module (Story 2.5, AC #4, #5, #7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategy.specification import StrategySpecification
from strategy.versioner import (
    FieldChange,
    SpecificationManifest,
    VersionDiff,
    VersionEntry,
    compute_version_diff,
    create_manifest,
    format_diff_text,
    increment_version,
    load_manifest,
    save_manifest,
    update_manifest_version,
)


def _make_spec(**overrides) -> StrategySpecification:
    """Build a minimal valid StrategySpecification for testing."""
    base = {
        "metadata": {
            "schema_version": "1",
            "name": "test-strategy",
            "version": "v001",
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "test",
            "status": "draft",
        },
        "entry_rules": {
            "conditions": [
                {
                    "indicator": "sma_crossover",
                    "parameters": {"fast_period": 20, "slow_period": 50},
                    "threshold": 0.0,
                    "comparator": "crosses_above",
                }
            ],
            "filters": [],
            "confirmation": [],
        },
        "exit_rules": {
            "stop_loss": {"type": "atr_multiple", "value": 1.5},
            "take_profit": {"type": "risk_reward", "value": 3.0},
        },
        "position_sizing": {
            "method": "fixed_risk",
            "risk_percent": 1.0,
            "max_lots": 1.0,
        },
    }
    for key, val in overrides.items():
        parts = key.split(".")
        d = base
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = val
    return StrategySpecification.model_validate(base)


class TestIncrementVersion:
    def test_v001_to_v002(self):
        assert increment_version("v001") == "v002"

    def test_v099_to_v100(self):
        assert increment_version("v099") == "v100"

    def test_v999_to_v1000(self):
        assert increment_version("v999") == "v1000"

    def test_v010_to_v011(self):
        assert increment_version("v010") == "v011"


class TestComputeVersionDiff:
    def test_diff_stop_loss_change(self):
        old = _make_spec()
        new_dict = old.model_dump(mode="python")
        new_dict["exit_rules"]["stop_loss"]["value"] = 2.0
        new_dict["metadata"]["version"] = "v002"
        new_spec = StrategySpecification.model_validate(new_dict)

        diff = compute_version_diff(old, new_spec)
        assert len(diff.changes) >= 1
        paths = [c.field_path for c in diff.changes]
        assert "exit_rules.stop_loss.value" in paths

    def test_diff_filter_added(self):
        old = _make_spec()
        new_dict = old.model_dump(mode="python")
        new_dict["entry_rules"]["filters"].append(
            {"type": "session", "params": {"include": ["london"]}}
        )
        new_dict["metadata"]["version"] = "v002"
        new_spec = StrategySpecification.model_validate(new_dict)

        diff = compute_version_diff(old, new_spec)
        assert len(diff.changes) >= 1
        assert any("filters" in c.field_path for c in diff.changes)

    def test_diff_filter_removed(self):
        old_dict = {
            "metadata": {
                "schema_version": "1",
                "name": "test-strategy",
                "version": "v001",
                "pair": "EURUSD",
                "timeframe": "H1",
                "created_by": "test",
                "status": "draft",
            },
            "entry_rules": {
                "conditions": [
                    {
                        "indicator": "sma_crossover",
                        "parameters": {"fast_period": 20, "slow_period": 50},
                        "threshold": 0.0,
                        "comparator": "crosses_above",
                    }
                ],
                "filters": [
                    {"type": "session", "params": {"include": ["london"]}}
                ],
                "confirmation": [],
            },
            "exit_rules": {
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "risk_reward", "value": 3.0},
            },
            "position_sizing": {
                "method": "fixed_risk",
                "risk_percent": 1.0,
                "max_lots": 1.0,
            },
        }
        old = StrategySpecification.model_validate(old_dict)

        new_dict = old.model_dump(mode="python")
        new_dict["entry_rules"]["filters"] = []
        new_dict["metadata"]["version"] = "v002"
        new_spec = StrategySpecification.model_validate(new_dict)

        diff = compute_version_diff(old, new_spec)
        assert len(diff.changes) >= 1
        assert any("filters" in c.field_path for c in diff.changes)

    def test_diff_multiple_changes(self):
        old = _make_spec()
        new_dict = old.model_dump(mode="python")
        new_dict["exit_rules"]["stop_loss"]["value"] = 2.0
        new_dict["position_sizing"]["risk_percent"] = 2.0
        new_dict["metadata"]["version"] = "v002"
        new_spec = StrategySpecification.model_validate(new_dict)

        diff = compute_version_diff(old, new_spec)
        assert len(diff.changes) >= 2

    def test_diff_no_changes(self):
        spec = _make_spec()
        diff = compute_version_diff(spec, spec)
        assert len(diff.changes) == 0

    def test_diff_ignores_metadata(self):
        """Version/status changes should not appear in diff."""
        old = _make_spec()
        new_dict = old.model_dump(mode="python")
        new_dict["metadata"]["version"] = "v002"
        new_dict["metadata"]["status"] = "confirmed"
        new_dict["metadata"]["config_hash"] = "abc123"
        new_spec = StrategySpecification.model_validate(new_dict)

        diff = compute_version_diff(old, new_spec)
        # Only metadata fields we ignore should change
        paths = [c.field_path for c in diff.changes]
        assert "metadata.version" not in paths
        assert "metadata.status" not in paths
        assert "metadata.config_hash" not in paths

    def test_format_diff_plain_english(self):
        diff = VersionDiff(
            old_version="v001",
            new_version="v002",
            changes=[
                FieldChange(
                    field_path="exit_rules.stop_loss.value",
                    old_value="1.5",
                    new_value="2.0",
                    description="Stop loss value changed from 1.5 to 2.0",
                )
            ],
        )
        text = format_diff_text(diff)
        assert "v001" in text
        assert "v002" in text
        assert "Stop loss" in text
        assert "1.5" in text
        assert "2.0" in text


class TestManifest:
    def test_manifest_create(self):
        entry = VersionEntry(
            version="v001",
            status="draft",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at=None,
            config_hash=None,
            spec_hash="abc123",
        )
        manifest = create_manifest("test-slug", entry)
        assert manifest.strategy_slug == "test-slug"
        assert len(manifest.versions) == 1
        assert manifest.current_version == "v001"
        assert manifest.latest_confirmed_version is None

    def test_manifest_update_version(self):
        entry1 = VersionEntry(
            version="v001",
            status="draft",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at=None,
            config_hash=None,
            spec_hash="abc123",
        )
        manifest = create_manifest("test-slug", entry1)

        entry2 = VersionEntry(
            version="v002",
            status="draft",
            created_at="2026-03-15T11:00:00Z",
            confirmed_at=None,
            config_hash=None,
            spec_hash="def456",
        )
        manifest = update_manifest_version(manifest, entry2)
        assert len(manifest.versions) == 2
        assert manifest.current_version == "v002"

    def test_manifest_confirmation_recorded(self):
        entry = VersionEntry(
            version="v001",
            status="confirmed",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at="2026-03-15T10:05:00Z",
            config_hash="config_hash_abc",
            spec_hash="spec_hash_def",
        )
        manifest = create_manifest("test-slug", entry)
        v = manifest.versions[0]
        assert v.confirmed_at == "2026-03-15T10:05:00Z"
        assert v.config_hash == "config_hash_abc"

    def test_manifest_roundtrip_json(self, tmp_path):
        entry = VersionEntry(
            version="v001",
            status="confirmed",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at="2026-03-15T10:05:00Z",
            config_hash="config_hash_abc",
            spec_hash="spec_hash_def",
        )
        manifest = create_manifest("test-roundtrip", entry)
        save_manifest(manifest, tmp_path)

        loaded = load_manifest("test-roundtrip", tmp_path)
        assert loaded is not None
        assert loaded.strategy_slug == manifest.strategy_slug
        assert loaded.current_version == manifest.current_version
        assert loaded.latest_confirmed_version == manifest.latest_confirmed_version
        assert len(loaded.versions) == len(manifest.versions)
        assert loaded.versions[0].version == "v001"
        assert loaded.versions[0].confirmed_at == "2026-03-15T10:05:00Z"
        assert loaded.versions[0].config_hash == "config_hash_abc"

    def test_manifest_latest_confirmed_version(self):
        """latest_confirmed_version updated on confirmation, stable after new draft."""
        entry1 = VersionEntry(
            version="v001",
            status="confirmed",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at="2026-03-15T10:05:00Z",
            config_hash="hash1",
            spec_hash="spec1",
        )
        manifest = create_manifest("test-slug", entry1)
        assert manifest.latest_confirmed_version == "v001"

        # Add a new draft — latest_confirmed should stay v001
        entry2 = VersionEntry(
            version="v002",
            status="draft",
            created_at="2026-03-15T11:00:00Z",
            confirmed_at=None,
            config_hash=None,
            spec_hash="spec2",
        )
        manifest = update_manifest_version(manifest, entry2)
        assert manifest.latest_confirmed_version == "v001"
        assert manifest.current_version == "v002"

    def test_manifest_load_nonexistent(self, tmp_path):
        result = load_manifest("nonexistent", tmp_path)
        assert result is None
