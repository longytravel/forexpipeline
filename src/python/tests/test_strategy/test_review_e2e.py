"""End-to-end tests for strategy review/confirmation/versioning (Story 2.5).

Tests full workflows: review→confirm, modify→review→confirm, modification chains.
Also contains @pytest.mark.live integration tests that exercise real file I/O.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import tomli_w

from strategy.confirmer import confirm_specification
from strategy.modifier import ModificationIntent, apply_modifications
from strategy.reviewer import format_summary_text, generate_summary, save_summary_artifact
from strategy.specification import StrategySpecification
from strategy.versioner import (
    compute_version_diff,
    format_diff_text,
    load_manifest,
    save_manifest,
)


def _make_spec_dict(version: str = "v001", status: str = "draft") -> dict:
    """Build a minimal valid spec dict."""
    return {
        "metadata": {
            "schema_version": "1",
            "name": "test-e2e-strategy",
            "version": version,
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "e2e-test",
            "status": status,
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


def _setup_full_env(tmp_path: Path) -> tuple[Path, Path]:
    """Create strategy dir + config dir with spec v001.

    Returns (artifacts_dir, config_dir).
    """
    artifacts_dir = tmp_path / "artifacts"
    config_dir = tmp_path / "config"

    # Strategy spec
    strategy_dir = artifacts_dir / "strategies" / "e2e-slug"
    strategy_dir.mkdir(parents=True)
    spec_dict = _make_spec_dict()
    (strategy_dir / "v001.toml").write_text(
        tomli_w.dumps(spec_dict), encoding="utf-8"
    )

    # Config
    config_dir.mkdir(parents=True)
    (config_dir / "base.toml").write_text(
        '[project]\nname = "e2e-test"\n[data]\npair = "EURUSD"\n',
        encoding="utf-8",
    )

    return artifacts_dir, config_dir


class TestE2EReviewConfirmFlow:
    """AC #1, #2, #6, #7: review → confirm → verify."""

    def test_e2e_review_confirm_flow(self, tmp_path):
        artifacts_dir, config_dir = _setup_full_env(tmp_path)
        strategy_dir = artifacts_dir / "strategies" / "e2e-slug"

        # Step 1: Load spec and generate review
        spec_path = strategy_dir / "v001.toml"
        with open(spec_path, "rb") as f:
            raw = tomllib.load(f)
        spec = StrategySpecification.model_validate(raw)

        summary = generate_summary(spec)
        text = format_summary_text(summary)

        # Verify review quality
        assert "EURUSD" in text
        assert "H1" in text
        assert "SMA Crossover" in text
        assert "1.5" in text  # stop loss
        assert "London" in text  # filter
        assert summary.status == "draft"

        # Save review artifact
        review_path = save_summary_artifact(text, "e2e-slug", "v001", artifacts_dir)
        assert review_path.exists()

        # Step 2: Confirm
        result = confirm_specification("e2e-slug", "v001", artifacts_dir, config_dir)
        assert result.spec.metadata.status == "confirmed"
        assert result.config_hash
        assert result.spec_hash
        assert result.confirmed_at

        # Step 3: Verify manifest
        manifest = load_manifest("e2e-slug", artifacts_dir)
        assert manifest is not None
        assert manifest.latest_confirmed_version == "v001"
        v001 = next(v for v in manifest.versions if v.version == "v001")
        assert v001.status == "confirmed"
        assert v001.config_hash is not None


class TestE2EModifyReviewConfirmFlow:
    """AC #3, #4, #5: modify → review → confirm."""

    def test_e2e_modify_review_confirm_flow(self, tmp_path):
        artifacts_dir, config_dir = _setup_full_env(tmp_path)

        # Step 1: Modify (wider stops)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        mod_result = apply_modifications("e2e-slug", mods, artifacts_dir)
        assert mod_result.new_version == "v002"
        assert mod_result.old_version == "v001"

        # Step 2: Verify diff
        diff_text = format_diff_text(mod_result.diff)
        assert "v001" in diff_text
        assert "v002" in diff_text
        assert any("stop_loss" in c.field_path for c in mod_result.diff.changes)

        # Step 3: Review v002
        summary = generate_summary(mod_result.new_spec)
        text = format_summary_text(summary)
        assert "2.0" in text  # new stop loss value

        # Step 4: Confirm v002
        result = confirm_specification("e2e-slug", "v002", artifacts_dir, config_dir)
        assert result.spec.metadata.status == "confirmed"

        # Step 5: Verify manifest
        manifest = load_manifest("e2e-slug", artifacts_dir)
        assert manifest.latest_confirmed_version == "v002"
        assert manifest.current_version == "v002"

        # Both versions in manifest
        versions = {v.version for v in manifest.versions}
        assert "v001" in versions
        assert "v002" in versions


class TestE2EModificationChain:
    """AC #4, #7: v001 → v002 → v003, all preserved."""

    def test_e2e_modification_chain(self, tmp_path):
        artifacts_dir, config_dir = _setup_full_env(tmp_path)
        strategy_dir = artifacts_dir / "strategies" / "e2e-slug"

        # Modify 1: v001 → v002
        mods1 = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result1 = apply_modifications("e2e-slug", mods1, artifacts_dir)
        assert result1.new_version == "v002"

        # Modify 2: v002 → v003
        mods2 = [
            ModificationIntent(
                field_path="position_sizing.risk_percent",
                action="set",
                new_value=2.0,
                description="increase risk",
            )
        ]
        result2 = apply_modifications("e2e-slug", mods2, artifacts_dir)
        assert result2.new_version == "v003"

        # All versions preserved
        assert (strategy_dir / "v001.toml").exists()
        assert (strategy_dir / "v002.toml").exists()
        assert (strategy_dir / "v003.toml").exists()

        # Manifest tracks all
        manifest = load_manifest("e2e-slug", artifacts_dir)
        assert manifest is not None
        assert manifest.current_version == "v003"
        assert len(manifest.versions) == 3

        # Diff artifacts exist
        diffs_dir = strategy_dir / "diffs"
        assert (diffs_dir / "v001_v002_diff.txt").exists()
        assert (diffs_dir / "v002_v003_diff.txt").exists()


# ============================================================
# LIVE INTEGRATION TESTS — @pytest.mark.live
# ============================================================

@pytest.mark.live
class TestLiveReviewConfirmFlow:
    """Live integration: real file I/O, real hashing, real validation."""

    def test_live_full_review_confirm_cycle(self, tmp_path):
        """Full cycle: create spec → review → save artifact → confirm → verify manifest."""
        artifacts_dir, config_dir = _setup_full_env(tmp_path)

        # Review
        spec_path = artifacts_dir / "strategies" / "e2e-slug" / "v001.toml"
        with open(spec_path, "rb") as f:
            raw = tomllib.load(f)
        spec = StrategySpecification.model_validate(raw)
        summary = generate_summary(spec)
        text = format_summary_text(summary)

        # Save review artifact
        review_path = save_summary_artifact(text, "e2e-slug", "v001", artifacts_dir)
        assert review_path.exists()
        content = review_path.read_text(encoding="utf-8")
        assert "EURUSD" in content
        assert "SMA Crossover" in content

        # Confirm
        result = confirm_specification("e2e-slug", "v001", artifacts_dir, config_dir)

        # Verify persisted spec on disk
        with open(spec_path, "rb") as f:
            confirmed_raw = tomllib.load(f)
        assert confirmed_raw["metadata"]["status"] == "confirmed"
        assert confirmed_raw["metadata"]["config_hash"] is not None

        # Verify manifest on disk
        manifest_path = artifacts_dir / "strategies" / "e2e-slug" / "manifest.json"
        assert manifest_path.exists()
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        assert manifest_data["latest_confirmed_version"] == "v001"

    def test_live_modification_chain_artifacts(self, tmp_path):
        """Live: v001 → v002 → v003, verify all disk artifacts."""
        artifacts_dir, config_dir = _setup_full_env(tmp_path)
        strategy_dir = artifacts_dir / "strategies" / "e2e-slug"

        # Modify twice
        mods1 = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        apply_modifications("e2e-slug", mods1, artifacts_dir)

        mods2 = [
            ModificationIntent(
                field_path="exit_rules.take_profit.value",
                action="set",
                new_value=4.0,
                description="higher TP",
            )
        ]
        apply_modifications("e2e-slug", mods2, artifacts_dir)

        # Verify all TOML files on disk
        for ver in ["v001", "v002", "v003"]:
            path = strategy_dir / f"{ver}.toml"
            assert path.exists(), f"{ver}.toml missing"
            with open(path, "rb") as f:
                raw = tomllib.load(f)
            assert raw["metadata"]["version"] == ver

        # Verify diffs on disk
        assert (strategy_dir / "diffs" / "v001_v002_diff.txt").exists()
        assert (strategy_dir / "diffs" / "v002_v003_diff.txt").exists()

        # Verify diff content
        diff_content = (strategy_dir / "diffs" / "v001_v002_diff.txt").read_text()
        assert "stop_loss" in diff_content.lower() or "Stop loss" in diff_content

        # Verify manifest
        manifest = load_manifest("e2e-slug", artifacts_dir)
        assert manifest.current_version == "v003"
        assert len(manifest.versions) == 3

    def test_live_confirm_then_modify_preserves_confirmed(self, tmp_path):
        """Live: confirm v001, then modify → v002 draft. v001 stays confirmed."""
        artifacts_dir, config_dir = _setup_full_env(tmp_path)

        # Confirm v001
        confirm_specification("e2e-slug", "v001", artifacts_dir, config_dir)

        # Modify → v002
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result = apply_modifications("e2e-slug", mods, artifacts_dir)
        assert result.new_spec.metadata.status == "draft"

        # Manifest: latest_confirmed stays v001
        manifest = load_manifest("e2e-slug", artifacts_dir)
        assert manifest.latest_confirmed_version == "v001"
        assert manifest.current_version == "v002"

        # v001 on disk is still confirmed
        with open(artifacts_dir / "strategies" / "e2e-slug" / "v001.toml", "rb") as f:
            v001_raw = tomllib.load(f)
        assert v001_raw["metadata"]["status"] == "confirmed"
