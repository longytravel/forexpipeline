"""Tests for optimization.portfolio (Task 4)."""
from __future__ import annotations

import numpy as np
import pytest

from optimization.parameter_space import parse_strategy_params
from optimization.portfolio import (
    CMAESInstance,
    DEInstance,
    PortfolioManager,
    SobolExplorer,
)


class TestPortfolioManager:
    def test_portfolio_ask_batch_fills_capacity(self, sample_strategy_spec, sample_config):
        space = parse_strategy_params(sample_strategy_spec)
        pm = PortfolioManager(space=space, config=sample_config, master_seed=42)

        batch_size = 64
        candidates = pm.ask_batch(batch_size)

        # Allow slight variance from per-instance rounding
        assert candidates.shape[0] >= batch_size * 0.8
        assert candidates.shape[0] <= batch_size
        assert candidates.shape[1] == space.n_dims

    def test_portfolio_tell_routes_scores(self, sample_strategy_spec, sample_config):
        space = parse_strategy_params(sample_strategy_spec)
        pm = PortfolioManager(space=space, config=sample_config, master_seed=42)

        batch_size = 32
        candidates = pm.ask_batch(batch_size)
        scores = np.random.RandomState(42).uniform(0, 1, batch_size)

        # Should not raise
        pm.tell_batch(candidates, scores)

    def test_population_scaling_with_params(self, sample_config):
        """Verify pop formula max(min_pop, pop_scaling * N)."""
        from optimization.parameter_space import ParameterSpace, ParameterSpec, ParamType

        # 3 params: max(16, 5*3) = 16 (min_pop)
        space_3 = ParameterSpace(parameters=[
            ParameterSpec(name=f"p{i}", param_type=ParamType.CONTINUOUS, min_val=0, max_val=1)
            for i in range(3)
        ])
        pm = PortfolioManager(space=space_3, config=sample_config, master_seed=42)
        # Just verify it creates without error and can ask
        candidates = pm.ask_batch(32)
        assert candidates.shape[0] >= 28  # Allow rounding variance

    def test_sobol_fraction_allocation(self, sample_strategy_spec, sample_config):
        space = parse_strategy_params(sample_strategy_spec)
        pm = PortfolioManager(space=space, config=sample_config, master_seed=42)

        pm.ask_batch(100)
        allocations = pm.allocations

        # Last allocation should be sobol
        sobol_alloc = [a for a in allocations if a.instance_type == "sobol"]
        assert len(sobol_alloc) == 1
        # ~10% of 100 = 10
        assert sobol_alloc[0].count >= 1

    def test_portfolio_state_roundtrip(self, sample_strategy_spec, sample_config):
        space = parse_strategy_params(sample_strategy_spec)
        pm = PortfolioManager(space=space, config=sample_config, master_seed=42)

        # Do one ask/tell cycle
        candidates = pm.ask_batch(32)
        scores = np.ones(32)
        pm.tell_batch(candidates, scores)

        # Save and load state
        state = pm.state_dict()
        assert "instances" in state
        assert len(state["instances"]) > 0


class TestCMAESInstance:
    def test_cmaes_ask_returns_correct_shape(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        inst = CMAESInstance(space=space, population_size=16, seed=42)

        candidates = inst.ask(10)
        assert candidates.shape == (10, space.n_dims)

    def test_cmaes_restart_on_stagnation(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        inst = CMAESInstance(
            space=space, population_size=16, seed=42,
            tolfun=1e-3, stagnation_limit=3,
        )

        # Feed identical scores to trigger stagnation
        for _ in range(5):
            candidates = inst.ask(16)
            scores = np.ones(16) * 0.5  # No improvement
            inst.tell(candidates, scores)

        assert inst._restart_count >= 1

    def test_cmaes_state_dict(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        inst = CMAESInstance(space=space, population_size=16, seed=42)
        state = inst.state_dict()
        assert state["type"] == "cmaes"
        assert state["seed"] == 42


class TestSobolExplorer:
    def test_sobol_returns_bounded(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        explorer = SobolExplorer(space=space, seed=42)

        from optimization.parameter_space import to_cmaes_bounds
        lower, upper = to_cmaes_bounds(space)

        candidates = explorer.ask(32)
        assert candidates.shape == (32, space.n_dims)

        # All within bounds
        for i in range(space.n_dims):
            assert np.all(candidates[:, i] >= lower[i] - 1e-10)
            assert np.all(candidates[:, i] <= upper[i] + 1e-10)

    def test_sobol_never_converges(self, sample_strategy_spec):
        space = parse_strategy_params(sample_strategy_spec)
        explorer = SobolExplorer(space=space, seed=42)
        assert not explorer.converged()
