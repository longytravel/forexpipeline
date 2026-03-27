"""Tests for three-tier parameter classification."""
import pytest
import numpy as np

from optimization.param_classifier import (
    ParamClassification,
    classify_params,
    build_override_spec,
    compute_group_hash,
    compute_signal_hash,
    write_toml_spec,
    RUST_BATCH_PARAMS,
)
from optimization.parameter_space import (
    ParameterSpace,
    ParameterSpec,
    ParamType,
    parse_strategy_params,
    extract_params_by_indices,
    snap_to_grid,
)


# --- Fixtures ---

CHANNEL_BREAKOUT_SPEC = {
    "metadata": {"schema_version": "1", "name": "channel-breakout", "version": "v001",
                 "pair": "EURUSD", "timeframe": "H1"},
    "entry_rules": {
        "conditions": [
            {"indicator": "channel_breakout", "threshold": 0.0, "comparator": "crosses_above",
             "parameters": {"swing_bars": 3, "atr_period": 14, "atr_multiplier": 1.0,
                            "confirmation_bars": 2, "use_close": "true"}},
            {"indicator": "channel_breakout", "threshold": 0.0, "comparator": "crosses_below",
             "parameters": {"swing_bars": 3, "atr_period": 14, "atr_multiplier": 1.0,
                            "confirmation_bars": 2, "use_close": "true"}},
        ],
    },
    "exit_rules": {
        "stop_loss": {"type": "atr_multiple", "value": 2.0},
        "take_profit": {"type": "risk_reward", "value": 2.0},
        "trailing": {"type": "chandelier", "params": {"atr_period": 14, "atr_multiplier": 2.0}},
    },
    "optimization_plan": {
        "schema_version": 2,
        "objective_function": "sharpe",
        "parameters": {
            "swing_bars": {"type": "integer", "min": 2.0, "max": 20.0, "step": 1.0},
            "atr_period": {"type": "integer", "min": 5.0, "max": 50.0, "step": 1.0},
            "atr_multiplier": {"type": "continuous", "min": 0.25, "max": 5.0, "step": 0.25},
            "confirmation_bars": {"type": "integer", "min": 1.0, "max": 10.0, "step": 1.0},
            "sl_atr_multiplier": {"type": "continuous", "min": 0.5, "max": 6.0, "step": 0.5},
            "tp_rr_ratio": {"type": "continuous", "min": 0.5, "max": 5.0, "step": 0.5},
            "trailing_atr_multiplier": {"type": "continuous", "min": 0.5, "max": 8.0, "step": 0.5},
            "trailing_atr_period": {"type": "integer", "min": 5.0, "max": 50.0, "step": 1.0},
        },
    },
}

MA_CROSSOVER_SPEC = {
    "metadata": {"schema_version": "1", "name": "ma-crossover", "version": "v002",
                 "pair": "EURUSD", "timeframe": "H1"},
    "entry_rules": {
        "conditions": [
            {"indicator": "sma_crossover", "threshold": 0.0, "comparator": "crosses_above",
             "parameters": {"fast_period": 20, "slow_period": 50}},
        ],
        "filters": [
            {"type": "session", "params": {"include": ["london", "new_york"]}},
        ],
    },
    "exit_rules": {
        "stop_loss": {"type": "atr_multiple", "value": 1.5},
        "take_profit": {"type": "risk_reward", "value": 3.0},
        "trailing": {"type": "chandelier", "params": {"atr_period": 14, "atr_multiplier": 3.0}},
    },
    "optimization_plan": {
        "schema_version": 2,
        "objective_function": "sharpe",
        "parameters": {
            "fast_period": {"type": "integer", "min": 5.0, "max": 80.0, "step": 5.0},
            "slow_period": {"type": "integer", "min": 20.0, "max": 200.0, "step": 10.0},
            "sl_atr_multiplier": {"type": "continuous", "min": 0.5, "max": 5.0},
            "tp_rr_ratio": {"type": "continuous", "min": 1.0, "max": 5.0},
            "trailing_atr_period": {"type": "integer", "min": 5.0, "max": 50.0, "step": 5.0},
            "trailing_atr_multiplier": {"type": "continuous", "min": 1.0, "max": 5.0},
            "session_filter": {"type": "categorical", "choices": ["asian", "london", "new_york", "london_ny_overlap"]},
        },
    },
}


# --- Classification Tests ---

class TestClassifyParams:
    def test_channel_breakout_four_signal_four_batch(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        assert set(c.signal_params.keys()) == {
            "swing_bars", "atr_period", "atr_multiplier", "confirmation_bars"
        }
        assert c.batch_params == {
            "sl_atr_multiplier", "tp_rr_ratio", "trailing_atr_multiplier", "trailing_atr_period"
        }
        assert len(c.spec_override_params) == 0

    def test_channel_breakout_signal_paths_both_conditions(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        # swing_bars appears in both conditions
        assert len(c.signal_params["swing_bars"]) == 2
        assert "entry_rules.conditions[0]" in c.signal_params["swing_bars"][0]
        assert "entry_rules.conditions[1]" in c.signal_params["swing_bars"][1]

    def test_ma_crossover_two_signal_four_batch_one_override(self):
        space = parse_strategy_params(MA_CROSSOVER_SPEC)
        c = classify_params(MA_CROSSOVER_SPEC, space)

        assert set(c.signal_params.keys()) == {"fast_period", "slow_period"}
        assert c.batch_params == {
            "sl_atr_multiplier", "tp_rr_ratio", "trailing_atr_multiplier", "trailing_atr_period"
        }
        assert "session_filter" in c.spec_override_params

    def test_indices_cover_all_params(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        all_indices = sorted(c.signal_indices + c.batch_indices + c.spec_override_indices)
        assert all_indices == list(range(space.n_dims))

    def test_group_key_indices(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        # Group key = signal + spec_override
        assert c.group_key_indices == sorted(c.signal_indices)

    def test_has_signal_params(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)
        assert c.has_signal_params is True

    def test_no_entry_params_strategy(self):
        """Strategy with only exit params in optimization_plan."""
        spec = {
            "metadata": {"schema_version": "1", "name": "test", "version": "v001",
                         "pair": "EURUSD", "timeframe": "H1"},
            "entry_rules": {"conditions": [
                {"indicator": "sma_crossover", "parameters": {"fast_period": 20, "slow_period": 50}}
            ]},
            "exit_rules": {"stop_loss": {"type": "atr_multiple", "value": 2.0}},
            "optimization_plan": {
                "schema_version": 2,
                "parameters": {
                    "sl_atr_multiplier": {"type": "continuous", "min": 0.5, "max": 5.0},
                    "tp_rr_ratio": {"type": "continuous", "min": 1.0, "max": 5.0},
                },
            },
        }
        space = parse_strategy_params(spec)
        c = classify_params(spec, space)

        assert c.has_signal_params is False
        assert len(c.batch_params) == 2


# --- Override Spec Tests ---

class TestBuildOverrideSpec:
    def test_signal_params_applied_to_both_conditions(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        override = build_override_spec(
            base_spec=CHANNEL_BREAKOUT_SPEC,
            signal_params={"swing_bars": 7, "atr_period": 20, "atr_multiplier": 2.0, "confirmation_bars": 4},
            spec_override_params={},
            classification=c,
        )

        for cond in override["entry_rules"]["conditions"]:
            assert cond["parameters"]["swing_bars"] == 7
            assert cond["parameters"]["atr_period"] == 20
            assert cond["parameters"]["atr_multiplier"] == 2.0
            assert cond["parameters"]["confirmation_bars"] == 4

    def test_original_spec_unchanged(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        build_override_spec(
            CHANNEL_BREAKOUT_SPEC,
            {"swing_bars": 99}, {},
            c,
        )

        # Original unchanged
        assert CHANNEL_BREAKOUT_SPEC["entry_rules"]["conditions"][0]["parameters"]["swing_bars"] == 3


# --- Hash Tests ---

class TestHashing:
    def test_same_params_same_hash(self):
        h1 = compute_signal_hash({"swing_bars": 5, "atr_period": 20})
        h2 = compute_signal_hash({"swing_bars": 5, "atr_period": 20})
        assert h1 == h2

    def test_different_params_different_hash(self):
        h1 = compute_signal_hash({"swing_bars": 5, "atr_period": 20})
        h2 = compute_signal_hash({"swing_bars": 5, "atr_period": 21})
        assert h1 != h2

    def test_key_order_irrelevant(self):
        h1 = compute_signal_hash({"atr_period": 20, "swing_bars": 5})
        h2 = compute_signal_hash({"swing_bars": 5, "atr_period": 20})
        assert h1 == h2

    def test_group_hash_includes_spec_override(self):
        h1 = compute_group_hash({"swing_bars": 5}, {})
        h2 = compute_group_hash({"swing_bars": 5}, {"session_filter": "london"})
        assert h1 != h2


# --- Snap to Grid Tests ---

class TestSnapToGrid:
    def test_integer_snapping(self):
        spec = ParameterSpec("x", ParamType.INTEGER, min_val=2.0, max_val=20.0, step=1.0)
        assert snap_to_grid(4.7, spec) == 5
        assert snap_to_grid(4.3, spec) == 4
        assert snap_to_grid(4.5, spec) == 4  # banker's rounding

    def test_integer_clamped_to_bounds(self):
        spec = ParameterSpec("x", ParamType.INTEGER, min_val=5.0, max_val=50.0, step=1.0)
        assert snap_to_grid(2.0, spec) == 5
        assert snap_to_grid(55.0, spec) == 50

    def test_continuous_snapping(self):
        spec = ParameterSpec("x", ParamType.CONTINUOUS, min_val=0.25, max_val=5.0, step=0.25)
        assert snap_to_grid(1.1, spec) == 1.0
        assert snap_to_grid(1.2, spec) == 1.25

    def test_categorical_snapping(self):
        spec = ParameterSpec("x", ParamType.CATEGORICAL, choices=["a", "b", "c"])
        assert snap_to_grid(0.4, spec) == "a"
        assert snap_to_grid(1.6, spec) == "c"


# --- Extract Params Tests ---

class TestExtractParams:
    def test_extract_signal_params(self):
        space = parse_strategy_params(CHANNEL_BREAKOUT_SPEC)
        c = classify_params(CHANNEL_BREAKOUT_SPEC, space)

        # Build a fake candidate vector
        candidate = np.zeros(space.n_dims)
        for i, p in enumerate(space.parameters):
            if p.name == "swing_bars":
                candidate[i] = 7.3
            elif p.name == "atr_period":
                candidate[i] = 20.8

        result = extract_params_by_indices(candidate, space, c.signal_indices)
        assert result["swing_bars"] == 7  # snapped
        assert result["atr_period"] == 21  # snapped


# --- TOML Writer Tests ---

class TestTomlWriter:
    def test_write_and_read(self, tmp_path):
        spec = {"metadata": {"name": "test"}, "value": 42, "list": [1, 2, 3]}
        path = write_toml_spec(spec, tmp_path, "abc123")
        assert path.exists()
        content = path.read_text()
        assert "name" in content
        assert "42" in content
