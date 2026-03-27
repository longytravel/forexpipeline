"""Multi-objective ranking — TOPSIS + CRITIC + Pareto (Story 5.6, Task 4, FR27).

4-stage filtering funnel:
1. Hard gates (DSR pass, PBO ≤ threshold, cost stress survival)
2. TOPSIS ranking with CRITIC-derived weights
3. Stability filtering (fold_score_std threshold)
4. Pareto frontier extraction
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from logging_setup.setup import get_logger
from selection.config import SelectionConfig
from selection.models import (
    ClusterAssignment,
    EquityCurveQuality,
    FunnelStats,
    RankedCandidate,
)

logger = get_logger("selection.ranking")


def compute_critic_weights(decision_matrix: np.ndarray) -> np.ndarray:
    """CRITIC method: correlation-adjusted standard deviation weights.

    Each criterion's weight is proportional to its information content,
    measured as std * sum(1 - correlation with other criteria).

    Args:
        decision_matrix: (n_candidates × n_criteria) matrix.

    Returns:
        Weight vector summing to 1.0.
    """
    n_candidates, n_criteria = decision_matrix.shape

    if n_candidates < 2 or n_criteria < 1:
        return np.ones(n_criteria) / n_criteria

    # Normalize columns to [0, 1]
    col_min = decision_matrix.min(axis=0)
    col_max = decision_matrix.max(axis=0)
    col_range = col_max - col_min
    # Avoid division by zero for constant columns
    col_range[col_range == 0] = 1.0
    normalized = (decision_matrix - col_min) / col_range

    # Standard deviation per column
    stds = normalized.std(axis=0, ddof=1)
    stds[np.isnan(stds)] = 0.0

    # Correlation matrix
    if n_candidates < 3:
        # Not enough data for meaningful correlation
        corr = np.eye(n_criteria)
    else:
        corr = np.corrcoef(normalized.T)
        if np.any(np.isnan(corr)):
            corr = np.nan_to_num(corr, nan=0.0)

    # Information content: std * sum(1 - abs(correlation))
    info = np.zeros(n_criteria)
    for j in range(n_criteria):
        conflict = np.sum(1.0 - np.abs(corr[j, :]))
        info[j] = stds[j] * conflict

    total = info.sum()
    if total == 0:
        return np.ones(n_criteria) / n_criteria

    return info / total


def topsis_rank(
    decision_matrix: np.ndarray,
    weights: np.ndarray,
    benefit_columns: list[int],
    cost_columns: list[int],
) -> np.ndarray:
    """TOPSIS: Technique for Order of Preference by Similarity to Ideal Solution.

    Args:
        decision_matrix: (n_candidates × n_criteria) matrix.
        weights: Weight per criterion (sums to 1.0).
        benefit_columns: Column indices where higher is better.
        cost_columns: Column indices where lower is better.

    Returns:
        Closeness coefficients in [0, 1], higher = better.
    """
    n, m = decision_matrix.shape
    if n == 0:
        return np.array([])

    # Step 1: Normalize (vector normalization)
    norms = np.sqrt(np.sum(decision_matrix**2, axis=0))
    norms[norms == 0] = 1.0
    normalized = decision_matrix / norms

    # Step 2: Weighted normalized matrix
    weighted = normalized * weights

    # Step 3: Ideal and anti-ideal solutions
    ideal = np.zeros(m)
    anti_ideal = np.zeros(m)
    for j in range(m):
        if j in benefit_columns:
            ideal[j] = weighted[:, j].max()
            anti_ideal[j] = weighted[:, j].min()
        elif j in cost_columns:
            ideal[j] = weighted[:, j].min()
            anti_ideal[j] = weighted[:, j].max()
        else:
            # Default: benefit
            ideal[j] = weighted[:, j].max()
            anti_ideal[j] = weighted[:, j].min()

    # Step 4: Distance to ideal and anti-ideal
    dist_ideal = np.sqrt(np.sum((weighted - ideal) ** 2, axis=1))
    dist_anti = np.sqrt(np.sum((weighted - anti_ideal) ** 2, axis=1))

    # Step 5: Closeness coefficient
    denominator = dist_ideal + dist_anti
    denominator[denominator == 0] = 1.0
    closeness = dist_anti / denominator

    return closeness


def pareto_frontier(
    candidates: list[RankedCandidate],
    objectives: list[str],
    candidate_metrics: dict[int, dict[str, float]],
) -> list[RankedCandidate]:
    """Non-dominated sorting — assign Pareto ranks (rank 1 = Pareto front).

    All objectives are treated as maximization (higher = better).

    Args:
        candidates: List of ranked candidates.
        objectives: Objective names to use from candidate_metrics.
        candidate_metrics: {candidate_id: {metric_name: value}} lookup.

    Returns:
        Same candidates with updated pareto_rank.
    """
    if not candidates:
        return []

    n = len(candidates)
    # Build objective matrix
    obj_matrix = np.zeros((n, len(objectives)))
    for i, c in enumerate(candidates):
        metrics = candidate_metrics.get(c.candidate_id, {})
        for j, obj in enumerate(objectives):
            obj_matrix[i, j] = metrics.get(obj, 0.0)

    # Non-dominated sorting
    ranks = np.zeros(n, dtype=int)
    assigned = set()
    current_rank = 1

    while len(assigned) < n:
        # Find non-dominated candidates among unassigned
        front = []
        for i in range(n):
            if i in assigned:
                continue
            dominated = False
            for j in range(n):
                if j in assigned or j == i:
                    continue
                # Check if j dominates i
                if np.all(obj_matrix[j] >= obj_matrix[i]) and np.any(
                    obj_matrix[j] > obj_matrix[i]
                ):
                    dominated = True
                    break
            if not dominated:
                front.append(i)

        for i in front:
            ranks[i] = current_rank
            assigned.add(i)
        current_rank += 1

    result = []
    for i, c in enumerate(candidates):
        result.append(
            RankedCandidate(
                candidate_id=c.candidate_id,
                topsis_score=c.topsis_score,
                pareto_rank=int(ranks[i]),
                cluster_id=c.cluster_id,
                stability_pass=c.stability_pass,
                funnel_stage=c.funnel_stage,
                selection_reason=c.selection_reason,
            )
        )
    return result


def four_stage_funnel(
    candidates: pa.Table,
    quality_metrics: list[EquityCurveQuality],
    cluster_assignments: list[ClusterAssignment],
    config: SelectionConfig,
    hard_gate_config: dict[str, Any],
    scoring_manifests: dict[int, dict] | None = None,
) -> tuple[list[RankedCandidate], FunnelStats, dict[str, float], dict[str, int]]:
    """Execute the 4-stage filtering funnel.

    Stage 1: Hard gates (DSR pass, PBO ≤ 0.40, cost stress survival)
    Stage 2: TOPSIS ranking on multi-objective criteria
    Stage 3: Stability filtering (fold_score_std > threshold excluded)
    Stage 4: Pareto frontier across [topsis_score, robustness, diversity_distance]

    Args:
        candidates: Arrow table with candidate data.
        quality_metrics: Equity curve quality per candidate.
        cluster_assignments: Cluster assignments per candidate.
        config: Selection configuration.
        hard_gate_config: Hard gate thresholds from [confidence.hard_gates].
        scoring_manifests: Optional per-candidate scoring manifests for pre-filtering.

    Returns:
        Tuple of (ranked_candidates, funnel_stats, critic_weights).
    """
    df = candidates.to_pandas()
    total_input = len(df)

    # Build lookup maps
    quality_map = {q.candidate_id: q for q in quality_metrics}
    cluster_map = {a.candidate_id: a for a in cluster_assignments}
    gate_failure_counts: dict[str, int] = {"dsr": 0, "pbo": 0, "cost_stress": 0}

    # ── Stage 1: Hard gates ──
    pbo_threshold = hard_gate_config.get("pbo_max_threshold", 0.40)
    dsr_required = hard_gate_config.get("dsr_pass_required", True)

    survivors_1: list[int] = []
    for idx in range(total_input):
        cid = int(df.iloc[idx].get("candidate_id", idx))

        # If scoring manifests available, use them for gate decisions
        if scoring_manifests and cid in scoring_manifests:
            manifest = scoring_manifests[cid]
            gate_results = manifest.get("gate_results", {})

            if dsr_required and not gate_results.get("dsr_passed", False):
                gate_failure_counts["dsr"] += 1
                continue
            if gate_results.get("pbo_value", 1.0) > pbo_threshold:
                gate_failure_counts["pbo"] += 1
                continue
            stage_summaries = manifest.get("per_stage_summaries", {})
            mc = stage_summaries.get("monte_carlo", {})
            if not mc.get("stress_survived", False):
                gate_failure_counts["cost_stress"] += 1
                continue
        else:
            # Use quality metrics for DSR gate
            q = quality_map.get(cid)
            if q and dsr_required and q.dsr < 0.05:
                gate_failure_counts["dsr"] += 1
                continue

        survivors_1.append(idx)

    after_hard_gates = len(survivors_1)

    if after_hard_gates == 0:
        logger.error(
            "All candidates failed hard gates",
            extra={
                "component": "selection.ranking",
                "ctx": {"total": total_input, "gate_failures": gate_failure_counts},
            },
        )
        empty_stats = FunnelStats(
            total_input=total_input,
            after_hard_gates=0,
            after_topsis=0,
            after_stability=0,
            after_pareto=0,
            final_selected=0,
        )
        return [], empty_stats, {}, gate_failure_counts

    # ── Stage 2: TOPSIS ranking ──
    # Build decision matrix: [cv_objective, k_ratio, 1/ulcer_index, gain_to_pain, serenity_ratio, 1/fold_std]
    criteria_names = [
        "cv_objective",
        "k_ratio",
        "ulcer_index_inv",
        "gain_to_pain",
        "serenity_ratio",
        "fold_score_std_inv",
    ]
    benefit_cols = [0, 1, 2, 3, 4, 5]  # All benefit (higher = better)
    cost_cols: list[int] = []

    decision_rows = []
    survivor_ids: list[int] = []
    for idx in survivors_1:
        cid = int(df.iloc[idx].get("candidate_id", idx))
        q = quality_map.get(cid)
        row_data = df.iloc[idx]

        cv_obj = float(row_data.get("cv_objective", 0.0))
        k_ratio = q.k_ratio if q else 0.0
        ulcer_inv = 1.0 / (1.0 + (q.ulcer_index if q else 0.0))
        gtp = q.gain_to_pain if q else 0.0
        serenity = q.serenity_ratio if q else 0.0

        fold_scores = row_data.get("fold_scores")
        if fold_scores is not None and hasattr(fold_scores, '__len__') and len(fold_scores) > 1:
            fold_std = float(np.std(fold_scores))
        else:
            fold_std = 0.0
        fold_std_inv = 1.0 / (1.0 + fold_std)

        decision_rows.append([cv_obj, k_ratio, ulcer_inv, gtp, serenity, fold_std_inv])
        survivor_ids.append(cid)

    decision_matrix = np.array(decision_rows, dtype=np.float64)
    critic_weights_arr = compute_critic_weights(decision_matrix)
    critic_weights = {name: float(w) for name, w in zip(criteria_names, critic_weights_arr)}

    closeness = topsis_rank(decision_matrix, critic_weights_arr, benefit_cols, cost_cols)

    # Take top-N by TOPSIS score
    top_n = min(config.topsis_top_n, len(closeness))
    top_indices = np.argsort(closeness)[::-1][:top_n]

    after_topsis = len(top_indices)

    # ── Stage 3: Stability filtering ──
    stable_candidates: list[RankedCandidate] = []
    for rank, arr_idx in enumerate(top_indices):
        cid = survivor_ids[arr_idx]
        row_data = df.loc[df.get("candidate_id", df.index) == cid]
        if row_data.empty:
            row_data = df.iloc[[survivors_1[arr_idx] if arr_idx < len(survivors_1) else arr_idx]]

        fold_scores = df.iloc[survivors_1[arr_idx] if arr_idx < len(survivors_1) else 0].get("fold_scores")
        if fold_scores is not None and hasattr(fold_scores, '__len__') and len(fold_scores) > 1:
            fold_std = float(np.std(fold_scores))
        else:
            fold_std = 0.0

        stability_pass = fold_std <= config.stability_threshold
        ca = cluster_map.get(cid)
        cluster_id = ca.cluster_id if ca else -1

        rc = RankedCandidate(
            candidate_id=cid,
            topsis_score=float(closeness[arr_idx]),
            pareto_rank=0,
            cluster_id=cluster_id,
            stability_pass=stability_pass,
            funnel_stage="stability" if stability_pass else "filtered_stability",
            selection_reason=f"TOPSIS rank {rank + 1}, score {closeness[arr_idx]:.4f}",
        )
        if stability_pass:
            stable_candidates.append(rc)

    after_stability = len(stable_candidates)

    if after_stability == 0:
        logger.warning(
            "All TOPSIS survivors failed stability filter",
            extra={
                "component": "selection.ranking",
                "ctx": {"after_topsis": after_topsis, "threshold": config.stability_threshold},
            },
        )
        stats = FunnelStats(
            total_input=total_input,
            after_hard_gates=after_hard_gates,
            after_topsis=after_topsis,
            after_stability=0,
            after_pareto=0,
            final_selected=0,
        )
        return [], stats, critic_weights, gate_failure_counts

    # ── Stage 4: Pareto frontier ──
    # Build metrics for Pareto: [topsis_score, robustness, diversity_distance]
    candidate_metrics: dict[int, dict[str, float]] = {}
    for rc in stable_candidates:
        q = quality_map.get(rc.candidate_id)
        ca = cluster_map.get(rc.candidate_id)
        robustness = 0.0
        if ca and not ca.is_noise:
            robustness = ca.membership_prob

        candidate_metrics[rc.candidate_id] = {
            "topsis_score": rc.topsis_score,
            "robustness": robustness,
            "k_ratio": q.k_ratio if q else 0.0,
        }

    pareto_ranked = pareto_frontier(
        stable_candidates,
        ["topsis_score", "robustness", "k_ratio"],
        candidate_metrics,
    )

    after_pareto = len(pareto_ranked)

    # Update funnel_stage for Pareto front
    for rc in pareto_ranked:
        rc_new_stage = "pareto" if rc.pareto_rank == 1 else "pareto_dominated"
        # Create new with updated values since RankedCandidate isn't frozen
        rc.funnel_stage = rc_new_stage

    stats = FunnelStats(
        total_input=total_input,
        after_hard_gates=after_hard_gates,
        after_topsis=after_topsis,
        after_stability=after_stability,
        after_pareto=after_pareto,
        final_selected=after_pareto,
    )

    logger.info(
        "4-stage funnel complete",
        extra={
            "component": "selection.ranking",
            "ctx": {
                "total_input": total_input,
                "after_gates": after_hard_gates,
                "after_topsis": after_topsis,
                "after_stability": after_stability,
                "after_pareto": after_pareto,
            },
        },
    )

    return pareto_ranked, stats, critic_weights, gate_failure_counts
