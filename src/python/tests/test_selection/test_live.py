"""Live integration tests for candidate selection pipeline (Story 5.6).

These tests exercise REAL system behavior:
- Write real Arrow IPC candidates to disk
- Run full selection pipeline end-to-end
- Verify actual output files exist on disk
- Validate data content, not just code ran without errors
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from selection.executor import SelectionExecutor
from selection.models import SelectionManifest


def _selection_config() -> dict:
    return {
        "selection": {
            "min_cluster_size": 3,
            "hdbscan_min_samples": 2,
            "topsis_top_n": 30,
            "stability_threshold": 1.0,
            "target_candidates": 8,
            "deterministic_ratio": 0.8,
            "diversity_dimensions": ["trade_frequency", "avg_holding_time", "win_rate", "max_drawdown"],
            "max_clustering_candidates": 5000,
            "random_seed": 42,
        },
        "hard_gates": {
            "dsr_pass_required": False,
            "pbo_max_threshold": 0.40,
            "cost_stress_survival_multiplier": 1.5,
        },
    }


def _write_realistic_candidates(path: Path, n: int = 100) -> None:
    """Write realistic synthetic candidates mimicking optimization output."""
    rng = np.random.default_rng(42)

    # Simulate 3 distinct parameter clusters
    cluster_centers = [
        {"fast": 10, "slow": 50, "atr_mult": 1.5},
        {"fast": 25, "slow": 100, "atr_mult": 2.0},
        {"fast": 40, "slow": 150, "atr_mult": 3.0},
    ]

    candidate_ids = []
    params_jsons = []
    cv_objectives = []
    fold_scores_list = []
    ranks = []

    for i in range(n):
        center = cluster_centers[i % 3]
        params = {
            "fast_period": float(center["fast"] + rng.normal(0, 3)),
            "slow_period": float(center["slow"] + rng.normal(0, 8)),
            "atr_multiplier": float(center["atr_mult"] + rng.normal(0, 0.3)),
            "sl_pips": float(rng.uniform(20, 80)),
        }
        candidate_ids.append(i)
        params_jsons.append(json.dumps(params))
        cv_obj = float(rng.uniform(0.3, 2.5))
        cv_objectives.append(cv_obj)
        fold_scores_list.append([float(cv_obj + rng.normal(0, 0.3)) for _ in range(5)])
        ranks.append(i)

    table = pa.table({
        "candidate_id": candidate_ids,
        "rank": ranks,
        "params_json": params_jsons,
        "cv_objective": cv_objectives,
        "fold_scores": fold_scores_list,
        "branch": ["cmaes"] * n,
        "instance_type": ["CMAESInstance"] * n,
    })

    path.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_file(str(path), table.schema) as writer:
        writer.write_table(table)


@pytest.mark.live
class TestLiveFullSelectionPipeline:
    """Live integration: full selection pipeline end-to-end."""

    def test_live_full_pipeline_produces_manifest(self, tmp_path):
        """Full pipeline: candidates.arrow → selection manifest + viz data on disk."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_realistic_candidates(candidates_path, n=100)
        version_dir = tmp_path / "ma_crossover" / "v001"

        executor = SelectionExecutor(_selection_config())
        result = executor.execute("ma_crossover", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "live_opt_run_001",
            "version_dir": str(version_dir),
        })

        # Verify execution succeeded
        assert result.outcome == "success", f"Executor failed: {result.metrics}"

        # Verify manifest file exists on disk
        manifest_path = Path(result.manifest_ref)
        assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
        assert manifest_path.stat().st_size > 0, "Manifest is empty"

        # Verify manifest content is valid JSON with correct schema
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["strategy_id"] == "ma_crossover"
        assert data["optimization_run_id"] == "live_opt_run_001"
        assert 1 <= len(data["selected_candidates"]) <= 8
        assert data["random_seed_used"] == 42
        assert data["config_hash"].startswith("sha256:")

        # Verify upstream refs have real content
        refs = data["upstream_refs"]
        assert refs["candidates_path"] == str(candidates_path)
        assert refs["candidates_hash"].startswith("sha256:")
        assert len(refs["candidates_hash"]) > 10

        # Verify funnel stats are consistent
        stats = data["funnel_stats"]
        assert stats["total_input"] > 0
        assert stats["after_hard_gates"] <= stats["total_input"]
        assert stats["final_selected"] == len(data["selected_candidates"])

        # Verify clusters have valid content
        assert len(data["clusters"]) > 0
        for cluster in data["clusters"]:
            assert cluster["size"] > 0
            assert isinstance(cluster["centroid_params"], dict)
            assert len(cluster["centroid_params"]) > 0

        # Verify CRITIC weights were computed (not hardcoded)
        assert len(data["critic_weights"]) > 0
        total_weight = sum(data["critic_weights"].values())
        assert abs(total_weight - 1.0) < 0.01, f"CRITIC weights don't sum to 1: {total_weight}"

    def test_live_viz_data_output(self, tmp_path):
        """Visualization data files are written to disk with valid content."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_realistic_candidates(candidates_path, n=60)
        version_dir = tmp_path / "ma_crossover" / "v001"

        executor = SelectionExecutor(_selection_config())
        result = executor.execute("ma_crossover", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "live_opt_run_002",
            "version_dir": str(version_dir),
        })

        assert result.outcome == "success"

        # Verify viz directory and files exist on disk
        viz_dir = version_dir / "selection" / "viz"
        assert viz_dir.exists(), f"Viz directory not found at {viz_dir}"

        viz_files = list(viz_dir.glob("*.json"))
        assert len(viz_files) >= 3, f"Expected >= 3 viz files, got {len(viz_files)}: {viz_files}"

        # Validate each viz file is valid JSON with content
        for vf in viz_files:
            with open(vf) as f:
                viz_data = json.load(f)
            assert isinstance(viz_data, dict), f"{vf.name} is not a dict"

        # Check parallel coordinates has traces
        pc_path = viz_dir / "parallel_coordinates.json"
        if pc_path.exists():
            with open(pc_path) as f:
                pc = json.load(f)
            assert "traces" in pc
            assert "axes" in pc

        # Check parameter heatmap has matrix
        hm_path = viz_dir / "parameter_heatmap.json"
        if hm_path.exists():
            with open(hm_path) as f:
                hm = json.load(f)
            assert "cluster_ids" in hm
            assert "param_names" in hm
            assert "matrix" in hm

    def test_live_deterministic_reproducibility(self, tmp_path):
        """Same input + same seed → identical output (excluding timestamp)."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_realistic_candidates(candidates_path, n=50)

        config = _selection_config()

        # Run 1
        dir1 = tmp_path / "run1" / "v001"
        executor1 = SelectionExecutor(config)
        result1 = executor1.execute("test_strat", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "determinism_test",
            "version_dir": str(dir1),
        })

        # Run 2
        dir2 = tmp_path / "run2" / "v001"
        executor2 = SelectionExecutor(config)
        result2 = executor2.execute("test_strat", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "determinism_test",
            "version_dir": str(dir2),
        })

        assert result1.outcome == "success"
        assert result2.outcome == "success"

        with open(result1.manifest_ref) as f:
            data1 = json.load(f)
        with open(result2.manifest_ref) as f:
            data2 = json.load(f)

        # Remove timestamp for comparison
        data1.pop("selected_at")
        data2.pop("selected_at")
        # Paths will differ
        data1["upstream_refs"].pop("candidates_path")
        data2["upstream_refs"].pop("candidates_path")

        assert data1 == data2, "Deterministic reproducibility failed — runs differ"
