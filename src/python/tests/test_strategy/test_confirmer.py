"""Tests for strategy confirmer module (Story 2.5, AC #2, #6, #7)."""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path

import pytest
import tomli_w

from strategy.confirmer import ConfirmationResult, confirm_specification
from strategy.specification import StrategySpecification
from strategy.versioner import load_manifest


def _make_spec_dict(version: str = "v001", status: str = "draft") -> dict:
    """Build a minimal valid spec dict for testing."""
    return {
        "metadata": {
            "schema_version": "1",
            "name": "test-strategy",
            "version": version,
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "test",
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


def _setup_spec_and_config(tmp_path: Path, version: str = "v001", status: str = "draft") -> tuple[Path, Path]:
    """Create a spec file and config dir for testing.

    Returns (artifacts_dir, config_dir).
    """
    artifacts_dir = tmp_path / "artifacts"
    config_dir = tmp_path / "config"

    # Create spec file
    strategy_dir = artifacts_dir / "strategies" / "test-slug"
    strategy_dir.mkdir(parents=True)
    spec_dict = _make_spec_dict(version=version, status=status)
    spec_path = strategy_dir / f"{version}.toml"
    spec_path.write_text(tomli_w.dumps(spec_dict), encoding="utf-8")

    # Create config
    config_dir.mkdir(parents=True)
    (config_dir / "base.toml").write_text(
        '[project]\nname = "test"\n[data]\npair = "EURUSD"\n',
        encoding="utf-8",
    )

    return artifacts_dir, config_dir


class TestConfirmSpecification:
    def test_confirm_sets_status_confirmed(self, tmp_path):
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        assert result.spec.metadata.status == "confirmed"

    def test_confirm_attaches_config_hash(self, tmp_path):
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        assert result.config_hash
        assert len(result.config_hash) > 0

    def test_confirm_attaches_confirmation_timestamp(self, tmp_path):
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        assert result.confirmed_at
        # Should be valid ISO format
        dt = datetime.fromisoformat(result.confirmed_at.replace("Z", "+00:00"))
        assert dt.year >= 2026

    def test_confirm_computes_spec_hash(self, tmp_path):
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        assert result.spec_hash
        assert len(result.spec_hash) == 64  # SHA-256 hex digest

    def test_confirm_idempotent_already_confirmed(self, tmp_path):
        """Confirming an already-confirmed spec returns existing result."""
        artifacts_dir, config_dir = _setup_spec_and_config(
            tmp_path, version="v001", status="confirmed"
        )
        # Need to add config_hash to the spec for idempotent case
        spec_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        spec_dict = _make_spec_dict(version="v001", status="confirmed")
        spec_dict["metadata"]["config_hash"] = "existing_hash"
        spec_path.write_text(tomli_w.dumps(spec_dict), encoding="utf-8")

        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        assert result.version == "v001"
        assert result.config_hash == "existing_hash"

    def test_confirm_updates_manifest(self, tmp_path):
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)

        manifest = load_manifest("test-slug", artifacts_dir)
        assert manifest is not None
        assert len(manifest.versions) >= 1
        v001 = next(v for v in manifest.versions if v.version == "v001")
        assert v001.status == "confirmed"
        assert v001.config_hash is not None

    def test_confirm_crash_safe_write(self, tmp_path):
        """Confirmed spec should be persisted to disk."""
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)

        # Re-read from disk
        spec_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        assert spec_path.exists()
        with open(spec_path, "rb") as f:
            raw = tomllib.load(f)
        assert raw["metadata"]["status"] == "confirmed"
        assert raw["metadata"]["config_hash"] is not None

    def test_confirm_sets_latest_confirmed_version(self, tmp_path):
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        confirm_specification("test-slug", "v001", artifacts_dir, config_dir)

        manifest = load_manifest("test-slug", artifacts_dir)
        assert manifest is not None
        assert manifest.latest_confirmed_version == "v001"

    def test_confirm_file_not_found(self, tmp_path):
        artifacts_dir = tmp_path / "artifacts"
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "base.toml").write_text('[project]\nname = "test"\n')

        with pytest.raises(FileNotFoundError):
            confirm_specification("nonexistent", "v001", artifacts_dir, config_dir)


@pytest.mark.regression
class TestConfirmerRegression:
    """Regression tests for bugs caught during Story 2.5 code review."""

    def test_confirmed_at_persisted_in_toml(self, tmp_path):
        """Regression: confirmed_at must be written to spec TOML and reloadable.

        Codex HIGH-1 flagged that confirm_specification() computed confirmed_at
        but never wrote it into spec_dict['metadata'] before saving.
        """
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)

        # Re-read from disk and verify confirmed_at is persisted
        spec_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        with open(spec_path, "rb") as f:
            raw = tomllib.load(f)

        assert "confirmed_at" in raw["metadata"]
        assert raw["metadata"]["confirmed_at"] == result.confirmed_at

    def test_created_at_not_overwritten_by_confirmation_time(self, tmp_path):
        """Regression: manifest created_at should reflect spec creation, not confirmation.

        BMAD M4 flagged that created_at fell back to confirmed_at when the
        metadata field was missing.
        """
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)

        # Write a spec with explicit created_at
        spec_dict = _make_spec_dict(version="v001", status="draft")
        spec_dict["metadata"]["created_at"] = "2026-03-15T08:00:00Z"
        spec_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        spec_path.write_text(tomli_w.dumps(spec_dict), encoding="utf-8")

        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)

        manifest = load_manifest("test-slug", artifacts_dir)
        v001 = next(v for v in manifest.versions if v.version == "v001")
        # created_at should be the original, not the confirmation time
        assert v001.created_at == "2026-03-15T08:00:00Z"
        assert v001.confirmed_at == result.confirmed_at
        assert v001.created_at != v001.confirmed_at

    def test_v999_roundtrip_through_model_validation(self, tmp_path):
        """Regression: v1000 must pass StrategySpecification model validation.

        BMAD H1 / Codex HIGH-3 flagged that VERSION_PATTERN only accepted
        exactly 3 digits, so v1000 would crash model_validate().
        """
        spec_dict = _make_spec_dict(version="v1000", status="draft")
        # This must not raise ValidationError
        spec = StrategySpecification.model_validate(spec_dict)
        assert spec.metadata.version == "v1000"

    def test_spec_hash_stable_before_and_after_confirmation(self, tmp_path):
        """Regression: spec_hash must not change when status/timestamps change.

        BMAD M6 / Codex MEDIUM-3 flagged spec_hash included lifecycle metadata.
        """
        from strategy.hasher import compute_spec_hash

        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)

        # Compute hash of draft spec
        spec_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        from strategy.loader import load_strategy_spec
        draft_spec = load_strategy_spec(spec_path)
        hash_before = compute_spec_hash(draft_spec)

        # Confirm it
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        hash_after = compute_spec_hash(result.spec)

        # Content hash must be identical — only lifecycle metadata changed
        assert hash_before == hash_after
