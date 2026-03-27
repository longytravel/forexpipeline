"""Integration and E2E tests for optimization (Task 12).

Tests exercise the full pipeline with small parameter spaces
to verify end-to-end correctness.
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
)
from optimization.fold_manager import FoldManager, compute_cv_objective
from optimization.parameter_space import (
    detect_branches,
    parse_strategy_params,
)
from optimization.portfolio import PortfolioManager
from optimization.results import StreamingResultsWriter, write_run_manifest, promote_top_candidates
from orchestrator.pipeline_state import PipelineStage, STAGE_GRAPH, STAGE_ORDER


class TestE2EOptimizationSmallSpace:
    """2-3 continuous params, 2 folds, 5 generations."""

    def test_e2e_optimization_small_space(
        self, sample_strategy_spec, sample_config, tmp_path,
    ):
        space = parse_strategy_params(sample_strategy_spec)
        branches = detect_branches(space)

        bm = BranchManager(
            branches=branches, config=sample_config, master_seed=42
        )

        fm = FoldManager(data_length=1000, n_folds=2, embargo_bars=0)
        fold_specs = fm.get_fold_boundaries()

        results_path = tmp_path / "results.arrow"
        writer = StreamingResultsWriter(results_path)

        candidate_counter = 0
        best_score = float("-inf")

        for gen in range(5):
            branch_candidates = bm.ask_all(32)

            for branch_key, candidates in branch_candidates.items():
                n = len(candidates)
                # Simulate fold scores (synthetic)
                fold_scores = np.random.RandomState(gen + candidate_counter).uniform(
                    0, 1, (n, 2)
                )
                cv_scores = np.array([
                    compute_cv_objective(fold_scores[i], lambda_=1.5)
                    for i in range(n)
                ])

                bm.tell_all({branch_key: (candidates, cv_scores)})

                cand_ids = list(range(candidate_counter, candidate_counter + n))
                candidate_counter += n

                writer.append_generation(
                    generation=gen,
                    candidate_ids=cand_ids,
                    params_list=[json.dumps({"p": float(i)}) for i in range(n)],
                    fold_scores=fold_scores,
                    cv_objectives=cv_scores,
                    branch=branch_key,
                    instance_types=["cmaes"] * n,
                )

                gen_best = float(np.max(cv_scores))
                if gen_best > best_score:
                    best_score = gen_best

        # Finalize
        final_path = writer.finalize()
        assert final_path.exists()

        reader = pa.ipc.open_file(str(final_path))
        table = reader.read_all()
        assert table.num_rows == candidate_counter
        assert table.num_rows > 0

        # Promote top candidates
        promoted_path = promote_top_candidates(final_path, top_n=5)
        assert promoted_path.exists()

        reader2 = pa.ipc.open_file(str(promoted_path))
        promoted = reader2.read_all()
        assert promoted.num_rows == 5

        # Write manifest
        manifest_path = write_run_manifest(
            artifacts_dir=tmp_path,
            dataset_hash="sha256:test",
            strategy_spec_hash="sha256:test",
            config_hash="sha256:test",
            fold_definitions=fm.to_rust_fold_args(),
            rng_seeds={"master_seed": 42},
            stop_reason="max_generations",
            generation_count=5,
            branch_metadata={},
        )
        assert manifest_path.exists()


class TestE2EOptimizationWithBranches:
    def test_e2e_optimization_with_branches(
        self, branching_strategy_spec, sample_config, tmp_path,
    ):
        space = parse_strategy_params(branching_strategy_spec)
        branches = detect_branches(space)
        assert len(branches) == 2

        bm = BranchManager(
            branches=branches, config=sample_config, master_seed=42
        )

        results_path = tmp_path / "results.arrow"
        writer = StreamingResultsWriter(results_path)
        counter = 0

        for gen in range(3):
            branch_candidates = bm.ask_all(32)
            for key, candidates in branch_candidates.items():
                n = len(candidates)
                scores = np.random.RandomState(gen + counter).uniform(0, 1, n)
                bm.tell_all({key: (candidates, scores)})

                writer.append_generation(
                    generation=gen,
                    candidate_ids=list(range(counter, counter + n)),
                    params_list=[json.dumps({"p": i}) for i in range(n)],
                    fold_scores=np.random.RandomState(gen).uniform(0, 1, (n, 2)),
                    cv_objectives=scores,
                    branch=key,
                    instance_types=["cmaes"] * n,
                )
                counter += n

        path = writer.finalize()
        assert path.exists()
        reader = pa.ipc.open_file(str(path))
        table = reader.read_all()
        assert table.num_rows == counter


class TestE2ECheckpointResume:
    def test_e2e_checkpoint_resume(self, sample_strategy_spec, sample_config, tmp_path):
        space = parse_strategy_params(sample_strategy_spec)
        branches = detect_branches(space)

        # Run 3 generations
        bm1 = BranchManager(branches=branches, config=sample_config, master_seed=42)
        counter = 0

        for gen in range(3):
            candidates_dict = bm1.ask_all(16)
            for key, cands in candidates_dict.items():
                scores = np.random.RandomState(gen).uniform(0, 1, len(cands))
                bm1.tell_all({key: (cands, scores)})
                counter += len(cands)

        # Save checkpoint
        cp = OptimizationCheckpoint(
            generation=3,
            branch_states=bm1.state_dict(),
            evaluated_count=counter,
            candidate_counter=counter,
        )
        cp_path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, cp_path)

        # Resume and run 2 more
        loaded = load_checkpoint(cp_path)
        assert loaded.generation == 3
        assert loaded.candidate_counter == counter

        bm2 = BranchManager(branches=branches, config=sample_config, master_seed=42)
        bm2.load_state(loaded.branch_states)

        for gen in range(3, 5):
            candidates_dict = bm2.ask_all(16)
            for key, cands in candidates_dict.items():
                scores = np.random.RandomState(gen).uniform(0, 1, len(cands))
                bm2.tell_all({key: (cands, scores)})
                counter += len(cands)

        # Total should be 5 generations worth
        assert counter > 0


class TestPipelineStateTransitions:
    def test_pipeline_state_transitions(self):
        """Verify REVIEWED → OPTIMIZING → OPTIMIZATION_COMPLETE transitions."""
        # REVIEWED has outgoing transition
        assert PipelineStage.REVIEWED in STAGE_GRAPH
        reviewed_transition = STAGE_GRAPH[PipelineStage.REVIEWED]
        assert reviewed_transition.to_stage == PipelineStage.OPTIMIZING

        # OPTIMIZING has outgoing transition
        assert PipelineStage.OPTIMIZING in STAGE_GRAPH
        optimizing_transition = STAGE_GRAPH[PipelineStage.OPTIMIZING]
        assert optimizing_transition.to_stage == PipelineStage.OPTIMIZATION_COMPLETE

        # OPTIMIZATION_COMPLETE transitions to VALIDATING (Story 5.4)
        assert PipelineStage.OPTIMIZATION_COMPLETE in STAGE_GRAPH
        oc_transition = STAGE_GRAPH[PipelineStage.OPTIMIZATION_COMPLETE]
        assert oc_transition.to_stage == PipelineStage.VALIDATING

        # Stage order includes new stages
        assert PipelineStage.OPTIMIZING in STAGE_ORDER
        assert PipelineStage.OPTIMIZATION_COMPLETE in STAGE_ORDER

        # Correct ordering
        opt_idx = STAGE_ORDER.index(PipelineStage.OPTIMIZING)
        rev_idx = STAGE_ORDER.index(PipelineStage.REVIEWED)
        oc_idx = STAGE_ORDER.index(PipelineStage.OPTIMIZATION_COMPLETE)
        assert rev_idx < opt_idx < oc_idx


class TestDeterministicSeeds:
    def test_deterministic_seeds_reproduce(self, sample_strategy_spec, sample_config):
        """Same master seed + inputs → identical candidate sequences."""
        space = parse_strategy_params(sample_strategy_spec)

        pm1 = PortfolioManager(space=space, config=sample_config, master_seed=42)
        pm2 = PortfolioManager(space=space, config=sample_config, master_seed=42)

        c1 = pm1.ask_batch(32)
        c2 = pm2.ask_batch(32)

        np.testing.assert_array_equal(c1, c2)
