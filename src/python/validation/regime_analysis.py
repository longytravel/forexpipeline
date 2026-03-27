"""Regime analyzer — volatility x session cross-tabulation (Story 5.4, Task 7).

V1 implements volatility tercile x forex session cross-tabulation.
Python-only — operates on trade results + market data, no Rust dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from logging_setup.setup import get_logger
from validation.config import RegimeConfig

logger = get_logger("validation.regime_analysis")


@dataclass
class RegimeBucket:
    volatility: str  # "low", "medium", "high"
    session: str  # "asian", "london", etc.
    trade_count: int
    win_rate: float
    avg_pnl: float
    sharpe: float
    sufficient: bool  # trade_count >= min_trades_per_bucket


@dataclass
class RegimeResult:
    buckets: list[RegimeBucket]
    sufficient_buckets: int
    total_buckets: int
    weakest_regime: str  # "volatility_session" with lowest sharpe among sufficient
    artifact_path: Path | None = None


def classify_regimes(
    market_data: pa.Table,
    config: RegimeConfig,
) -> pa.Table:
    """Add volatility_tercile column to market data.

    Uses ATR-based volatility classification:
    - Compute per-bar true range (high - low, or ATR proxy)
    - Rolling window ATR (e.g., 1440-bar = 1 day)
    - Classify into terciles based on quantiles from config
    """
    if len(market_data) == 0:
        return market_data

    high = market_data.column("high").to_numpy()
    low = market_data.column("low").to_numpy()
    close = market_data.column("close").to_numpy()

    # True range
    tr = high - low  # Simplified TR for M1 bars
    if len(close) > 1:
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]
        tr = np.maximum(tr, np.abs(high - prev_close))
        tr = np.maximum(tr, np.abs(low - prev_close))

    # Rolling ATR (1440-bar window for M1 = 1 day)
    atr_window = min(1440, len(tr))
    atr = np.convolve(tr, np.ones(atr_window) / atr_window, mode='same')

    # Classify into terciles
    q_low, q_high = np.quantile(atr, config.volatility_quantiles)
    labels = np.where(atr <= q_low, "low",
             np.where(atr <= q_high, "medium", "high"))

    # Add column to table
    vol_col = pa.array(labels, type=pa.utf8())
    return market_data.append_column("volatility_tercile", vol_col)


def run_regime_analysis(
    trade_results: pa.Table,
    market_data: pa.Table,
    config: RegimeConfig,
) -> RegimeResult:
    """Cross-tabulate performance by volatility tercile x session.

    Per bucket: trade count, win rate, avg PnL, Sharpe.
    Flags buckets with trade_count < min_trades_per_bucket as insufficient.
    """
    # Classify market data into volatility regimes
    classified_data = classify_regimes(market_data, config)

    # Get trade data
    if len(trade_results) == 0:
        return RegimeResult(buckets=[], sufficient_buckets=0, total_buckets=0, weakest_regime="none")

    # Extract trade entry times and PnL
    pnl_col = _get_pnl(trade_results)
    entry_times = None
    if "entry_time" in trade_results.column_names:
        entry_times = trade_results.column("entry_time").to_numpy()

    # Map trades to sessions
    trade_sessions = _get_trade_sessions(trade_results)

    # Map trades to volatility regimes
    trade_volatility = _get_trade_volatility(
        trade_results, classified_data, entry_times
    )

    # Build cross-tabulation
    buckets = []
    volatility_levels = ["low", "medium", "high"]
    sessions = config.sessions

    for vol in volatility_levels:
        for sess in sessions:
            mask = (trade_volatility == vol) & (trade_sessions == sess)
            bucket_pnl = pnl_col[mask]
            count = int(np.sum(mask))

            if count == 0:
                buckets.append(RegimeBucket(
                    volatility=vol, session=sess, trade_count=0,
                    win_rate=0.0, avg_pnl=0.0, sharpe=0.0,
                    sufficient=False,
                ))
                continue

            wins = int(np.sum(bucket_pnl > 0))
            win_rate = wins / count
            avg_pnl = float(np.mean(bucket_pnl))
            std_pnl = float(np.std(bucket_pnl, ddof=1)) if count > 1 else 1.0
            sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0.0
            sufficient = count >= config.min_trades_per_bucket

            buckets.append(RegimeBucket(
                volatility=vol, session=sess, trade_count=count,
                win_rate=win_rate, avg_pnl=avg_pnl, sharpe=sharpe,
                sufficient=sufficient,
            ))

    sufficient_buckets = sum(1 for b in buckets if b.sufficient)
    total_buckets = len(buckets)

    # Find weakest regime among sufficient buckets
    sufficient_list = [b for b in buckets if b.sufficient]
    if sufficient_list:
        weakest = min(sufficient_list, key=lambda b: b.sharpe)
        weakest_regime = f"{weakest.volatility}_{weakest.session}"
    else:
        weakest_regime = "none"

    logger.info(
        f"Regime analysis: {sufficient_buckets}/{total_buckets} sufficient buckets, "
        f"weakest={weakest_regime}",
        extra={
            "component": "validation.regime_analysis",
            "ctx": {
                "sufficient": sufficient_buckets,
                "total": total_buckets,
                "weakest": weakest_regime,
            },
        },
    )

    return RegimeResult(
        buckets=buckets,
        sufficient_buckets=sufficient_buckets,
        total_buckets=total_buckets,
        weakest_regime=weakest_regime,
    )


def _get_pnl(trades: pa.Table) -> np.ndarray:
    if "pnl_pips" in trades.column_names:
        return trades.column("pnl_pips").to_numpy()
    if "pnl" in trades.column_names:
        return trades.column("pnl").to_numpy()
    # Check for any float column as last resort
    for name in trades.column_names:
        col = trades.column(name)
        if pa.types.is_floating(col.type):
            return col.to_numpy()
    return np.zeros(len(trades))


def _get_trade_sessions(trades: pa.Table) -> np.ndarray:
    if "entry_session" in trades.column_names:
        return np.array(trades.column("entry_session").to_pylist())
    return np.array(["unknown"] * len(trades))


def _get_trade_volatility(
    trades: pa.Table,
    classified_data: pa.Table,
    entry_times: np.ndarray | None,
) -> np.ndarray:
    """Map each trade to its volatility regime based on entry time."""
    n_trades = len(trades)
    if entry_times is None or "volatility_tercile" not in classified_data.column_names:
        return np.array(["medium"] * n_trades)

    vol_labels = classified_data.column("volatility_tercile").to_pylist()
    if "timestamp" in classified_data.column_names:
        timestamps = classified_data.column("timestamp").to_numpy()
    else:
        timestamps = np.arange(len(classified_data))

    # For each trade, find the closest market data bar
    result = []
    for et in entry_times:
        idx = np.searchsorted(timestamps, et, side="right") - 1
        idx = max(0, min(idx, len(vol_labels) - 1))
        result.append(vol_labels[idx])

    return np.array(result)
