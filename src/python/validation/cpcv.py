"""Combinatorial Purged Cross-Validation (CPCV) validator (Story 5.4, Task 4).

Implements CPCV with Probability of Backtest Overfitting (PBO) computation
per Bailey et al.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.special import comb as scipy_comb

from logging_setup.setup import get_logger
from validation.config import CPCVConfig

logger = get_logger("validation.cpcv")


@dataclass
class CombinationResult:
    combination_id: int
    train_groups: list[int]
    test_groups: list[int]
    oos_sharpe: float
    oos_pf: float
    oos_pnl: float


@dataclass
class CPCVResult:
    combinations: list[CombinationResult]
    pbo: float
    pbo_gate_passed: bool
    mean_oos_sharpe: float
    artifact_path: Path | None = None


def generate_cpcv_combinations(
    n_groups: int, k_test: int
) -> list[tuple[list[int], list[int]]]:
    """Generate all C(n, k) train/test group combinations.

    Returns list of (train_group_indices, test_group_indices) tuples.
    """
    all_groups = list(range(n_groups))
    result = []
    for test_combo in combinations(all_groups, k_test):
        test_groups = list(test_combo)
        train_groups = [g for g in all_groups if g not in test_groups]
        result.append((train_groups, test_groups))
    return result


def compute_pbo(oos_returns: list[float], is_returns: list[float]) -> float:
    """Compute Probability of Backtest Overfitting per Bailey et al.

    For single-candidate CPCV, PBO measures whether combinations that
    look good in-sample tend to look bad out-of-sample (overfitting signal).

    Algorithm:
    1. Identify IS-best combinations (IS Sharpe >= IS median)
    2. Check what fraction of those IS-best are OOS-worst (OOS < OOS median)
    3. PBO = that fraction. High PBO = IS winners are OOS losers = overfit.

    Both IS and OOS returns are required. If IS returns are missing or
    identical to OOS (indicating a data leak), falls back to OOS-only
    median test with a warning.
    """
    if len(oos_returns) < 2:
        return 0.0

    n = len(oos_returns)
    if len(is_returns) != n:
        # Mismatched lengths — fall back to OOS-only
        median_oos = float(np.median(oos_returns))
        below_median = sum(1 for r in oos_returns if r < median_oos)
        return below_median / n

    # Check for data leak: IS and OOS identical
    is_arr = np.array(is_returns)
    oos_arr = np.array(oos_returns)
    if np.allclose(is_arr, oos_arr):
        logger.warning(
            "IS and OOS returns are identical — possible data leak in PBO input",
            extra={"component": "validation.cpcv"},
        )
        median_oos = float(np.median(oos_returns))
        below_median = sum(1 for r in oos_returns if r < median_oos)
        return below_median / n

    # Proper IS-vs-OOS ranking PBO
    is_median = float(np.median(is_returns))
    oos_median = float(np.median(oos_returns))

    # IS-best = combinations where IS performance >= IS median
    is_best_indices = [i for i in range(n) if is_returns[i] >= is_median]
    if not is_best_indices:
        return 0.0

    # Count how many IS-best are OOS-worst (below OOS median)
    overfit_count = sum(1 for i in is_best_indices if oos_returns[i] < oos_median)
    pbo = overfit_count / len(is_best_indices)
    return pbo


def run_cpcv(
    candidate: dict,
    market_data_path: Path,
    strategy_spec: dict,
    cost_model: dict,
    config: CPCVConfig,
    dispatcher,  # BatchDispatcher protocol
    seed: int,
    data_length: int | None = None,
) -> CPCVResult:
    """Run Combinatorial Purged Cross-Validation.

    Dispatches each combination to evaluator. Applies purge/embargo
    between adjacent train/test groups. Computes PBO.
    """
    combos = generate_cpcv_combinations(config.n_groups, config.k_test_groups)

    if data_length is None:
        import pyarrow.ipc
        reader = pyarrow.ipc.open_file(str(market_data_path))
        table = reader.read_all()
        data_length = len(table)

    group_size = data_length // config.n_groups
    rng = np.random.Generator(np.random.PCG64(seed))

    combination_results = []
    oos_returns = []
    is_returns = []

    for combo_idx, (train_groups, test_groups) in enumerate(combos):
        # Calculate bar ranges for train and test groups
        train_ranges = []
        for g in train_groups:
            start = g * group_size
            end = min((g + 1) * group_size, data_length)
            train_ranges.append((start, end))

        test_ranges = []
        for g in test_groups:
            start = g * group_size
            end = min((g + 1) * group_size, data_length)
            test_ranges.append((start, end))

        # Apply purge/embargo between adjacent train/test groups
        # (purge bars around train/test boundaries)
        purged_train_ranges = _apply_purge_embargo(
            train_ranges, test_ranges, config.purge_bars, config.embargo_bars
        )

        if hasattr(dispatcher, 'evaluate_candidate'):
            # Evaluate each non-contiguous test group segment separately
            # to avoid contaminating test with intervening train data
            seg_sharpes, seg_pfs, seg_pnls, seg_weights = [], [], [], []
            for t_start, t_end in test_ranges:
                seg_metrics = dispatcher.evaluate_candidate(
                    candidate, market_data_path, strategy_spec, cost_model,
                    window_start=t_start,
                    window_end=t_end,
                    seed=seed + combo_idx,
                )
                seg_len = t_end - t_start
                seg_sharpes.append(seg_metrics.get("sharpe", 0.0))
                seg_pfs.append(seg_metrics.get("profit_factor", 0.0))
                seg_pnls.append(seg_metrics.get("net_pnl", 0.0))
                seg_weights.append(seg_len)

            # Length-weighted aggregate across test segments
            total_w = sum(seg_weights) or 1
            oos_metrics = {
                "sharpe": sum(s * w for s, w in zip(seg_sharpes, seg_weights)) / total_w,
                "profit_factor": sum(p * w for p, w in zip(seg_pfs, seg_weights)) / total_w,
                "net_pnl": sum(seg_pnls),
            }

            # Evaluate IS (train) performance using purged train ranges
            is_seg_sharpes, is_seg_weights = [], []
            for tr_start, tr_end in purged_train_ranges:
                is_seg = dispatcher.evaluate_candidate(
                    candidate, market_data_path, strategy_spec, cost_model,
                    window_start=tr_start,
                    window_end=tr_end,
                    seed=seed + combo_idx + 10000,
                )
                is_seg_sharpes.append(is_seg.get("sharpe", 0.0))
                is_seg_weights.append(tr_end - tr_start)
            is_total_w = sum(is_seg_weights) or 1
            is_sharpe = sum(s * w for s, w in zip(is_seg_sharpes, is_seg_weights)) / is_total_w
        else:
            oos_metrics = {"sharpe": 0.0, "profit_factor": 0.0, "net_pnl": 0.0}
            is_sharpe = 0.0

        oos_sharpe = oos_metrics.get("sharpe", 0.0)
        oos_pf = oos_metrics.get("profit_factor", 0.0)
        oos_pnl = oos_metrics.get("net_pnl", 0.0)

        combination_results.append(CombinationResult(
            combination_id=combo_idx,
            train_groups=train_groups,
            test_groups=test_groups,
            oos_sharpe=oos_sharpe,
            oos_pf=oos_pf,
            oos_pnl=oos_pnl,
        ))
        oos_returns.append(oos_sharpe)
        is_returns.append(is_sharpe)

        if combo_idx % 20 == 0:
            logger.info(
                f"CPCV combination {combo_idx}/{len(combos)}",
                extra={
                    "component": "validation.cpcv",
                    "ctx": {"combo_idx": combo_idx, "total": len(combos)},
                },
            )

    pbo = compute_pbo(oos_returns, is_returns)
    mean_oos_sharpe = float(np.mean(oos_returns)) if oos_returns else 0.0
    pbo_gate_passed = pbo <= config.pbo_red_threshold

    logger.info(
        f"CPCV complete: PBO={pbo:.3f}, gate={'PASS' if pbo_gate_passed else 'FAIL'}",
        extra={
            "component": "validation.cpcv",
            "ctx": {
                "pbo": pbo,
                "threshold": config.pbo_red_threshold,
                "n_combinations": len(combos),
                "mean_oos_sharpe": mean_oos_sharpe,
            },
        },
    )

    return CPCVResult(
        combinations=combination_results,
        pbo=pbo,
        pbo_gate_passed=pbo_gate_passed,
        mean_oos_sharpe=mean_oos_sharpe,
    )


def _apply_purge_embargo(
    train_ranges: list[tuple[int, int]],
    test_ranges: list[tuple[int, int]],
    purge_bars: int,
    embargo_bars: int,
) -> list[tuple[int, int]]:
    """Apply purge/embargo gaps to train ranges near test boundaries."""
    if not test_ranges:
        return train_ranges

    # Build set of bars to exclude (purge before test, embargo after test)
    excluded = set()
    for test_start, test_end in test_ranges:
        # Purge: bars before test start
        for b in range(max(0, test_start - purge_bars), test_start):
            excluded.add(b)
        # Embargo: bars after test end
        for b in range(test_end, test_end + embargo_bars):
            excluded.add(b)

    # Filter train ranges
    purged = []
    for start, end in train_ranges:
        # Find contiguous segments not in excluded
        seg_start = None
        for b in range(start, end):
            if b not in excluded:
                if seg_start is None:
                    seg_start = b
            else:
                if seg_start is not None:
                    purged.append((seg_start, b))
                    seg_start = None
        if seg_start is not None:
            purged.append((seg_start, end))

    return purged
