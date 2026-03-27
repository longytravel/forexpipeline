"""Tests for selection executor and pipeline integration (Story 5.6, Task 9)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from orchestrator.pipeline_state import (
    PipelineStage,
    STAGE_GRAPH,
    STAGE_ORDER,
    TransitionType,
)
from selection.executor import SelectionExecutor
from selection.models import SelectionManifest


def _selection_config_dict() -> dict:
    return {
        "selection": {
            "min_cluster_size": 3,
            "hdbscan_min_samples": 2,
            "topsis_top_n": 20,
            "stability_threshold": 1.0,
            "target_candidates": 5,
            "deterministic_ratio": 0.8,
            "diversity_dimensions": ["trade_frequency", "win_rate"],
            "max_clustering_candidates": 5000,
            "random_seed": 42,
        },
        "hard_gates": {
            "dsr_pass_required": False,
            "pbo_max_threshold": 0.40,
            "cost_stress_survival_multiplier": 1.5,
        },
    }


def _write_synthetic_candidates(path: Path, n: int = 30) -> None:
    """Write a synthetic candidates.arrow file."""
    rng = np.random.default_rng(42)
    table = pa.table({
        "candidate_id": list(range(n)),
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


class TestSelectionExecutorStage:
    def test_selection_executor_stage_registration(self):
        """SelectionExecutor has correct stage attribute for pipeline discovery."""
        assert SelectionExecutor.stage == PipelineStage.SELECTING

    def test_selecting_stage_exists_in_enum(self):
        """SELECTING and SELECTION_COMPLETE stages exist in PipelineStage."""
        assert PipelineStage.SELECTING.value == "selecting"
        assert PipelineStage.SELECTION_COMPLETE.value == "selection-complete"

    def test_selecting_stage_in_stage_graph(self):
        """SELECTING has a transition defined in STAGE_GRAPH."""
        assert PipelineStage.SELECTING in STAGE_GRAPH
        transition = STAGE_GRAPH[PipelineStage.SELECTING]
        assert transition.to_stage == PipelineStage.SELECTION_COMPLETE
        assert transition.transition_type == TransitionType.AUTOMATIC

    def test_scoring_complete_transitions_to_selecting(self):
        """SCORING_COMPLETE → SELECTING transition exists."""
        assert PipelineStage.SCORING_COMPLETE in STAGE_GRAPH
        transition = STAGE_GRAPH[PipelineStage.SCORING_COMPLETE]
        assert transition.to_stage == PipelineStage.SELECTING

    def test_selection_complete_is_gated(self):
        """SELECTION_COMPLETE is a gated stage — operator reviews selections."""
        transition = STAGE_GRAPH[PipelineStage.SELECTION_COMPLETE]
        assert transition.transition_type == TransitionType.GATED


class TestSelectionExecutorEndToEnd:
    def test_selection_executor_end_to_end(self, tmp_path):
        """Synthetic candidates → full pipeline → manifest output."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=30)
        version_dir = tmp_path / "strategy_test" / "v001"

        config = _selection_config_dict()
        executor = SelectionExecutor(config)

        result = executor.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(version_dir),
        })

        assert result.outcome == "success"
        assert result.artifact_path is not None

        # Verify manifest file exists
        manifest_path = Path(result.manifest_ref)
        assert manifest_path.exists()

        # Verify manifest content
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["strategy_id"] == "test_strategy"
        assert data["optimization_run_id"] == "opt_run_001"
        assert len(data["selected_candidates"]) > 0
        assert len(data["selected_candidates"]) <= 5
        assert data["random_seed_used"] == 42

    def test_selection_executor_crash_safe_write(self, tmp_path):
        """Verify no partial files remain after successful write."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=20)
        version_dir = tmp_path / "strategy_test" / "v001"

        config = _selection_config_dict()
        executor = SelectionExecutor(config)
        executor.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(version_dir),
        })

        # No .partial files should remain
        selection_dir = version_dir / "selection"
        partial_files = list(selection_dir.rglob("*.partial"))
        assert partial_files == []

    def test_selection_executor_missing_scoring(self, tmp_path):
        """Graceful fallback without confidence scores."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=20)
        version_dir = tmp_path / "strategy_test" / "v001"

        config = _selection_config_dict()
        executor = SelectionExecutor(config)

        result = executor.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(version_dir),
            "scoring_manifest_path": "/nonexistent/path/manifest.json",
        })

        assert result.outcome == "success"


class TestSelectionManifestSchema:
    def test_selection_manifest_schema_complete(self, tmp_path):
        """All required fields populated in manifest including provenance."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=20)
        version_dir = tmp_path / "strategy_test" / "v001"

        config = _selection_config_dict()
        executor = SelectionExecutor(config)
        result = executor.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(version_dir),
        })

        with open(result.manifest_ref) as f:
            data = json.load(f)

        required = [
            "strategy_id", "optimization_run_id", "selected_candidates",
            "clusters", "diversity_archive", "funnel_stats", "config_hash",
            "selected_at", "upstream_refs", "critic_weights",
            "gate_failure_summary", "random_seed_used",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

        # Validate upstream_refs are populated
        refs = data["upstream_refs"]
        assert refs["candidates_path"]
        assert refs["candidates_hash"].startswith("sha256:")

    def test_selection_deterministic_rerun(self, tmp_path):
        """Same inputs + same seed → identical manifest (excluding selected_at)."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=20)

        config = _selection_config_dict()

        # Run 1
        dir1 = tmp_path / "run1" / "v001"
        executor1 = SelectionExecutor(config)
        result1 = executor1.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(dir1),
        })

        # Run 2
        dir2 = tmp_path / "run2" / "v001"
        executor2 = SelectionExecutor(config)
        result2 = executor2.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(dir2),
        })

        with open(result1.manifest_ref) as f:
            data1 = json.load(f)
        with open(result2.manifest_ref) as f:
            data2 = json.load(f)

        # Everything except selected_at should be identical
        data1.pop("selected_at")
        data2.pop("selected_at")
        assert data1 == data2

    def test_selection_manifest_upstream_refs_populated(self, tmp_path):
        """candidates_path and candidates_hash are non-empty in manifest."""
        candidates_path = tmp_path / "optimization" / "candidates.arrow"
        _write_synthetic_candidates(candidates_path, n=15)
        version_dir = tmp_path / "strategy_test" / "v001"

        config = _selection_config_dict()
        executor = SelectionExecutor(config)
        result = executor.execute("test_strategy", {
            "candidates_path": str(candidates_path),
            "optimization_run_id": "opt_run_001",
            "version_dir": str(version_dir),
        })

        with open(result.manifest_ref) as f:
            data = json.load(f)

        refs = data["upstream_refs"]
        assert refs["candidates_path"] != ""
        assert refs["candidates_hash"] != ""
        assert refs["candidates_hash"].startswith("sha256:")
