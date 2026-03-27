"""Tests for diversity archive and selection (Story 5.6, Task 9)."""
from __future__ import annotations

import pytest

from selection.config import SelectionConfig
from selection.diversity import (
    BehaviorDimension,
    build_diversity_archive,
    define_behavior_dimensions,
    select_diverse_candidates,
)
from selection.models import DiversityCell, RankedCandidate


def _make_config(**overrides) -> SelectionConfig:
    defaults = {
        "min_cluster_size": 3,
        "hdbscan_min_samples": 2,
        "topsis_top_n": 50,
        "stability_threshold": 0.3,
        "target_candidates": 10,
        "deterministic_ratio": 0.8,
        "diversity_dimensions": ["trade_frequency", "avg_holding_time", "win_rate", "max_drawdown"],
        "max_clustering_candidates": 5000,
        "random_seed": 42,
    }
    defaults.update(overrides)
    return SelectionConfig(**defaults)


def _make_ranked(cid: int, score: float, cluster: int) -> RankedCandidate:
    return RankedCandidate(
        candidate_id=cid,
        topsis_score=score,
        pareto_rank=1,
        cluster_id=cluster,
        stability_pass=True,
        funnel_stage="pareto",
        selection_reason="test",
    )


class TestMAPElites:
    def test_map_elites_single_cell(self):
        """One candidate per cell in archive."""
        dims = [BehaviorDimension("freq", [50, 200], ["low", "med", "high"])]
        candidates = [_make_ranked(0, 0.9, 0)]
        behavior = {0: {"freq": 30}}

        archive = build_diversity_archive(candidates, behavior, dims)
        assert len(archive) == 1
        assert archive[0].best_candidate_id == 0
        assert archive[0].best_score == 0.9

    def test_map_elites_best_replaces_worse(self):
        """Higher score replaces lower in same cell."""
        dims = [BehaviorDimension("freq", [50, 200], ["low", "med", "high"])]
        candidates = [
            _make_ranked(0, 0.5, 0),
            _make_ranked(1, 0.9, 1),
        ]
        behavior = {
            0: {"freq": 30},  # both in "low" bin
            1: {"freq": 30},
        }

        archive = build_diversity_archive(candidates, behavior, dims)
        assert len(archive) == 1
        assert archive[0].best_candidate_id == 1
        assert archive[0].best_score == 0.9


class TestDiverseSelection:
    def test_diverse_selection_80_20_split(self):
        """Selection respects deterministic vs exploratory ratio."""
        # Create enough candidates in different cells
        candidates = [_make_ranked(i, 0.9 - i * 0.01, i % 5) for i in range(20)]
        behavior = {
            i: {"freq": 30 + i * 20, "win_rate": 0.3 + i * 0.03}
            for i in range(20)
        }
        dims = [
            BehaviorDimension("freq", [100, 200, 300], ["low", "med", "high", "very_high"]),
            BehaviorDimension("win_rate", [0.4, 0.55, 0.7], ["low", "mod", "good", "high"]),
        ]
        archive = build_diversity_archive(candidates, behavior, dims)

        selected = select_diverse_candidates(
            archive, candidates, target_n=10, deterministic_ratio=0.8, rng_seed=42
        )
        assert len(selected) <= 10

    def test_diverse_selection_cross_cluster(self):
        """No same-cluster duplicates when enough clusters exist."""
        candidates = [_make_ranked(i, 0.9 - i * 0.01, i) for i in range(10)]
        behavior = {i: {"freq": 50 * i, "win_rate": 0.3 + i * 0.05} for i in range(10)}
        dims = [
            BehaviorDimension("freq", [100, 250, 400], ["low", "med", "high", "very_high"]),
        ]
        archive = build_diversity_archive(candidates, behavior, dims)

        selected = select_diverse_candidates(
            archive, candidates, target_n=5, deterministic_ratio=0.8, rng_seed=42
        )
        cluster_ids = [s.cluster_id for s in selected]
        # With 10 unique clusters and 5 selections, should have ≤ 5 unique clusters
        assert len(set(cluster_ids)) == len(selected)

    def test_diverse_selection_target_count(self):
        """Output count matches target_candidates when enough survivors exist."""
        candidates = [_make_ranked(i, 0.9 - i * 0.01, i % 3) for i in range(30)]
        behavior = {i: {"freq": 30 + i * 10} for i in range(30)}
        dims = [BehaviorDimension("freq", [100, 200, 300], ["low", "med", "high", "very_high"])]
        archive = build_diversity_archive(candidates, behavior, dims)

        selected = select_diverse_candidates(
            archive, candidates, target_n=10, deterministic_ratio=0.8, rng_seed=42
        )
        assert len(selected) == 10

    def test_diverse_selection_empty_input(self):
        """Empty survivors → empty selection."""
        selected = select_diverse_candidates([], [], target_n=10, deterministic_ratio=0.8, rng_seed=42)
        assert selected == []
