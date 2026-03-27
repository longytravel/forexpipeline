"""Tests for memory-related concerns (Story 5.6, Task 9)."""
from __future__ import annotations

import json

import numpy as np
import pyarrow as pa
import pytest

from selection.clustering import compute_gower_distance, pre_filter_candidates


class TestGowerChunkedComputation:
    def test_gower_chunked_computation(self):
        """Chunked Gower produces same result as dense computation."""
        rng = np.random.default_rng(42)
        n = 50
        table = pa.table({
            "candidate_id": list(range(n)),
            "param_a": rng.uniform(0, 100, n).tolist(),
            "param_b": rng.uniform(0, 100, n).tolist(),
        })

        # Dense (single batch)
        dense = compute_gower_distance(table, ["param_a", "param_b"], chunk_size=n + 1)

        # Chunked
        chunked = compute_gower_distance(table, ["param_a", "param_b"], chunk_size=15)

        np.testing.assert_allclose(dense, chunked, atol=1e-4)


class TestPreFilterLargeCandidateSet:
    def test_pre_filter_large_candidate_set(self):
        """Large input triggers pre-filtering to max_clustering_candidates."""
        rng = np.random.default_rng(42)
        n = 200
        table = pa.table({
            "candidate_id": list(range(n)),
            "cv_objective": rng.uniform(0, 5, n).tolist(),
            "params_json": [json.dumps({"p": float(rng.uniform(0, 100))}) for _ in range(n)],
        })

        filtered = pre_filter_candidates(table, max_candidates=50)
        assert len(filtered) == 50

        # Filtered candidates should have highest cv_objective values
        df_filt = filtered.to_pandas()
        df_all = table.to_pandas()
        min_kept = df_filt["cv_objective"].min()
        max_removed = df_all[~df_all["candidate_id"].isin(df_filt["candidate_id"])]["cv_objective"].max()
        assert min_kept >= max_removed

    def test_pre_filter_below_threshold_no_op(self):
        """Below threshold → no filtering."""
        rng = np.random.default_rng(42)
        n = 30
        table = pa.table({
            "candidate_id": list(range(n)),
            "cv_objective": rng.uniform(0, 5, n).tolist(),
        })

        filtered = pre_filter_candidates(table, max_candidates=100)
        assert len(filtered) == n
