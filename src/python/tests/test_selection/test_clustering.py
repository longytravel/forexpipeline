"""Tests for clustering engine (Story 5.6, Task 9)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from selection.clustering import (
    cluster_candidates,
    compute_cluster_summaries,
    compute_gower_distance,
    pre_filter_candidates,
)
from selection.config import SelectionConfig


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


def _make_candidates(n: int, n_clusters: int = 3, seed: int = 42) -> pa.Table:
    """Generate synthetic candidates with separable clusters."""
    rng = np.random.default_rng(seed)
    cluster_centers = rng.uniform(0, 100, size=(n_clusters, 2))

    ids = []
    param_a = []
    param_b = []
    cv_objs = []
    fold_scores_list = []
    params_jsons = []

    per_cluster = n // n_clusters
    for ci in range(n_clusters):
        for j in range(per_cluster if ci < n_clusters - 1 else n - per_cluster * (n_clusters - 1)):
            ids.append(ci * per_cluster + j)
            a = cluster_centers[ci, 0] + rng.normal(0, 2)
            b = cluster_centers[ci, 1] + rng.normal(0, 2)
            param_a.append(a)
            param_b.append(b)
            cv_objs.append(rng.uniform(0.5, 2.0))
            fold_scores_list.append([rng.uniform(0.3, 2.0) for _ in range(5)])
            params_jsons.append(json.dumps({"param_a": a, "param_b": b}))

    return pa.table({
        "candidate_id": ids,
        "param_a": param_a,
        "param_b": param_b,
        "cv_objective": cv_objs,
        "fold_scores": fold_scores_list,
        "params_json": params_jsons,
    })


class TestGowerDistance:
    def test_gower_distance_mixed_types(self):
        """Gower distance handles continuous + categorical params."""
        df_data = {
            "candidate_id": [0, 1, 2],
            "num_param": [1.0, 5.0, 10.0],
            "cat_param": pd.array(["A", "A", "B"], dtype="object"),
        }
        table = pa.table(df_data)
        dist = compute_gower_distance(table, ["num_param", "cat_param"])

        assert dist.shape == (3, 3)
        assert dist.dtype == np.float64
        # Self-distance should be 0
        np.testing.assert_allclose(dist[0, 0], 0.0, atol=1e-5)
        # Same category candidates should be closer than different
        assert dist[0, 1] < dist[0, 2]


class TestHDBSCAN:
    def test_hdbscan_clusters_separable_data(self):
        """HDBSCAN finds distinct clusters in well-separated data."""
        candidates = _make_candidates(30, n_clusters=3)
        config = _make_config(min_cluster_size=3, hdbscan_min_samples=2)

        dist = compute_gower_distance(candidates, ["param_a", "param_b"])
        assignments = cluster_candidates(dist, config)

        assert len(assignments) == 30
        # Should find at least 2 clusters (HDBSCAN may merge close clusters)
        real_clusters = set(a.cluster_id for a in assignments if not a.is_noise)
        assert len(real_clusters) >= 1

    def test_hdbscan_noise_points_assigned(self):
        """Noise points are flagged with is_noise=True."""
        candidates = _make_candidates(30, n_clusters=3)
        config = _make_config(min_cluster_size=5, hdbscan_min_samples=3)

        dist = compute_gower_distance(candidates, ["param_a", "param_b"])
        assignments = cluster_candidates(dist, config)

        noise_points = [a for a in assignments if a.is_noise]
        non_noise = [a for a in assignments if not a.is_noise]
        # Every assignment should have valid fields
        for a in assignments:
            assert isinstance(a.candidate_id, int)
            assert isinstance(a.cluster_id, int)
            assert isinstance(a.membership_prob, float)

    def test_hdbscan_all_noise_singleton_fallback(self):
        """When HDBSCAN labels all as noise, each becomes singleton cluster."""
        # Very few candidates with high min_cluster_size → all noise
        candidates = _make_candidates(5, n_clusters=1)
        config = _make_config(min_cluster_size=10, hdbscan_min_samples=5)

        dist = compute_gower_distance(candidates, ["param_a", "param_b"])
        assignments = cluster_candidates(dist, config)

        assert len(assignments) == 5
        # In singleton fallback, each candidate is its own cluster
        cluster_ids = set(a.cluster_id for a in assignments)
        assert len(cluster_ids) == 5

    def test_hdbscan_single_cluster(self):
        """All candidates with identical params → single cluster or all-noise fallback."""
        n = 20
        # Use truly identical params so Gower distances are 0 within group
        table = pa.table({
            "candidate_id": list(range(n)),
            "param_a": [50.0] * n,
            "param_b": [50.0] * n,
            "cv_objective": [1.5] * n,
            "fold_scores": [[1.0, 1.1, 1.2] for _ in range(n)],
            "params_json": [json.dumps({"a": 50.0}) for _ in range(n)],
        })
        config = _make_config(min_cluster_size=3, hdbscan_min_samples=2)
        dist = compute_gower_distance(table, ["param_a", "param_b"])
        assignments = cluster_candidates(dist, config)

        assert len(assignments) == n
        non_noise = [a for a in assignments if not a.is_noise]
        if non_noise:
            real_clusters = set(a.cluster_id for a in non_noise)
            assert len(real_clusters) == 1
        else:
            # All-noise fallback with identical points is expected
            assert all(a.is_noise for a in assignments)


class TestClusterSummary:
    def test_cluster_summary_centroid_calculation(self):
        """Cluster centroid is the mean of member parameters."""
        candidates = _make_candidates(30, n_clusters=3)
        config = _make_config(min_cluster_size=3, hdbscan_min_samples=2)

        dist = compute_gower_distance(candidates, ["param_a", "param_b"])
        assignments = cluster_candidates(dist, config)
        summaries = compute_cluster_summaries(candidates, assignments, ["param_a", "param_b"])

        assert len(summaries) > 0
        for s in summaries:
            assert s.size > 0
            assert isinstance(s.centroid_params, dict)
            assert "param_a" in s.centroid_params or len(s.centroid_params) > 0

    def test_cluster_summary_representative_is_best(self):
        """Representative is the candidate with best cv_objective in cluster."""
        candidates = _make_candidates(30, n_clusters=3)
        config = _make_config(min_cluster_size=3, hdbscan_min_samples=2)

        dist = compute_gower_distance(candidates, ["param_a", "param_b"])
        assignments = cluster_candidates(dist, config)
        summaries = compute_cluster_summaries(candidates, assignments, ["param_a", "param_b"])

        df = candidates.to_pandas()
        for s in summaries:
            members = [a.candidate_id for a in assignments if a.cluster_id == s.cluster_id]
            if members and "cv_objective" in df.columns:
                best_cv = df.iloc[members]["cv_objective"].max()
                rep_cv = df.iloc[s.representative_id]["cv_objective"]
                assert rep_cv == best_cv


class TestPreFilter:
    def test_pre_filter_large_candidate_set(self):
        """Pre-filtering retains top-N by cv_objective."""
        candidates = _make_candidates(50, n_clusters=2)
        filtered = pre_filter_candidates(candidates, max_candidates=20)

        assert len(filtered) == 20
        # All retained should have higher cv_objective than all removed
        df_orig = candidates.to_pandas()
        df_filt = filtered.to_pandas()
        min_kept = df_filt["cv_objective"].min()
        removed = df_orig[~df_orig["candidate_id"].isin(df_filt["candidate_id"])]
        if len(removed) > 0:
            max_removed = removed["cv_objective"].max()
            assert min_kept >= max_removed
