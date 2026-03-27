"""Batch dispatch adapter for optimization (Story 5.3, AC #3, #5, #11).

Wraps the existing BatchRunner to dispatch fold-aware candidate batches
to the Rust evaluator.  Also provides ``PersistentBatchDispatcher`` which
delegates to a ``WorkerPool`` of persistent Rust workers for zero-startup
evaluations.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc

from data_pipeline.utils.safe_write import safe_write_arrow_ipc
from logging_setup.setup import get_logger
from optimization.fold_manager import FoldSpec
from optimization.parameter_space import ParameterSpace, decode_candidate
from rust_bridge.batch_runner import BacktestJob, BatchRunner, _get_available_memory_mb

logger = get_logger("optimization.batch_dispatch")

OS_RESERVE_MB = 2048


class OptimizationBatchDispatcher:
    """Dispatches candidate batches to Rust evaluator with fold-aware scoring."""

    def __init__(
        self,
        batch_runner: BatchRunner,
        artifacts_dir: Path,
        config: dict,
    ):
        self._runner = batch_runner
        self._artifacts_dir = artifacts_dir
        self._config = config
        opt_config = config.get("optimization", {})
        self._memory_budget_mb = opt_config.get("memory_budget_mb", 5632)
        # Limit concurrent Rust subprocesses to avoid overwhelming Windows
        # process creation. CPU count is a good ceiling since vectorized
        # evaluator is single-threaded per subprocess.
        import os
        max_procs = opt_config.get("max_concurrent_procs", os.cpu_count() or 16)
        self._subprocess_semaphore = asyncio.Semaphore(max_procs)

    def check_memory(self, batch_size: int, n_folds: int) -> tuple[bool, int]:
        """Pre-flight memory check. Returns (ok, adjusted_batch_size).

        If insufficient memory, reduces batch size before starting (NFR4).
        """
        available = _get_available_memory_mb()
        if available > OS_RESERVE_MB:
            available -= OS_RESERVE_MB

        if available <= 0:
            return True, batch_size  # Can't check, proceed optimistically

        # Estimate: ~1KB per candidate per fold (conservative)
        estimated_mb = (batch_size * n_folds * 1024) / (1024 * 1024)
        budget = min(self._memory_budget_mb, available)

        if estimated_mb <= budget:
            return True, batch_size

        # Reduce batch size to fit
        max_candidates = int(budget * 1024 * 1024 / (n_folds * 1024))
        adjusted = max(64, min(batch_size, max_candidates))

        logger.warning(
            f"Memory budget exceeded: reducing batch {batch_size} -> {adjusted}",
            extra={
                "component": "optimization.batch_dispatch",
                "ctx": {
                    "original_batch": batch_size,
                    "adjusted_batch": adjusted,
                    "available_mb": available,
                    "budget_mb": budget,
                },
            },
        )

        return False, adjusted

    async def dispatch_generation(
        self,
        candidates: np.ndarray,
        fold_specs: list[FoldSpec],
        strategy_spec_path: Path,
        market_data_path: Path,
        cost_model_path: Path,
        generation: int,
        param_names: list[str] | None = None,
        group_hash: str | None = None,
        parameter_space: ParameterSpace | None = None,
    ) -> np.ndarray:
        """Dispatch candidates to Rust evaluator for fold-aware evaluation.

        Args:
            group_hash: Optional group identifier for multi-group generations.
                When provided, output dirs become gen_X/grp_Y/fold_Z to
                prevent collisions between groups in the same generation.
            parameter_space: ParameterSpace for snapping continuous CMA-ES
                values to grid (integers rounded, steps applied). Without
                this, raw floats are written which breaks signal column
                matching in the Rust backtester.

        Returns score matrix of shape (n_candidates, n_folds).
        """
        n_candidates = len(candidates)
        n_folds = len(fold_specs)
        gen_dir = self._artifacts_dir / f"gen_{generation:06d}"
        if group_hash is not None:
            gen_dir = gen_dir / f"grp_{group_hash[:8]}"
        gen_dir.mkdir(parents=True, exist_ok=True)

        # Write candidate parameters snapped to grid (integers, step values)
        if parameter_space is not None:
            param_batch = [
                decode_candidate(candidates[i], parameter_space)
                for i in range(n_candidates)
            ]
        elif param_names and len(param_names) == candidates.shape[1]:
            param_batch = [
                {param_names[j]: float(candidates[i, j]) for j in range(candidates.shape[1])}
                for i in range(n_candidates)
            ]
        else:
            param_batch = [
                {f"p{j}": float(candidates[i, j]) for j in range(candidates.shape[1])}
                for i in range(n_candidates)
            ]

        # Build fold boundaries for Rust
        fold_boundaries = [
            (f.train_start, f.train_end, f.test_start, f.test_end)
            for f in fold_specs
        ]

        # Build all fold jobs first (sequential, fast)
        all_fold_scores = np.full((n_candidates, n_folds), float("-inf"), dtype=np.float64)

        fold_jobs = []
        fold_dirs = []
        for fold_idx, fold in enumerate(fold_specs):
            fold_dir = gen_dir / f"fold_{fold.fold_id}"
            fold_dir.mkdir(parents=True, exist_ok=True)

            job = BacktestJob(
                strategy_spec_path=strategy_spec_path,
                market_data_path=market_data_path,
                cost_model_path=cost_model_path,
                output_directory=fold_dir,
                config_hash=self._config.get("pipeline", {}).get("config_hash", ""),
                memory_budget_mb=self._memory_budget_mb,
                fold_boundaries=[(fold.train_start, fold.train_end)],
                embargo_bars=fold.embargo_bars,
                window_start=fold.test_start,
                window_end=fold.test_end,
                parameter_batch=param_batch,
            )
            fold_jobs.append(job)
            fold_dirs.append(fold_dir)

        # Dispatch ALL folds in parallel, throttled by semaphore to avoid
        # overwhelming Windows with too many concurrent subprocesses.
        async def _throttled_dispatch(job):
            async with self._subprocess_semaphore:
                return await self._runner.dispatch(job, n_concurrent=n_folds)

        results = await asyncio.gather(
            *[_throttled_dispatch(job) for job in fold_jobs],
            return_exceptions=True,
        )

        # Process results (gather with return_exceptions=True may yield exceptions)
        for fold_idx, (result, fold_dir, fold) in enumerate(
            zip(results, fold_dirs, fold_specs)
        ):
            if isinstance(result, BaseException):
                logger.error(
                    f"Fold {fold.fold_id} raised exception: {result}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {"generation": generation, "fold_id": fold.fold_id},
                    },
                )
                # all_fold_scores already initialized to -inf
                continue
            if result.exit_code == 0:
                scores = self._read_fold_scores(fold_dir, n_candidates)
                all_fold_scores[:, fold_idx] = scores
                if np.all(np.isinf(scores) & (scores < 0)):
                    stderr_snippet = (result.error or "")[:500]
                    logger.warning(
                        f"Fold {fold.fold_id} returned all -inf scores "
                        f"(exit_code=0 but no scores.arrow). "
                        f"Rust stderr: {stderr_snippet}",
                        extra={
                            "component": "optimization.batch_dispatch",
                            "ctx": {
                                "generation": generation,
                                "fold_id": fold.fold_id,
                                "fold_dir": str(fold_dir),
                            },
                        },
                    )
            else:
                logger.error(
                    f"Fold {fold.fold_id} dispatch failed (exit_code={result.exit_code}): "
                    f"{(result.error or '')[:500]}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {
                            "generation": generation,
                            "fold_id": fold.fold_id,
                            "exit_code": result.exit_code,
                        },
                    },
                )
                all_fold_scores[:, fold_idx] = float("-inf")

        return all_fold_scores

    async def dispatch_generation_multi_group(
        self,
        groups: dict[str, tuple[np.ndarray, Path, Path]],
        fold_specs: list[FoldSpec],
        market_data_path: Path,
        cost_model_path: Path,
        generation: int,
        parameter_space: ParameterSpace,
    ) -> dict[str, np.ndarray]:
        """Dispatch ALL groups in a single manifest per fold.

        Instead of spawning N_groups * N_folds subprocesses, this builds one
        manifest JSON per fold containing every group, then dispatches only
        N_folds subprocesses total.

        Args:
            groups: Maps group_hash -> (candidates_array, strategy_spec_path,
                enriched_data_path).
            fold_specs: Fold boundary definitions.
            market_data_path: Shared market data Arrow file.
            cost_model_path: Shared cost model JSON.
            generation: Current generation number.
            parameter_space: For snapping continuous values to grid.

        Returns:
            dict mapping group_hash -> score matrix of shape
            (n_candidates, n_folds).
        """
        n_folds = len(fold_specs)
        gen_dir = self._artifacts_dir / f"gen_{generation:06d}"
        gen_dir.mkdir(parents=True, exist_ok=True)

        def norm(p: Path) -> str:
            return str(p).replace("\\", "/")

        # Pre-snap all candidates per group
        group_param_batches: dict[str, list[dict]] = {}
        for g_hash, (candidates, _spec, _data) in groups.items():
            group_param_batches[g_hash] = [
                decode_candidate(candidates[i], parameter_space)
                for i in range(len(candidates))
            ]

        # Initialize result matrices
        result_matrices: dict[str, np.ndarray] = {}
        for g_hash, (candidates, _, _) in groups.items():
            result_matrices[g_hash] = np.full(
                (len(candidates), n_folds), float("-inf"), dtype=np.float64,
            )

        # Build one manifest per fold, dispatch in parallel
        fold_manifests: list[Path] = []
        fold_group_dirs: list[dict[str, Path]] = []  # per-fold mapping of group -> output_dir

        for fold_idx, fold in enumerate(fold_specs):
            group_entries = []
            dirs_for_fold: dict[str, Path] = {}

            for g_hash, (candidates, spec_path, data_path) in groups.items():
                output_dir = gen_dir / f"grp_{g_hash[:8]}" / f"fold_{fold.fold_id}"
                output_dir.mkdir(parents=True, exist_ok=True)
                dirs_for_fold[g_hash] = output_dir

                group_entries.append({
                    "group_id": f"grp_{g_hash[:8]}",
                    "spec_path": norm(spec_path),
                    "data_path": norm(data_path),
                    "candidates": group_param_batches[g_hash],
                    "output_dir": norm(output_dir),
                })

            manifest = {
                "groups": group_entries,
                "market_data_path": norm(market_data_path),
                "cost_model_path": norm(cost_model_path),
                "fold_boundaries": [(fold.train_start, fold.train_end)],
                "window_start": fold.test_start,
                "window_end": fold.test_end,
                "scores_only": True,
            }

            manifest_path = gen_dir / f"manifest_fold_{fold.fold_id}.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
            fold_manifests.append(manifest_path)
            fold_group_dirs.append(dirs_for_fold)

        # Dispatch all folds in parallel, throttled by semaphore
        async def _throttled_manifest(m_path):
            async with self._subprocess_semaphore:
                return await self._runner.dispatch_manifest(
                    m_path, memory_budget_mb=self._memory_budget_mb,
                )

        results = await asyncio.gather(
            *[_throttled_manifest(m) for m in fold_manifests],
            return_exceptions=True,
        )

        # Read back scores per group per fold
        for fold_idx, (result, dirs_map, fold) in enumerate(
            zip(results, fold_group_dirs, fold_specs)
        ):
            if isinstance(result, BaseException):
                logger.error(
                    f"Manifest fold {fold.fold_id} raised exception: {result}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {"generation": generation, "fold_id": fold.fold_id},
                    },
                )
                continue

            if result.exit_code != 0:
                logger.error(
                    f"Manifest fold {fold.fold_id} failed (exit={result.exit_code}): "
                    f"{(result.error or '')[:500]}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {
                            "generation": generation,
                            "fold_id": fold.fold_id,
                            "exit_code": result.exit_code,
                        },
                    },
                )
                continue

            for g_hash, output_dir in dirs_map.items():
                n_cands = len(groups[g_hash][0])
                scores = self._read_fold_scores(output_dir, n_cands)
                result_matrices[g_hash][:, fold_idx] = scores

        return result_matrices

    def _read_fold_scores(self, fold_dir: Path, n_candidates: int) -> np.ndarray:
        """Read per-candidate scores from Rust evaluator output."""
        scores_path = fold_dir / "scores.arrow"
        if scores_path.exists():
            reader = pa.ipc.open_file(str(scores_path))
            table = reader.read_all()
            if "score" in table.column_names:
                return table.column("score").to_numpy()

        # Fallback: try JSON scores
        json_path = fold_dir / "scores.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return np.array(data.get("scores", [0.0] * n_candidates), dtype=np.float64)

        logger.error(
            f"No scores found in {fold_dir} — returning -inf (possible evaluator fault)",
            extra={
                "component": "optimization.batch_dispatch",
                "ctx": {"fold_dir": str(fold_dir), "n_candidates": n_candidates},
            },
        )
        return np.full(n_candidates, float("-inf"), dtype=np.float64)


class PersistentBatchDispatcher:
    """Dispatches candidate batches via persistent WorkerPool (zero-startup eval).

    Implements the same high-level interface as ``OptimizationBatchDispatcher``
    but delegates evaluation to a pool of long-lived Rust worker processes
    communicating over JSON-lines, rather than spawning fresh subprocesses
    per generation.

    The subprocess-based dispatcher remains the default; this is activated
    by ``use_persistent_worker: true`` in the ``[optimization]`` config.
    """

    def __init__(
        self,
        worker_pool: "WorkerPool",
        artifacts_dir: Path,
        config: dict,
    ):
        from rust_bridge.worker_client import WorkerPool  # deferred to avoid circular

        self._pool: WorkerPool = worker_pool
        self._artifacts_dir = artifacts_dir
        self._config = config
        opt_config = config.get("optimization", {})
        self._memory_budget_mb = opt_config.get("memory_budget_mb", 5632)
        # Track data keys preloaded on each worker for routing
        self._preloaded_keys: list[tuple[str, Path]] = []

    def check_memory(self, batch_size: int, n_folds: int) -> tuple[bool, int]:
        """Pre-flight memory check (same logic as subprocess dispatcher)."""
        available = _get_available_memory_mb()
        if available > OS_RESERVE_MB:
            available -= OS_RESERVE_MB

        if available <= 0:
            return True, batch_size

        estimated_mb = (batch_size * n_folds * 1024) / (1024 * 1024)
        budget = min(self._memory_budget_mb, available)

        if estimated_mb <= budget:
            return True, batch_size

        max_candidates = int(budget * 1024 * 1024 / (n_folds * 1024))
        adjusted = max(64, min(batch_size, max_candidates))

        logger.warning(
            f"Memory budget exceeded: reducing batch {batch_size} -> {adjusted}",
            extra={
                "component": "optimization.batch_dispatch",
                "ctx": {
                    "original_batch": batch_size,
                    "adjusted_batch": adjusted,
                    "available_mb": available,
                    "budget_mb": budget,
                    "dispatcher": "persistent",
                },
            },
        )
        return False, adjusted

    async def preload_data(self, keys_and_paths: list[tuple[str, Path]]) -> None:
        """Preload enriched data files into the worker pool.

        Must be called before any ``dispatch_generation*`` methods.
        """
        self._preloaded_keys = keys_and_paths
        await self._pool.preload_data(keys_and_paths)

    async def dispatch_generation(
        self,
        candidates: np.ndarray,
        fold_specs: list[FoldSpec],
        strategy_spec_path: Path,
        market_data_path: Path,
        cost_model_path: Path,
        generation: int,
        param_names: list[str] | None = None,
        group_hash: str | None = None,
        parameter_space: ParameterSpace | None = None,
    ) -> np.ndarray:
        """Dispatch candidates to persistent workers for fold-aware evaluation.

        Returns score matrix of shape (n_candidates, n_folds).
        """
        n_candidates = len(candidates)
        n_folds = len(fold_specs)

        # Snap candidates to grid
        if parameter_space is not None:
            param_batch = [
                decode_candidate(candidates[i], parameter_space)
                for i in range(n_candidates)
            ]
        elif param_names and len(param_names) == candidates.shape[1]:
            param_batch = [
                {param_names[j]: float(candidates[i, j]) for j in range(candidates.shape[1])}
                for i in range(n_candidates)
            ]
        else:
            param_batch = [
                {f"p{j}": float(candidates[i, j]) for j in range(candidates.shape[1])}
                for i in range(n_candidates)
            ]

        # Derive data key from market_data_path
        data_key = _path_to_data_key(market_data_path)

        # Build single group for eval
        group_id = f"grp_{group_hash[:8]}" if group_hash else "grp_default"
        groups = [{
            "group_id": group_id,
            "spec_path": str(strategy_spec_path).replace("\\", "/"),
            "candidates": param_batch,
        }]

        # Dispatch one eval per fold across workers (round-robin)
        all_fold_scores = np.full((n_candidates, n_folds), float("-inf"), dtype=np.float64)

        async def _eval_fold(fold_idx: int, fold: FoldSpec) -> tuple[int, np.ndarray]:
            worker_idx = fold_idx % self._pool.n_workers
            try:
                results = await self._pool.eval_on_worker(
                    worker_idx=worker_idx,
                    data_key=data_key,
                    groups=groups,
                    window_start=fold.test_start,
                    window_end=fold.test_end,
                )
                scores = results.get(group_id, [])
                return fold_idx, np.array(scores, dtype=np.float64)
            except Exception as e:
                logger.error(
                    f"Persistent eval failed fold {fold.fold_id}: {e}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {
                            "generation": generation,
                            "fold_id": fold.fold_id,
                            "worker_idx": worker_idx,
                            "dispatcher": "persistent",
                        },
                    },
                )
                return fold_idx, np.full(n_candidates, float("-inf"), dtype=np.float64)

        fold_results = await asyncio.gather(
            *[_eval_fold(fi, f) for fi, f in enumerate(fold_specs)],
            return_exceptions=True,
        )

        for result in fold_results:
            if isinstance(result, BaseException):
                logger.error(
                    f"Fold eval raised exception: {result}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {"generation": generation, "dispatcher": "persistent"},
                    },
                )
                continue
            fold_idx, scores = result
            if len(scores) == n_candidates:
                all_fold_scores[:, fold_idx] = scores

        return all_fold_scores

    async def dispatch_generation_multi_group(
        self,
        groups: dict[str, tuple[np.ndarray, Path, Path]],
        fold_specs: list[FoldSpec],
        market_data_path: Path,
        cost_model_path: Path,
        generation: int,
        parameter_space: ParameterSpace,
    ) -> dict[str, np.ndarray]:
        """Dispatch ALL groups via persistent workers.

        Groups are batched into a single eval call per fold, distributed
        across workers round-robin.

        Returns:
            dict mapping group_hash -> score matrix (n_candidates, n_folds).
        """
        n_folds = len(fold_specs)

        # Pre-snap candidates per group
        group_param_batches: dict[str, list[dict]] = {}
        for g_hash, (candidates, _spec, _data) in groups.items():
            group_param_batches[g_hash] = [
                decode_candidate(candidates[i], parameter_space)
                for i in range(len(candidates))
            ]

        # Initialize result matrices
        result_matrices: dict[str, np.ndarray] = {}
        for g_hash, (candidates, _, _) in groups.items():
            result_matrices[g_hash] = np.full(
                (len(candidates), n_folds), float("-inf"), dtype=np.float64,
            )

        # Build eval groups list for the worker protocol
        eval_groups = []
        group_id_map: dict[str, str] = {}  # group_id -> g_hash
        for g_hash, (candidates, spec_path, data_path) in groups.items():
            group_id = f"grp_{g_hash[:8]}"
            group_id_map[group_id] = g_hash
            eval_groups.append({
                "group_id": group_id,
                "spec_path": str(spec_path).replace("\\", "/"),
                "data_path": str(data_path).replace("\\", "/"),
                "candidates": group_param_batches[g_hash],
            })

        # Derive data key from first group's enriched data (or market data)
        first_data_path = next(iter(groups.values()))[2]
        data_key = _path_to_data_key(first_data_path)

        # Dispatch per fold
        async def _eval_fold(fold_idx: int, fold: FoldSpec):
            worker_idx = fold_idx % self._pool.n_workers
            try:
                results = await self._pool.eval_on_worker(
                    worker_idx=worker_idx,
                    data_key=data_key,
                    groups=eval_groups,
                    window_start=fold.test_start,
                    window_end=fold.test_end,
                )
                return fold_idx, results
            except Exception as e:
                logger.error(
                    f"Persistent multi-group eval failed fold {fold.fold_id}: {e}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {
                            "generation": generation,
                            "fold_id": fold.fold_id,
                            "dispatcher": "persistent",
                        },
                    },
                )
                return fold_idx, {}

        fold_results = await asyncio.gather(
            *[_eval_fold(fi, f) for fi, f in enumerate(fold_specs)],
            return_exceptions=True,
        )

        for result in fold_results:
            if isinstance(result, BaseException):
                logger.error(
                    f"Multi-group fold eval raised exception: {result}",
                    extra={
                        "component": "optimization.batch_dispatch",
                        "ctx": {"generation": generation, "dispatcher": "persistent"},
                    },
                )
                continue

            fold_idx, group_results = result
            for group_id, scores_list in group_results.items():
                g_hash = group_id_map.get(group_id)
                if g_hash is None:
                    continue
                n_cands = len(groups[g_hash][0])
                scores = np.array(scores_list, dtype=np.float64)
                if len(scores) == n_cands:
                    result_matrices[g_hash][:, fold_idx] = scores

        return result_matrices


def _path_to_data_key(path: Path) -> str:
    """Derive a stable data key from a file path for worker cache addressing.

    Uses ``parent_dir/stem`` to avoid collisions when multiple folds share
    the same filename (e.g. ``fold_0/enriched.arrow`` vs ``fold_1/enriched.arrow``).
    """
    return f"{path.parent.name}_{path.stem}"
