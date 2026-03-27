"""Branch portfolio orchestration (Story 5.3, AC #14).

Manages sub-portfolios per conditional parameter branch with UCB1
budget allocation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from logging_setup.setup import get_logger
from optimization.parameter_space import ParameterSpace
from optimization.portfolio import PortfolioManager

logger = get_logger("optimization.branch_manager")


@dataclass
class BranchStats:
    """UCB1 tracking stats for a single branch."""
    total_score: float = 0.0
    total_candidates: int = 0
    visit_count: int = 0
    best_score: float = float("-inf")

    @property
    def mean_score(self) -> float:
        if self.total_candidates == 0:
            return 0.0
        return self.total_score / self.total_candidates


class BranchManager:
    """Manages sub-portfolios per conditional parameter branch.

    If no branching detected, wraps a single portfolio transparently.
    """

    def __init__(
        self,
        branches: dict[str, ParameterSpace],
        config: dict,
        master_seed: int = 42,
    ):
        self._branches: dict[str, PortfolioManager] = {}
        self._stats: dict[str, BranchStats] = {}
        self._config = config
        opt_config = config.get("optimization", {})
        self._exploration_weight = opt_config.get("ucb1_exploration", 1.414)
        self._is_single = len(branches) == 1 and "__default__" in branches

        for i, (key, space) in enumerate(branches.items()):
            seed = master_seed + i * 100
            self._branches[key] = PortfolioManager(
                space=space, config=config, master_seed=seed
            )
            self._stats[key] = BranchStats()

        logger.info(
            f"BranchManager: {len(branches)} branches",
            extra={
                "component": "optimization.branch_manager",
                "ctx": {"branches": list(branches.keys()), "single": self._is_single},
            },
        )

    def allocate_budget(self, total_batch: int) -> dict[str, int]:
        """Allocate batch budget across branches using UCB1 or proportional."""
        n = len(self._branches)
        if n == 1:
            key = next(iter(self._branches))
            return {key: total_batch}

        total_visits = sum(s.visit_count for s in self._stats.values())

        # If any branch has 0 visits, give equal allocation first
        unvisited = [k for k, s in self._stats.items() if s.visit_count == 0]
        if unvisited:
            per_branch = total_batch // n
            remainder = total_batch - per_branch * n
            alloc = {k: per_branch for k in self._branches}
            # Distribute remainder to first branches
            for i, k in enumerate(self._branches):
                if i < remainder:
                    alloc[k] += 1
            return alloc

        # UCB1 scoring
        ucb_scores: dict[str, float] = {}
        for key, stats in self._stats.items():
            exploit = stats.mean_score
            explore = self._exploration_weight * math.sqrt(
                math.log(total_visits) / stats.visit_count
            )
            ucb_scores[key] = exploit + explore

        # Allocate proportional to UCB1 scores (softmax-like)
        total_ucb = sum(max(0.01, s) for s in ucb_scores.values())
        alloc: dict[str, int] = {}
        remaining = total_batch

        keys = list(self._branches.keys())
        for key in keys[:-1]:
            share = max(1, int(total_batch * max(0.01, ucb_scores[key]) / total_ucb))
            alloc[key] = share
            remaining -= share

        alloc[keys[-1]] = max(1, remaining)
        return alloc

    def ask_all(self, total_batch: int) -> dict[str, np.ndarray]:
        """Ask candidates from each branch according to budget."""
        budget = self.allocate_budget(total_batch)
        result: dict[str, np.ndarray] = {}

        for key, batch_size in budget.items():
            if batch_size > 0:
                result[key] = self._branches[key].ask_batch(batch_size)

        return result

    def tell_all(
        self, branch_results: dict[str, tuple[np.ndarray, np.ndarray]]
    ) -> None:
        """Tell scores back per branch. Updates UCB1 stats."""
        for key, (candidates, scores) in branch_results.items():
            if key in self._branches:
                self._branches[key].tell_batch(candidates, scores)

                # Update UCB1 stats (weighted by candidate count, not batch count)
                stats = self._stats[key]
                stats.visit_count += 1
                stats.total_score += float(np.sum(scores)) if len(scores) > 0 else 0.0
                stats.total_candidates += len(scores)
                best = float(np.max(scores)) if len(scores) > 0 else float("-inf")
                if best > stats.best_score:
                    stats.best_score = best

    def check_convergence(self) -> bool:
        """Check if all branches have converged."""
        return all(pm.check_convergence() for pm in self._branches.values())

    def get_instance_types(self, branch_key: str) -> list[str]:
        """Get per-candidate instance types from last ask_batch allocations."""
        pm = self._branches.get(branch_key)
        if pm is None:
            return []
        return pm.get_candidate_instance_types()

    def narrow_bounds(self, narrowed_bounds: dict[str, tuple[float, float]]) -> None:
        """Narrow parameter bounds and restart CMA-ES instances.

        Args:
            narrowed_bounds: Mapping of param_name -> (new_lower, new_upper).
        """
        for key, pm in self._branches.items():
            pm.narrow_bounds(narrowed_bounds)
        logger.info(
            f"Narrowed bounds for {len(narrowed_bounds)} params across "
            f"{len(self._branches)} branches",
            extra={
                "component": "optimization.branch_manager",
                "ctx": {"n_params": len(narrowed_bounds)},
            },
        )

    def warm_start(self, top_candidates: list[np.ndarray]) -> None:
        """Seed CMA-ES instances with top candidate vectors from pre-screening.

        Args:
            top_candidates: List of parameter vectors (numpy arrays) to use
                as initial mean vectors for CMA-ES instances.
        """
        for key, pm in self._branches.items():
            pm.warm_start(top_candidates)
        logger.info(
            f"Warm-started {len(self._branches)} branches with "
            f"{len(top_candidates)} pre-screening candidates",
            extra={
                "component": "optimization.branch_manager",
                "ctx": {"n_candidates": len(top_candidates)},
            },
        )

    def state_dict(self) -> dict:
        return {
            "branches": {
                key: pm.state_dict() for key, pm in self._branches.items()
            },
            "stats": {
                key: {
                    "total_score": s.total_score,
                    "total_candidates": s.total_candidates,
                    "visit_count": s.visit_count,
                    "best_score": s.best_score,
                }
                for key, s in self._stats.items()
            },
        }

    def load_state(self, state: dict) -> None:
        for key, pm_state in state.get("branches", {}).items():
            if key in self._branches:
                self._branches[key].load_state(pm_state)
        for key, s_data in state.get("stats", {}).items():
            if key in self._stats:
                self._stats[key].total_score = s_data["total_score"]
                self._stats[key].total_candidates = s_data.get("total_candidates", s_data.get("visit_count", 0))
                self._stats[key].visit_count = s_data["visit_count"]
                self._stats[key].best_score = s_data["best_score"]
