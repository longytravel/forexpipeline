"""Shared metrics computation — single source of truth (Architecture D11).

Both the narrative generator and evidence pack assembler MUST call
``compute_metrics()`` from this module. Never compute metrics independently.
"""
from __future__ import annotations

import math
from typing import Any


def compute_metrics(trades: list[dict[str, Any]], run_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute backtest summary metrics from trade data.

    Args:
        trades: List of trade dicts with at least ``pnl_pips`` key.
                Optional keys: ``entry_time``, ``exit_time``, ``session``.
        run_meta: Optional run metadata dict (currently unused, reserved
                  for future enrichment).

    Returns:
        Dict with keys: win_rate, profit_factor, sharpe_ratio,
        max_drawdown_pct, total_trades, avg_trade_pnl, total_pnl,
        avg_trade_duration.
    """
    total_trades = len(trades)

    if total_trades == 0:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "total_trades": 0,
            "avg_trade_pnl": 0.0,
            "total_pnl": 0.0,
            "avg_trade_duration": 0.0,
        }

    pnls = [t["pnl_pips"] for t in trades]
    total_pnl = sum(pnls)

    # Use strict inequality: breakeven trades (pnl == 0) are neither win nor loss
    wins = [p for p in pnls if p > 0.0]
    losses = [p for p in pnls if p < 0.0]

    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    avg_trade_pnl = total_pnl / total_trades

    # Profit factor: sum of wins / abs(sum of losses)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Sharpe ratio: mean(pnl) / std(pnl) * sqrt(total_trades)
    sharpe_ratio = _compute_sharpe(pnls)

    # Max drawdown as percentage of peak equity
    max_drawdown_pct = _compute_max_drawdown_pct(pnls)

    # Average trade duration in hours (if entry/exit times available)
    avg_trade_duration = _compute_avg_duration(trades)

    return {
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if math.isfinite(profit_factor) else profit_factor,
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "total_trades": total_trades,
        "avg_trade_pnl": round(avg_trade_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "avg_trade_duration": round(avg_trade_duration, 2),
    }


def _compute_sharpe(pnls: list[float]) -> float:
    """Compute Sharpe ratio from trade PnL list.

    Uses trade-level Sharpe: mean / stdev * sqrt(N).
    Returns 0.0 when standard deviation is zero.
    """
    n = len(pnls)
    if n < 2:
        return 0.0

    mean = sum(pnls) / n
    variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    std = math.sqrt(variance)

    if std == 0.0:
        return 0.0

    return (mean / std) * math.sqrt(n)


def _compute_max_drawdown_pct(pnls: list[float]) -> float:
    """Compute max drawdown as percentage of peak cumulative equity.

    Tracks peak-to-trough drawdown from cumulative PnL curve.
    Returns 0.0 when no drawdown exists.
    """
    if not pnls:
        return 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd_pct = 0.0

    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        if peak > 0:
            dd_pct = (peak - cumulative) / peak * 100.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    return max_dd_pct


def _compute_avg_duration(trades: list[dict[str, Any]]) -> float:
    """Compute average trade duration in hours from entry/exit times.

    Handles ISO 8601 string timestamps. Returns 0.0 if timestamps
    are not available.
    """
    from datetime import datetime

    durations = []
    for t in trades:
        entry = t.get("entry_time")
        exit_ = t.get("exit_time")
        if entry is None or exit_ is None:
            continue
        try:
            if isinstance(entry, str) and isinstance(exit_, str):
                et = datetime.fromisoformat(entry.replace("Z", "+00:00"))
                xt = datetime.fromisoformat(exit_.replace("Z", "+00:00"))
                delta = (xt - et).total_seconds() / 3600.0
                if delta >= 0:
                    durations.append(delta)
        except (ValueError, TypeError):
            continue

    if not durations:
        return 0.0

    return sum(durations) / len(durations)
