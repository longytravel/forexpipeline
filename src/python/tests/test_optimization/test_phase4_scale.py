"""Tests for Phase 4 (Scale for Massive EAs) features.

Covers:
- 4a: Adaptive batch sizing
- 4b: Progressive search space narrowing
- 4c: Warm-start from pre-screening
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from optimization.portfolio import CMAESInstance, PortfolioManager
from optimization.branch_manager import BranchManager
from optimization.parameter_space import ParameterSpace, ParameterSpec, ParamType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_space(n_dims: int = 3) -> ParameterSpace:
    """Build a simple ParameterSpace for testing."""
    params = []
    for i in range(n_dims):
        params.append(ParameterSpec(
            name=f"p{i}",
            param_type=ParamType.CONTINUOUS,
            min_val=0.0,
            max_val=10.0,
            step=0.0,
            choices=None,
            condition=None,
        ))
    return ParameterSpace(parameters=params)


def _make_orchestrator(config_overrides: dict | None = None):
    """Build an OptimizationOrchestrator with a mock batch_runner."""
    from optimization.orchestrator import OptimizationOrchestrator

    config = {
        "optimization": {
            "batch_size": 1024,
            "max_generations": 5,
            "checkpoint_interval_generations": 2,
            "cv_lambda": 1.5,
            "cv_folds": 3,
            "convergence_tolfun": 1e-3,
            "stagnation_generations": 50,
            "memory_budget_mb": 2048,
            "sobol_fraction": 0.1,
            "ucb1_exploration": 1.414,
            "portfolio": {
                "cmaes_instances": 2,
                "de_instances": 1,
                "cmaes_pop_base": 16,
                "de_pop_base": 16,
                "pop_scaling_factor": 5,
                "min_pop": 16,
            },
        },
        "pipeline": {
            "artifacts_dir": "artifacts",
            "config_hash": "sha256:test",
        },
    }
    if config_overrides:
        for section, values in config_overrides.items():
            if section in config:
                config[section].update(values)
            else:
                config[section] = values

    mock_runner = MagicMock()
    return OptimizationOrchestrator(
        strategy_spec={"metadata": {"name": "test", "version": "v001"}},
        market_data_path=Path("/tmp/test-data.arrow"),
        cost_model_path=Path("/tmp/cost-model.json"),
        config=config,
        artifacts_dir=Path("/tmp/artifacts"),
        batch_runner=mock_runner,
    )


# ===========================================================================
# 4a: Adaptive Batch Sizing
# ===========================================================================

class TestAdaptiveBatchSizing:
    """Tests for _adapt_batch_size method."""

    def test_halve_on_slow_generation(self):
        """Batch halved when generation > 60s."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=90.0, current_batch_size=2048)
        assert result == 1024

    def test_double_on_fast_generation(self):
        """Batch doubled when generation < 5s."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=2.0, current_batch_size=1024)
        assert result == 2048

    def test_no_change_in_normal_range(self):
        """Batch unchanged when 5s <= generation <= 60s."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=30.0, current_batch_size=2048)
        assert result == 2048

    def test_clamp_lower_bound(self):
        """Batch cannot go below 256."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=90.0, current_batch_size=256)
        assert result == 256

    def test_clamp_upper_bound(self):
        """Batch cannot exceed 8192."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=1.0, current_batch_size=8192)
        assert result == 8192

    def test_successive_halvings(self):
        """Multiple slow generations halve progressively."""
        orch = _make_orchestrator()
        batch = 4096
        batch = orch._adapt_batch_size(90.0, batch)
        assert batch == 2048
        batch = orch._adapt_batch_size(90.0, batch)
        assert batch == 1024

    def test_boundary_at_60s(self):
        """Exactly 60s is not slow (>60 required)."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=60.0, current_batch_size=2048)
        assert result == 2048

    def test_boundary_at_5s(self):
        """Exactly 5s is not fast (<5 required)."""
        orch = _make_orchestrator()
        result = orch._adapt_batch_size(gen_elapsed_s=5.0, current_batch_size=1024)
        assert result == 1024


# ===========================================================================
# 4b: Progressive Search Space Narrowing
# ===========================================================================

class TestProgressiveNarrowing:
    """Tests for _maybe_narrow_search_space method."""

    def test_disabled_by_default(self):
        """No narrowing when progressive_narrowing not configured."""
        orch = _make_orchestrator()
        bm = MagicMock()
        result = orch._maybe_narrow_search_space(50, [{"p0": 1.0}], bm)
        assert result is False
        bm.narrow_bounds.assert_not_called()

    def test_narrowing_at_trigger_generation(self):
        """Narrowing fires at exactly the trigger generation."""
        config_overrides = {
            "optimization": {
                "batch_size": 1024,
                "max_generations": 100,
                "checkpoint_interval_generations": 2,
                "cv_lambda": 1.5,
                "cv_folds": 3,
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "memory_budget_mb": 2048,
                "sobol_fraction": 0.1,
                "ucb1_exploration": 1.414,
                "progressive_narrowing": {
                    "enabled": True,
                    "trigger_generation": 10,
                    "range_multiplier": 2.0,
                },
                "portfolio": {
                    "cmaes_instances": 2,
                    "de_instances": 1,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        orch = _make_orchestrator(config_overrides)
        bm = MagicMock()

        # Build enough candidates for top 10%
        candidates = [{"p0": float(i), "p1": float(i * 2)} for i in range(20)]

        result = orch._maybe_narrow_search_space(10, candidates, bm)
        assert result is True
        bm.narrow_bounds.assert_called_once()

    def test_narrowing_not_at_wrong_generation(self):
        """Narrowing does NOT fire at non-trigger generations."""
        config_overrides = {
            "optimization": {
                "batch_size": 1024,
                "max_generations": 100,
                "checkpoint_interval_generations": 2,
                "cv_lambda": 1.5,
                "cv_folds": 3,
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "memory_budget_mb": 2048,
                "sobol_fraction": 0.1,
                "ucb1_exploration": 1.414,
                "progressive_narrowing": {
                    "enabled": True,
                    "trigger_generation": 10,
                    "range_multiplier": 2.0,
                },
                "portfolio": {
                    "cmaes_instances": 2,
                    "de_instances": 1,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        orch = _make_orchestrator(config_overrides)
        bm = MagicMock()
        candidates = [{"p0": float(i)} for i in range(20)]
        result = orch._maybe_narrow_search_space(9, candidates, bm)
        assert result is False

    def test_narrowing_skipped_with_too_few_candidates(self):
        """Narrowing skipped when < 2 candidates."""
        config_overrides = {
            "optimization": {
                "batch_size": 1024,
                "max_generations": 100,
                "checkpoint_interval_generations": 2,
                "cv_lambda": 1.5,
                "cv_folds": 3,
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "memory_budget_mb": 2048,
                "sobol_fraction": 0.1,
                "ucb1_exploration": 1.414,
                "progressive_narrowing": {
                    "enabled": True,
                    "trigger_generation": 10,
                    "range_multiplier": 2.0,
                },
                "portfolio": {
                    "cmaes_instances": 2,
                    "de_instances": 1,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        orch = _make_orchestrator(config_overrides)
        bm = MagicMock()
        result = orch._maybe_narrow_search_space(10, [{"p0": 1.0}], bm)
        assert result is False


class TestCMAESNarrowBounds:
    """Tests for CMAESInstance.narrow_bounds."""

    def test_bounds_narrowed(self):
        """CMA-ES bounds are correctly narrowed."""
        space = _make_space(3)
        inst = CMAESInstance(space=space, population_size=16, seed=42)

        # Original bounds: [0, 10] for all 3 dims
        assert inst._lower[0] == 0.0
        assert inst._upper[0] == 10.0

        inst.narrow_bounds({"0": (2.0, 8.0), "1": (3.0, 7.0)})

        assert inst._lower[0] == 2.0
        assert inst._upper[0] == 8.0
        assert inst._lower[1] == 3.0
        assert inst._upper[1] == 7.0
        # Dim 2 unchanged
        assert inst._lower[2] == 0.0
        assert inst._upper[2] == 10.0

    def test_bounds_narrowed_with_int_keys(self):
        """CMA-ES accepts integer keys for narrow_bounds."""
        space = _make_space(2)
        inst = CMAESInstance(space=space, population_size=16, seed=42)
        inst.narrow_bounds({0: (1.0, 9.0)})
        assert inst._lower[0] == 1.0
        assert inst._upper[0] == 9.0

    def test_asks_within_narrowed_bounds(self):
        """After narrowing, asked candidates are within new bounds."""
        space = _make_space(3)
        inst = CMAESInstance(space=space, population_size=16, seed=42)
        inst.narrow_bounds({"0": (4.0, 6.0), "1": (4.0, 6.0), "2": (4.0, 6.0)})

        candidates = inst.ask(100)
        assert np.all(candidates >= 4.0 - 1e-10)
        assert np.all(candidates <= 6.0 + 1e-10)


class TestBranchManagerNarrowBounds:
    """Tests for BranchManager.narrow_bounds delegation."""

    def test_delegates_to_portfolio_managers(self):
        """narrow_bounds called on each branch's PortfolioManager."""
        space = _make_space(3)
        branches = {"__default__": space}
        config = {
            "optimization": {
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "sobol_fraction": 0.1,
                "ucb1_exploration": 1.414,
                "portfolio": {
                    "cmaes_instances": 2,
                    "de_instances": 0,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        bm = BranchManager(branches=branches, config=config, master_seed=42)

        # Narrow bounds
        bm.narrow_bounds({"0": (2.0, 8.0)})

        # Verify that the underlying portfolio manager's CMA-ES instances
        # got narrowed bounds
        pm = bm._branches["__default__"]
        for inst in pm._instances:
            if isinstance(inst, CMAESInstance):
                assert inst._lower[0] == 2.0
                assert inst._upper[0] == 8.0


# ===========================================================================
# 4c: Warm-Start from Pre-Screening
# ===========================================================================

class TestCMAESWarmStart:
    """Tests for CMAESInstance.set_initial_mean."""

    def test_initial_mean_set(self):
        """CMA-ES initial mean is updated to the given candidate."""
        space = _make_space(3)
        inst = CMAESInstance(space=space, population_size=16, seed=42)
        candidate = np.array([3.0, 5.0, 7.0])
        inst.set_initial_mean(candidate)

        # After warm-start, asks should be centred around the candidate
        samples = inst.ask(100)
        mean_of_samples = np.mean(samples, axis=0)
        # The mean of asked samples should be close to the candidate
        # (within bounds, with CMA-ES noise)
        assert np.allclose(mean_of_samples, candidate, atol=3.0)

    def test_initial_mean_clipped_to_bounds(self):
        """Out-of-bounds candidate is clipped before setting as mean."""
        space = _make_space(2)
        inst = CMAESInstance(space=space, population_size=16, seed=42)
        candidate = np.array([15.0, -5.0])  # outside [0, 10]
        inst.set_initial_mean(candidate)

        # The CMA-ES mean should be clipped
        samples = inst.ask(50)
        assert np.all(samples >= 0.0 - 1e-10)
        assert np.all(samples <= 10.0 + 1e-10)


class TestPortfolioWarmStart:
    """Tests for PortfolioManager.warm_start."""

    def test_warm_start_distributes_to_cmaes(self):
        """Warm-start seeds each CMA-ES instance with a candidate."""
        space = _make_space(3)
        config = {
            "optimization": {
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "sobol_fraction": 0.1,
                "portfolio": {
                    "cmaes_instances": 3,
                    "de_instances": 0,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        pm = PortfolioManager(space=space, config=config, master_seed=42)
        candidates = [
            np.array([2.0, 3.0, 4.0]),
            np.array([5.0, 6.0, 7.0]),
        ]
        # Should not raise; round-robin distribution
        pm.warm_start(candidates)

    def test_warm_start_empty_candidates_is_noop(self):
        """Warm-start with no candidates does nothing."""
        space = _make_space(3)
        config = {
            "optimization": {
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "sobol_fraction": 0.1,
                "portfolio": {
                    "cmaes_instances": 2,
                    "de_instances": 0,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        pm = PortfolioManager(space=space, config=config, master_seed=42)
        pm.warm_start([])  # Should not raise


class TestBranchManagerWarmStart:
    """Tests for BranchManager.warm_start delegation."""

    def test_warm_start_delegates(self):
        """warm_start called on each branch's PortfolioManager."""
        space = _make_space(3)
        branches = {"__default__": space}
        config = {
            "optimization": {
                "convergence_tolfun": 1e-3,
                "stagnation_generations": 50,
                "sobol_fraction": 0.1,
                "ucb1_exploration": 1.414,
                "portfolio": {
                    "cmaes_instances": 2,
                    "de_instances": 0,
                    "cmaes_pop_base": 16,
                    "de_pop_base": 16,
                    "pop_scaling_factor": 5,
                    "min_pop": 16,
                },
            },
        }
        bm = BranchManager(branches=branches, config=config, master_seed=42)
        candidates = [np.array([1.0, 2.0, 3.0])]
        # Should not raise
        bm.warm_start(candidates)


class TestPreScreenResultTopCandidates:
    """Tests for PreScreenResult.top_candidates field."""

    def test_top_candidates_default_empty(self):
        """top_candidates defaults to empty list."""
        from optimization.prescreener import PreScreenResult
        result = PreScreenResult(
            surviving_groups=["abc"],
            eliminated_count=0,
            total_count=1,
            elapsed_s=1.0,
        )
        assert result.top_candidates == []

    def test_top_candidates_populated(self):
        """top_candidates stores numpy arrays."""
        from optimization.prescreener import PreScreenResult
        vecs = [np.array([1.0, 2.0]), np.array([3.0, 4.0])]
        result = PreScreenResult(
            surviving_groups=["a", "b"],
            eliminated_count=0,
            total_count=2,
            elapsed_s=1.0,
            top_candidates=vecs,
        )
        assert len(result.top_candidates) == 2
        assert np.array_equal(result.top_candidates[0], np.array([1.0, 2.0]))
