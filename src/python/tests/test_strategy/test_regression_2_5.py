"""Regression tests for Story 2.5 synthesis review fixes.

Each test targets a specific accepted finding and would have caught the
original bug. Marked with @pytest.mark.regression for filtering.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import tomli_w

from strategy.confirmer import confirm_specification
from strategy.modifier import (
    ModificationIntent,
    apply_modifications,
    apply_single_modification,
)
from strategy.specification import StrategySpecification
from strategy.storage import list_versions, load_latest_version, save_strategy_spec
from strategy.versioner import (
    VersionEntry,
    _format_value,
    compute_version_diff,
    create_manifest,
    update_manifest_version,
)


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


def _setup_spec_and_config(
    tmp_path: Path, version: str = "v001", status: str = "draft"
) -> tuple[Path, Path]:
    """Create a spec file and config dir. Returns (artifacts_dir, config_dir)."""
    artifacts_dir = tmp_path / "artifacts"
    config_dir = tmp_path / "config"

    strategy_dir = artifacts_dir / "strategies" / "test-slug"
    strategy_dir.mkdir(parents=True)
    spec_dict = _make_spec_dict(version=version, status=status)
    spec_path = strategy_dir / f"{version}.toml"
    spec_path.write_text(tomli_w.dumps(spec_dict), encoding="utf-8")

    config_dir.mkdir(parents=True)
    (config_dir / "base.toml").write_text(
        '[project]\nname = "test"\n[data]\npair = "EURUSD"\n',
        encoding="utf-8",
    )
    return artifacts_dir, config_dir


# ---------------------------------------------------------------------------
# Fix 1: Version overflow v999 → v1000 (BMAD H1 + Codex HIGH 3)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestVersionOverflowRoundtrip:
    """v1000+ must be accepted by StrategySpecification and storage layer."""

    def test_v1000_accepted_by_spec_model(self):
        """VERSION_PATTERN must accept 4+ digit versions."""
        d = _make_spec_dict(version="v1000")
        spec = StrategySpecification.model_validate(d)
        assert spec.metadata.version == "v1000"

    def test_v1000_storage_list_versions(self, tmp_path):
        """list_versions must find v1000.toml files."""
        strategy_dir = tmp_path / "strategies"
        strategy_dir.mkdir(parents=True)

        for v in ["v999", "v1000", "v1001"]:
            d = _make_spec_dict(version=v)
            (strategy_dir / f"{v}.toml").write_text(
                tomli_w.dumps(d), encoding="utf-8"
            )

        versions = list_versions(strategy_dir)
        assert "v999" in versions
        assert "v1000" in versions
        assert "v1001" in versions
        # Must be in numeric order
        assert versions.index("v999") < versions.index("v1000")
        assert versions.index("v1000") < versions.index("v1001")

    def test_v1000_load_latest(self, tmp_path):
        """load_latest_version must return v1000 when it's the highest."""
        strategy_dir = tmp_path / "strategies"
        strategy_dir.mkdir(parents=True)

        for v in ["v999", "v1000"]:
            d = _make_spec_dict(version=v)
            (strategy_dir / f"{v}.toml").write_text(
                tomli_w.dumps(d), encoding="utf-8"
            )

        spec, ver = load_latest_version(strategy_dir)
        assert ver == "v1000"

    def test_v999_save_auto_increments_to_v1000(self, tmp_path):
        """save_strategy_spec after v999 must produce v1000.toml, not collide."""
        strategy_dir = tmp_path / "strategies"
        strategy_dir.mkdir(parents=True)

        # Write v999 manually
        d = _make_spec_dict(version="v999")
        (strategy_dir / "v999.toml").write_text(
            tomli_w.dumps(d), encoding="utf-8"
        )

        spec = StrategySpecification.model_validate(_make_spec_dict())
        path = save_strategy_spec(spec, strategy_dir)
        assert path.name == "v1000.toml"
        assert path.exists()


# ---------------------------------------------------------------------------
# Fix 2: Lifecycle timestamps persisted (Codex HIGH 1 + BMAD M3/M4)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestLifecycleTimestampsPersisted:
    """confirmed_at and created_at must be stored in the spec and reloadable."""

    def test_confirmed_at_persisted_to_toml(self, tmp_path):
        """After confirmation, the saved TOML must contain confirmed_at."""
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        result = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)

        spec_path = artifacts_dir / "strategies" / "test-slug" / "v001.toml"
        with open(spec_path, "rb") as f:
            raw = tomllib.load(f)

        assert "confirmed_at" in raw["metadata"]
        assert raw["metadata"]["confirmed_at"] == result.confirmed_at

    def test_idempotent_confirm_returns_real_timestamp(self, tmp_path):
        """Idempotent confirm must return the actual confirmed_at, not empty string."""
        artifacts_dir, config_dir = _setup_spec_and_config(tmp_path)
        # First confirm
        result1 = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        # Idempotent second confirm
        result2 = confirm_specification("test-slug", "v001", artifacts_dir, config_dir)
        assert result2.confirmed_at != ""
        assert result2.confirmed_at == result1.confirmed_at

    def test_modifier_sets_created_at_on_new_version(self, tmp_path):
        """New versions from modifications must have created_at set."""
        artifacts_dir, _ = _setup_spec_and_config(tmp_path)
        mods = [
            ModificationIntent(
                field_path="exit_rules.stop_loss.value",
                action="set",
                new_value=2.0,
                description="wider stops",
            )
        ]
        result = apply_modifications("test-slug", mods, artifacts_dir)

        # Read back from disk
        v002_path = artifacts_dir / "strategies" / "test-slug" / "v002.toml"
        with open(v002_path, "rb") as f:
            raw = tomllib.load(f)
        assert "created_at" in raw["metadata"]
        assert raw["metadata"]["created_at"] is not None

    def test_created_at_and_confirmed_at_ignored_in_diff(self):
        """Timestamps must not appear in version diffs."""
        old_dict = _make_spec_dict(version="v001")
        old_dict["metadata"]["created_at"] = "2026-03-15T10:00:00Z"
        old = StrategySpecification.model_validate(old_dict)

        new_dict = _make_spec_dict(version="v002")
        new_dict["metadata"]["created_at"] = "2026-03-15T11:00:00Z"
        new_dict["metadata"]["confirmed_at"] = "2026-03-15T11:05:00Z"
        new = StrategySpecification.model_validate(new_dict)

        diff = compute_version_diff(old, new)
        paths = [c.field_path for c in diff.changes]
        assert "metadata.created_at" not in paths
        assert "metadata.confirmed_at" not in paths


# ---------------------------------------------------------------------------
# Fix 4: current_version regression (Codex MEDIUM 1)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestCurrentVersionNoRegression:
    """current_version must always track the highest version number."""

    def test_confirming_v001_after_v002_exists(self):
        """Confirming v001 must not regress current_version from v002."""
        entry1 = VersionEntry(
            version="v001",
            status="draft",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at=None,
            config_hash=None,
            spec_hash="aaa",
        )
        manifest = create_manifest("test-slug", entry1)

        entry2 = VersionEntry(
            version="v002",
            status="draft",
            created_at="2026-03-15T11:00:00Z",
            confirmed_at=None,
            config_hash=None,
            spec_hash="bbb",
        )
        manifest = update_manifest_version(manifest, entry2)
        assert manifest.current_version == "v002"

        # Now confirm v001 — current_version must stay v002
        entry1_confirmed = VersionEntry(
            version="v001",
            status="confirmed",
            created_at="2026-03-15T10:00:00Z",
            confirmed_at="2026-03-15T12:00:00Z",
            config_hash="hash1",
            spec_hash="aaa",
        )
        manifest = update_manifest_version(manifest, entry1_confirmed)
        assert manifest.current_version == "v002"
        assert manifest.latest_confirmed_version == "v001"


# ---------------------------------------------------------------------------
# Fix 5: _format_value nested dict repr (BMAD L4 + Codex HIGH 4)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestFormatValueNoPythonRepr:
    """Diff formatting must not expose raw Python dict/list syntax."""

    def test_nested_dict_no_braces(self):
        """Nested dicts must not produce {'key': 'value'} style output."""
        val = {"type": "session", "params": {"include": ["london"]}}
        formatted = _format_value(val)
        assert "{" not in formatted
        assert "}" not in formatted
        assert "[" not in formatted
        assert "]" not in formatted

    def test_simple_dict_readable(self):
        val = {"period": 20, "source": "close"}
        formatted = _format_value(val)
        assert "period: 20" in formatted
        assert "source: close" in formatted


# ---------------------------------------------------------------------------
# Fix 6: Modifier path error handling (Codex MEDIUM 2)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestModifierPathErrorHandling:
    """Invalid path operations must raise ValueError, not raw TypeError/IndexError."""

    def test_set_on_nonexistent_deep_path_raises_valueerror(self):
        """Setting a value on a path that doesn't exist in the spec structure."""
        spec = StrategySpecification.model_validate(_make_spec_dict())
        mod = ModificationIntent(
            field_path="exit_rules.trailing.type",
            action="set",
            new_value="trailing_stop",
            description="add trailing",
        )
        # trailing is None, so traversing into it should give a clear error
        # not a raw TypeError
        with pytest.raises((ValueError,)):
            apply_single_modification(spec, mod)
