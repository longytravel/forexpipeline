"""Tests for optimization.parameter_space (Task 3)."""
from __future__ import annotations

import numpy as np
import pytest

from optimization.parameter_space import (
    ParamType,
    ParameterSpace,
    ParameterSpec,
    decode_candidate,
    detect_branches,
    encode_params,
    parse_strategy_params,
    to_cmaes_bounds,
)


class TestParseStrategyParams:
    def test_parse_continuous_params(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        continuous = space.continuous_params
        assert len(continuous) == 1
        assert continuous[0].name == "exit.stop_loss_pips"
        assert continuous[0].min_val == 10.0
        assert continuous[0].max_val == 100.0

    def test_parse_mixed_params(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        assert space.n_dims == 3
        assert len(space.integer_params) == 2
        assert len(space.continuous_params) == 1
        assert len(space.categorical_params) == 0

    def test_parse_rejects_schema_v1(self):
        spec = {
            "optimization_plan": {
                "schema_version": 1,
                "parameters": {},
            }
        }
        with pytest.raises(ValueError, match="schema_version"):
            parse_strategy_params(spec)

    def test_parse_categorical_params(self, branching_strategy_spec):
        space = parse_strategy_params(branching_strategy_spec)
        cats = space.categorical_params
        assert len(cats) == 1
        assert cats[0].name == "exit_type"
        assert cats[0].choices == ["trailing_stop", "take_profit"]


class TestDetectBranches:
    def test_no_branches_returns_default(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        branches = detect_branches(space)
        assert "__default__" in branches
        assert len(branches) == 1
        assert branches["__default__"].n_dims == 3

    def test_detect_branches_exit_type(self, branching_strategy_spec):
        space = parse_strategy_params(branching_strategy_spec)
        branches = detect_branches(space)
        assert len(branches) == 2
        assert "exit_type=trailing_stop" in branches
        assert "exit_type=take_profit" in branches

        # Trailing branch: sma_period + trailing_distance
        trailing = branches["exit_type=trailing_stop"]
        assert trailing.n_dims == 2
        names = trailing.param_names
        assert "entry.sma_period" in names
        assert "exit.trailing_distance" in names

        # TP branch: sma_period + tp_pips
        tp = branches["exit_type=take_profit"]
        assert tp.n_dims == 2
        assert "exit.tp_pips" in tp.param_names


class TestToCmaesBounds:
    def test_to_cmaes_bounds_shape(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        lower, upper = to_cmaes_bounds(space)
        assert lower.shape == (3,)
        assert upper.shape == (3,)
        assert np.all(lower < upper)

    def test_to_cmaes_bounds_values(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        lower, upper = to_cmaes_bounds(space)
        # First param is integer (5-50)
        assert lower[0] == 5.0
        assert upper[0] == 50.0


class TestEncodeDecodeCandidates:
    def test_roundtrip(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        params = {
            "entry.sma_fast_period": 10,
            "entry.sma_slow_period": 50,
            "exit.stop_loss_pips": 30.5,
        }
        vec = encode_params(params, space)
        decoded = decode_candidate(vec, space)

        assert decoded["entry.sma_fast_period"] == 10
        assert decoded["entry.sma_slow_period"] == 50
        assert abs(decoded["exit.stop_loss_pips"] - 30.5) < 1e-6

    def test_categorical_encode_decode(self, branching_strategy_spec):
        space = parse_strategy_params(branching_strategy_spec)
        params = {
            "entry.sma_period": 20,
            "exit_type": "take_profit",
            "exit.trailing_distance": 50.0,
            "exit.tp_pips": 100.0,
        }
        vec = encode_params(params, space)
        decoded = decode_candidate(vec, space)
        assert decoded["exit_type"] == "take_profit"
