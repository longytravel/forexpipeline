"""Tests for optimization.results (Task 10)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc
import pytest

from optimization.results import (
    CANDIDATES_SCHEMA,
    PROMOTED_SCHEMA,
    StreamingResultsWriter,
    promote_top_candidates,
    write_run_manifest,
)


class TestStreamingResultsWriter:
    def test_streaming_writer_incremental(self, tmp_path: Path):
        """Verify file grows per generation without memory accumulation."""
        output = tmp_path / "results.arrow"
        writer = StreamingResultsWriter(output)

        for gen in range(3):
            n = 10
            writer.append_generation(
                generation=gen,
                candidate_ids=list(range(gen * n, (gen + 1) * n)),
                params_list=[json.dumps({"p": float(i)}) for i in range(n)],
                fold_scores=np.random.RandomState(gen).uniform(0, 1, (n, 3)),
                cv_objectives=np.random.RandomState(gen).uniform(0, 1, n),
                branch="__default__",
                instance_types=["cmaes"] * n,
            )

        path = writer.finalize()
        assert path.exists()

        # Read and verify
        reader = pa.ipc.open_file(str(path))
        table = reader.read_all()
        assert table.num_rows == 30  # 3 generations * 10

    def test_results_arrow_schema_matches_contract(self, tmp_path: Path):
        output = tmp_path / "results.arrow"
        writer = StreamingResultsWriter(output)
        writer.append_generation(
            generation=0,
            candidate_ids=[1],
            params_list=['{"p": 1.0}'],
            fold_scores=np.array([[0.5, 0.6, 0.7]]),
            cv_objectives=np.array([0.5]),
            branch="__default__",
            instance_types=["cmaes"],
        )
        path = writer.finalize()

        reader = pa.ipc.open_file(str(path))
        table = reader.read_all()

        # Verify schema fields match contract
        assert "candidate_id" in table.column_names
        assert "generation" in table.column_names
        assert "branch" in table.column_names
        assert "instance_type" in table.column_names
        assert "params_json" in table.column_names
        assert "cv_objective" in table.column_names
        assert "fold_scores" in table.column_names


class TestPromoteTopCandidates:
    def test_promote_top_n_ordering(self, tmp_path: Path):
        # Create a results file with known scores
        output = tmp_path / "results.arrow"
        writer = StreamingResultsWriter(output)

        n = 50
        scores = np.arange(n, dtype=np.float64)  # 0, 1, 2, ..., 49
        writer.append_generation(
            generation=0,
            candidate_ids=list(range(n)),
            params_list=[json.dumps({"p": float(i)}) for i in range(n)],
            fold_scores=np.random.RandomState(42).uniform(0, 1, (n, 3)),
            cv_objectives=scores,
            branch="__default__",
            instance_types=["cmaes"] * n,
        )
        results_path = writer.finalize()

        # Promote top 10
        promoted_path = promote_top_candidates(results_path, top_n=10)
        assert promoted_path.exists()

        reader = pa.ipc.open_file(str(promoted_path))
        table = reader.read_all()
        assert table.num_rows == 10

        # Verify ordering: best first
        objectives = table.column("cv_objective").to_numpy()
        assert objectives[0] == 49.0  # Best score
        assert np.all(np.diff(objectives) <= 0)  # Descending

        # Verify rank column
        ranks = table.column("rank").to_numpy()
        assert list(ranks) == list(range(1, 11))


class TestRunManifest:
    def test_run_manifest_contains_provenance(self, tmp_path: Path):
        manifest_path = write_run_manifest(
            artifacts_dir=tmp_path,
            dataset_hash="sha256:data123",
            strategy_spec_hash="sha256:spec456",
            config_hash="sha256:config789",
            fold_definitions=[{"fold_id": 0, "train_start": 0, "train_end": 5000}],
            rng_seeds={"master_seed": 42},
            stop_reason="max_generations",
            generation_count=100,
            branch_metadata={"__default__": {"visit_count": 100}},
            total_evaluations=5000,
        )

        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert manifest["dataset_hash"] == "sha256:data123"
        assert manifest["strategy_spec_hash"] == "sha256:spec456"
        assert manifest["config_hash"] == "sha256:config789"
        assert manifest["stop_reason"] == "max_generations"
        assert manifest["generation_count"] == 100
        assert manifest["total_evaluations"] == 5000
        assert "fold_definitions" in manifest
        assert "rng_seeds" in manifest
        assert manifest["rng_seeds"]["master_seed"] == 42
