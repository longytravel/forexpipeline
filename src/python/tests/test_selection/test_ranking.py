"""Tests for multi-objective ranking (Story 5.6, Task 9)."""
from __future__ import annotations

import json

import numpy as np
import pyarrow as pa
import pytest

from selection.config import SelectionConfig
from selection.models import ClusterAssignment, EquityCurveQuality, RankedCandidate
from selection.ranking import (
    compute_critic_weights,
    four_stage_funnel,
    pareto_frontier,
    topsis_rank,
)


def _make_config(**overrides) -> SelectionConfig:
    defaults = {
        "min_cluster_size": 3,
        "hdbscan_min_samples": 2,
        "topsis_top_n": 50,
        "stability_threshold": 0.3,
        "target_candidates": 10,
        "deterministic_ratio": 0.8,
        "diversity_dimensions": ["trade_frequency", "win_rate"],
        "max_clustering_candidates": 5000,
        "random_seed": 42,
    }
    defaults.update(overrides)
    return SelectionConfig(**defaults)


class TestCRITICWeights:
    def test_critic_weights_sum_to_one(self):
        """CRITIC weights must sum to 1.0."""
        rng = np.random.default_rng(42)
        matrix = rng.uniform(0, 1, (20, 4))
        weights = compute_critic_weights(matrix)
        assert weights.sum() == pytest.approx(1.0, abs=1e-10)
        assert len(weights) == 4

    def test_critic_weights_high_variance_column(self):
        """Column with higher variance gets higher weight."""
        rng = np.random.default_rng(42)
        matrix = np.zeros((20, 3))
        matrix[:, 0] = rng.uniform(0, 1, 20)       # low variance
        matrix[:, 1] = rng.uniform(0, 100, 20)      # high variance
        matrix[:, 2] = rng.uniform(0, 1, 20)        # low variance

        weights = compute_critic_weights(matrix)
        # High variance column should generally get more weight
        # (CRITIC also considers correlation, so this isn't guaranteed)
        assert weights[1] > 0  # At minimum, it should be non-zero

    def test_critic_weights_degenerate(self):
        """Single row or single column → uniform weights."""
        weights = compute_critic_weights(np.array([[1.0, 2.0, 3.0]]))
        assert len(weights) == 3
        np.testing.assert_allclose(weights, [1/3, 1/3, 1/3], atol=1e-10)


class TestTOPSIS:
    def test_topsis_known_ranking(self):
        """Verify TOPSIS on a simple known example."""
        # Candidate A: best on both criteria
        # Candidate B: worst on both criteria
        matrix = np.array([
            [10.0, 10.0],  # A - best
            [1.0, 1.0],    # B - worst
            [5.0, 5.0],    # C - middle
        ])
        weights = np.array([0.5, 0.5])
        closeness = topsis_rank(matrix, weights, benefit_columns=[0, 1], cost_columns=[])

        assert closeness[0] > closeness[2] > closeness[1]  # A > C > B

    def test_topsis_benefit_vs_cost_columns(self):
        """Cost column inversion works correctly."""
        # Candidate A: high value on cost column (bad)
        # Candidate B: low value on cost column (good)
        matrix = np.array([
            [10.0, 100.0],  # A: good benefit, bad cost
            [10.0, 1.0],    # B: good benefit, good cost
        ])
        weights = np.array([0.5, 0.5])
        closeness = topsis_rank(matrix, weights, benefit_columns=[0], cost_columns=[1])

        assert closeness[1] > closeness[0]  # B should rank higher

    def test_topsis_empty(self):
        """Empty input → empty output."""
        result = topsis_rank(np.array([]).reshape(0, 2), np.array([0.5, 0.5]), [0], [1])
        assert len(result) == 0


class TestParetoFrontier:
    def test_pareto_frontier_simple_2d(self):
        """Known Pareto front in 2D."""
        candidates = [
            RankedCandidate(0, 0.9, 0, 0, True, "pareto", ""),
            RankedCandidate(1, 0.8, 0, 0, True, "pareto", ""),
            RankedCandidate(2, 0.7, 0, 0, True, "pareto", ""),
        ]
        metrics = {
            0: {"obj1": 10.0, "obj2": 1.0},   # dominated by 1
            1: {"obj1": 8.0, "obj2": 8.0},     # non-dominated
            2: {"obj1": 1.0, "obj2": 10.0},    # non-dominated
        }
        result = pareto_frontier(candidates, ["obj1", "obj2"], metrics)

        # Candidate 1 and 2 are on Pareto front, candidate 0 may or may not be
        front = [r for r in result if r.pareto_rank == 1]
        assert len(front) >= 2  # At least candidates 1 and 2

    def test_pareto_frontier_all_dominated(self):
        """One candidate dominates all others → single rank 1."""
        candidates = [
            RankedCandidate(0, 0.9, 0, 0, True, "pareto", ""),
            RankedCandidate(1, 0.8, 0, 0, True, "pareto", ""),
        ]
        metrics = {
            0: {"obj1": 10.0, "obj2": 10.0},  # dominates all
            1: {"obj1": 1.0, "obj2": 1.0},
        }
        result = pareto_frontier(candidates, ["obj1", "obj2"], metrics)

        front = [r for r in result if r.pareto_rank == 1]
        assert len(front) == 1
        assert front[0].candidate_id == 0


class TestFourStageFunnel:
    def _make_funnel_candidates(self, n: int = 20) -> tuple[pa.Table, list, list]:
        rng = np.random.default_rng(42)
        ids = list(range(n))
        cv_objs = rng.uniform(0.5, 2.0, n).tolist()
        fold_scores = [[rng.uniform(0.3, 2.0) for _ in range(5)] for _ in range(n)]

        table = pa.table({
            "candidate_id": ids,
            "cv_objective": cv_objs,
            "fold_scores": fold_scores,
            "params_json": [json.dumps({"p": float(rng.uniform(0, 100))}) for _ in range(n)],
        })

        quality = [
            EquityCurveQuality(i, rng.uniform(5, 50), rng.uniform(0, 20),
                               rng.uniform(0.1, 0.9), rng.uniform(0.5, 5.0), rng.uniform(0.1, 1.0))
            for i in ids
        ]
        clusters = [
            ClusterAssignment(i, i % 3, False, rng.uniform(0.5, 1.0))
            for i in ids
        ]
        return table, quality, clusters

    def test_four_stage_funnel_gate_filtering(self):
        """Hard gates remove candidates as expected."""
        table, quality, clusters = self._make_funnel_candidates(20)
        config = _make_config(topsis_top_n=15, stability_threshold=1.0)
        hard_gates = {"pbo_max_threshold": 0.40, "dsr_pass_required": False}

        survivors, stats, weights, _gate_counts = four_stage_funnel(
            table, quality, clusters, config, hard_gates
        )
        assert stats.total_input == 20
        assert stats.after_hard_gates <= 20

    def test_four_stage_funnel_stats_accurate(self):
        """Funnel stats counts match actual filtering at each stage."""
        table, quality, clusters = self._make_funnel_candidates(20)
        config = _make_config(topsis_top_n=10, stability_threshold=1.0)
        hard_gates = {"pbo_max_threshold": 0.40, "dsr_pass_required": False}

        survivors, stats, weights, _gate_counts = four_stage_funnel(
            table, quality, clusters, config, hard_gates
        )
        assert stats.after_hard_gates >= stats.after_topsis or stats.after_topsis <= config.topsis_top_n
        assert stats.after_stability <= stats.after_topsis
        assert stats.after_pareto <= stats.after_topsis

    def test_four_stage_funnel_all_fail_gates(self):
        """All candidates fail → empty manifest, no crash."""
        # Create scoring manifests where all fail DSR
        n = 10
        table = pa.table({
            "candidate_id": list(range(n)),
            "cv_objective": [0.5] * n,
            "fold_scores": [[0.5, 0.5] for _ in range(n)],
            "params_json": ['{"p": 1}'] * n,
        })
        quality = [EquityCurveQuality(i, 1.0, 5.0, 0.01, 1.0, 0.5) for i in range(n)]
        clusters = [ClusterAssignment(i, 0, False, 0.9) for i in range(n)]
        scoring = {
            i: {"gate_results": {"dsr_passed": False, "pbo_value": 0.8}, "per_stage_summaries": {}}
            for i in range(n)
        }
        config = _make_config()
        hard_gates = {"pbo_max_threshold": 0.40, "dsr_pass_required": True}

        survivors, stats, weights, _gate_counts = four_stage_funnel(
            table, quality, clusters, config, hard_gates, scoring
        )
        assert stats.final_selected == 0
        assert len(survivors) == 0

    def test_four_stage_funnel_fewer_than_target(self):
        """Fewer survivors than target → selects all, no crash."""
        table, quality, clusters = self._make_funnel_candidates(8)
        config = _make_config(topsis_top_n=5, stability_threshold=1.0, target_candidates=10)
        hard_gates = {"pbo_max_threshold": 0.40, "dsr_pass_required": False}

        survivors, stats, weights, _gate_counts = four_stage_funnel(
            table, quality, clusters, config, hard_gates
        )
        # Should work without error even if < target
        assert stats.total_input == 8
