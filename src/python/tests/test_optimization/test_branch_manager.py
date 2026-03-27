"""Tests for optimization.branch_manager (Task 5)."""
from __future__ import annotations

import numpy as np
import pytest

from optimization.branch_manager import BranchManager
from optimization.parameter_space import detect_branches, parse_strategy_params


class TestBranchManager:
    def test_single_branch_passthrough(self, sample_strategy_spec, sample_config):
        space = parse_strategy_params(sample_strategy_spec)
        branches = detect_branches(space)
        bm = BranchManager(branches=branches, config=sample_config, master_seed=42)

        result = bm.ask_all(32)
        assert "__default__" in result
        # Allow slight variance from per-instance rounding
        assert result["__default__"].shape[0] >= 28

    def test_branch_ucb1_shifts_budget(self, branching_strategy_spec, sample_config):
        space = parse_strategy_params(branching_strategy_spec)
        branches = detect_branches(space)
        bm = BranchManager(branches=branches, config=sample_config, master_seed=42)

        # First round: equal allocation (no visit history)
        result = bm.ask_all(64)
        assert len(result) == 2

        # Tell with one branch much better than the other
        branch_results = {}
        for key, candidates in result.items():
            if "trailing" in key:
                scores = np.ones(len(candidates)) * 10.0  # Good branch
            else:
                scores = np.ones(len(candidates)) * 1.0   # Weak branch
            branch_results[key] = (candidates, scores)
        bm.tell_all(branch_results)

        # Second round: UCB1 should shift budget toward better branch
        budget = bm.allocate_budget(64)
        trailing_key = [k for k in budget if "trailing" in k][0]
        tp_key = [k for k in budget if "take_profit" in k][0]

        # Better branch should get more budget
        assert budget[trailing_key] >= budget[tp_key]

    def test_branch_state_roundtrip(self, branching_strategy_spec, sample_config):
        space = parse_strategy_params(branching_strategy_spec)
        branches = detect_branches(space)
        bm = BranchManager(branches=branches, config=sample_config, master_seed=42)

        # Do an ask/tell cycle
        result = bm.ask_all(32)
        for key, candidates in result.items():
            scores = np.random.RandomState(42).uniform(0, 1, len(candidates))
            bm.tell_all({key: (candidates, scores)})

        state = bm.state_dict()
        assert "branches" in state
        assert "stats" in state

        # Load state into new manager
        bm2 = BranchManager(branches=branches, config=sample_config, master_seed=42)
        bm2.load_state(state)

        # Stats should match
        for key in state["stats"]:
            assert bm2._stats[key].visit_count == bm._stats[key].visit_count

    def test_convergence_check(self, sample_strategy_spec, sample_config):
        space = parse_strategy_params(sample_strategy_spec)
        branches = detect_branches(space)
        bm = BranchManager(branches=branches, config=sample_config, master_seed=42)

        # Initially not converged (CMA-ES instances never start converged)
        assert not bm.check_convergence()
