"""Regression tests for Story 5-2b review findings.

Each test guards against a specific bug found during code review synthesis.
"""

from pathlib import Path

import pytest

from strategy.indicator_registry import reset_registry
from strategy.range_proposal import (
    TIMEFRAME_PERIOD_RANGES,
    _apply_physical_constraints,
    _determine_source_layer,
    apply_cross_parameter_constraints,
    compute_pair_atr_stats,
    ATRStats,
    propose_ranges,
)
from strategy.specification import ParameterCondition, SearchParameter
from strategy.loader import load_strategy_spec

PROJECT_ROOT = Path(__file__).resolve().parents[4]
V002_SPEC = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v002.toml"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


@pytest.mark.regression
def test_slow_period_max_not_clamped_below_story_spec():
    """Regression: engine clamped slow_period.max to tf_max (100), but story
    spec requires 200 for H1 slow_period with current=50.

    The bug was a redundant `min(proposed_max, tf_max)` that defeated the
    'ensure at least 2x current' guarantee.
    """
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)

    assert "slow_period" in proposed
    sp = proposed["slow_period"]
    # Story spec Task 5 says slow_period max=200 for H1
    assert sp.max >= 200.0, (
        f"slow_period.max={sp.max} is below the story-required 200. "
        f"Engine clamping logic is too restrictive."
    )


@pytest.mark.regression
def test_period_max_respects_soft_ceiling():
    """Regression: period max should have a soft ceiling at 2x timeframe max,
    not a hard clamp at tf_max.
    """
    from strategy.range_proposal import _propose_indicator_param

    tf_min, tf_max = TIMEFRAME_PERIOD_RANGES["H1"]
    stats = ATRStats(
        pair="EURUSD", timeframe="H1", atr_14_median=5.0, atr_14_p90=7.5,
        bar_range_median=15.0, typical_spread=1.0, data_bars=0, source="default",
    )

    # For current=50 on H1 (tf_max=100): 4x=200, soft ceiling=200
    result = _propose_indicator_param("slow_period", 50, tf_min, tf_max, stats)
    assert result is not None
    assert result.max == 200.0

    # For current=20 on H1: 4x=80, should stay at 80 (below ceiling)
    result = _propose_indicator_param("fast_period", 20, tf_min, tf_max, stats)
    assert result is not None
    assert result.max == 80.0


@pytest.mark.regression
def test_constraint_preserves_condition_metadata():
    """Regression: _apply_physical_constraints and apply_cross_parameter_constraints
    rebuilt SearchParameter objects without preserving the `condition` field,
    silently dropping conditional activation rules.
    """
    condition = ParameterCondition(parent="exit_type", value="trailing_stop")

    # Test _apply_physical_constraints preserves condition
    stats = ATRStats(
        pair="EURUSD", timeframe="H1", atr_14_median=5.0, atr_14_p90=7.5,
        bar_range_median=15.0, typical_spread=2.0, data_bars=500, source="computed",
    )

    params = {
        "sl_pips": SearchParameter(
            type="continuous", min=0.5, max=20.0, condition=condition,
        ),
        "test_period": SearchParameter(
            type="integer", min=5.0, max=1000.0, step=5.0, condition=condition,
        ),
    }
    _apply_physical_constraints(params, stats)

    # sl_pips should have been adjusted (0.5 < 2.0 * 1.5 = 3.0)
    assert params["sl_pips"].min >= 2.0 * 1.5
    assert params["sl_pips"].condition is not None, "condition dropped by physical constraints"
    assert params["sl_pips"].condition.parent == "exit_type"

    # test_period should have been adjusted (1000 > 500/10 = 50)
    assert params["test_period"].max <= 50
    assert params["test_period"].condition is not None, "condition dropped by period constraint"
    assert params["test_period"].condition.value == "trailing_stop"

    # Test apply_cross_parameter_constraints preserves condition
    sp_condition = ParameterCondition(parent="strategy_type", value="dual_ma")
    params2 = {
        "fast_period": SearchParameter(type="integer", min=5.0, max=50.0, step=5.0),
        "slow_period": SearchParameter(
            type="integer", min=3.0, max=200.0, step=10.0, condition=sp_condition,
        ),
    }
    result = apply_cross_parameter_constraints(params2)
    assert result["slow_period"].condition is not None, "condition dropped by cross-param constraints"
    assert result["slow_period"].condition.parent == "strategy_type"


@pytest.mark.regression
def test_multiplier_params_attributed_to_l1_not_l3():
    """Regression: _determine_source_layer marked sl_atr_multiplier and
    tp_rr_ratio as L3 (ATR/volatility) because of prefix matching on 'sl_'
    and 'tp_'. These are dimensionless multipliers with hardcoded ranges,
    not pip-based ATR-scaled params. They should be L1.
    """
    stats = ATRStats(
        pair="EURUSD", timeframe="H1", atr_14_median=5.0, atr_14_p90=7.5,
        bar_range_median=15.0, typical_spread=1.0, data_bars=0, source="default",
    )

    # Multiplier params should be L1 (registry metadata), not L3
    sl_mult = SearchParameter(type="continuous", min=0.5, max=5.0)
    assert _determine_source_layer("sl_atr_multiplier", sl_mult, stats) == "L1"

    tp_ratio = SearchParameter(type="continuous", min=1.0, max=5.0)
    assert _determine_source_layer("tp_rr_ratio", tp_ratio, stats) == "L1"

    trailing_mult = SearchParameter(type="continuous", min=1.0, max=5.0)
    assert _determine_source_layer("trailing_atr_multiplier", trailing_mult, stats) == "L1"

    # Pip-denominated params should still be L3
    sl_pips = SearchParameter(type="continuous", min=5.0, max=30.0)
    assert _determine_source_layer("sl_pips", sl_pips, stats) == "L3"

    trailing_dist = SearchParameter(type="continuous", min=3.0, max=15.0)
    assert _determine_source_layer("trailing_distance_pips", trailing_dist, stats) == "L3"


@pytest.mark.regression
def test_bar_range_median_field_renamed():
    """Regression: ATRStats.daily_range_median was misleading — it computed
    per-bar range, not daily aggregated range. Field renamed to bar_range_median.
    """
    stats = ATRStats(
        pair="EURUSD", timeframe="H1", atr_14_median=5.0, atr_14_p90=7.5,
        bar_range_median=15.0, typical_spread=1.0, data_bars=1000, source="computed",
    )
    # Verify the field exists with the correct name
    assert hasattr(stats, "bar_range_median")
    assert stats.bar_range_median == 15.0
    # Verify old name does NOT exist
    assert not hasattr(stats, "daily_range_median")
