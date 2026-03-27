"""Live integration tests for optimization (Story 5.3).

These tests exercise REAL system behavior — creating actual optimization
artifacts on disk, running real algorithm instances, and verifying outputs.

Run with: pytest -m live tests/test_optimization/test_live_optimization.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc
import pytest

from optimization.branch_manager import BranchManager
from optimization.checkpoint import (
    OptimizationCheckpoint,
    load_checkpoint,
    save_checkpoint,
    should_checkpoint,
)
from optimization.fold_manager import FoldManager, compute_cv_objective
from optimization.parameter_space import (
    ParameterSpace,
    ParameterSpec,
    ParamType,
    decode_candidate,
    detect_branches,
    parse_strategy_params,
    to_cmaes_bounds,
)
from optimization.portfolio import PortfolioManager
from optimization.results import (
    StreamingResultsWriter,
    promote_top_candidates,
    write_run_manifest,
)


def _make_strategy_spec() -> dict:
    """Build a realistic strategy spec for live testing."""
    return {
        "metadata": {
            "schema_version": "1",
            "name": "live-test-strategy",
            "version": "v001",
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "live-test",
        },
        "optimization_plan": {
            "schema_version": 2,
            "parameters": {
                "entry.sma_fast": {
                    "type": "integer",
                    "min": 5,
                    "max": 50,
                    "step": 1,
                },
                "entry.sma_slow": {
                    "type": "integer",
                    "min": 20,
                    "max": 200,
                    "step": 1,
                },
                "exit.stop_loss": {
                    "type": "continuous",
                    "min": 10.0,
                    "max": 100.0,
                },
                "exit.take_profit": {
                    "type": "continuous",
                    "min": 20.0,
                    "max": 200.0,
                },
            },
            "objective_function": "sharpe",
        },
    }


def _make_config() -> dict:
    """Build optimization config for live tests (small scale)."""
    return {
        "optimization": {
            "batch_size": 48,
            "max_generations": 5,
            "checkpoint_interval_generations": 2,
            "cv_lambda": 1.5,
            "cv_folds": 3,
            "convergence_tolfun": 1e-3,
            "stagnation_generations": 50,
            "memory_budget_mb": 2048,
            "sobol_fraction": 0.1,
            "ucb1_exploration": 1.414,
            "portfolio": {
                "cmaes_instances": 2,
                "de_instances": 1,
                "cmaes_pop_base": 16,
                "de_pop_base": 16,
                "pop_scaling_factor": 5,
                "min_pop": 16,
            },
        },
        "pipeline": {
            "artifacts_dir": "artifacts",
            "checkpoint_enabled": True,
            "config_hash": "sha256:livetest",
        },
    }


@pytest.mark.live
class TestLiveFullOptimizationLoop:
    """End-to-end optimization loop writing real artifacts to disk."""

    def test_live_full_optimization_loop(self, tmp_path: Path):
        """Run a full optimization loop and verify all output artifacts."""
        spec = _make_strategy_spec()
        config = _make_config()

        # Parse and branch
        space = parse_strategy_params(spec)
        assert space.n_dims == 4

        branches = detect_branches(space)
        assert "__default__" in branches

        bm = BranchManager(branches=branches, config=config, master_seed=42)
        fm = FoldManager(data_length=5000, n_folds=3, embargo_bars=50)
        fold_specs = fm.get_fold_boundaries()
        assert len(fold_specs) == 3

        # Streaming results writer
        results_path = tmp_path / "optimization-results.arrow"
        writer = StreamingResultsWriter(results_path)

        candidate_counter = 0
        best_score = float("-inf")
        best_params = {}

        for gen in range(5):
            branch_candidates = bm.ask_all(48)

            for branch_key, candidates in branch_candidates.items():
                n = len(candidates)

                # Simulate realistic fold-aware scoring
                rng = np.random.RandomState(gen * 1000 + candidate_counter)
                fold_scores = rng.uniform(-0.5, 2.0, (n, 3))
                cv_scores = np.array([
                    compute_cv_objective(fold_scores[i], lambda_=1.5)
                    for i in range(n)
                ])

                bm.tell_all({branch_key: (candidates, cv_scores)})

                # Generate stable candidate IDs
                cand_ids = list(range(candidate_counter, candidate_counter + n))
                candidate_counter += n

                branch_space = branches.get(branch_key, space)
                params_list = [
                    json.dumps(decode_candidate(c, branch_space))
                    for c in candidates
                ]

                writer.append_generation(
                    generation=gen,
                    candidate_ids=cand_ids,
                    params_list=params_list,
                    fold_scores=fold_scores,
                    cv_objectives=cv_scores,
                    branch=branch_key,
                    instance_types=["cmaes"] * n,
                )

                gen_best_idx = int(np.argmax(cv_scores))
                gen_best_score = float(cv_scores[gen_best_idx])
                if gen_best_score > best_score:
                    best_score = gen_best_score
                    best_params = decode_candidate(candidates[gen_best_idx], branch_space)

            # Checkpoint at interval
            if should_checkpoint(gen, 2):
                cp = OptimizationCheckpoint(
                    generation=gen + 1,
                    branch_states=bm.state_dict(),
                    best_candidates=[best_params],
                    evaluated_count=candidate_counter,
                    config_hash="sha256:livetest",
                    master_seed=42,
                    candidate_counter=candidate_counter,
                )
                save_checkpoint(cp, tmp_path / "checkpoint.json")

        # Finalize results
        final_path = writer.finalize()

        # VERIFY: Results file exists and has correct content
        assert final_path.exists()
        assert final_path.stat().st_size > 0

        reader = pa.ipc.open_file(str(final_path))
        table = reader.read_all()
        assert table.num_rows == candidate_counter
        assert table.num_rows > 0

        # Verify schema columns
        assert "candidate_id" in table.column_names
        assert "generation" in table.column_names
        assert "cv_objective" in table.column_names
        assert "fold_scores" in table.column_names
        assert "params_json" in table.column_names

        # Verify candidate IDs are monotonic
        ids = table.column("candidate_id").to_numpy()
        assert np.all(np.diff(ids) > 0) or len(ids) == 1

        # Verify generations are present
        gens = table.column("generation").to_numpy()
        assert set(gens) == {0, 1, 2, 3, 4}

        # Promote top candidates
        promoted_path = promote_top_candidates(final_path, top_n=10)
        assert promoted_path.exists()

        promoted_reader = pa.ipc.open_file(str(promoted_path))
        promoted_table = promoted_reader.read_all()
        assert promoted_table.num_rows == 10

        # Verify promoted are sorted descending by objective
        objectives = promoted_table.column("cv_objective").to_numpy()
        assert np.all(np.diff(objectives) <= 1e-10)  # Descending

        # Write run manifest
        manifest_path = write_run_manifest(
            artifacts_dir=tmp_path,
            dataset_hash="sha256:livedata",
            strategy_spec_hash="sha256:livestrategy",
            config_hash="sha256:livetest",
            fold_definitions=fm.to_rust_fold_args(),
            rng_seeds={"master_seed": 42},
            stop_reason="max_generations",
            generation_count=5,
            branch_metadata={"__default__": {"visit_count": 5}},
            total_evaluations=candidate_counter,
        )
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["generation_count"] == 5
        assert manifest["total_evaluations"] == candidate_counter
        assert manifest["rng_seeds"]["master_seed"] == 42

        # Checkpoint exists and is valid
        cp_path = tmp_path / "checkpoint.json"
        assert cp_path.exists()
        loaded_cp = load_checkpoint(cp_path)
        assert loaded_cp.generation > 0


@pytest.mark.live
class TestLiveCheckpointResumeIntegrity:
    """Verify checkpoint resume produces consistent state."""

    def test_live_checkpoint_resume_integrity(self, tmp_path: Path):
        spec = _make_strategy_spec()
        config = _make_config()
        space = parse_strategy_params(spec)
        branches = detect_branches(space)

        # Phase 1: Run 3 generations
        bm1 = BranchManager(branches=branches, config=config, master_seed=42)
        counter = 0

        for gen in range(3):
            cands = bm1.ask_all(32)
            for key, c in cands.items():
                scores = np.random.RandomState(gen + counter).uniform(0, 1, len(c))
                bm1.tell_all({key: (c, scores)})
                counter += len(c)

        # Save checkpoint
        cp = OptimizationCheckpoint(
            generation=3,
            branch_states=bm1.state_dict(),
            evaluated_count=counter,
            candidate_counter=counter,
            master_seed=42,
        )
        cp_path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, cp_path)

        # VERIFY: checkpoint file on disk
        assert cp_path.exists()
        assert cp_path.stat().st_size > 100  # Non-trivial content

        # No .partial file left
        partial = cp_path.with_name(cp_path.name + ".partial")
        assert not partial.exists()

        # Phase 2: Resume
        loaded = load_checkpoint(cp_path)
        assert loaded.generation == 3
        assert loaded.candidate_counter == counter

        bm2 = BranchManager(branches=branches, config=config, master_seed=42)
        bm2.load_state(loaded.branch_states)

        # Run 2 more generations
        for gen in range(3, 5):
            cands = bm2.ask_all(32)
            for key, c in cands.items():
                scores = np.random.RandomState(gen + counter).uniform(0, 1, len(c))
                bm2.tell_all({key: (c, scores)})
                counter += len(c)

        # Save final checkpoint
        cp2 = OptimizationCheckpoint(
            generation=5,
            branch_states=bm2.state_dict(),
            evaluated_count=counter,
            candidate_counter=counter,
        )
        cp2_path = tmp_path / "checkpoint-final.json"
        save_checkpoint(cp2, cp2_path)

        loaded2 = load_checkpoint(cp2_path)
        assert loaded2.generation == 5
        assert loaded2.candidate_counter == counter
        assert loaded2.evaluated_count == counter


@pytest.mark.live
class TestLiveResultsArtifactVerification:
    """Verify all optimization artifacts are valid on disk."""

    def test_live_results_artifact_on_disk(self, tmp_path: Path):
        """Write results + manifest + promoted candidates, verify all exist."""
        results_path = tmp_path / "results.arrow"
        writer = StreamingResultsWriter(results_path)

        total = 0
        for gen in range(10):
            n = 20
            rng = np.random.RandomState(gen)
            writer.append_generation(
                generation=gen,
                candidate_ids=list(range(total, total + n)),
                params_list=[json.dumps({"sma": rng.randint(5, 50)}) for _ in range(n)],
                fold_scores=rng.uniform(0, 2, (n, 5)),
                cv_objectives=rng.uniform(0, 1, n),
                branch="__default__",
                instance_types=["cmaes"] * n,
            )
            total += n

        final = writer.finalize()

        # Artifact 1: Results file
        assert final.exists()
        reader = pa.ipc.open_file(str(final))
        table = reader.read_all()
        assert table.num_rows == 200
        assert "candidate_id" in table.column_names
        assert "cv_objective" in table.column_names
        assert "fold_scores" in table.column_names

        # Artifact 2: Promoted candidates
        promoted = promote_top_candidates(final, top_n=20)
        assert promoted.exists()
        p_reader = pa.ipc.open_file(str(promoted))
        p_table = p_reader.read_all()
        assert p_table.num_rows == 20
        assert "rank" in p_table.column_names
        ranks = p_table.column("rank").to_numpy()
        assert list(ranks) == list(range(1, 21))

        # Artifact 3: Run manifest
        manifest = write_run_manifest(
            artifacts_dir=tmp_path,
            dataset_hash="sha256:abc",
            strategy_spec_hash="sha256:def",
            config_hash="sha256:ghi",
            fold_definitions=[{"fold_id": i} for i in range(5)],
            rng_seeds={"master_seed": 42, "instances": [42, 43, 44]},
            stop_reason="max_generations",
            generation_count=10,
            branch_metadata={"__default__": {"visit_count": 10, "best_score": 0.95}},
            total_evaluations=200,
        )
        assert manifest.exists()

        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["dataset_hash"] == "sha256:abc"
        assert data["strategy_spec_hash"] == "sha256:def"
        assert data["config_hash"] == "sha256:ghi"
        assert data["generation_count"] == 10
        assert data["total_evaluations"] == 200
        assert len(data["fold_definitions"]) == 5
        assert data["rng_seeds"]["master_seed"] == 42
        assert data["stop_reason"] == "max_generations"
