"""Live integration tests for strategy specification pipeline.

These tests exercise REAL system behavior:
- Load real TOML files from disk
- Write real versioned specs
- Validate full pipeline end-to-end
"""

import tomllib
from pathlib import Path

import pytest

from strategy.hasher import compute_spec_hash, verify_spec_hash
from strategy.indicator_registry import get_registry, is_indicator_known, reset_registry
from strategy.loader import load_strategy_spec, validate_strategy_spec
from strategy.storage import (
    list_versions,
    load_latest_version,
    save_strategy_spec,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MA_CROSSOVER_SPEC = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v002.toml"
INDICATOR_REGISTRY_TOML = PROJECT_ROOT / "contracts" / "indicator_registry.toml"
STRATEGY_SCHEMA_TOML = PROJECT_ROOT / "contracts" / "strategy_specification.toml"
ERROR_CODES_TOML = PROJECT_ROOT / "contracts" / "error_codes.toml"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


@pytest.mark.live
def test_live_full_validation_pipeline():
    """End-to-end: load real MA crossover spec, validate, hash, verify.

    Exercises the full pipeline against the actual reference artifact on disk.
    """
    # Verify the file exists on disk
    assert MA_CROSSOVER_SPEC.exists(), f"Reference spec not found: {MA_CROSSOVER_SPEC}"

    # Load and structural validation
    spec = load_strategy_spec(MA_CROSSOVER_SPEC)
    assert spec.metadata.name == "ma-crossover"
    assert spec.metadata.version == "v002"
    assert spec.metadata.pair == "EURUSD"
    # Verify single sma_crossover condition (review synthesis fix C1)
    assert len(spec.entry_rules.conditions) == 1
    assert spec.entry_rules.conditions[0].indicator == "sma_crossover"
    # Verify v2 flat optimization plan
    assert spec.optimization_plan is not None
    assert spec.optimization_plan.schema_version == 2
    assert "fast_period" in spec.optimization_plan.parameters

    # Semantic validation (indicator registry lookup)
    errors = validate_strategy_spec(spec)
    assert errors == [], f"Semantic validation failed: {errors}"

    # Hash determinism
    h1 = compute_spec_hash(spec)
    h2 = compute_spec_hash(spec)
    assert h1 == h2
    assert len(h1) == 64

    # Hash verification
    assert verify_spec_hash(spec, h1) is True


@pytest.mark.live
def test_live_versioned_storage_roundtrip(tmp_path):
    """Save real spec to disk, reload, verify content and versioning.

    Tests crash-safe write, auto-increment, and immutability on real filesystem.
    """
    # Load real reference spec
    spec = load_strategy_spec(MA_CROSSOVER_SPEC)

    # Save v001 and v002
    strategy_dir = tmp_path / "strategies" / "live-test"
    p1 = save_strategy_spec(spec, strategy_dir)
    p2 = save_strategy_spec(spec, strategy_dir)

    # Verify files on disk
    assert p1.exists()
    assert p2.exists()
    assert p1.name == "v001.toml"
    assert p2.name == "v002.toml"

    # Verify v001 content unchanged after v002 write (immutability)
    with open(p1, "rb") as f:
        raw1 = tomllib.load(f)
    assert raw1["metadata"]["name"] == "ma-crossover"

    # Verify versioning
    versions = list_versions(strategy_dir)
    assert versions == ["v001", "v002"]

    # Load latest
    loaded_spec, version = load_latest_version(strategy_dir)
    assert version == "v002"
    assert loaded_spec.metadata.name == spec.metadata.name
    # Verify metadata.version updated to match filename (review synthesis fix H-AC6)
    assert loaded_spec.metadata.version == "v002"

    # Hash roundtrip: reload v001 to compare same-version hashes
    from strategy.loader import load_strategy_spec as _load
    v001_reloaded = _load(p1)
    h_orig = compute_spec_hash(spec)
    h_v001 = compute_spec_hash(v001_reloaded)
    assert h_orig == h_v001


@pytest.mark.live
def test_live_contracts_exist_and_parse():
    """Verify all contract TOML files exist on disk and parse correctly."""
    # Strategy specification schema contract
    assert STRATEGY_SCHEMA_TOML.exists(), f"Schema contract missing: {STRATEGY_SCHEMA_TOML}"
    with open(STRATEGY_SCHEMA_TOML, "rb") as f:
        schema = tomllib.load(f)
    assert "metadata" in schema
    assert "entry_rules" in schema
    assert "exit_rules" in schema
    assert "position_sizing" in schema
    assert "optimization_plan" in schema
    assert "cost_model_reference" in schema

    # Indicator registry contract
    assert INDICATOR_REGISTRY_TOML.exists(), f"Indicator registry missing: {INDICATOR_REGISTRY_TOML}"
    registry = get_registry(INDICATOR_REGISTRY_TOML)
    assert len(registry) >= 18  # D10 minimum

    # Error codes contract has strategy section
    assert ERROR_CODES_TOML.exists(), f"Error codes missing: {ERROR_CODES_TOML}"
    with open(ERROR_CODES_TOML, "rb") as f:
        error_codes = tomllib.load(f)
    strategy_codes = error_codes.get("strategy", {})
    assert "SPEC_SCHEMA_INVALID" in strategy_codes
    assert "SPEC_INDICATOR_UNKNOWN" in strategy_codes
    assert "SPEC_PARAM_RANGE_INVALID" in strategy_codes
    assert "SPEC_COST_MODEL_REF_INVALID" in strategy_codes
    assert "SPEC_VERSION_CONFLICT" in strategy_codes


@pytest.mark.live
def test_live_indicator_registry_covers_ma_crossover_spec():
    """Every indicator referenced in the MA crossover spec is in the registry."""
    spec = load_strategy_spec(MA_CROSSOVER_SPEC)

    for cond in spec.entry_rules.conditions:
        assert is_indicator_known(cond.indicator), (
            f"Indicator '{cond.indicator}' used in MA crossover spec but not in registry"
        )

    for filt in spec.entry_rules.filters:
        if filt.type == "volatility":
            ind = filt.params.get("indicator")
            if ind:
                assert is_indicator_known(ind), (
                    f"Volatility filter indicator '{ind}' not in registry"
                )
