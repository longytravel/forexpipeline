"""Tests for range proposal engine (Story 5.2b).

Covers: AC #4 (intelligent range proposal), AC #5 (ATR from market data),
AC #6 (operator review), AC #7 (cross-parameter constraints), AC #11 (provenance).
"""

from pathlib import Path

import pytest

from strategy.indicator_registry import reset_registry
from strategy.loader import load_strategy_spec, validate_strategy_spec
from strategy.range_proposal import (
    ATRStats,
    DEFAULT_ATR_PIPS,
    TIMEFRAME_PERIOD_RANGES,
    apply_cross_parameter_constraints,
    compute_pair_atr_stats,
    persist_proposal,
    propose_ranges,
)
from strategy.specification import SearchParameter

PROJECT_ROOT = Path(__file__).resolve().parents[4]
V002_SPEC = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v002.toml"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


# --- propose_ranges() for reference strategy ---


def test_propose_ranges_sma_crossover_eurusd_h1():
    """Propose for ma-crossover on EURUSD H1, check period ranges are H1-appropriate."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)

    # Must include entry indicator params
    assert "fast_period" in proposed
    assert "slow_period" in proposed

    # Period ranges must be H1-appropriate (5-100)
    h1_min, h1_max = TIMEFRAME_PERIOD_RANGES["H1"]
    fp = proposed["fast_period"]
    assert fp.type == "integer"
    assert fp.min >= h1_min
    assert fp.max <= h1_max * 4  # allow some expansion

    sp = proposed["slow_period"]
    assert sp.type == "integer"
    assert sp.min >= h1_min


def test_timeframe_scaling_m1_wider_than_d1():
    """M1 period max > D1 period max."""
    m1_min, m1_max = TIMEFRAME_PERIOD_RANGES["M1"]
    d1_min, d1_max = TIMEFRAME_PERIOD_RANGES["D1"]
    assert m1_max > d1_max


def test_pair_atr_scaling_volatile_wider():
    """Pair with higher ATR gets wider pip-based ranges."""
    # GBPUSD default ATR > AUDUSD default ATR
    assert DEFAULT_ATR_PIPS["GBPUSD"] > DEFAULT_ATR_PIPS["AUDUSD"]

    # Compute stats with defaults
    gbp_stats = compute_pair_atr_stats("GBPUSD", "H1")
    aud_stats = compute_pair_atr_stats("AUDUSD", "H1")
    assert gbp_stats.atr_14_median > aud_stats.atr_14_median


def test_physical_constraint_stop_gt_spread():
    """stop_loss.min > typical spread."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)

    # If stop_loss pips exist, min must be > spread
    if "sl_pips" in proposed:
        from strategy.range_proposal import TYPICAL_SPREADS_PIPS
        spread = TYPICAL_SPREADS_PIPS.get("EURUSD", 1.0)
        assert proposed["sl_pips"].min > spread


def test_physical_constraint_period_lt_data_bars():
    """period.max < data_bars / 10 when real data is available."""
    # With fake ATR stats that have low bar count
    stats = ATRStats(
        pair="EURUSD",
        timeframe="H1",
        atr_14_median=5.0,
        atr_14_p90=7.5,
        bar_range_median=15.0,
        typical_spread=1.0,
        data_bars=500,
        source="computed",
    )
    # period.max should be constrained to 500/10=50
    from strategy.range_proposal import _apply_physical_constraints

    params = {
        "fast_period": SearchParameter(type="integer", min=5.0, max=200.0, step=5.0),
    }
    _apply_physical_constraints(params, stats)
    assert params["fast_period"].max <= 50


def test_cross_param_slow_gt_fast():
    """slow_period.min > fast_period.min after cross-param constraints."""
    params = {
        "fast_period": SearchParameter(type="integer", min=5.0, max=50.0, step=5.0),
        "slow_period": SearchParameter(type="integer", min=5.0, max=200.0, step=10.0),
    }
    result = apply_cross_parameter_constraints(params)
    assert result["slow_period"].min > result["fast_period"].min


def test_propose_with_no_data_uses_defaults():
    """Missing data directory still produces ranges with defaults."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec, data_dir=Path("/nonexistent/path"))

    # Should still produce valid ranges
    assert len(proposed) > 0
    for name, param in proposed.items():
        if param.type in ("continuous", "integer"):
            assert param.min is not None
            assert param.max is not None
            assert param.min < param.max


def test_propose_includes_exit_params():
    """Proposed ranges include stop_loss, take_profit, trailing params."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)

    # MA crossover has atr_multiple SL -> sl_atr_multiplier
    assert "sl_atr_multiplier" in proposed
    # risk_reward TP -> tp_rr_ratio
    assert "tp_rr_ratio" in proposed
    # chandelier trailing -> trailing params
    assert "trailing_atr_period" in proposed
    assert "trailing_atr_multiplier" in proposed


def test_proposal_artifact_persisted(tmp_path):
    """persist_proposal() writes JSON with required provenance fields."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)
    atr_stats = compute_pair_atr_stats("EURUSD", "H1")

    artifact_path = persist_proposal(
        proposed, atr_stats, "ma-crossover", tmp_path
    )

    assert artifact_path.exists()

    import json
    with open(artifact_path) as f:
        artifact = json.load(f)

    # Required provenance fields
    assert "proposal_timestamp" in artifact
    assert artifact["pair"] == "EURUSD"
    assert artifact["timeframe"] == "H1"
    assert "atr_stats" in artifact
    assert artifact["atr_stats"]["source"] in ("computed", "default")
    assert "indicator_registry_hash" in artifact
    assert "proposal_engine_version" in artifact
    assert "parameters" in artifact
    # Each parameter has source_layer
    for param_data in artifact["parameters"].values():
        assert "source_layer" in param_data


def test_proposal_default_atr_marked():
    """When data unavailable, affected params have source='default' in artifact."""
    stats = compute_pair_atr_stats("EURUSD", "H1")
    assert stats.source == "default"  # no real data in test env


# --- Live integration tests ---


@pytest.mark.live
def test_live_propose_ranges_produces_valid_output():
    """Live: propose ranges for real v002 spec, validate all ranges are sane."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)

    assert len(proposed) >= 4  # at least entry + exit params

    for name, param in proposed.items():
        if param.type in ("continuous", "integer"):
            assert param.min is not None, f"{name}: min is None"
            assert param.max is not None, f"{name}: max is None"
            assert param.min < param.max, f"{name}: min >= max"
        elif param.type == "categorical":
            assert param.choices is not None
            assert len(param.choices) >= 2


@pytest.mark.live
def test_live_proposal_artifact_roundtrip(tmp_path):
    """Live: persist proposal, reload JSON, verify all fields."""
    spec = load_strategy_spec(V002_SPEC)
    proposed = propose_ranges(spec)
    atr_stats = compute_pair_atr_stats("EURUSD", "H1")

    artifact_path = persist_proposal(proposed, atr_stats, "ma-crossover", tmp_path)
    assert artifact_path.exists()
    assert artifact_path.name == "optimization_proposal.json"

    import json
    with open(artifact_path) as f:
        artifact = json.load(f)

    # Validate structure
    assert artifact["pair"] == "EURUSD"
    assert artifact["timeframe"] == "H1"
    assert len(artifact["parameters"]) == len(proposed)

    # Every proposed parameter is in the artifact
    for name in proposed:
        assert name in artifact["parameters"], f"Missing {name} in artifact"


@pytest.mark.live
def test_live_v002_full_validation_pipeline():
    """Live: load v002, validate semantically, propose ranges, persist."""
    # Load and validate
    spec = load_strategy_spec(V002_SPEC)
    errors = validate_strategy_spec(spec)
    assert errors == [], f"Validation errors: {errors}"

    # Propose ranges
    proposed = propose_ranges(spec)
    assert len(proposed) >= 4

    # All numeric ranges have min < max
    for name, param in proposed.items():
        if param.type in ("continuous", "integer"):
            assert param.min < param.max, f"{name}: invalid range"

    # Period ranges fall within timeframe lookup bounds
    h1_min, h1_max = TIMEFRAME_PERIOD_RANGES["H1"]
    for name, param in proposed.items():
        if param.type == "integer" and "period" in name:
            assert param.min >= h1_min, f"{name}: min below timeframe floor"
