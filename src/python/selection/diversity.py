"""MAP-Elites diversity archive and diversity-preserving selection (Story 5.6, Task 5, FR28).

Behavioral diversity is maintained across dimensions: trade frequency,
holding time, win rate, max drawdown. Selection uses 80/20
deterministic-exploratory split.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from logging_setup.setup import get_logger
from selection.config import SelectionConfig
from selection.models import DiversityCell, RankedCandidate

logger = get_logger("selection.diversity")


@dataclass
class BehaviorDimension:
    """Definition of a single behavior dimension for MAP-Elites grid."""

    name: str
    bin_edges: list[float]
    bin_labels: list[str]

    def classify(self, value: float) -> str:
        """Classify a value into its bin label."""
        for i, edge in enumerate(self.bin_edges):
            if value <= edge:
                return self.bin_labels[i]
        return self.bin_labels[-1]


def define_behavior_dimensions(config: SelectionConfig) -> list[BehaviorDimension]:
    """Define behavior dimensions with bin boundaries from config.

    Args:
        config: Selection configuration containing diversity_dimensions list.

    Returns:
        List of BehaviorDimension with pre-defined bin edges.
    """
    dimension_defs: dict[str, BehaviorDimension] = {
        "trade_frequency": BehaviorDimension(
            name="trade_frequency",
            bin_edges=[50, 200, 500],
            bin_labels=["low", "medium", "high", "very_high"],
        ),
        "avg_holding_time": BehaviorDimension(
            name="avg_holding_time",
            bin_edges=[60, 240, 1440],
            bin_labels=["scalp", "intraday", "swing", "position"],
        ),
        "win_rate": BehaviorDimension(
            name="win_rate",
            bin_edges=[0.40, 0.55, 0.70],
            bin_labels=["low", "moderate", "good", "high"],
        ),
        "max_drawdown": BehaviorDimension(
            name="max_drawdown",
            bin_edges=[0.05, 0.10, 0.20],
            bin_labels=["minimal", "low", "moderate", "high"],
        ),
    }

    return [
        dimension_defs[dim]
        for dim in config.diversity_dimensions
        if dim in dimension_defs
    ]


def build_diversity_archive(
    ranked_candidates: list[RankedCandidate],
    behavior_data: dict[int, dict[str, float]],
    dimensions: list[BehaviorDimension],
) -> list[DiversityCell]:
    """Build MAP-Elites grid: each cell keeps best candidate by topsis_score.

    Args:
        ranked_candidates: Candidates from the funnel.
        behavior_data: {candidate_id: {dimension_name: value}} lookup.
        dimensions: Behavior dimensions for the grid.

    Returns:
        List of occupied DiversityCell entries.
    """
    # Grid keyed by tuple of bin labels
    grid: dict[tuple[str, ...], DiversityCell] = {}

    for rc in ranked_candidates:
        bdata = behavior_data.get(rc.candidate_id, {})
        if not bdata:
            continue

        # Classify into bins
        bin_key_parts: list[str] = []
        dim_labels: dict[str, str] = {}
        for dim in dimensions:
            value = bdata.get(dim.name, 0.0)
            label = dim.classify(value)
            bin_key_parts.append(label)
            dim_labels[dim.name] = label

        bin_key = tuple(bin_key_parts)

        # MAP-Elites: keep best score per cell
        if bin_key not in grid or rc.topsis_score > grid[bin_key].best_score:
            grid[bin_key] = DiversityCell(
                dimensions=dim_labels,
                best_candidate_id=rc.candidate_id,
                best_score=rc.topsis_score,
            )

    logger.info(
        "Diversity archive built",
        extra={
            "component": "selection.diversity",
            "ctx": {
                "n_candidates": len(ranked_candidates),
                "n_cells_occupied": len(grid),
                "n_dimensions": len(dimensions),
            },
        },
    )

    return list(grid.values())


def select_diverse_candidates(
    archive: list[DiversityCell],
    funnel_survivors: list[RankedCandidate],
    target_n: int,
    deterministic_ratio: float,
    rng_seed: int,
) -> list[RankedCandidate]:
    """Select diverse candidates with 80/20 deterministic-exploratory split.

    - 80% deterministic: top candidates from filled archive cells, one per cluster preference
    - 20% exploratory: random draw from remaining occupied cells

    Args:
        archive: MAP-Elites diversity archive.
        funnel_survivors: All candidates surviving the funnel.
        target_n: Desired number of selected candidates.
        deterministic_ratio: Fraction for deterministic selection (0.8).
        rng_seed: Seed for reproducible exploratory selection.

    Returns:
        List of selected RankedCandidate with updated selection_reason.
    """
    if not funnel_survivors:
        return []

    actual_target = min(target_n, len(funnel_survivors))
    n_deterministic = int(actual_target * deterministic_ratio) if deterministic_ratio > 0 else 0
    n_deterministic = min(n_deterministic, actual_target)
    if n_deterministic == 0 and deterministic_ratio > 0:
        n_deterministic = 1
    n_exploratory = actual_target - n_deterministic

    rng = np.random.default_rng(rng_seed)

    # Build lookup
    survivor_map = {rc.candidate_id: rc for rc in funnel_survivors}
    archive_ids = {cell.best_candidate_id for cell in archive}

    # Sort archive cells by best_score descending
    sorted_cells = sorted(archive, key=lambda c: c.best_score, reverse=True)

    selected: list[RankedCandidate] = []
    selected_ids: set[int] = set()
    used_clusters: set[int] = set()

    # ── Deterministic selection: top cells, one per cluster preference ──
    for cell in sorted_cells:
        if len(selected) >= n_deterministic:
            break
        cid = cell.best_candidate_id
        if cid in selected_ids:
            continue

        rc = survivor_map.get(cid)
        if rc is None:
            continue

        # Prefer cross-cluster diversity
        if rc.cluster_id in used_clusters and len(used_clusters) < len(
            set(s.cluster_id for s in funnel_survivors)
        ):
            continue

        selected.append(
            RankedCandidate(
                candidate_id=rc.candidate_id,
                topsis_score=rc.topsis_score,
                pareto_rank=rc.pareto_rank,
                cluster_id=rc.cluster_id,
                stability_pass=rc.stability_pass,
                funnel_stage="selected",
                selection_reason=f"deterministic: archive cell {cell.dimensions}, score {rc.topsis_score:.4f} (funnel: {rc.funnel_stage})",
            )
        )
        selected_ids.add(cid)
        used_clusters.add(rc.cluster_id)

    # If we didn't fill deterministic slots due to cluster constraint, relax it
    if len(selected) < n_deterministic:
        for cell in sorted_cells:
            if len(selected) >= n_deterministic:
                break
            cid = cell.best_candidate_id
            if cid in selected_ids:
                continue
            rc = survivor_map.get(cid)
            if rc is None:
                continue
            selected.append(
                RankedCandidate(
                    candidate_id=rc.candidate_id,
                    topsis_score=rc.topsis_score,
                    pareto_rank=rc.pareto_rank,
                    cluster_id=rc.cluster_id,
                    stability_pass=rc.stability_pass,
                    funnel_stage="selected",
                    selection_reason=f"deterministic (relaxed): archive cell {cell.dimensions} (funnel: {rc.funnel_stage})",
                )
            )
            selected_ids.add(cid)

    # ── Exploratory selection: random from remaining archive cells ──
    remaining_cells = [c for c in sorted_cells if c.best_candidate_id not in selected_ids]
    if remaining_cells and n_exploratory > 0:
        n_explore = min(n_exploratory, len(remaining_cells))
        explore_indices = rng.choice(len(remaining_cells), size=n_explore, replace=False)

        for idx in explore_indices:
            cell = remaining_cells[idx]
            rc = survivor_map.get(cell.best_candidate_id)
            if rc is None:
                continue
            selected.append(
                RankedCandidate(
                    candidate_id=rc.candidate_id,
                    topsis_score=rc.topsis_score,
                    pareto_rank=rc.pareto_rank,
                    cluster_id=rc.cluster_id,
                    stability_pass=rc.stability_pass,
                    funnel_stage="selected",
                    selection_reason=f"exploratory: random from archive cell {cell.dimensions} (funnel: {rc.funnel_stage})",
                )
            )
            selected_ids.add(cell.best_candidate_id)

    # If still short, fill from top funnel survivors not yet selected
    if len(selected) < actual_target:
        remaining_survivors = sorted(
            [rc for rc in funnel_survivors if rc.candidate_id not in selected_ids],
            key=lambda rc: rc.topsis_score,
            reverse=True,
        )
        for rc in remaining_survivors:
            if len(selected) >= actual_target:
                break
            selected.append(
                RankedCandidate(
                    candidate_id=rc.candidate_id,
                    topsis_score=rc.topsis_score,
                    pareto_rank=rc.pareto_rank,
                    cluster_id=rc.cluster_id,
                    stability_pass=rc.stability_pass,
                    funnel_stage="selected",
                    selection_reason=f"backfill: top funnel survivor (funnel: {rc.funnel_stage})",
                )
            )

    logger.info(
        "Diverse candidate selection complete",
        extra={
            "component": "selection.diversity",
            "ctx": {
                "target": target_n,
                "selected": len(selected),
                "deterministic": min(n_deterministic, len(selected)),
                "exploratory": max(0, len(selected) - n_deterministic),
                "clusters_covered": len(set(s.cluster_id for s in selected)),
            },
        },
    )

    return selected
