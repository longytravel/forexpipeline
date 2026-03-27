"""Clustering engine — Gower distance + HDBSCAN (Story 5.6, Task 2).

Handles mixed continuous/categorical parameters with Gower distance
and density-based clustering via HDBSCAN with automatic cluster count.
"""
from __future__ import annotations

import json
from typing import Any

import gower
import hdbscan
import numpy as np
import pandas as pd
import pyarrow as pa

from logging_setup.setup import get_logger
from selection.config import SelectionConfig
from selection.models import ClusterAssignment, ClusterSummary

logger = get_logger("selection.clustering")


def compute_gower_distance(
    candidates: pa.Table,
    param_columns: list[str],
    chunk_size: int = 1000,
) -> np.ndarray:
    """Compute Gower distance matrix with chunked computation for memory.

    Handles mixed continuous/categorical parameters. Uses float64 as required
    by HDBSCAN's mst_linkage_core (expects double_t).

    Args:
        candidates: Arrow table with candidate data.
        param_columns: Column names to use for distance computation.
        chunk_size: Row batch size for chunked computation.

    Returns:
        Square distance matrix as float64 ndarray.
    """
    # Select only columns that exist in the table
    available = [c for c in param_columns if c in candidates.column_names]
    if not available:
        raise ValueError(f"No param columns found in table. Available: {candidates.column_names}")
    df = candidates.select(available).to_pandas()
    n = len(df)

    # Gower needs categorical columns typed as object, not string/category
    for col in df.columns:
        if df[col].dtype == "object" or not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].astype("object")

    if n <= chunk_size:
        dist = gower.gower_matrix(df)
        result = dist.astype(np.float64)
        logger.info(
            "Gower distance computed (single batch)",
            extra={
                "component": "selection.clustering",
                "ctx": {"n_candidates": n, "n_params": len(available)},
            },
        )
        return result

    # Chunked computation for large candidate sets
    result = np.zeros((n, n), dtype=np.float64)
    for i_start in range(0, n, chunk_size):
        i_end = min(i_start + chunk_size, n)
        chunk_x = df.iloc[i_start:i_end]
        # Compute distances from this chunk to all candidates
        chunk_dist = gower.gower_matrix(chunk_x, df)
        result[i_start:i_end, :] = chunk_dist.astype(np.float64)

    logger.info(
        "Gower distance computed (chunked)",
        extra={
            "component": "selection.clustering",
            "ctx": {
                "n_candidates": n,
                "n_params": len(available),
                "n_chunks": (n + chunk_size - 1) // chunk_size,
                "memory_mb": round(result.nbytes / 1024 / 1024, 1),
            },
        },
    )
    return result


def cluster_candidates(
    distance_matrix: np.ndarray,
    config: SelectionConfig,
    candidate_ids: list[int] | None = None,
) -> list[ClusterAssignment]:
    """Run HDBSCAN clustering with precomputed distance matrix.

    If HDBSCAN labels all candidates as noise, each candidate becomes
    its own singleton cluster (edge case handling per story spec).

    Args:
        distance_matrix: Precomputed Gower distance matrix (float32).
        config: Selection configuration.
        candidate_ids: Actual candidate IDs from the table. If None,
            falls back to row indices (0..n-1).

    Returns:
        List of ClusterAssignment for each candidate.
    """
    n = distance_matrix.shape[0]
    ids = candidate_ids if candidate_ids is not None else list(range(n))

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=config.min_cluster_size,
        min_samples=config.hdbscan_min_samples,
        metric="precomputed",
    )
    clusterer.fit(distance_matrix)

    labels = clusterer.labels_
    probabilities = clusterer.probabilities_

    # Edge case: all noise — treat each as singleton cluster
    if np.all(labels == -1):
        logger.warning(
            "HDBSCAN labeled all candidates as noise — using singleton clusters",
            extra={
                "component": "selection.clustering",
                "ctx": {"n_candidates": n},
            },
        )
        assignments = [
            ClusterAssignment(
                candidate_id=ids[i],
                cluster_id=ids[i],
                is_noise=True,
                membership_prob=0.0,
            )
            for i in range(n)
        ]
        return assignments

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels == -1))

    logger.info(
        "HDBSCAN clustering complete",
        extra={
            "component": "selection.clustering",
            "ctx": {
                "n_candidates": n,
                "n_clusters": n_clusters,
                "n_noise": n_noise,
            },
        },
    )

    assignments = [
        ClusterAssignment(
            candidate_id=ids[i],
            cluster_id=int(labels[i]),
            is_noise=labels[i] == -1,
            membership_prob=float(probabilities[i]),
        )
        for i in range(n)
    ]
    return assignments


def compute_cluster_summaries(
    candidates: pa.Table,
    assignments: list[ClusterAssignment],
    param_columns: list[str],
) -> list[ClusterSummary]:
    """Compute summary statistics for each cluster.

    Per cluster: centroid (mean of each param), representative (best cv_objective),
    robustness_score (mean fold-score std within cluster).

    Args:
        candidates: Arrow table with candidate data.
        assignments: Cluster assignments from HDBSCAN.
        param_columns: Parameter column names for centroid computation.

    Returns:
        List of ClusterSummary, one per non-noise cluster.
    """
    df = candidates.to_pandas()
    n = len(df)

    # Build cluster membership map
    cluster_ids: dict[int, list[int]] = {}
    for a in assignments:
        cid = a.cluster_id
        if cid == -1 and not a.is_noise:
            # Singleton cluster case (all-noise fallback)
            cluster_ids.setdefault(cid, []).append(a.candidate_id)
        elif cid != -1:
            cluster_ids.setdefault(cid, []).append(a.candidate_id)
        else:
            # True noise — still track for singleton fallback
            cluster_ids.setdefault(cid, []).append(a.candidate_id)

    # Handle all-noise singleton case: each candidate is its own cluster
    all_noise = all(a.is_noise for a in assignments)

    summaries: list[ClusterSummary] = []
    unique_clusters = sorted(set(a.cluster_id for a in assignments))

    for cid in unique_clusters:
        members = [a.candidate_id for a in assignments if a.cluster_id == cid]
        if not members:
            continue

        # Look up members by candidate_id, not by row position
        if "candidate_id" in df.columns:
            member_df = df[df["candidate_id"].isin(members)]
        else:
            member_df = df.iloc[members]

        # Centroid: mean of numeric param columns
        centroid: dict[str, float] = {}
        for col in param_columns:
            if col in member_df.columns and pd.api.types.is_numeric_dtype(member_df[col]):
                centroid[col] = float(member_df[col].mean())

        # Representative: best cv_objective within cluster
        if "cv_objective" in member_df.columns:
            best_idx = member_df["cv_objective"].idxmax()
            if "candidate_id" in member_df.columns:
                representative_id = int(member_df.loc[best_idx, "candidate_id"])
            else:
                representative_id = int(best_idx)
            best_cv = float(member_df.loc[best_idx, "cv_objective"])
        else:
            representative_id = members[0]
            best_cv = 0.0

        # Robustness: mean fold-score std within cluster
        robustness = _compute_robustness(member_df)

        metrics_summary: dict[str, float] = {
            "mean_cv_objective": float(member_df["cv_objective"].mean())
            if "cv_objective" in member_df.columns
            else 0.0,
            "best_cv_objective": best_cv,
        }

        summaries.append(
            ClusterSummary(
                cluster_id=cid,
                size=len(members),
                centroid_params=centroid,
                representative_id=representative_id,
                robustness_score=robustness,
                metrics_summary=metrics_summary,
            )
        )

    return summaries


def _compute_robustness(member_df: pd.DataFrame) -> float:
    """Compute robustness score (mean fold-score std) for cluster members."""
    if "fold_scores" not in member_df.columns:
        return 0.0

    stds = []
    for _, row in member_df.iterrows():
        fold_scores = row["fold_scores"]
        if fold_scores is not None and len(fold_scores) > 1:
            stds.append(float(np.std(fold_scores)))

    if not stds:
        return 0.0

    # Lower std = more robust. Invert so higher = better.
    mean_std = float(np.mean(stds))
    return 1.0 / (1.0 + mean_std)


def pre_filter_candidates(
    candidates: pa.Table,
    max_candidates: int,
) -> pa.Table:
    """Pre-filter candidates by cv_objective when count exceeds threshold.

    Args:
        candidates: Full candidate table.
        max_candidates: Maximum candidates to retain.

    Returns:
        Filtered table with top candidates by cv_objective.
    """
    if len(candidates) <= max_candidates:
        return candidates

    df = candidates.to_pandas()
    df_sorted = df.nlargest(max_candidates, "cv_objective")

    logger.warning(
        "Pre-filtering candidates for clustering",
        extra={
            "component": "selection.clustering",
            "ctx": {
                "original_count": len(candidates),
                "filtered_count": max_candidates,
            },
        },
    )

    return pa.Table.from_pandas(df_sorted, preserve_index=False)
