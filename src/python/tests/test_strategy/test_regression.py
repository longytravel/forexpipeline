"""Regression tests for review synthesis findings (Story 2-3).

Each test guards against a specific class of bug found during code review.
Marker: @pytest.mark.regression
"""

from pathlib import Path

import pytest
import tomllib
from pydantic import ValidationError

from strategy.indicator_registry import get_registry, is_indicator_known, reset_registry
from strategy.loader import load_strategy_spec, validate_strategy_spec
from strategy.specification import (
    EntryCondition,
    EntryFilter,
    ExitTrailing,
    OptimizationPlan,
    SearchParameter,
    StrategySpecification,
)
from strategy.storage import load_latest_version, save_strategy_spec

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MA_CROSSOVER_SPEC = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v002.toml"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


# --- C1 (Both): MA crossover must use sma_crossover, not two separate SMA conditions ---


@pytest.mark.regression
def test_ma_crossover_uses_single_crossover_indicator():
    """Regression for C1: reference spec must express cross-indicator comparison
    via sma_crossover indicator, not two separate SMA conditions with threshold=0.0."""
    spec = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")
    assert len(spec.entry_rules.conditions) == 1
    cond = spec.entry_rules.conditions[0]
    assert cond.indicator == "sma_crossover"
    assert "fast_period" in cond.parameters
    assert "slow_period" in cond.parameters
    assert cond.comparator == "crosses_above"


@pytest.mark.regression
def test_sma_crossover_in_indicator_registry():
    """Regression for C1: sma_crossover must exist in the shared indicator registry."""
    assert is_indicator_known("sma_crossover")
    meta = get_registry()["sma_crossover"]
    assert "fast_period" in meta.required_params
    assert "slow_period" in meta.required_params


# --- H-AC4 (Codex): extra="forbid" rejects unknown fields ---


@pytest.mark.regression
def test_extra_fields_rejected_at_top_level():
    """Regression for H-AC4: unknown top-level fields in spec must be rejected."""
    valid_raw = _load_raw_fixture("valid_ma_crossover.toml")
    valid_raw["bogus_section"] = {"key": "value"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        StrategySpecification.model_validate(valid_raw)


@pytest.mark.regression
def test_extra_fields_rejected_in_metadata():
    """Regression for H-AC4: unknown fields in metadata must be rejected."""
    valid_raw = _load_raw_fixture("valid_ma_crossover.toml")
    valid_raw["metadata"]["unknown_field"] = "surprise"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        StrategySpecification.model_validate(valid_raw)


# --- H2 (Both): Indicator required params must be enforced ---


@pytest.mark.regression
def test_indicator_missing_required_param_caught():
    """Regression for H2: SMA without 'period' param must fail semantic validation."""
    valid_raw = _load_raw_fixture("valid_ma_crossover.toml")
    # Replace sma_crossover with sma but give it wrong params
    valid_raw["entry_rules"]["conditions"] = [
        {
            "indicator": "sma",
            "parameters": {"window": 20},  # wrong param name — should be 'period'
            "threshold": 50.0,
            "comparator": ">",
        }
    ]
    # Also fix optimization to reference existing params (v2 flat format)
    valid_raw["optimization_plan"]["parameters"] = {
        "window": {"type": "integer", "min": 5.0, "max": 50.0, "step": 5.0}
    }
    spec = StrategySpecification.model_validate(valid_raw)
    errors = validate_strategy_spec(spec)
    assert any("requires parameter 'period'" in e for e in errors)
    assert any("has no parameter 'window'" in e for e in errors)


# --- H1 (Both): Optimization params must reference actual entry params ---


@pytest.mark.regression
def test_optimization_param_not_in_entry_conditions_caught():
    """Regression for H1: optimization params referencing non-existent entry
    condition params must fail semantic validation."""
    valid_raw = _load_raw_fixture("valid_ma_crossover.toml")
    # Add a bogus optimization parameter that doesn't exist in any condition
    valid_raw["optimization_plan"]["parameters"]["nonexistent_param"] = {
        "type": "integer", "min": 1.0, "max": 10.0, "step": 1.0
    }
    spec = StrategySpecification.model_validate(valid_raw)
    errors = validate_strategy_spec(spec)
    assert any("nonexistent_param" in e and "not found" in e for e in errors)


# --- H3 (Both): Numeric range validation for filter/trailing params ---


@pytest.mark.regression
def test_volatility_filter_period_zero_rejected():
    """Regression for H3: volatility filter period <= 0 must be rejected."""
    with pytest.raises(ValidationError, match="period.*must be > 0"):
        EntryFilter(type="volatility", params={"indicator": "atr", "period": 0})


@pytest.mark.regression
def test_volatility_filter_period_negative_rejected():
    """Regression for H3: volatility filter negative period must be rejected."""
    with pytest.raises(ValidationError, match="period.*must be > 0"):
        EntryFilter(type="volatility", params={"indicator": "atr", "period": -5})


@pytest.mark.regression
def test_trailing_stop_distance_pips_zero_rejected():
    """Regression for H3: trailing_stop distance_pips <= 0 must be rejected."""
    with pytest.raises(ValidationError, match="distance_pips.*must be > 0"):
        ExitTrailing(type="trailing_stop", params={"distance_pips": 0.0})


@pytest.mark.regression
def test_chandelier_atr_period_zero_rejected():
    """Regression for H3: chandelier atr_period <= 0 must be rejected."""
    with pytest.raises(ValidationError, match="atr_period.*must be > 0"):
        ExitTrailing(type="chandelier", params={"atr_period": 0, "atr_multiplier": 3.0})


@pytest.mark.regression
def test_chandelier_atr_multiplier_negative_rejected():
    """Regression for H3: chandelier atr_multiplier <= 0 must be rejected."""
    with pytest.raises(ValidationError, match="atr_multiplier.*must be > 0"):
        ExitTrailing(type="chandelier", params={"atr_period": 14, "atr_multiplier": -1.0})


# --- H-AC6 (Codex): Saved version updates metadata.version ---


@pytest.mark.regression
def test_saved_version_updates_metadata_version(tmp_path):
    """Regression for H-AC6: saving v002 must set metadata.version to 'v002'."""
    spec = load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")
    strategy_dir = tmp_path / "strategies" / "test"

    save_strategy_spec(spec, strategy_dir)  # v001
    save_strategy_spec(spec, strategy_dir)  # v002

    loaded, version = load_latest_version(strategy_dir)
    assert version == "v002"
    assert loaded.metadata.version == "v002"

    # Also verify the TOML on disk has the right version
    with open(strategy_dir / "v002.toml", "rb") as f:
        raw = tomllib.load(f)
    assert raw["metadata"]["version"] == "v002"


# --- M-Codex (migrated): condition references must point to valid categorical parents ---


@pytest.mark.regression
def test_condition_references_nonexistent_parent():
    """Regression for M-Codex: condition referencing unknown parent must fail."""
    with pytest.raises(ValidationError, match="unknown parent.*bogus"):
        OptimizationPlan(
            schema_version=2,
            parameters={
                "real_param": SearchParameter(type="integer", min=1.0, max=10.0, step=1.0),
                "child_param": SearchParameter(
                    type="integer", min=1.0, max=5.0,
                    condition={"parent": "bogus", "value": "x"},
                ),
            },
            objective_function="sharpe",
        )


@pytest.mark.regression
def test_valid_condition_references_accepted():
    """Regression for M-Codex: valid condition references must pass."""
    plan = OptimizationPlan(
        schema_version=2,
        parameters={
            "exit_type": SearchParameter(type="categorical", choices=["fixed", "trailing"]),
            "trail_dist": SearchParameter(
                type="continuous", min=1.0, max=10.0,
                condition={"parent": "exit_type", "value": "trailing"},
            ),
        },
        objective_function="sharpe",
    )
    assert "exit_type" in plan.parameters
    assert plan.parameters["trail_dist"].condition.parent == "exit_type"


# --- Helpers ---


def _load_raw_fixture(name: str) -> dict:
    """Load a TOML fixture as raw dict for manipulation."""
    with open(FIXTURES / name, "rb") as f:
        return tomllib.load(f)
