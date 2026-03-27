"""Fast pre-screening to eliminate weak signal groups before full optimization.

Supports two modes:
- H1: Precompute signals at H1 resolution (~920x less data than M1).
  Best for trend/swing strategies where H1 direction correlates with M1 results.
- M1_slice: Use a representative 2-3 month M1 slice.
  Better for scalping/intraday strategies sensitive to execution quality.

The prescreener runs a mini-optimization (few generations) per signal group
and keeps only the top-performing groups by CV objective.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from logging_setup.setup import get_logger
from optimization.fold_manager import FoldManager, compute_cv_objective
from optimization.param_classifier import (
    ParamClassification,
    build_override_spec,
    compute_group_hash,
    compute_signal_hash,
)
from optimization.parameter_space import (
    ParameterSpace,
    extract_params_by_indices,
)
from optimization.signal_cache import SignalCacheManager
from rust_bridge.batch_runner import BatchRunner

logger = get_logger("optimization.prescreener")


@dataclass
class PreScreenResult:
    """Result of a pre-screening pass."""
    surviving_groups: list[str]  # group hashes that survived
    eliminated_count: int
    total_count: int
    elapsed_s: float
    group_scores: dict[str, float] = field(default_factory=dict)
    top_candidates: list[np.ndarray] = field(default_factory=list)  # best vectors for warm-start


class PreScreener:
    """Fast pre-screening to eliminate weak signal groups.

    Runs a quick mini-optimization per signal group using reduced data
    (H1 bars or M1 time-slice) and eliminates groups whose best CV
    objective falls below the survival threshold.
    """

    def __init__(
        self,
        strategy_spec: dict,
        market_data_path: Path,
        config: dict,
        artifacts_dir: Path,
        classification: ParamClassification,
        data_hash: str,
        batch_runner: BatchRunner,
        year_range: tuple[int, int] | None = None,
        cost_model_path: Path | None = None,
    ):
        self._strategy_spec = strategy_spec
        self._market_data_path = Path(market_data_path)
        self._config = config
        self._artifacts_dir = artifacts_dir
        self._classification = classification
        self._data_hash = data_hash
        self._batch_runner = batch_runner
        self._year_range = year_range
        self._cost_model_path = cost_model_path

    async def screen(
        self,
        space: ParameterSpace,
        branches: dict,
        mode: str = "H1",
        m1_slice_months: int = 3,
        n_generations: int = 5,
        survival_ratio: float = 0.2,
    ) -> PreScreenResult:
        """Run pre-screening and return surviving group hashes.

        Args:
            space: Full parameter space definition.
            branches: Branch definitions from detect_branches().
            mode: "H1" for H1-resolution screening, "M1_slice" for
                time-slice screening.
            m1_slice_months: Number of months for M1_slice mode.
            n_generations: Number of mini-optimization generations.
            survival_ratio: Fraction of groups to keep (0.0-1.0).

        Returns:
            PreScreenResult with surviving group hashes and statistics.
        """
        start = time.monotonic()

        # Determine output resolution and year_range for pre-screening data
        if mode == "H1":
            output_resolution = "H1"
            prescreen_year_range = self._year_range
        elif mode == "M1_slice":
            output_resolution = "M1"
            prescreen_year_range = self._compute_slice_year_range(m1_slice_months)
        else:
            raise ValueError(f"Unknown prescreening mode: {mode}")

        # Build signal cache for pre-screening (separate cache dir to avoid
        # collisions with main optimization cache)
        prescreen_cache = SignalCacheManager(
            cache_dir=self._artifacts_dir / "prescreen_cache",
            strategy_spec=self._strategy_spec,
            market_data_path=self._market_data_path,
            data_hash=self._data_hash,
            classification=self._classification,
            session_schedule=self._config.get("sessions"),
            max_entries=256,
            max_cache_bytes=20_000_000_000,
            parallelism=4,
            year_range=prescreen_year_range,
            output_resolution=output_resolution,
        )

        # Enumerate unique signal groups by sampling the parameter space
        group_scores, group_best_candidates = await self._evaluate_groups(
            space=space,
            branches=branches,
            signal_cache=prescreen_cache,
            n_generations=n_generations,
            output_resolution=output_resolution,
            prescreen_year_range=prescreen_year_range,
        )

        total_count = len(group_scores)
        if total_count == 0:
            elapsed = time.monotonic() - start
            return PreScreenResult(
                surviving_groups=[],
                eliminated_count=0,
                total_count=0,
                elapsed_s=elapsed,
            )

        # Rank groups by best CV objective and keep top survival_ratio
        n_survive = max(1, int(total_count * survival_ratio))
        sorted_groups = sorted(
            group_scores.items(), key=lambda kv: kv[1], reverse=True
        )
        surviving = [g_hash for g_hash, _ in sorted_groups[:n_survive]]

        # Collect top candidate vectors from surviving groups for warm-start
        top_candidates = [
            group_best_candidates[g_hash]
            for g_hash in surviving
            if g_hash in group_best_candidates
        ]

        elapsed = time.monotonic() - start

        logger.info(
            f"Pre-screening complete: {n_survive}/{total_count} groups survived "
            f"(mode={mode}, {elapsed:.1f}s)",
            extra={
                "component": "optimization.prescreener",
                "ctx": {
                    "mode": mode,
                    "n_generations": n_generations,
                    "survival_ratio": survival_ratio,
                    "total_groups": total_count,
                    "surviving": n_survive,
                    "top_score": sorted_groups[0][1] if sorted_groups else None,
                    "cutoff_score": sorted_groups[n_survive - 1][1] if sorted_groups else None,
                },
            },
        )

        return PreScreenResult(
            surviving_groups=surviving,
            eliminated_count=total_count - n_survive,
            total_count=total_count,
            elapsed_s=elapsed,
            group_scores=dict(sorted_groups),
            top_candidates=top_candidates,
        )

    async def _evaluate_groups(
        self,
        space: ParameterSpace,
        branches: dict,
        signal_cache: SignalCacheManager,
        n_generations: int,
        output_resolution: str,
        prescreen_year_range: tuple[int, int] | None,
    ) -> tuple[dict[str, float], dict[str, np.ndarray]]:
        """Evaluate all signal groups with mini-optimization.

        Returns:
            Tuple of (group_hash -> best CV score, group_hash -> best candidate vector).
        """
        from optimization.batch_dispatch import OptimizationBatchDispatcher
        from optimization.param_classifier import write_toml_spec

        opt_config = self._config.get("optimization", {})
        cv_lambda = opt_config.get("cv_lambda", 1.5)
        cv_folds = opt_config.get("cv_folds", 5)
        embargo_bars = opt_config.get("embargo_bars", 0)
        batch_size = min(opt_config.get("batch_size", 512), 512)
        cost_model_path = self._cost_model_path or Path(
            self._config.get("pipeline", {}).get(
                "cost_model_path",
                self._artifacts_dir / "cost-model" / "v001.json",
            )
        )

        # Estimate data length for fold construction
        # For H1 mode, data is ~60x smaller than M1
        if output_resolution == "H1":
            # Rough estimate: M1 bars / 60
            raw_estimate = 100000  # conservative default
            try:
                import pyarrow.ipc
                reader = pyarrow.ipc.open_file(str(self._market_data_path))
                total_m1 = sum(
                    reader.get_batch(i).num_rows
                    for i in range(reader.num_record_batches)
                )
                raw_estimate = max(total_m1 // 60, 1000)
            except Exception:
                pass
            data_length = raw_estimate
        else:
            data_length = 100000

        fold_manager = FoldManager(
            data_length=data_length,
            n_folds=cv_folds,
            embargo_bars=embargo_bars,
        )
        fold_specs = fold_manager.get_fold_boundaries()

        dispatcher = OptimizationBatchDispatcher(
            batch_runner=self._batch_runner,
            artifacts_dir=self._artifacts_dir / "prescreen",
            config=self._config,
        )

        # Generate candidate groups by sampling the parameter space
        signal_indices = self._classification.signal_indices
        spec_override_indices = self._classification.spec_override_indices

        # Enumerate unique signal param combinations from the grid
        unique_groups: dict[str, dict] = {}  # group_hash -> signal_params
        rng = np.random.default_rng(42)

        # Sample candidates to discover signal groups
        for _ in range(n_generations):
            candidates = rng.uniform(
                size=(batch_size, space.n_dims),
            )
            # Snap to grid
            for i, p in enumerate(space.parameters):
                if p.step > 0:
                    candidates[:, i] = np.round(
                        candidates[:, i] * (p.max_val - p.min_val) / p.step
                    ) * p.step + p.min_val
                    candidates[:, i] = np.clip(candidates[:, i], p.min_val, p.max_val)

            for c in candidates:
                sig_params = extract_params_by_indices(c, space, signal_indices)
                so_params = extract_params_by_indices(c, space, spec_override_indices)
                g_hash = compute_group_hash(sig_params, so_params)
                if g_hash not in unique_groups:
                    unique_groups[g_hash] = sig_params

        logger.info(
            f"Pre-screening: discovered {len(unique_groups)} unique signal groups",
            extra={"component": "optimization.prescreener"},
        )

        # Evaluate each group with a mini-batch
        group_scores: dict[str, float] = {}
        group_best_candidates: dict[str, np.ndarray] = {}
        gen_spec_dir = self._artifacts_dir / "prescreen" / "specs"
        gen_spec_dir.mkdir(parents=True, exist_ok=True)

        for g_hash, sig_params in unique_groups.items():
            try:
                # Get enriched data from cache
                enriched_path = signal_cache.get_or_compute(sig_params)

                # Build override spec
                override_spec = build_override_spec(
                    base_spec=self._strategy_spec,
                    signal_params=sig_params,
                    spec_override_params={},
                    classification=self._classification,
                )
                spec_path = write_toml_spec(override_spec, gen_spec_dir, g_hash)

                # Generate random candidates for this group
                mini_candidates = rng.uniform(size=(batch_size, space.n_dims))
                for i, p in enumerate(space.parameters):
                    if p.step > 0:
                        mini_candidates[:, i] = np.round(
                            mini_candidates[:, i] * (p.max_val - p.min_val) / p.step
                        ) * p.step + p.min_val
                        mini_candidates[:, i] = np.clip(
                            mini_candidates[:, i], p.min_val, p.max_val
                        )

                # Dispatch evaluation
                fold_score_matrix = await dispatcher.dispatch_generation(
                    candidates=mini_candidates,
                    fold_specs=fold_specs,
                    strategy_spec_path=spec_path,
                    market_data_path=enriched_path,
                    cost_model_path=cost_model_path,
                    generation=0,
                    param_names=space.param_names,
                    parameter_space=space,
                )

                # Compute best CV objective for this group
                cv_scores = np.array([
                    compute_cv_objective(fold_score_matrix[i], cv_lambda)
                    for i in range(len(mini_candidates))
                ])
                best_idx = int(np.argmax(cv_scores))
                best_score = float(cv_scores[best_idx])
                group_scores[g_hash] = best_score
                group_best_candidates[g_hash] = mini_candidates[best_idx].copy()

                logger.debug(
                    f"Pre-screen group {g_hash}: best_cv={best_score:.6f}",
                    extra={
                        "component": "optimization.prescreener",
                        "ctx": {"group_hash": g_hash, "best_cv": best_score},
                    },
                )

            except Exception as e:
                logger.warning(
                    f"Pre-screen group {g_hash} failed: {e}",
                    extra={"component": "optimization.prescreener"},
                )
                # Failed groups get worst score — they'll be eliminated
                group_scores[g_hash] = float("-inf")

        return group_scores, group_best_candidates

    def _compute_slice_year_range(
        self, m1_slice_months: int,
    ) -> tuple[int, int] | None:
        """Compute a year range for M1_slice mode.

        Uses the most recent m1_slice_months of data from the dataset's
        end. Returns a year range that approximately covers the desired
        slice. For sub-year slices, returns the year containing the slice.
        """
        if self._year_range is not None:
            # Slice from the end of the configured year range
            end_year = self._year_range[1]
            # For 3 months, stay within the same year
            if m1_slice_months <= 12:
                return (end_year, end_year)
            start_year = end_year - (m1_slice_months // 12)
            return (start_year, end_year)

        # No year range configured — try to determine from data
        try:
            import pyarrow.ipc
            import pyarrow.compute as pc

            reader = pyarrow.ipc.open_file(str(self._market_data_path))
            table = reader.read_all()
            ts_col = table.column("timestamp")
            ts_max = pc.max(ts_col).as_py()

            if ts_max is None:
                return None

            # Determine unit
            if ts_max > 1e15:
                divisor = 1e6
            elif ts_max > 1e12:
                divisor = 1e3
            else:
                divisor = 1

            from datetime import datetime, timezone
            end_dt = datetime.fromtimestamp(ts_max / divisor, tz=timezone.utc)
            end_year = end_dt.year

            if m1_slice_months <= 12:
                return (end_year, end_year)
            start_year = end_year - (m1_slice_months // 12)
            return (start_year, end_year)

        except Exception:
            return None
