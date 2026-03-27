"""Main optimization orchestrator (Story 5.3, AC #1-#16).

Manages the full optimization loop: parse params, create branches,
dispatch batches, compute CV objectives, checkpoint, and write results.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from logging_setup.setup import get_logger
from optimization.batch_dispatch import OptimizationBatchDispatcher, PersistentBatchDispatcher
from optimization.branch_manager import BranchManager
from optimization.checkpoint import (
    OptimizationCheckpoint,
    load_checkpoint,
    save_checkpoint,
    should_checkpoint,
    validate_checkpoint_config,
)
from optimization.fold_manager import FoldManager, compute_cv_objective
from optimization.param_classifier import (
    ParamClassification,
    build_override_spec,
    classify_params,
    compute_group_hash,
    compute_signal_hash,
    write_toml_spec,
)
from optimization.parameter_space import (
    ParameterSpace,
    decode_candidate,
    detect_branches,
    extract_params_by_indices,
    parse_strategy_params,
)
from optimization.results import (
    StreamingResultsWriter,
    promote_top_candidates,
    write_run_manifest,
)
from optimization.prescreener import PreScreener
from optimization.signal_cache import SignalCacheManager
from rust_bridge.batch_runner import BatchRunner

logger = get_logger("optimization.orchestrator")


@dataclass
class PostOptimizationValidation:
    """Results from post-optimization validation gauntlet + confidence scoring."""
    gauntlet_output_dir: Path | None = None
    scoring_manifest_path: Path | None = None
    n_candidates_validated: int = 0
    n_green: int = 0
    n_yellow: int = 0
    n_red: int = 0
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class OptimizationResult:
    """Result of an optimization run."""
    best_candidates: list = field(default_factory=list)
    all_candidates_path: Path | None = None
    promoted_candidates_path: Path | None = None
    run_manifest_path: Path | None = None
    generations_run: int = 0
    total_evaluations: int = 0
    convergence_reached: bool = False
    stop_reason: str = ""
    validation: PostOptimizationValidation | None = None


@dataclass
class _CandidateGroup:
    """Internal grouping of candidates by entry-param hash."""
    group_hash: str
    signal_hash: str
    signal_params: dict
    spec_override_params: dict
    candidate_indices: list[int]
    candidate_rows: list  # list of np.ndarray rows


class OptimizationOrchestrator:
    """Orchestrates portfolio-based optimization with CV-inside-objective."""

    def __init__(
        self,
        strategy_spec: dict,
        market_data_path: Path,
        cost_model_path: Path,
        config: dict,
        artifacts_dir: Path,
        batch_runner: BatchRunner,
    ):
        self._strategy_spec = strategy_spec
        self._market_data_path = market_data_path
        self._cost_model_path = cost_model_path
        self._config = config
        self._artifacts_dir = artifacts_dir
        self._batch_runner = batch_runner

        opt = config.get("optimization", {})
        self._batch_size = opt.get("batch_size", 2048)
        self._max_generations = opt.get("max_generations", 500)
        self._checkpoint_interval = opt.get("checkpoint_interval_generations", 10)
        self._cv_lambda = opt.get("cv_lambda", 1.5)
        self._cv_folds = opt.get("cv_folds", 5)
        self._embargo_bars = opt.get("embargo_bars", 0)
        self._master_seed = opt.get("master_seed", 42)
        self._use_manifest_dispatch = opt.get("use_manifest_dispatch", True)
        self._use_persistent_worker = opt.get("use_persistent_worker", False)
        self._worker_pool = None  # initialized in run() if persistent mode

        if self._use_persistent_worker:
            # Deferred: WorkerPool created in run() after we know enriched paths
            self._dispatcher = None  # type: ignore[assignment]
        else:
            self._dispatcher = OptimizationBatchDispatcher(
                batch_runner=batch_runner,
                artifacts_dir=artifacts_dir,
                config=config,
            )

    async def run(self, resume_from: Path | None = None) -> OptimizationResult:
        """Execute the main optimization loop.

        Args:
            resume_from: Path to checkpoint file for resuming.

        Returns:
            OptimizationResult with paths to all output artifacts.
        """
        start_time = time.monotonic()

        # 1. Parse parameter space
        space = parse_strategy_params(self._strategy_spec)

        # 2. Detect branches, create BranchManager
        branches = detect_branches(space)
        branch_manager = BranchManager(
            branches=branches,
            config=self._config,
            master_seed=self._master_seed,
        )

        # 2b. Extract year_range from optimization_plan (optional)
        opt_plan = self._strategy_spec.get("optimization_plan", {})
        year_range_raw = opt_plan.get("year_range")
        year_range: tuple[int, int] | None = None
        if year_range_raw is not None:
            year_range = (int(year_range_raw[0]), int(year_range_raw[1]))
            logger.info(
                f"Year-range filter active: [{year_range[0]}, {year_range[1]}]",
                extra={"component": "optimization.orchestrator"},
            )

        # 3. Create FoldManager
        data_length = self._estimate_data_length(year_range=year_range)
        fold_manager = FoldManager(
            data_length=data_length,
            n_folds=self._cv_folds,
            embargo_bars=self._embargo_bars,
        )
        fold_specs = fold_manager.get_fold_boundaries()

        # 3b. Classify parameters and set up signal cache for joint optimization.
        #     Signal-affecting params (entry indicators) trigger per-group
        #     enriched data precompute. Batch params (exit rules) vary per
        #     candidate via Rust's param_batch. Spec-override params get
        #     per-group TOML specs.
        classification = classify_params(self._strategy_spec, space)
        data_hash = self._compute_data_hash()

        signal_cache_config = self._config.get("optimization", {}).get(
            "signal_cache", {}
        )
        signal_cache = SignalCacheManager(
            cache_dir=self._artifacts_dir / "signal_cache",
            strategy_spec=self._strategy_spec,
            market_data_path=self._market_data_path,
            data_hash=data_hash,
            classification=classification,
            session_schedule=self._config.get("sessions"),
            max_entries=signal_cache_config.get("max_entries", 1024),
            max_cache_bytes=signal_cache_config.get(
                "max_cache_bytes", 80_000_000_000
            ),
            parallelism=signal_cache_config.get("parallelism", 4),
            log_stats_interval=signal_cache_config.get("log_stats_interval", 10),
            year_range=year_range,
        )
        self._signal_cache = signal_cache
        self._classification = classification

        # 4. Initialize persistent worker pool if configured
        if self._use_persistent_worker:
            from rust_bridge.worker_client import WorkerPool

            pw_config = self._config.get("optimization", {})
            import os
            n_workers = pw_config.get("persistent_workers", min(os.cpu_count() or 4, 8))
            eval_timeout = pw_config.get("persistent_eval_timeout", 120.0)

            # Worker binary is forex_worker, not forex_backtester
            worker_binary = self._batch_runner._binary_path.parent / (
                "forex_worker" + self._batch_runner._binary_path.suffix
            )
            self._worker_pool = WorkerPool(
                binary_path=worker_binary,
                cost_model_path=self._cost_model_path,
                n_workers=n_workers,
                memory_budget_mb=pw_config.get("memory_budget_mb", 5632),
                eval_timeout=eval_timeout,
            )
            await self._worker_pool.start()

            self._dispatcher = PersistentBatchDispatcher(
                worker_pool=self._worker_pool,
                artifacts_dir=self._artifacts_dir,
                config=self._config,
            )
            logger.info(
                f"Using persistent worker pool ({n_workers} workers)",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {"n_workers": n_workers, "eval_timeout": eval_timeout},
                },
            )

        # 4b. Memory preflight check
        ok, adjusted_batch = self._dispatcher.check_memory(
            self._batch_size, len(fold_specs)
        )
        if not ok:
            self._batch_size = adjusted_batch
            logger.warning(
                f"Batch size adjusted to {adjusted_batch} due to memory constraints",
                extra={"component": "optimization.orchestrator"},
            )

        # 5. Resume from checkpoint if available
        generation = 0
        candidate_counter = 0
        total_evaluations = 0
        elapsed_prior = 0.0
        best_candidates: list[dict] = []
        best_score = float("-inf")

        current_config_hash = self._config.get("pipeline", {}).get("config_hash", "")

        if resume_from is not None and resume_from.exists():
            cp = load_checkpoint(resume_from)
            if not validate_checkpoint_config(cp, current_config_hash):
                logger.warning(
                    "Config changed since checkpoint — starting fresh",
                    extra={"component": "optimization.orchestrator"},
                )
            else:
                generation = cp.generation
                candidate_counter = cp.candidate_counter
                total_evaluations = cp.evaluated_count
                elapsed_prior = cp.elapsed_time
                best_candidates = cp.best_candidates
                best_score = cp.best_score
                branch_manager.load_state(cp.branch_states)
                logger.info(
                    f"Resumed from checkpoint at generation {generation}",
                    extra={"component": "optimization.orchestrator"},
                )

        # 6. Pre-screening (optional, eliminates weak signal groups early)
        prescreening_cfg = opt_plan.get("prescreening", {})
        self._surviving_groups: set[str] | None = None  # None = no filtering
        prescreen_top_candidates: list[np.ndarray] | None = None

        if prescreening_cfg.get("enabled", False):
            prescreener = PreScreener(
                strategy_spec=self._strategy_spec,
                market_data_path=self._market_data_path,
                config=self._config,
                artifacts_dir=self._artifacts_dir,
                classification=classification,
                data_hash=data_hash,
                batch_runner=self._batch_runner,
                year_range=year_range,
                cost_model_path=self._cost_model_path,
            )
            prescreen_result = await prescreener.screen(
                space=space,
                branches=branches,
                mode=prescreening_cfg.get("mode", "H1"),
                m1_slice_months=prescreening_cfg.get("m1_slice_months", 3),
                n_generations=prescreening_cfg.get("n_generations", 5),
                survival_ratio=prescreening_cfg.get("survival_ratio", 0.2),
            )
            if prescreen_result.surviving_groups:
                self._surviving_groups = set(prescreen_result.surviving_groups)
            # 6a. Warm-start: extract top candidate vectors for CMA-ES seeding
            if prescreen_result.top_candidates:
                prescreen_top_candidates = prescreen_result.top_candidates
                logger.info(
                    f"Warm-start: {len(prescreen_top_candidates)} top candidates "
                    f"from pre-screening will seed CMA-ES",
                    extra={
                        "component": "optimization.orchestrator",
                        "ctx": {"n_warm_start": len(prescreen_top_candidates)},
                    },
                )
            logger.info(
                f"Pre-screening eliminated {prescreen_result.eliminated_count}/"
                f"{prescreen_result.total_count} groups in "
                f"{prescreen_result.elapsed_s:.1f}s (mode: {prescreening_cfg.get('mode', 'H1')})",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {
                        "surviving": len(prescreen_result.surviving_groups),
                        "eliminated": prescreen_result.eliminated_count,
                        "elapsed_s": prescreen_result.elapsed_s,
                    },
                },
            )

        # 6b. Apply warm-start to branch manager if we have pre-screening candidates
        if prescreen_top_candidates is not None and generation == 0:
            branch_manager.warm_start(prescreen_top_candidates)

        # 6b. Set up streaming results writer
        results_path = self._artifacts_dir / "optimization-results.arrow"

        # 7. Base strategy spec path for Rust dispatch (used when no grouping needed)
        base_strategy_spec_path = self._resolve_strategy_spec_path()

        # 8. Generation loop
        stop_reason = "max_generations"

        checkpoint_path = self._artifacts_dir / "optimization-checkpoint.json"
        generations_completed = generation  # tracks progress even if loop doesn't run

        writer = StreamingResultsWriter(results_path)
        try:
          for gen in range(generation, self._max_generations):
            gen_start = time.monotonic()

            # a. Ask candidates from all branches
            branch_candidates = branch_manager.ask_all(self._batch_size)

            # b. For each branch, dispatch and score
            branch_results: dict[str, tuple[np.ndarray, np.ndarray]] = {}

            for branch_key, candidates in branch_candidates.items():
                if len(candidates) == 0:
                    continue

                branch_space = branches.get(branch_key, space)
                n_cands_in_branch = len(candidates)
                n_folds = len(fold_specs)

                # --- Group-by-entry dispatch ---
                # Group candidates by signal + spec_override params.
                # Only batch params (exit rules) vary freely within a group.
                if classification.has_signal_params or classification.spec_override_params:
                    fold_score_matrix = await self._dispatch_grouped(
                        candidates=candidates,
                        branch_space=branch_space,
                        classification=classification,
                        fold_specs=fold_specs,
                        base_spec_path=base_strategy_spec_path,
                        generation=gen,
                        n_folds=n_folds,
                    )
                else:
                    # No signal params — single group, use baseline enriched data.
                    # Compute baseline enriched on first call.
                    if not hasattr(self, "_baseline_enriched"):
                        baseline_signal = extract_params_by_indices(
                            candidates[0], branch_space, classification.signal_indices
                        ) if classification.signal_indices else {}
                        paths = signal_cache.get_or_compute_batch(
                            [baseline_signal] if baseline_signal else [{}]
                        )
                        self._baseline_enriched = next(iter(paths.values()))
                    fold_score_matrix = await self._dispatcher.dispatch_generation(
                        candidates=candidates,
                        fold_specs=fold_specs,
                        strategy_spec_path=base_strategy_spec_path,
                        market_data_path=self._baseline_enriched,
                        cost_model_path=self._cost_model_path,
                        generation=gen,
                        param_names=branch_space.param_names,
                        parameter_space=branch_space,
                    )

                # c. Compute CV objectives
                cv_scores = np.array([
                    compute_cv_objective(fold_score_matrix[i], self._cv_lambda)
                    for i in range(n_cands_in_branch)
                ])

                branch_results[branch_key] = (candidates, cv_scores)

                # Generate stable candidate IDs
                n_cands = len(candidates)
                cand_ids = list(range(
                    candidate_counter,
                    candidate_counter + n_cands,
                ))
                candidate_counter += n_cands
                total_evaluations += n_cands

                # Write results incrementally
                params_json_list = [
                    json.dumps(decode_candidate(c, branch_space))
                    for c in candidates
                ]
                instance_types = branch_manager.get_instance_types(branch_key)

                writer.append_generation(
                    generation=gen,
                    candidate_ids=cand_ids,
                    params_list=params_json_list,
                    fold_scores=fold_score_matrix,
                    cv_objectives=cv_scores,
                    branch=branch_key,
                    instance_types=instance_types,
                )

                # Track best
                gen_best_idx = int(np.argmax(cv_scores))
                gen_best_score = float(cv_scores[gen_best_idx])
                if gen_best_score > best_score:
                    best_score = gen_best_score
                    best_candidates = [decode_candidate(candidates[gen_best_idx], branch_space)]

            # d. Tell scores back to branch manager
            branch_manager.tell_all(branch_results)

            # e. Log progress (D6 structured JSON) with diversity metrics
            elapsed = time.monotonic() - gen_start
            diversity_metrics = {}
            for bkey, (cands, _scores) in branch_results.items():
                if len(cands) > 1:
                    std_per_dim = np.std(cands, axis=0)
                    diversity_metrics[bkey] = {
                        "mean_std": float(np.mean(std_per_dim)),
                        "min_std": float(np.min(std_per_dim)),
                    }
            cache_ctx = signal_cache.cache_stats() if (
                signal_cache._log_stats_interval
                and gen % signal_cache._log_stats_interval == 0
            ) else {}
            logger.info(
                f"Generation {gen}: best={best_score:.6f}, evals={total_evaluations}",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {
                        "generation": gen,
                        "best_score": best_score,
                        "total_evaluations": total_evaluations,
                        "gen_elapsed_s": elapsed,
                        "diversity": diversity_metrics,
                        **({"signal_cache": cache_ctx} if cache_ctx else {}),
                    },
                },
            )

            # f. Checkpoint if interval reached
            generations_completed = gen + 1
            if should_checkpoint(gen, self._checkpoint_interval):
                cp = OptimizationCheckpoint(
                    generation=gen + 1,
                    branch_states=branch_manager.state_dict(),
                    best_candidates=best_candidates,
                    best_score=best_score,
                    evaluated_count=total_evaluations,
                    elapsed_time=elapsed_prior + (time.monotonic() - start_time),
                    config_hash=self._config.get("pipeline", {}).get("config_hash", ""),
                    master_seed=self._master_seed,
                    candidate_counter=candidate_counter,
                )
                save_checkpoint(cp, checkpoint_path)

            # g. Adaptive batch sizing
            self._batch_size = self._adapt_batch_size(elapsed, self._batch_size)

            # h. Progressive search space narrowing
            self._maybe_narrow_search_space(gen, best_candidates, branch_manager)

            # i. Check convergence
            if branch_manager.check_convergence():
                stop_reason = "convergence"
                logger.info(
                    "All branches converged",
                    extra={"component": "optimization.orchestrator"},
                )
                break
          else:
            stop_reason = "max_generations"

          # 9. Finalize results
          all_candidates_path = writer.finalize()
        except Exception:
            writer.__exit__(None, None, None)
            raise
        finally:
            # Shut down persistent worker pool if active
            if self._worker_pool is not None:
                try:
                    await self._worker_pool.shutdown_all()
                except Exception as e:
                    logger.warning(
                        f"Worker pool shutdown error: {e}",
                        extra={"component": "optimization.orchestrator"},
                    )
                self._worker_pool = None

        # 10. Write run manifest
        total_elapsed = elapsed_prior + (time.monotonic() - start_time)
        spec_hash = hashlib.sha256(
            json.dumps(self._strategy_spec, sort_keys=True).encode()
        ).hexdigest()

        manifest_path = write_run_manifest(
            artifacts_dir=self._artifacts_dir,
            dataset_hash=self._compute_data_hash(),
            strategy_spec_hash=f"sha256:{spec_hash}",
            config_hash=self._config.get("pipeline", {}).get("config_hash", ""),
            fold_definitions=fold_manager.to_rust_fold_args(),
            rng_seeds={"master_seed": self._master_seed},
            stop_reason=stop_reason,
            generation_count=generations_completed,
            branch_metadata={
                k: {"visit_count": s.visit_count, "best_score": s.best_score}
                for k, s in branch_manager._stats.items()
            } if hasattr(branch_manager, '_stats') else {},
            total_evaluations=total_evaluations,
        )

        # 11. Promote top candidates
        promoted_path = None
        if all_candidates_path.exists():
            try:
                promoted_path = promote_top_candidates(all_candidates_path, top_n=20)
            except Exception as e:
                logger.warning(
                    f"Candidate promotion failed: {e}",
                    extra={"component": "optimization.orchestrator"},
                )

        # 12. Post-optimization validation gauntlet + confidence scoring
        validation_result = self._run_post_optimization_gauntlet(
            promoted_path=promoted_path,
            manifest_path=manifest_path,
            total_evaluations=total_evaluations,
        )

        return OptimizationResult(
            best_candidates=best_candidates,
            all_candidates_path=all_candidates_path,
            promoted_candidates_path=promoted_path,
            run_manifest_path=manifest_path,
            generations_run=generations_completed,
            total_evaluations=total_evaluations,
            convergence_reached=(stop_reason == "convergence"),
            stop_reason=stop_reason,
            validation=validation_result,
        )

    def get_progress(self) -> dict:
        """Return current progress for status display."""
        result = {
            "batch_size": self._batch_size,
            "max_generations": self._max_generations,
            "cv_folds": self._cv_folds,
            "cv_lambda": self._cv_lambda,
        }
        if hasattr(self, "_signal_cache"):
            result["signal_cache"] = self._signal_cache.cache_stats()
        return result

    async def _dispatch_grouped(
        self,
        candidates: np.ndarray,
        branch_space: ParameterSpace,
        classification: ParamClassification,
        fold_specs: list,
        base_spec_path: Path,
        generation: int,
        n_folds: int,
    ) -> np.ndarray:
        """Dispatch candidates grouped by entry params for joint optimization.

        Groups candidates by their signal + spec_override params, computes
        or retrieves cached enriched data per group, writes per-group TOML
        specs, and dispatches each group separately. Results are scattered
        back to the original candidate order.

        Returns fold_score_matrix of shape (n_candidates, n_folds).
        """
        n_candidates = len(candidates)

        # 1. Extract group key params for each candidate (snapped to step grid)
        group_key_indices = classification.group_key_indices
        signal_indices = classification.signal_indices
        spec_override_indices = classification.spec_override_indices

        # Build per-candidate group info
        groups: dict[str, _CandidateGroup] = {}
        surviving = getattr(self, "_surviving_groups", None)
        for i in range(n_candidates):
            sig_params = extract_params_by_indices(
                candidates[i], branch_space, signal_indices
            )
            so_params = extract_params_by_indices(
                candidates[i], branch_space, spec_override_indices
            )
            g_hash = compute_group_hash(sig_params, so_params)

            # Skip groups eliminated by pre-screening
            if surviving is not None and g_hash not in surviving:
                continue

            s_hash = compute_signal_hash(sig_params)

            if g_hash not in groups:
                groups[g_hash] = _CandidateGroup(
                    group_hash=g_hash,
                    signal_hash=s_hash,
                    signal_params=sig_params,
                    spec_override_params=so_params,
                    candidate_indices=[],
                    candidate_rows=[],
                )
            groups[g_hash].candidate_indices.append(i)
            groups[g_hash].candidate_rows.append(candidates[i])

        # 2. Resolve enriched data per unique signal param set (cached)
        unique_signal_sets = {
            g.signal_hash: g.signal_params for g in groups.values()
        }
        enriched_paths: dict[str, Path] = {}
        for s_hash, s_params in unique_signal_sets.items():
            enriched_paths[s_hash] = self._signal_cache.get_or_compute(s_params)

        # 3. Prepare per-group specs and enriched data paths
        fold_score_matrix = np.full(
            (n_candidates, n_folds), float("-inf"), dtype=np.float64
        )

        gen_spec_dir = self._artifacts_dir / f"gen_{generation:06d}" / "specs"
        gen_spec_dir.mkdir(parents=True, exist_ok=True)

        group_tasks = []
        for group in groups.values():
            group_candidates = np.array(group.candidate_rows, dtype=np.float64)
            enriched_path = enriched_paths[group.signal_hash]

            override_spec = build_override_spec(
                base_spec=self._strategy_spec,
                signal_params=group.signal_params,
                spec_override_params=group.spec_override_params,
                classification=classification,
            )
            spec_path = write_toml_spec(override_spec, gen_spec_dir, group.group_hash)
            group_tasks.append((group, group_candidates, enriched_path, spec_path))

        # 4. Dispatch — use multi-group manifest (N_folds procs) or fallback
        #    to per-group dispatch (N_groups * N_folds procs).
        if self._use_manifest_dispatch:
            try:
                return await self._dispatch_grouped_manifest(
                    group_tasks, fold_specs, generation, n_folds,
                    n_candidates, branch_space,
                )
            except Exception as e:
                logger.warning(
                    f"Manifest dispatch failed, falling back to per-group: {e}",
                    extra={"component": "optimization.orchestrator"},
                )
                self._use_manifest_dispatch = False

        # Fallback: per-group dispatch (original path)
        async def _dispatch_one(grp, cands, e_path, s_path):
            return await self._dispatcher.dispatch_generation(
                candidates=cands,
                fold_specs=fold_specs,
                strategy_spec_path=s_path,
                market_data_path=e_path,
                cost_model_path=self._cost_model_path,
                generation=generation,
                param_names=branch_space.param_names,
                group_hash=grp.group_hash,
                parameter_space=branch_space,
            )

        group_results = await asyncio.gather(*[
            _dispatch_one(g, c, e, s) for g, c, e, s in group_tasks
        ])

        for (group, _, _, _), group_scores in zip(group_tasks, group_results):
            for local_i, global_i in enumerate(group.candidate_indices):
                fold_score_matrix[global_i] = group_scores[local_i]

        return fold_score_matrix

    async def _dispatch_grouped_manifest(
        self,
        group_tasks: list[tuple],
        fold_specs: list,
        generation: int,
        n_folds: int,
        n_candidates: int,
        branch_space: ParameterSpace,
    ) -> np.ndarray:
        """Dispatch all groups via multi-group manifest (N_folds subprocesses).

        Builds the groups dict expected by dispatch_generation_multi_group(),
        dispatches, and scatters results back to original candidate order.
        """
        # Build groups dict: group_hash -> (candidates, spec_path, enriched_path)
        multi_groups: dict[str, tuple[np.ndarray, Path, Path]] = {}
        for group, group_candidates, enriched_path, spec_path in group_tasks:
            multi_groups[group.group_hash] = (group_candidates, spec_path, enriched_path)

        # Dispatch via manifest — returns {group_hash: (n_cands, n_folds)}
        group_score_maps = await self._dispatcher.dispatch_generation_multi_group(
            groups=multi_groups,
            fold_specs=fold_specs,
            market_data_path=self._market_data_path,
            cost_model_path=self._cost_model_path,
            generation=generation,
            parameter_space=branch_space,
        )

        # Scatter results back to original candidate order
        fold_score_matrix = np.full(
            (n_candidates, n_folds), float("-inf"), dtype=np.float64
        )
        for group, _, _, _ in group_tasks:
            group_scores = group_score_maps.get(group.group_hash)
            if group_scores is not None:
                for local_i, global_i in enumerate(group.candidate_indices):
                    fold_score_matrix[global_i] = group_scores[local_i]

        return fold_score_matrix

    def _estimate_data_length(self, year_range: tuple[int, int] | None = None) -> int:
        """Estimate data length from market data file metadata.

        If year_range is provided, estimates the fraction of bars within
        the year range using timestamp sampling rather than loading
        the full dataset.
        """
        import pyarrow.ipc

        try:
            reader = pyarrow.ipc.open_file(str(self._market_data_path))
            total = sum(
                reader.get_batch(i).num_rows
                for i in range(reader.num_record_batches)
            )

            if year_range is None:
                return total

            # Estimate year-filtered length from first/last timestamps
            import pyarrow.compute as pc

            table = reader.read_all()
            ts_col = table.column("timestamp")
            ts_min = pc.min(ts_col).as_py()
            ts_max = pc.max(ts_col).as_py()

            if ts_min is None or ts_max is None or ts_max <= ts_min:
                return total

            # Determine timestamp unit
            if ts_max > 1e15:
                divisor = 1e6  # microseconds
            elif ts_max > 1e12:
                divisor = 1e3  # milliseconds
            else:
                divisor = 1  # seconds

            from datetime import datetime, timezone
            data_start = datetime.fromtimestamp(ts_min / divisor, tz=timezone.utc)
            data_end = datetime.fromtimestamp(ts_max / divisor, tz=timezone.utc)
            total_span = (data_end - data_start).total_seconds()
            if total_span <= 0:
                return total

            # Clamp year range to data range
            yr_start_dt = datetime(year_range[0], 1, 1, tzinfo=timezone.utc)
            yr_end_dt = datetime(year_range[1] + 1, 1, 1, tzinfo=timezone.utc)
            eff_start = max(data_start, yr_start_dt)
            eff_end = min(data_end, yr_end_dt)

            if eff_end <= eff_start:
                return max(1000, total // 10)  # Fallback: minimal overlap

            filtered_span = (eff_end - eff_start).total_seconds()
            ratio = filtered_span / total_span
            estimated = int(total * ratio)
            return max(estimated, 1000)  # Floor at 1000 bars

        except Exception:
            return 100000  # Fallback: 100k bars

    def _resolve_strategy_spec_path(self) -> Path:
        """Find the strategy spec TOML path on disk."""
        spec_name = self._strategy_spec.get("metadata", {}).get("name", "unknown")
        spec_version = self._strategy_spec.get("metadata", {}).get("version", "v001")

        # Standard location: artifacts/strategies/<name>/<version>.toml
        # Try walking up from artifacts_dir to find the strategies/ sibling
        search = self._artifacts_dir
        for _ in range(5):  # walk up at most 5 levels
            candidate = search / "strategies" / spec_name / f"{spec_version}.toml"
            if candidate.exists():
                return candidate
            search = search.parent

        # Also try the config-based artifacts dir
        config_artifacts = Path(self._config.get("pipeline", {}).get("artifacts_dir", "artifacts"))
        spec_path = config_artifacts / "strategies" / spec_name / f"{spec_version}.toml"
        if spec_path.exists():
            return spec_path

        # Fallback: write spec to temp location as JSON
        spec_path = self._artifacts_dir / "strategy-spec.json"
        if not spec_path.exists():
            from artifacts.storage import crash_safe_write
            crash_safe_write(
                spec_path,
                json.dumps(self._strategy_spec, indent=2, default=str),
            )
        return spec_path

    def _adapt_batch_size(self, gen_elapsed_s: float, current_batch_size: int) -> int:
        """Adjust batch size based on generation wall-clock time.

        If a generation takes >60s, halve the batch (more frequent optimizer
        updates).  If <5s, double it (better throughput).  Clamps to
        [256, 8192].
        """
        new_batch = current_batch_size
        if gen_elapsed_s > 60.0:
            new_batch = current_batch_size // 2
        elif gen_elapsed_s < 5.0:
            new_batch = current_batch_size * 2
        new_batch = max(256, min(8192, new_batch))
        if new_batch != current_batch_size:
            logger.info(
                f"Adaptive batch size: {current_batch_size} -> {new_batch} "
                f"(gen took {gen_elapsed_s:.1f}s)",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {
                        "old_batch": current_batch_size,
                        "new_batch": new_batch,
                        "gen_elapsed_s": gen_elapsed_s,
                    },
                },
            )
        return new_batch

    def _maybe_narrow_search_space(
        self,
        gen: int,
        best_candidates: list,
        branch_manager: BranchManager,
    ) -> bool:
        """Narrow parameter bounds based on top performer distribution.

        After ``trigger_generation`` generations, analyze the top 10% of
        historical best candidates and shrink each parameter's bounds to
        ``range_multiplier`` times the observed range of those top
        performers.  Then restart CMA-ES instances with the tighter bounds.

        Returns True if narrowing was applied.
        """
        pn_cfg = self._config.get("optimization", {}).get(
            "progressive_narrowing", {}
        )
        if not pn_cfg.get("enabled", False):
            return False
        trigger = pn_cfg.get("trigger_generation", 50)
        if gen != trigger:
            return False
        multiplier = pn_cfg.get("range_multiplier", 2.0)

        if len(best_candidates) < 2:
            logger.debug(
                "Progressive narrowing skipped: too few candidates",
                extra={"component": "optimization.orchestrator"},
            )
            return False

        # Analyze top 10% of best_candidates (they are dicts of param->value)
        n_top = max(2, len(best_candidates) // 10)
        top = best_candidates[:n_top]

        # Compute per-param observed range among top performers
        param_names = list(top[0].keys())
        narrowed_bounds: dict[str, tuple[float, float]] = {}
        for pname in param_names:
            vals = [c[pname] for c in top if pname in c]
            if len(vals) < 2:
                continue
            lo, hi = float(min(vals)), float(max(vals))
            span = hi - lo
            center = (lo + hi) / 2.0
            half_range = (span * multiplier) / 2.0
            narrowed_bounds[pname] = (center - half_range, center + half_range)

        if not narrowed_bounds:
            return False

        branch_manager.narrow_bounds(narrowed_bounds)
        logger.info(
            f"Progressive narrowing applied at generation {gen}: "
            f"{len(narrowed_bounds)} params narrowed (multiplier={multiplier})",
            extra={
                "component": "optimization.orchestrator",
                "ctx": {
                    "generation": gen,
                    "multiplier": multiplier,
                    "n_params_narrowed": len(narrowed_bounds),
                },
            },
        )
        return True

    def _compute_data_hash(self) -> str:
        """Compute hash of market data file."""
        try:
            h = hashlib.sha256()
            with open(self._market_data_path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            return f"sha256:{h.hexdigest()}"
        except Exception:
            return "sha256:unknown"

    def _run_post_optimization_gauntlet(
        self,
        promoted_path: Path | None,
        manifest_path: Path,
        total_evaluations: int,
    ) -> PostOptimizationValidation:
        """Run validation gauntlet and confidence scoring on promoted candidates.

        Graceful degradation: if any component fails, logs a warning and
        returns a result with skipped=True. Never crashes the optimization.
        """
        run_gauntlet = self._config.get("optimization", {}).get(
            "run_validation_gauntlet", True
        )
        if not run_gauntlet:
            logger.info(
                "Post-optimization validation gauntlet disabled by config",
                extra={"component": "optimization.orchestrator"},
            )
            return PostOptimizationValidation(
                skipped=True, skip_reason="disabled_by_config"
            )

        if promoted_path is None or not promoted_path.exists():
            logger.warning(
                "Skipping validation gauntlet: no promoted candidates available",
                extra={"component": "optimization.orchestrator"},
            )
            return PostOptimizationValidation(
                skipped=True, skip_reason="no_promoted_candidates"
            )

        # --- Load promoted candidates ---
        try:
            import pyarrow.ipc

            reader = pyarrow.ipc.open_file(str(promoted_path))
            table = reader.read_all()
            candidates: list[dict] = []
            if "params_json" in table.column_names:
                for row_idx in range(len(table)):
                    params = json.loads(
                        table.column("params_json")[row_idx].as_py()
                    )
                    candidates.append(params)

            if not candidates:
                logger.warning(
                    "Skipping validation gauntlet: promoted file has no candidates",
                    extra={"component": "optimization.orchestrator"},
                )
                return PostOptimizationValidation(
                    skipped=True, skip_reason="empty_promoted_file"
                )
        except Exception as e:
            logger.warning(
                f"Skipping validation gauntlet: failed to load promoted candidates: {e}",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {"error": str(e)},
                },
            )
            return PostOptimizationValidation(
                skipped=True, skip_reason=f"load_error: {e}"
            )

        # --- Load optimization manifest ---
        try:
            optimization_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except Exception:
            optimization_manifest = {"run_id": "", "total_trials": total_evaluations}

        # --- Run validation gauntlet ---
        gauntlet_output_dir = self._artifacts_dir / "validation"
        gauntlet_output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from validation.config import ValidationConfig
            from validation.gauntlet import ValidationGauntlet

            val_config = ValidationConfig.from_dict(self._config)
            gauntlet = ValidationGauntlet(config=val_config, dispatcher=self._batch_runner)

            gauntlet_results = gauntlet.run(
                candidates=candidates,
                market_data_path=self._market_data_path,
                strategy_spec=self._strategy_spec,
                cost_model=json.loads(self._cost_model_path.read_text(encoding="utf-8"))
                if self._cost_model_path.suffix == ".json"
                else {},
                optimization_manifest=optimization_manifest,
                output_dir=gauntlet_output_dir,
            )

            n_validated = len(gauntlet_results.candidates)
            n_short_circuited = sum(
                1 for c in gauntlet_results.candidates if c.short_circuited
            )
            logger.info(
                f"Validation gauntlet complete: {n_validated} candidates, "
                f"{n_short_circuited} short-circuited",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {
                        "n_validated": n_validated,
                        "n_short_circuited": n_short_circuited,
                        "dsr_passed": gauntlet_results.dsr.passed
                        if gauntlet_results.dsr
                        else None,
                    },
                },
            )

            # Write gauntlet artifacts for downstream consumption
            from validation.results import (
                write_gauntlet_manifest,
                write_stage_artifact,
                write_stage_summary,
            )

            artifact_paths: dict[int, dict[str, str]] = {}
            for cv in gauntlet_results.candidates:
                candidate_dir = gauntlet_output_dir / f"candidate_{cv.candidate_id:03d}"
                cand_artifacts: dict[str, str] = {}
                for stage_name, stage_output in cv.stages.items():
                    if stage_output.result is not None:
                        art_path = write_stage_artifact(
                            stage_name, stage_output.result, candidate_dir
                        )
                        write_stage_summary(
                            stage_name, stage_output.result, candidate_dir
                        )
                        cand_artifacts[stage_name] = str(art_path)
                artifact_paths[cv.candidate_id] = cand_artifacts

            write_gauntlet_manifest(
                gauntlet_results,
                optimization_manifest,
                gauntlet_output_dir,
                validation_config=self._config.get("validation", {}),
                artifact_paths=artifact_paths,
            )

        except Exception as e:
            logger.warning(
                f"Validation gauntlet failed (non-fatal): {e}",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {"error": str(e)},
                },
            )
            return PostOptimizationValidation(
                gauntlet_output_dir=gauntlet_output_dir,
                skipped=True,
                skip_reason=f"gauntlet_error: {e}",
            )

        # --- Run confidence scoring ---
        scoring_manifest_path = None
        n_green = n_yellow = n_red = 0

        try:
            from confidence.config import confidence_config_from_dict
            from confidence.orchestrator import ConfidenceOrchestrator

            conf_config = confidence_config_from_dict(self._config)
            confidence_orch = ConfidenceOrchestrator(conf_config)

            scoring_output_dir = self._artifacts_dir / "confidence"
            scoring_output_dir.mkdir(parents=True, exist_ok=True)

            scoring_manifest_path = confidence_orch.score_all_candidates(
                gauntlet_results_dir=gauntlet_output_dir,
                optimization_manifest=optimization_manifest,
                output_dir=scoring_output_dir,
            )

            # Read back the manifest to extract grade counts
            manifest_data = json.loads(
                scoring_manifest_path.read_text(encoding="utf-8")
            )
            scored_candidates = manifest_data.get("candidates", [])
            n_green = sum(1 for c in scored_candidates if c.get("rating") == "GREEN")
            n_yellow = sum(1 for c in scored_candidates if c.get("rating") == "YELLOW")
            n_red = sum(1 for c in scored_candidates if c.get("rating") == "RED")

            logger.info(
                f"Confidence scoring complete: "
                f"GREEN={n_green}, YELLOW={n_yellow}, RED={n_red}",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {
                        "n_green": n_green,
                        "n_yellow": n_yellow,
                        "n_red": n_red,
                        "scoring_manifest": str(scoring_manifest_path),
                    },
                },
            )

        except Exception as e:
            logger.warning(
                f"Confidence scoring failed (non-fatal): {e}",
                extra={
                    "component": "optimization.orchestrator",
                    "ctx": {"error": str(e)},
                },
            )

        return PostOptimizationValidation(
            gauntlet_output_dir=gauntlet_output_dir,
            scoring_manifest_path=scoring_manifest_path,
            n_candidates_validated=n_validated,
            n_green=n_green,
            n_yellow=n_yellow,
            n_red=n_red,
        )
