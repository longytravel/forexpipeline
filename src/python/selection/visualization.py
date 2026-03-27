"""Visualization data preparation (Story 5.6, Task 6, FR26/FR76).

Prepares JSON-serializable data structures for downstream dashboard rendering.
All functions return dict structures — actual rendering is deferred to Story 5.7 / Epic 4.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from selection.models import ClusterAssignment, ClusterSummary, RankedCandidate


def prepare_parallel_coordinates(
    candidates: list[RankedCandidate],
    params: dict[int, dict[str, float]],
    quality_metrics: dict[int, dict[str, float]],
) -> dict[str, Any]:
    """Prepare parallel coordinates visualization data.

    Args:
        candidates: Selected/ranked candidates.
        params: {candidate_id: {param_name: value}} for parameter axes.
        quality_metrics: {candidate_id: {metric_name: value}} for quality axes.

    Returns:
        JSON-serializable dict with axes and traces.
    """
    if not candidates:
        return {"axes": [], "traces": []}

    # Collect all parameter and metric names
    param_names: set[str] = set()
    metric_names: set[str] = set()
    for cid_params in params.values():
        param_names.update(cid_params.keys())
    for cid_metrics in quality_metrics.values():
        metric_names.update(cid_metrics.keys())

    axes = sorted(param_names) + sorted(metric_names)

    traces = []
    for rc in candidates:
        cid = rc.candidate_id
        p = params.get(cid, {})
        q = quality_metrics.get(cid, {})
        values = [p.get(a, q.get(a, 0.0)) for a in axes]
        traces.append({
            "candidate_id": cid,
            "cluster_id": rc.cluster_id,
            "topsis_score": rc.topsis_score,
            "values": values,
            "selected": rc.funnel_stage == "selected",
        })

    return {"axes": axes, "traces": traces}


def prepare_parameter_heatmap(
    clusters: list[ClusterSummary],
) -> dict[str, Any]:
    """Prepare cluster × parameter heatmap data.

    Args:
        clusters: Cluster summaries with centroid parameters.

    Returns:
        JSON-serializable dict with matrix data for heatmap rendering.
    """
    if not clusters:
        return {"cluster_ids": [], "param_names": [], "matrix": []}

    # Collect all parameter names across clusters
    all_params: set[str] = set()
    for cs in clusters:
        all_params.update(cs.centroid_params.keys())

    param_names = sorted(all_params)
    cluster_ids = [cs.cluster_id for cs in clusters]

    # Build normalized matrix (0-1 per parameter for color mapping)
    raw_matrix = []
    for cs in clusters:
        row = [cs.centroid_params.get(p, 0.0) for p in param_names]
        raw_matrix.append(row)

    matrix = np.array(raw_matrix, dtype=np.float64)

    # Normalize per column
    col_min = matrix.min(axis=0) if len(matrix) > 0 else np.zeros(len(param_names))
    col_max = matrix.max(axis=0) if len(matrix) > 0 else np.ones(len(param_names))
    col_range = col_max - col_min
    col_range[col_range == 0] = 1.0
    normalized = ((matrix - col_min) / col_range).tolist()

    return {
        "cluster_ids": cluster_ids,
        "param_names": param_names,
        "matrix": normalized,
        "raw_matrix": raw_matrix,
    }


def prepare_cluster_membership(
    assignments: list[ClusterAssignment],
    selected_ids: set[int],
    projection_2d: np.ndarray | None = None,
) -> dict[str, Any]:
    """Prepare 2D cluster membership plot data.

    If projection_2d is None, a simple placeholder is used.
    UMAP projection should be computed externally on selected candidates +
    cluster representatives only (not all 10K).

    Args:
        assignments: All cluster assignments.
        selected_ids: Set of selected candidate IDs for highlighting.
        projection_2d: Optional (n, 2) array of UMAP/tSNE coordinates.

    Returns:
        JSON-serializable dict with point data for scatter plot.
    """
    points = []
    for i, a in enumerate(assignments):
        x = float(projection_2d[i, 0]) if projection_2d is not None and i < len(projection_2d) else float(i)
        y = float(projection_2d[i, 1]) if projection_2d is not None and i < len(projection_2d) else 0.0

        points.append({
            "candidate_id": a.candidate_id,
            "cluster_id": a.cluster_id,
            "is_noise": a.is_noise,
            "x": x,
            "y": y,
            "selected": a.candidate_id in selected_ids,
            "membership_prob": a.membership_prob,
        })

    return {
        "points": points,
        "has_projection": projection_2d is not None,
        "n_clusters": len(set(a.cluster_id for a in assignments if not a.is_noise)),
        "n_selected": len(selected_ids),
    }
