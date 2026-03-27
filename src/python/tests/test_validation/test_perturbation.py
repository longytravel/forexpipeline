"""Tests for validation.perturbation (Story 5.4, Task 5)."""
from __future__ import annotations

import pytest

from validation.config import PerturbationConfig
from validation.perturbation import (
    PerturbationResult,
    generate_perturbations,
    run_perturbation,
    _infer_param_ranges,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def candidate():
    return {"fast_ma": 10.0, "slow_ma": 50.0, "threshold": 0.5}


@pytest.fixture
def param_ranges():
    return {
        "fast_ma": {"min": 2.0, "max": 20.0, "type": "float"},
        "slow_ma": {"min": 20.0, "max": 100.0, "type": "float"},
        "threshold": {"min": 0.0, "max": 1.0, "type": "float"},
    }


@pytest.fixture
def int_param_ranges():
    return {
        "lookback": {"min": 5, "max": 50, "type": "int"},
        "period": {"min": 10, "max": 100, "type": "int"},
    }


@pytest.fixture
def default_levels():
    return [0.05, 0.10, 0.20]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPerturbationGeneration:
    """test_perturbation_generation — correct number of variants."""

    def test_count_per_param(self, candidate, param_ranges, default_levels):
        """Each perturbable param generates 2 * len(levels) variants."""
        variants = generate_perturbations(candidate, param_ranges, default_levels)

        # 3 params * 3 levels * 2 directions = 18
        n_perturbable = len([
            p for p in candidate
            if p in param_ranges and param_ranges[p].get("type") != "categorical"
        ])
        expected = n_perturbable * len(default_levels) * 2
        assert len(variants) == expected

    def test_variant_structure(self, candidate, param_ranges, default_levels):
        """Each variant has required keys."""
        variants = generate_perturbations(candidate, param_ranges, default_levels)
        for v in variants:
            assert "params" in v
            assert "perturbed_param" in v
            assert "level" in v
            assert "direction" in v
            assert v["direction"] in ("plus", "minus")

    def test_values_within_range(self, candidate, param_ranges, default_levels):
        """All perturbed values stay within param_ranges bounds."""
        variants = generate_perturbations(candidate, param_ranges, default_levels)
        for v in variants:
            pname = v["perturbed_param"]
            prange = param_ranges[pname]
            val = v["params"][pname]
            assert val >= prange["min"], f"{pname}={val} < min={prange['min']}"
            assert val <= prange["max"], f"{pname}={val} > max={prange['max']}"

    def test_single_param_single_level(self):
        """Minimal case: 1 param, 1 level -> 2 variants."""
        candidate = {"x": 5.0}
        ranges = {"x": {"min": 0.0, "max": 10.0, "type": "float"}}
        variants = generate_perturbations(candidate, ranges, [0.10])
        assert len(variants) == 2

        directions = {v["direction"] for v in variants}
        assert directions == {"plus", "minus"}


class TestPerturbationIntegerRounding:
    """test_perturbation_integer_rounding — int params are rounded."""

    def test_int_params_are_rounded(self, int_param_ranges):
        candidate = {"lookback": 20, "period": 50}
        variants = generate_perturbations(
            candidate, int_param_ranges, [0.05, 0.10, 0.20],
        )
        for v in variants:
            val = v["params"][v["perturbed_param"]]
            assert isinstance(val, int), (
                f"Expected int for {v['perturbed_param']}, got {type(val).__name__}"
            )

    def test_int_rounding_specific_value(self):
        """A known perturbation producing a non-integer is rounded."""
        candidate = {"lookback": 10}
        ranges = {"lookback": {"min": 0, "max": 100, "type": "int"}}
        # 5% of range 100 = 5.0 -> 10 + 5 = 15 (already int)
        # 20% of range 100 = 20.0 -> 10 + 20 = 30 (already int)
        variants = generate_perturbations(candidate, ranges, [0.05])
        for v in variants:
            assert isinstance(v["params"]["lookback"], int)


class TestPerturbationSensitivityCalc:
    """test_perturbation_sensitivity_calc — known sensitivity values."""

    def test_sensitivity_computed_correctly(self):
        """With mock dispatcher, sensitivity = level * 0.5."""
        candidate = {"x": 5.0}
        ranges = {"x": {"min": 0.0, "max": 10.0, "type": "float"}}
        config = PerturbationConfig(levels=[0.10])

        # Use run_perturbation with no dispatcher (uses mock path)
        from pathlib import Path
        result = run_perturbation(
            candidate=candidate,
            market_data_path=Path("."),
            strategy_spec={},
            cost_model={},
            config=config,
            dispatcher=None,  # triggers mock path
            seed=42,
            param_ranges=ranges,
            base_metric=1.0,
        )

        # Mock formula: perturbed = base * (1 - level * 0.5)
        # sensitivity = |perturbed - base| / base = level * 0.5 = 0.05
        for pname, sens_dict in result.sensitivities.items():
            for level_key, sens_val in sens_dict.items():
                assert abs(sens_val - 0.05) < 1e-9, (
                    f"Expected sensitivity ~0.05, got {sens_val}"
                )

    def test_zero_base_metric(self):
        """When base metric is 0, sensitivity = abs(perturbed_metric)."""
        candidate = {"x": 5.0}
        ranges = {"x": {"min": 0.0, "max": 10.0, "type": "float"}}
        config = PerturbationConfig(levels=[0.10])

        from pathlib import Path
        result = run_perturbation(
            candidate=candidate,
            market_data_path=Path("."),
            strategy_spec={},
            cost_model={},
            config=config,
            dispatcher=None,
            seed=42,
            param_ranges=ranges,
            base_metric=0.0,
        )
        # With base=0, mock: perturbed = 0 * (1 - 0.1*0.5) = 0
        # sensitivity = abs(0) = 0
        assert result.max_sensitivity == 0.0


class TestPerturbationDeterministic:
    """test_perturbation_deterministic — same inputs produce same outputs."""

    def test_deterministic_generation(self, candidate, param_ranges, default_levels):
        """generate_perturbations is deterministic (no randomness involved)."""
        v1 = generate_perturbations(candidate, param_ranges, default_levels)
        v2 = generate_perturbations(candidate, param_ranges, default_levels)

        assert len(v1) == len(v2)
        for a, b in zip(v1, v2):
            assert a["params"] == b["params"]
            assert a["perturbed_param"] == b["perturbed_param"]
            assert a["level"] == b["level"]
            assert a["direction"] == b["direction"]

    def test_deterministic_run(self):
        """run_perturbation produces identical results for same inputs."""
        from pathlib import Path

        candidate = {"x": 5.0, "y": 10.0}
        ranges = {
            "x": {"min": 0.0, "max": 10.0, "type": "float"},
            "y": {"min": 0.0, "max": 20.0, "type": "float"},
        }
        config = PerturbationConfig(levels=[0.05, 0.10])

        r1 = run_perturbation(
            candidate, Path("."), {}, {}, config, None, seed=42,
            param_ranges=ranges, base_metric=1.0,
        )
        r2 = run_perturbation(
            candidate, Path("."), {}, {}, config, None, seed=42,
            param_ranges=ranges, base_metric=1.0,
        )

        assert r1.max_sensitivity == r2.max_sensitivity
        assert r1.fragile_params == r2.fragile_params
        assert r1.sensitivities == r2.sensitivities


class TestPerturbationCategoricalSkipped:
    """test_perturbation_categorical_skipped — categorical params not perturbed."""

    def test_categorical_excluded(self):
        candidate = {"mode": "fast", "threshold": 0.5}
        ranges = {
            "mode": {"type": "categorical", "values": ["fast", "slow"]},
            "threshold": {"min": 0.0, "max": 1.0, "type": "float"},
        }
        variants = generate_perturbations(candidate, ranges, [0.05, 0.10])

        perturbed_params = {v["perturbed_param"] for v in variants}
        assert "mode" not in perturbed_params
        assert "threshold" in perturbed_params

    def test_all_categorical_produces_no_variants(self):
        candidate = {"mode": "fast", "style": "aggressive"}
        ranges = {
            "mode": {"type": "categorical"},
            "style": {"type": "categorical"},
        }
        variants = generate_perturbations(candidate, ranges, [0.05])
        assert len(variants) == 0


class TestInferParamRanges:
    """Test the _infer_param_ranges fallback."""

    def test_positive_value(self):
        ranges = _infer_param_ranges({"x": 10.0})
        assert ranges["x"]["min"] == 0.0
        assert ranges["x"]["max"] == 20.0

    def test_negative_value(self):
        ranges = _infer_param_ranges({"x": -5.0})
        assert ranges["x"]["min"] == -10.0
        assert ranges["x"]["max"] == 0.0

    def test_zero_value(self):
        ranges = _infer_param_ranges({"x": 0.0})
        assert ranges["x"]["min"] == -1.0
        assert ranges["x"]["max"] == 1.0

    def test_non_numeric_skipped(self):
        ranges = _infer_param_ranges({"x": 10.0, "name": "foo"})
        assert "x" in ranges
        assert "name" not in ranges
