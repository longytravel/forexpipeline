"""Regression tests for Story 5-6 code review findings.

Each test guards against a specific bug class found during dual review synthesis.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from selection.clustering import cluster_candidates, compute_cluster_summaries
from selection.config import SelectionConfig
from selection.diversity import select_diverse_candidates, build_diversity_archive, BehaviorDimension
from selection.models import (
    ClusterAssignment,
    DiversityCell,
    EquityCurveQuality,
    RankedCandidate,
)
from selection.ranking import four_stage_funnel


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


def _write_synthetic_candidates(path: Path, n: int = 30, id_offset: int = 0) -> None:
    """Write a synthetic candidates.arrow file with configurable ID offset."""
    rng = np.random.default_rng(42)
    table = pa.table({
        "candidate_id": [i + id_offset for i in range(n)],
        "rank": list(range(n)),
        "params_json": [
            json.dumps({"fast": rng.uniform(5, 50), "slow": rng.uniform(50, 200)})
            for _ in range(n)
        ],
        "cv_objective": rng.uniform(0.5, 2.0, n).tolist(),
        "fold_scores": [[rng.uniform(0.3, 2.0) for _ in range(5)] for _ in range(n)],
        "branch": ["cmaes"] * n,
        "instance_type": ["CMAESInstance"] * n,
    })

    path.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_file(str(path), table.schema) as writer:
        writer.write_table(table)


# --- Regression: Cluster ID corruption (Codex H2) ---

@pytest.mark.regression
class TestClusterCandidateIdNonContiguous:
    """Verify cluster_candidates works with non-contiguous candidate IDs.

    Bug: cluster_candidates used row index i as candidate_id instead of
    actual IDs from the table. After pre-filter/dedup, row indices don't
    match candidate_ids, causing cluster lookups to fail silently.
    """

    def test_cluster_ids_match_actual_candidates(self):
        """Cluster assignments must use actual candidate_ids, not row indices."""
        rng = np.random.default_rng(42)
        # Non-contiguous IDs (as after pre-filter/dedup)
        actual_ids = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        n = len(actual_ids)
        distance_matrix = rng.uniform(0, 1, (n, n)).astype(np.float64)
        np.fill_diagonal(distance_matrix, 0)
        distance_matrix = (distance_matrix + distance_matrix.T) / 2

        config = _make_config(min_cluster_size=2, hdbscan_min_samples=1)
        assignments = cluster_candidates(distance_matrix, config, candidate_ids=actual_ids)

        assigned_ids = {a.candidate_id for a in assignments}
        assert assigned_ids == set(actual_ids), (
            f"Cluster assignments should use actual IDs {actual_ids}, got {assigned_ids}"
        )
        # No assignment should have row index 0..9 unless it happens to be in actual_ids
        for a in assignments:
            assert a.candidate_id in actual_ids

    def test_cluster_summaries_with_non_contiguous_ids(self):
        """compute_cluster_summaries must handle non-contiguous candidate IDs."""
        actual_ids = [50, 150, 250]
        table = pa.table({
            "candidate_id": actual_ids,
            "cv_objective": [1.0, 2.0, 3.0],
            "param_a": [10.0, 20.0, 30.0],
        })

        # All in one cluster
        assignments = [
            ClusterAssignment(candidate_id=cid, cluster_id=0, is_noise=False, membership_prob=0.9)
            for cid in actual_ids
        ]

        summaries = compute_cluster_summaries(table, assignments, ["param_a"])
        assert len(summaries) == 1
        # Representative should be candidate 250 (best cv_objective=3.0)
        assert summaries[0].representative_id == 250

    def test_singleton_fallback_uses_actual_ids(self):
        """All-noise singleton fallback must use actual candidate_ids."""
        actual_ids = [42, 99, 777]
        n = len(actual_ids)
        # Tiny distance matrix that will force all-noise with high min_cluster_size
        distance_matrix = np.eye(n, dtype=np.float64)

        config = _make_config(min_cluster_size=10, hdbscan_min_samples=5)
        assignments = cluster_candidates(distance_matrix, config, candidate_ids=actual_ids)

        assigned_ids = {a.candidate_id for a in assignments}
        assert assigned_ids == set(actual_ids)


# --- Regression: Synthetic equity curve WARNING (BMAD H1 + Codex H3) ---

@pytest.mark.regression
class TestSyntheticEquityCurveWarning:
    """Verify WARNING is logged when synthetic equity curves are used.

    Bug: Silent fallback to identical synthetic curves made AC #2 quality
    metrics meaningless constants across all candidates.
    """

    def test_synthetic_curves_produce_warning(self, tmp_path, caplog):
        """Orchestrator must warn when using synthetic equity curves."""
        from selection.orchestrator import SelectionOrchestrator

        candidates_path = tmp_path / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=5)

        orchestrator = SelectionOrchestrator()
        table = orchestrator._load_candidates(candidates_path)
        table, _ = orchestrator._expand_param_columns(table)

        with caplog.at_level(logging.WARNING, logger="selection.orchestrator"):
            metrics = orchestrator._compute_quality_metrics(table, None, 5, 5)

        assert any("synthetic fallback" in r.message.lower() for r in caplog.records), (
            "Expected WARNING about synthetic equity curve fallback"
        )
        assert len(metrics) == 5


# --- Regression: Viz params empty (Codex H5) ---

@pytest.mark.regression
class TestVizParamsPopulated:
    """Verify parallel coordinates has actual parameter axes.

    Bug: _prepare_viz_data set params[cid] = {} for all candidates,
    producing parallel coordinates with no parameter axes.
    """

    def test_parallel_coordinates_has_param_axes(self, tmp_path):
        """Parallel coordinates data must include actual parameter values."""
        from selection.executor import SelectionExecutor

        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=20)
        version_dir = tmp_path / "strategy_test" / "v001"

        config = {
            "selection": {
                "min_cluster_size": 3, "hdbscan_min_samples": 2,
                "topsis_top_n": 15, "stability_threshold": 1.0,
                "target_candidates": 5, "deterministic_ratio": 0.8,
                "diversity_dimensions": ["trade_frequency", "win_rate"],
                "max_clustering_candidates": 5000, "random_seed": 42,
            },
            "hard_gates": {"dsr_pass_required": False, "pbo_max_threshold": 0.40},
        }
        executor = SelectionExecutor(config)
        result = executor.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(version_dir),
        })

        assert result.outcome == "success"
        viz_path = Path(result.artifact_path) / "viz" / "parallel_coordinates.json"
        assert viz_path.exists()

        with open(viz_path) as f:
            viz = json.load(f)

        # Must have actual axes (parameters + quality metrics)
        assert len(viz["axes"]) > 0, "Parallel coordinates must have parameter/metric axes"
        # At least one trace must have non-zero values
        if viz["traces"]:
            values = viz["traces"][0]["values"]
            assert any(v != 0.0 for v in values), "Trace values must not all be zero"


# --- Regression: Funnel provenance lost (Codex H6) ---

@pytest.mark.regression
class TestFunnelProvenancePreserved:
    """Verify selected candidates preserve funnel stage info.

    Bug: diversity.py overwrote funnel_stage with 'selected', losing
    the original funnel position required by AC #7.
    """

    def test_selection_reason_contains_funnel_stage(self):
        """Selected candidates must record original funnel stage in selection_reason."""
        candidates = [
            RankedCandidate(1, 0.9, 1, 0, True, "pareto", "TOPSIS rank 1"),
            RankedCandidate(2, 0.8, 2, 1, True, "pareto_dominated", "TOPSIS rank 2"),
            RankedCandidate(3, 0.7, 1, 2, True, "pareto", "TOPSIS rank 3"),
        ]
        behavior = {
            1: {"trade_frequency": 100, "win_rate": 0.6},
            2: {"trade_frequency": 200, "win_rate": 0.5},
            3: {"trade_frequency": 50, "win_rate": 0.7},
        }
        dims = [
            BehaviorDimension("trade_frequency", [50, 200, 500], ["low", "med", "high", "vhigh"]),
            BehaviorDimension("win_rate", [0.4, 0.55, 0.7], ["low", "mod", "good", "high"]),
        ]
        archive = build_diversity_archive(candidates, behavior, dims)

        selected = select_diverse_candidates(archive, candidates, 3, 0.8, 42)
        assert len(selected) > 0

        for s in selected:
            assert "funnel:" in s.selection_reason, (
                f"selection_reason must contain original funnel stage, got: {s.selection_reason}"
            )


# --- Regression: Gate failure counts discarded (BMAD M2 + Codex M2) ---

@pytest.mark.regression
class TestGateFailureFromFunnel:
    """Verify gate_failure_summary uses funnel-computed values.

    Bug: Funnel computed gate_failure_counts internally but didn't return
    them. Orchestrator recomputed separately with different logic.
    """

    def test_funnel_returns_gate_failure_counts(self):
        """four_stage_funnel must return gate_failure_counts as 4th element."""
        rng = np.random.default_rng(42)
        n = 10
        table = pa.table({
            "candidate_id": list(range(n)),
            "cv_objective": rng.uniform(0.5, 2.0, n).tolist(),
            "fold_scores": [[rng.uniform(0.3, 2.0) for _ in range(5)] for _ in range(n)],
            "params_json": [json.dumps({"p": float(rng.uniform(0, 100))}) for _ in range(n)],
        })
        quality = [
            EquityCurveQuality(i, rng.uniform(5, 50), rng.uniform(0, 20),
                               rng.uniform(0.1, 0.9), rng.uniform(0.5, 5.0), rng.uniform(0.1, 1.0))
            for i in range(n)
        ]
        clusters = [ClusterAssignment(i, i % 3, False, rng.uniform(0.5, 1.0)) for i in range(n)]
        config = _make_config(stability_threshold=1.0)
        hard_gates = {"dsr_pass_required": False, "pbo_max_threshold": 0.40}

        result = four_stage_funnel(table, quality, clusters, config, hard_gates)
        assert len(result) == 4, f"Expected 4-tuple, got {len(result)}-tuple"

        survivors, stats, weights, gate_counts = result
        assert isinstance(gate_counts, dict)
        assert "dsr" in gate_counts
        assert "pbo" in gate_counts
        assert "cost_stress" in gate_counts

    def test_gate_failures_counted_when_all_fail(self):
        """Gate failure counts must be non-zero when candidates fail gates."""
        n = 5
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
        hard_gates = {"dsr_pass_required": True, "pbo_max_threshold": 0.40}

        _, _, _, gate_counts = four_stage_funnel(
            table, quality, clusters, config, hard_gates, scoring
        )
        assert gate_counts["dsr"] == n, f"Expected {n} DSR failures, got {gate_counts['dsr']}"


# --- Regression: deterministic_ratio=0.0 (Codex M3) ---

@pytest.mark.regression
class TestDeterministicRatioZero:
    """Verify deterministic_ratio=0.0 produces 0 deterministic picks.

    Bug: max(1, int(target * 0.0)) = max(1, 0) = 1, forcing at least
    one deterministic pick even when ratio is explicitly 0.0.
    """

    def test_zero_ratio_all_exploratory(self):
        """deterministic_ratio=0.0 should produce only exploratory picks."""
        candidates = [
            RankedCandidate(i, 0.9 - i * 0.1, 1, i, True, "pareto", f"rank {i}")
            for i in range(5)
        ]
        archive = [
            DiversityCell({"freq": "low"}, 0, 0.9),
            DiversityCell({"freq": "med"}, 1, 0.8),
            DiversityCell({"freq": "high"}, 2, 0.7),
        ]

        selected = select_diverse_candidates(archive, candidates, 3, 0.0, 42)
        assert len(selected) > 0
        # All should be exploratory (not deterministic)
        for s in selected:
            assert "exploratory" in s.selection_reason or "backfill" in s.selection_reason, (
                f"With ratio=0.0, expected exploratory/backfill, got: {s.selection_reason}"
            )


# --- Regression: Behavior data WARNING (BMAD M1 + Codex M1) ---

@pytest.mark.regression
class TestBehaviorDataWarning:
    """Verify WARNING for default behavior values.

    Bug: Behavior data defaults used without any logging, making AC #5
    diversity archive silently degraded.
    """

    def test_default_behavior_produces_warning(self, tmp_path, caplog):
        """Orchestrator must warn when using default behavior values."""
        from selection.orchestrator import SelectionOrchestrator

        candidates_path = tmp_path / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=5)

        orchestrator = SelectionOrchestrator()
        table = orchestrator._load_candidates(candidates_path)

        quality = [
            EquityCurveQuality(i, 10.0, 5.0, 0.5, 2.0, 0.8) for i in range(5)
        ]

        with caplog.at_level(logging.WARNING, logger="selection.orchestrator"):
            behavior = orchestrator._extract_behavior_data(table, quality)

        assert any("default values" in r.message.lower() or "behavior dimensions" in r.message.lower()
                    for r in caplog.records), (
            "Expected WARNING about default behavior values"
        )
