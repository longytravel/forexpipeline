"""Tests for strategy modifier module (Story 2.5, AC #3, #4, #5)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import tomli_w

from strategy.modifier import (
    ModificationIntent,
    ModificationResult,
    apply_modifications,
    apply_single_modification,
    find_latest_version,
    parse_modification_intent,
)
from strategy.specification import StrategySpecification
from strategy.versioner import load_manifest


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
    return StrategySpecification.model_validate(base)


def _make_spec_dict() -> dict:
    """Return a minimal valid spec dict."""
    return {
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


def _setup_strategy_dir(tmp_path: Path, version: str = "v001") -> Path:
    """Create a strategy dir with a spec file. Returns artifacts_dir."""
    artifacts_dir = tmp_path / "artifacts"
    strategy_dir = artifacts_dir / "strategies" / "test-slug"
    strategy_dir.mkdir(parents=True)

    spec_dict = _make_spec_dict()
    spec_dict["metadata"]["version"] = version
    spec_path = strategy_dir / f"{version}.toml"
    spec_path.write_text(tomli_w.dumps(spec_dict), encoding="utf-8")

    return artifacts_dir


class TestParseModificationIntent:
    def test_parse_stop_loss(self):
        inp = {
            "modifications": [
                {
                    "field": "exit_rules.stop_loss.value",
                    "action": "set",
                    "value": 2.0,
                    "description": "wider stops",
                }
            ]
        }
        mods = parse_modification_intent(inp)
        assert len(mods) == 1
        assert mods[0].field_path == "exit_rules.stop_loss.value"
        assert mods[0].action == "set"
        assert mods[0].new_value == 2.0

    def test_parse_add_filter(self):
        inp = {
            "modifications": [
                {
                    "field": "entry_rules.filters",
                    "action": "add",
                    "value": {"type": "session", "params": {"include": ["london"]}},
                    "description": "add London session filter",
                }
            ]
        }
        mods = parse_modification_intent(inp)
        assert len(mods) == 1
        assert mods[0].action == "add"

    def test_parse_remove_filter(self):
        inp = {
            "modifications": [
                {
                    "field": "entry_rules.filters",
                    "action": "remove",
                    "value": {"type": "session", "params": {"include": ["london"]}},
                    "description": "remove London session filter",
                }
            ]
        }
        mods = parse_modification_intent(inp)
        assert mods[0].action == "remove"

    def test_parse_invalid_field(self):
        inp = {
            "modifications": [
                {
                    "field": "nonexistent.field.path",
                    "action": "set",
                    "value": 42,
                    "description": "bad field",
                }
            ]
        }
        with pytest.raises(ValueError, match="Unknown field path"):
            parse_modification_intent(inp)


class TestApplySingleModification:
    def test_set_stop_loss_value(self):
        spec = _make_spec()
        mod = ModificationIntent(
            field_path="exit_rules.stop_loss.value",
            action="set",
            new_value=2.0,
            description="wider stops",
        )
        new_spec = apply_single_modification(spec, mod)
        assert new_spec.exit_rules.stop_loss.value == 2.0
        # Original unchanged
        assert spec.exit_rules.stop_loss.value == 1.5

    def test_add_filter(self):
        spec = _make_spec()
        mod = ModificationIntent(
            field_path="entry_rules.filters",
            action="add",
            new_value={"type": "session", "params": {"include": ["london"]}},
            description="add London filter",
        )
        new_spec = apply_single_modification(spec, mod)
        assert len(new_spec.entry_rules.filters) == 1
        assert new_spec.entry_rules.filters[0].type == "session"


class TestApplyModifications:
    def test_creates_new_version(self, tmp_path):
        artifacts_dir = _setup_strategy_dir(tmp_path)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result = apply_modifications("test-slug", mods, artifacts_dir)
        assert result.new_version == "v002"
        assert result.old_version == "v001"

    def test_preserves_previous_version(self, tmp_path):
        artifacts_dir = _setup_strategy_dir(tmp_path)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        apply_modifications("test-slug", mods, artifacts_dir)

        # v001 should still exist unchanged
        v001_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        assert v001_path.exists()
        with open(v001_path, "rb") as f:
            raw = tomllib.load(f)
        assert raw["exit_rules"]["stop_loss"]["value"] == 1.5

    def test_validates_modified_spec(self, tmp_path):
        """Modified spec passes Story 2.3 validation."""
        artifacts_dir = _setup_strategy_dir(tmp_path)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result = apply_modifications("test-slug", mods, artifacts_dir)
        # If we got here without error, validation passed
        assert result.new_spec.exit_rules.stop_loss.value == 2.0

    def test_diff_shows_changes(self, tmp_path):
        artifacts_dir = _setup_strategy_dir(tmp_path)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result = apply_modifications("test-slug", mods, artifacts_dir)
        assert len(result.diff.changes) >= 1
        assert any("stop_loss" in c.field_path for c in result.diff.changes)

    def test_multiple_modifications(self, tmp_path):
        artifacts_dir = _setup_strategy_dir(tmp_path)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            ),
            ModificationIntent(
                field_path="position_sizing.risk_percent",
                action="set",
                new_value=2.0,
                description="increase risk",
            ),
        ]
        result = apply_modifications("test-slug", mods, artifacts_dir)
        assert result.new_spec.exit_rules.stop_loss.value == 2.0
        assert result.new_spec.position_sizing.risk_percent == 2.0

    def test_modification_to_confirmed_spec(self, tmp_path):
        """Modifying a confirmed spec creates a new draft version."""
        artifacts_dir = tmp_path / "artifacts"
        strategy_dir = artifacts_dir / "strategies" / "test-slug"
        strategy_dir.mkdir(parents=True)

        spec_dict = _make_spec_dict()
        spec_dict["metadata"]["status"] = "confirmed"
        spec_dict["metadata"]["config_hash"] = "abc123"
        (strategy_dir / "v001.toml").write_text(
            tomli_w.dumps(spec_dict), encoding="utf-8"
        )

        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result = apply_modifications("test-slug", mods, artifacts_dir)
        assert result.new_spec.metadata.status == "draft"
        assert result.new_version == "v002"


class TestFindLatestVersion:
    def test_finds_highest_version(self, tmp_path):
        artifacts_dir = _setup_strategy_dir(tmp_path, version="v001")
        # Add v002
        strategy_dir = artifacts_dir / "strategies" / "test-slug"
        spec_dict = _make_spec_dict()
        spec_dict["metadata"]["version"] = "v002"
        (strategy_dir / "v002.toml").write_text(
            tomli_w.dumps(spec_dict), encoding="utf-8"
        )

        ver, path = find_latest_version("test-slug", artifacts_dir)
        assert ver == "v002"

    def test_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            find_latest_version("nonexistent", tmp_path)
