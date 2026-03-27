"""Walk-forward rolling OOS validator (Story 5.4, Task 3).

Fixed-candidate rolling out-of-sample evaluation. Candidate parameters
are held constant across all windows — this is NOT walk-forward re-optimization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from logging_setup.setup import get_logger
from validation.config import WalkForwardConfig

logger = get_logger("validation.walk_forward")


@dataclass
class WindowSpec:
    window_id: int
    train_start: int  # bar index
    train_end: int
    test_start: int
    test_end: int
    purge_start: int
    purge_end: int


@dataclass
class WindowResult:
    window_id: int
    oos_sharpe: float
    oos_pf: float
    oos_drawdown: float
    oos_trades: int
    oos_pnl: float
    is_sharpe: float  # in-sample sharpe for divergence detection
    is_pf: float = 0.0  # in-sample profit factor for AC9


@dataclass
class WalkForwardResult:
    windows: list[WindowResult]
    aggregate_sharpe: float
    aggregate_pf: float
    is_oos_divergence: float  # ratio of IS to OOS sharpe (AC #9)
    is_oos_pf_divergence: float = 0.0  # ratio of IS to OOS profit factor (AC #9)
    suspicious: bool = False  # auto-flagged if divergence exceeds threshold
    artifact_path: Path | None = None
    window_specs: list[WindowSpec] | None = None  # train/test boundaries for AC12


def generate_walk_forward_windows(
    data_length: int, config: WalkForwardConfig
) -> list[WindowSpec]:
    """Compute train/test boundaries with purge/embargo gaps.

    Creates N rolling windows where:
    - Each window has train_ratio of usable data as training
    - Purge gap between train end and test start
    - Embargo gap after test end (consumed from next window's space)
    - Temporal ordering enforced: train ALWAYS before test
    """
    n = config.n_windows
    purge = config.purge_bars
    embargo = config.embargo_bars

    if data_length <= 0:
        return []

    # Total overhead per window boundary
    gap = purge + embargo

    # Each window needs: train + purge + test + embargo
    # We slide the window, overlapping train portions
    # Step size = (data_length - initial_train) / n_windows
    total_usable = data_length - gap * n
    if total_usable <= 0:
        logger.warning(
            f"Data length {data_length} too short for {n} windows with purge={purge}, embargo={embargo}",
            extra={"component": "validation.walk_forward"},
        )
        return []

    window_size = data_length // n
    windows = []

    for i in range(n):
        # Anchored walk-forward: train starts at 0, grows with each window
        # Test window slides forward
        test_end = min((i + 1) * window_size, data_length)
        test_start = i * window_size + int(window_size * config.train_ratio)

        # Purge gap before test
        purge_end = test_start
        purge_start = max(0, purge_end - purge)

        # Train ends before purge
        train_end = purge_start
        train_start = 0  # anchored

        # Adjust test_start to account for embargo from purge end
        actual_test_start = purge_end + embargo
        if actual_test_start >= test_end:
            continue

        windows.append(WindowSpec(
            window_id=i,
            train_start=train_start,
            train_end=train_end,
            test_start=actual_test_start,
            test_end=test_end,
            purge_start=purge_start,
            purge_end=purge_end,
        ))

    return windows


def run_walk_forward(
    candidate: dict,
    market_data_path: Path,
    strategy_spec: dict,
    cost_model: dict,
    config: WalkForwardConfig,
    dispatcher,  # BatchDispatcher protocol
    seed: int,
    data_length: int | None = None,
) -> WalkForwardResult:
    """Run walk-forward validation on a fixed candidate.

    Dispatches each window's test segment to Rust evaluator via dispatcher.
    Returns per-window metrics + aggregate.
    """
    if data_length is None:
        # If not provided, try to determine from file
        import pyarrow.ipc
        reader = pyarrow.ipc.open_file(str(market_data_path))
        table = reader.read_all()
        data_length = len(table)

    windows = generate_walk_forward_windows(data_length, config)
    if not windows:
        return WalkForwardResult(
            windows=[], aggregate_sharpe=0.0, aggregate_pf=0.0,
            is_oos_divergence=0.0,
        )

    rng = np.random.Generator(np.random.PCG64(seed))
    window_results = []

    for w in windows:
        logger.info(
            f"Walk-forward window {w.window_id}: test [{w.test_start}:{w.test_end}]",
            extra={
                "component": "validation.walk_forward",
                "ctx": {
                    "window_id": w.window_id,
                    "train_range": [w.train_start, w.train_end],
                    "test_range": [w.test_start, w.test_end],
                },
            },
        )

        # Dispatch to evaluator for IS (train) and OOS (test) segments
        # The dispatcher evaluates the candidate on the specified data range
        if hasattr(dispatcher, 'evaluate_candidate'):
            is_metrics = dispatcher.evaluate_candidate(
                candidate, market_data_path, strategy_spec, cost_model,
                window_start=w.train_start, window_end=w.train_end,
                seed=seed + w.window_id,
            )
            oos_metrics = dispatcher.evaluate_candidate(
                candidate, market_data_path, strategy_spec, cost_model,
                window_start=w.test_start, window_end=w.test_end,
                seed=seed + w.window_id + 1000,
            )
        else:
            # Fallback for mock dispatchers
            is_metrics = {"sharpe": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "trade_count": 0, "net_pnl": 0.0}
            oos_metrics = {"sharpe": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "trade_count": 0, "net_pnl": 0.0}

        window_results.append(WindowResult(
            window_id=w.window_id,
            oos_sharpe=oos_metrics.get("sharpe", 0.0),
            oos_pf=oos_metrics.get("profit_factor", 0.0),
            oos_drawdown=oos_metrics.get("max_drawdown", 0.0),
            oos_trades=oos_metrics.get("trade_count", 0),
            oos_pnl=oos_metrics.get("net_pnl", 0.0),
            is_sharpe=is_metrics.get("sharpe", 0.0),
            is_pf=is_metrics.get("profit_factor", 0.0),
        ))

    # Aggregate metrics
    oos_sharpes = [w.oos_sharpe for w in window_results]
    oos_pfs = [w.oos_pf for w in window_results]
    is_sharpes = [w.is_sharpe for w in window_results]

    agg_sharpe = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    agg_pf = float(np.mean(oos_pfs)) if oos_pfs else 0.0

    # IS vs OOS divergence (AC #9) — Sharpe ratio
    mean_is = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    is_oos_divergence = (mean_is / agg_sharpe) if agg_sharpe != 0.0 else 0.0

    # IS vs OOS divergence — Profit Factor (AC #9)
    is_pfs = [w.is_pf for w in window_results]
    mean_is_pf = float(np.mean(is_pfs)) if is_pfs else 0.0
    is_oos_pf_divergence = (mean_is_pf / agg_pf) if agg_pf != 0.0 else 0.0

    # Auto-flag suspicious performance: IS >> OOS (ratio > 2.0 = suspicious)
    suspicious = abs(is_oos_divergence) > 2.0 or abs(is_oos_pf_divergence) > 2.0

    return WalkForwardResult(
        windows=window_results,
        aggregate_sharpe=agg_sharpe,
        aggregate_pf=agg_pf,
        is_oos_divergence=is_oos_divergence,
        is_oos_pf_divergence=is_oos_pf_divergence,
        suspicious=suspicious,
        window_specs=windows,
    )
