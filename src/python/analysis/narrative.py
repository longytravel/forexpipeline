"""Narrative generator — template-driven backtest summaries (D11).

Generates structured ``NarrativeResult`` from SQLite trade data.
All text is deterministic — derived from computed statistics via templates.
No LLM or stochastic components.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from analysis.metrics_builder import compute_metrics
from analysis.models import AnalysisError, NarrativeResult
from logging_setup.setup import get_logger

logger = get_logger("pipeline.analysis.narrative")

# Session values loaded from contracts/session_schema.toml
_SESSIONS = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]


def generate_narrative(
    backtest_id: str,
    db_path: Path | None = None,
) -> NarrativeResult:
    """Generate a structured narrative for a backtest run.

    Args:
        backtest_id: The backtest run ID (backtest_runs.run_id).
        db_path: Path to SQLite database. Resolved from config if None.

    Returns:
        NarrativeResult with chart-first structure.

    Raises:
        AnalysisError: If the backtest run is not found or data is invalid.
    """
    db_path = _resolve_db_path(db_path)

    logger.info(
        "Generating narrative",
        extra={
            "component": "pipeline.analysis.narrative",
            "ctx": {"backtest_id": backtest_id, "db_path": str(db_path)},
        },
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        run_meta = _load_run_metadata(conn, backtest_id)
        trades = _load_trades(conn, backtest_id)
    finally:
        conn.close()

    metrics = compute_metrics(trades, run_meta)
    session_breakdown = _compute_session_breakdown(trades)
    overview = _generate_overview(metrics, session_breakdown)
    strengths = _identify_strengths(metrics, session_breakdown)
    weaknesses = _identify_weaknesses(metrics, session_breakdown)
    risk_assessment = _assess_risk(metrics)

    result = NarrativeResult(
        overview=overview,
        metrics=metrics,
        strengths=strengths,
        weaknesses=weaknesses,
        session_breakdown=session_breakdown,
        risk_assessment=risk_assessment,
    )

    logger.info(
        "Narrative generated",
        extra={
            "component": "pipeline.analysis.narrative",
            "ctx": {
                "backtest_id": backtest_id,
                "total_trades": metrics["total_trades"],
                "strengths_count": len(strengths),
                "weaknesses_count": len(weaknesses),
            },
        },
    )

    return result


def _resolve_db_path(db_path: Path | None) -> Path:
    """Resolve SQLite database path."""
    if db_path is not None:
        return Path(db_path)
    # Default path for pipeline operations
    return Path("artifacts") / "backtest.db"


def _load_run_metadata(conn: sqlite3.Connection, backtest_id: str) -> dict[str, Any]:
    """Load backtest run metadata from SQLite."""
    row = conn.execute(
        "SELECT run_id, strategy_id, total_trades, started_at, completed_at, status "
        "FROM backtest_runs WHERE run_id = ?",
        (backtest_id,),
    ).fetchone()

    if row is None:
        raise AnalysisError("narrative", f"Backtest run not found: {backtest_id}")

    return dict(row)


def _load_trades(conn: sqlite3.Connection, backtest_id: str) -> list[dict[str, Any]]:
    """Load trade data from SQLite."""
    rows = conn.execute(
        "SELECT trade_id, direction, entry_time, exit_time, entry_price, exit_price, "
        "spread_cost, slippage_cost, pnl_pips, session, lot_size "
        "FROM trades WHERE backtest_run_id = ? ORDER BY entry_time",
        (backtest_id,),
    ).fetchall()

    return [dict(r) for r in rows]


def _compute_session_breakdown(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compute per-session trade count, win rate, and average PnL."""
    breakdown: dict[str, dict[str, Any]] = {}

    for session in _SESSIONS:
        session_trades = [t for t in trades if t.get("session") == session]
        count = len(session_trades)
        if count == 0:
            breakdown[session] = {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0}
            continue

        pnls = [t["pnl_pips"] for t in session_trades]
        wins = sum(1 for p in pnls if p > 0.0)
        avg_pnl = sum(pnls) / count

        breakdown[session] = {
            "trades": count,
            "win_rate": round(wins / count, 4),
            "avg_pnl": round(avg_pnl, 4),
        }

    return breakdown


def _generate_overview(metrics: dict[str, Any], session_breakdown: dict) -> str:
    """Generate chart-first overview: equity shape, drawdown, distribution."""
    total = metrics["total_trades"]
    if total == 0:
        return "No trades were executed during this backtest period."

    # Equity curve shape description
    total_pnl = metrics["total_pnl"]
    if total_pnl > 0:
        trend = "upward-trending"
    elif total_pnl < 0:
        trend = "downward-trending"
    else:
        trend = "flat"

    # Drawdown profile
    max_dd = metrics["max_drawdown_pct"]
    if max_dd < 5:
        dd_desc = "minimal"
    elif max_dd < 15:
        dd_desc = "moderate"
    elif max_dd < 30:
        dd_desc = "significant"
    else:
        dd_desc = "severe"

    # Trade distribution
    active_sessions = [s for s, v in session_breakdown.items() if v["trades"] > 0]
    session_counts = {s: v["trades"] for s, v in session_breakdown.items() if v["trades"] > 0}

    if session_counts:
        dominant = max(session_counts, key=session_counts.get)
        dominant_pct = session_counts[dominant] / total * 100
    else:
        dominant = "unknown"
        dominant_pct = 0.0

    overview = (
        f"The equity curve shows a {trend} pattern across {total} trades "
        f"with {dd_desc} drawdown (max {max_dd:.1f}%). "
        f"Trades are distributed across {len(active_sessions)} session(s), "
        f"with {dominant.replace('_', ' ')} accounting for {dominant_pct:.0f}% of activity. "
        f"Overall profit factor is {metrics['profit_factor']:.2f} "
        f"with a {metrics['win_rate']*100:.1f}% win rate."
    )

    return overview


def _identify_strengths(metrics: dict[str, Any], session_breakdown: dict) -> list[str]:
    """Identify strengths from metrics."""
    strengths: list[str] = []

    if metrics["win_rate"] >= 0.55:
        strengths.append(f"Above-average win rate ({metrics['win_rate']*100:.1f}%)")

    if metrics["profit_factor"] >= 1.5 and metrics["profit_factor"] != float("inf"):
        strengths.append(f"Strong profit factor ({metrics['profit_factor']:.2f})")

    if metrics["max_drawdown_pct"] < 10:
        strengths.append(f"Low maximum drawdown ({metrics['max_drawdown_pct']:.1f}%)")

    if metrics["sharpe_ratio"] > 1.0:
        strengths.append(f"Good risk-adjusted returns (Sharpe {metrics['sharpe_ratio']:.2f})")

    # Check for consistent session performance
    active_sessions = {s: v for s, v in session_breakdown.items() if v["trades"] >= 5}
    if active_sessions:
        profitable_sessions = [s for s, v in active_sessions.items() if v["avg_pnl"] > 0]
        if len(profitable_sessions) >= 3:
            strengths.append(f"Consistent profitability across {len(profitable_sessions)} sessions")

    if not strengths:
        strengths.append("No notable strengths identified from current metrics")

    return strengths


def _identify_weaknesses(metrics: dict[str, Any], session_breakdown: dict) -> list[str]:
    """Identify weaknesses from metrics."""
    weaknesses: list[str] = []

    if metrics["win_rate"] < 0.40:
        weaknesses.append(f"Low win rate ({metrics['win_rate']*100:.1f}%)")

    if 0 < metrics["profit_factor"] < 1.0:
        weaknesses.append(f"Unprofitable (profit factor {metrics['profit_factor']:.2f})")

    if metrics["max_drawdown_pct"] > 25:
        weaknesses.append(f"High maximum drawdown ({metrics['max_drawdown_pct']:.1f}%)")

    if metrics["sharpe_ratio"] < 0.5 and metrics["total_trades"] > 30:
        weaknesses.append(f"Weak risk-adjusted returns (Sharpe {metrics['sharpe_ratio']:.2f})")

    # Check for losing sessions
    active_sessions = {s: v for s, v in session_breakdown.items() if v["trades"] >= 5}
    losing_sessions = [s for s, v in active_sessions.items() if v["avg_pnl"] < 0]
    if losing_sessions:
        names = ", ".join(s.replace("_", " ") for s in losing_sessions)
        weaknesses.append(f"Negative performance in: {names}")

    # Trade clustering check
    total = metrics["total_trades"]
    if total > 0:
        session_counts = {s: v["trades"] for s, v in session_breakdown.items() if v["trades"] > 0}
        if session_counts:
            max_session_pct = max(session_counts.values()) / total
            if max_session_pct > 0.7:
                weaknesses.append("Heavy trade concentration in a single session (>70%)")

    if not weaknesses:
        weaknesses.append("No notable weaknesses identified from current metrics")

    return weaknesses


def _assess_risk(metrics: dict[str, Any]) -> str:
    """Generate overall risk characterization."""
    total = metrics["total_trades"]
    if total == 0:
        return "Insufficient data — no trades executed."

    dd = metrics["max_drawdown_pct"]
    sharpe = metrics["sharpe_ratio"]
    pf = metrics["profit_factor"]

    risk_factors = []

    if dd > 30:
        risk_factors.append("extreme drawdown")
    elif dd > 20:
        risk_factors.append("high drawdown")

    if sharpe < 0:
        risk_factors.append("negative risk-adjusted returns")
    elif sharpe < 0.5 and total > 30:
        risk_factors.append("weak risk-adjusted returns")

    if pf < 1.0 and pf > 0:
        risk_factors.append("negative expectancy")

    if total < 30:
        risk_factors.append("insufficient trade sample")

    if not risk_factors:
        if dd < 10 and sharpe > 1.0 and pf > 1.5:
            return "Low risk profile — controlled drawdown with positive expectancy and strong risk-adjusted returns."
        elif dd < 20 and pf > 1.0:
            return "Moderate risk profile — acceptable drawdown with positive expectancy."
        else:
            return "Moderate risk profile — metrics within acceptable ranges but monitor closely."

    return f"Elevated risk — factors: {', '.join(risk_factors)}. Requires careful review before pipeline progression."
