"""Anomaly detector — deterministic checks on backtest results (D11).

Anomaly flags are strictly informational. They NEVER raise exceptions
or return error codes that could block pipeline progression (AC #7).

Thresholds are loaded from a config dict, not hardcoded in checker functions.
Default thresholds from architecture D11 anomaly table.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from numbers import Integral
from pathlib import Path
from typing import Any

from analysis.models import AnalysisError, AnomalyFlag, AnomalyReport, AnomalyType, Severity
from logging_setup.setup import get_logger

logger = get_logger("pipeline.analysis.anomaly_detector")

# Default thresholds from architecture D11 anomaly table.
# Can be overridden via config_loader in future.
ANOMALY_THRESHOLDS: dict[str, Any] = {
    "low_trade_count": 30,
    "zero_trade_window_years": 2,
    "perfect_equity_max_dd_pips": 5.0,
    "perfect_equity_min_trades": 100,
    "extreme_profit_factor": 5.0,
    "trade_clustering_pct": 0.50,
    "win_rate_high": 0.90,
    "win_rate_low": 0.20,
    "win_rate_min_trades": 50,
}


def detect_anomalies(
    backtest_id: str,
    db_path: Path | None = None,
    thresholds: dict[str, Any] | None = None,
) -> AnomalyReport:
    """Run all anomaly checks on a backtest run.

    Args:
        backtest_id: The backtest run ID.
        db_path: Path to SQLite database.
        thresholds: Optional override for default thresholds.

    Returns:
        AnomalyReport with all detected anomalies (may be empty).
    """
    db_path = _resolve_db_path(db_path)
    cfg = {**ANOMALY_THRESHOLDS, **(thresholds or {})}

    logger.info(
        "Running anomaly detection",
        extra={
            "component": "pipeline.analysis.anomaly_detector",
            "ctx": {"backtest_id": backtest_id},
        },
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        run_meta = _load_run_metadata(conn, backtest_id)
        trades = _load_trades(conn, backtest_id)
    finally:
        conn.close()

    anomalies: list[AnomalyFlag] = []

    # Run each check; None means no anomaly detected
    checkers = [
        _check_low_trade_count(trades, run_meta, cfg),
        _check_zero_trade_windows(trades, run_meta, cfg),
        _check_perfect_equity(trades, cfg),
        _check_extreme_profit_factor(trades, cfg),
        _check_trade_clustering(trades, cfg),
        _check_win_rate_extremes(trades, cfg),
        _check_sensitivity_cliff(backtest_id, db_path),
        _check_dsr_below_threshold(backtest_id, db_path),
        _check_pbo_high_probability(backtest_id, db_path),
    ]

    for result in checkers:
        if result is not None:
            anomalies.append(result)

    logger.info(
        "Anomaly detection complete",
        extra={
            "component": "pipeline.analysis.anomaly_detector",
            "ctx": {
                "backtest_id": backtest_id,
                "anomaly_count": len(anomalies),
                "anomaly_types": [a.type.value for a in anomalies],
            },
        },
    )

    return AnomalyReport(
        backtest_id=backtest_id,
        anomalies=anomalies,
        run_timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _resolve_db_path(db_path: Path | None) -> Path:
    """Resolve SQLite database path."""
    if db_path is not None:
        return Path(db_path)
    return Path("artifacts") / "backtest.db"


def _load_run_metadata(conn: sqlite3.Connection, backtest_id: str) -> dict[str, Any]:
    """Load backtest run metadata."""
    row = conn.execute(
        "SELECT run_id, strategy_id, total_trades, started_at, completed_at "
        "FROM backtest_runs WHERE run_id = ?",
        (backtest_id,),
    ).fetchone()

    if row is None:
        raise AnalysisError(
            "anomaly_detector",
            f"Backtest run not found: {backtest_id}",
        )

    return dict(row)


def _load_trades(conn: sqlite3.Connection, backtest_id: str) -> list[dict[str, Any]]:
    """Load trade data for anomaly checks."""
    rows = conn.execute(
        "SELECT trade_id, direction, entry_time, exit_time, "
        "pnl_pips, session, lot_size "
        "FROM trades WHERE backtest_run_id = ? ORDER BY entry_time",
        (backtest_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Individual anomaly checkers
# ---------------------------------------------------------------------------


def _check_low_trade_count(
    trades: list[dict], run_meta: dict, cfg: dict,
) -> AnomalyFlag | None:
    """< threshold trades over backtest period -> WARNING."""
    threshold = cfg["low_trade_count"]
    count = len(trades)

    if count >= threshold:
        return None

    period = _estimate_period_years(run_meta)
    return AnomalyFlag(
        type=AnomalyType.LOW_TRADE_COUNT,
        severity=Severity.WARNING,
        description=(
            f"Only {count} trades over backtest period "
            f"(< {threshold} threshold)"
        ),
        evidence={
            "trade_count": count,
            "period_years": period,
            "threshold": threshold,
        },
        recommendation=(
            "Consider whether strategy filters are too restrictive "
            "or data coverage is insufficient"
        ),
    )


def _parse_entry_time(entry: Any) -> datetime | None:
    """Parse an ``entry_time`` value into a timezone-aware UTC datetime.

    Accepts both representations used by the pipeline:
      * ISO 8601 string (as stored in SQLite ``trades.entry_time``).
      * int64 epoch timestamp (as emitted by the Rust backtester into
        ``trade-log.arrow`` — see arrow_schemas.toml). The unit is
        auto-detected (s / ms / us / ns) because the Rust backtester
        forwards whatever unit the input market-data uses; this mirrors
        the auto-detection in ``orchestrator/signal_precompute.py``.

    Returns ``None`` if the value is missing or unparseable. This defensive
    handling prevents the bug where int64 microseconds were silently treated
    as ISO strings, bucketing all trades into 1970-01.
    """
    if entry is None:
        return None
    # Integer epoch timestamp (Arrow int64 path).
    # Note: bool is a subclass of int; explicitly reject it.
    if isinstance(entry, Integral) and not isinstance(entry, bool):
        try:
            v = int(entry)
            abs_v = abs(v)
            if abs_v > 10**17:
                seconds, remainder = divmod(v, 1_000_000_000)
                micros = remainder // 1_000
            elif abs_v > 10**14:
                seconds, micros = divmod(v, 1_000_000)
            elif abs_v > 10**11:
                seconds, millis = divmod(v, 1_000)
                micros = millis * 1_000
            else:
                seconds, micros = v, 0
            return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
                microsecond=micros,
            )
        except (OverflowError, OSError, ValueError):
            return None
    # ISO 8601 string (SQLite path).
    if isinstance(entry, str):
        try:
            return datetime.fromisoformat(entry.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def _check_zero_trade_windows(
    trades: list[dict], run_meta: dict, cfg: dict,
) -> AnomalyFlag | None:
    """0 trades in any N-year window -> ERROR."""
    window_years = cfg["zero_trade_window_years"]

    if not trades:
        # If there are no trades at all, low_trade_count will catch it
        return None

    # Parse entry_time timestamps (handles ISO strings and int64 microseconds).
    timestamps: list[datetime] = []
    for t in trades:
        parsed = _parse_entry_time(t.get("entry_time"))
        if parsed is not None:
            timestamps.append(parsed)

    if len(timestamps) < 2:
        return None

    timestamps.sort()

    # Check for gaps >= window_years between consecutive trades
    window_seconds = window_years * 365.25 * 24 * 3600
    for i in range(1, len(timestamps)):
        gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
        if gap >= window_seconds:
            return AnomalyFlag(
                type=AnomalyType.ZERO_TRADES,
                severity=Severity.ERROR,
                description=(
                    f"No trades for {gap / (365.25 * 24 * 3600):.1f} years "
                    f"between {timestamps[i-1].isoformat()} and {timestamps[i].isoformat()} "
                    f"(>{window_years}-year window threshold)"
                ),
                evidence={
                    "gap_start": timestamps[i - 1].isoformat(),
                    "gap_end": timestamps[i].isoformat(),
                    "gap_years": round(gap / (365.25 * 24 * 3600), 2),
                    "window_threshold_years": window_years,
                },
                recommendation=(
                    "Investigate why no trades were generated during this period. "
                    "Check data coverage and strategy filter conditions."
                ),
            )

    return None


def _check_perfect_equity(
    trades: list[dict], cfg: dict,
) -> AnomalyFlag | None:
    """Max DD < threshold with > min_trades trades -> ERROR (suspiciously perfect)."""
    min_trades = cfg["perfect_equity_min_trades"]
    max_dd_threshold = cfg["perfect_equity_max_dd_pips"]

    if len(trades) <= min_trades:
        return None

    pnls = [t["pnl_pips"] for t in trades]
    cumulative = 0.0
    peak = 0.0
    max_dd_pips = 0.0

    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd_pips:
            max_dd_pips = dd

    if max_dd_pips >= max_dd_threshold:
        return None

    return AnomalyFlag(
        type=AnomalyType.PERFECT_EQUITY,
        severity=Severity.ERROR,
        description=(
            f"Suspiciously perfect equity curve: max drawdown {max_dd_pips:.2f} pips "
            f"with {len(trades)} trades (< {max_dd_threshold} pip threshold)"
        ),
        evidence={
            "max_drawdown_pips": round(max_dd_pips, 4),
            "trade_count": len(trades),
            "threshold_dd_pips": max_dd_threshold,
            "threshold_min_trades": min_trades,
        },
        recommendation=(
            "This equity curve is unrealistically smooth. Check for look-ahead bias, "
            "curve fitting, or data snooping in the strategy logic."
        ),
    )


def _check_sensitivity_cliff(
    backtest_id: str, db_path: Path | None,
) -> AnomalyFlag | None:
    """STUB: Requires optimization_candidates data (Epic 5).

    Always returns None with a debug log.
    """
    logger.debug(
        "Sensitivity cliff check skipped — requires optimization data (Epic 5)",
        extra={
            "component": "pipeline.analysis.anomaly_detector",
            "ctx": {"backtest_id": backtest_id},
        },
    )
    return None


def _check_dsr_below_threshold(
    backtest_id: str, db_path: Path | None,
) -> AnomalyFlag | None:
    """STUB: DSR computation requires trial count context (Epic 5).

    Always returns None.
    """
    logger.debug(
        "DSR check skipped — requires optimization trial context (Epic 5)",
        extra={
            "component": "pipeline.analysis.anomaly_detector",
            "ctx": {"backtest_id": backtest_id},
        },
    )
    return None


def _check_pbo_high_probability(
    backtest_id: str, db_path: Path | None,
) -> AnomalyFlag | None:
    """STUB: PBO requires combinatorial validation across folds (Epic 5).

    Always returns None.
    """
    logger.debug(
        "PBO check skipped — requires combinatorial fold validation (Epic 5)",
        extra={
            "component": "pipeline.analysis.anomaly_detector",
            "ctx": {"backtest_id": backtest_id},
        },
    )
    return None


def _check_extreme_profit_factor(
    trades: list[dict], cfg: dict,
) -> AnomalyFlag | None:
    """Profit factor > threshold -> WARNING."""
    threshold = cfg["extreme_profit_factor"]

    if not trades:
        return None

    pnls = [t["pnl_pips"] for t in trades]
    gross_profit = sum(p for p in pnls if p > 0.0)
    gross_loss = abs(sum(p for p in pnls if p < 0.0))

    if gross_loss == 0:
        # No losing trades — infinite PF, check_perfect_equity handles this
        return None

    pf = gross_profit / gross_loss
    if pf <= threshold:
        return None

    return AnomalyFlag(
        type=AnomalyType.EXTREME_PROFIT_FACTOR,
        severity=Severity.WARNING,
        description=(
            f"Extremely high profit factor ({pf:.2f}) exceeds "
            f"{threshold} threshold"
        ),
        evidence={
            "profit_factor": round(pf, 4),
            "gross_profit": round(gross_profit, 4),
            "gross_loss": round(gross_loss, 4),
            "threshold": threshold,
        },
        recommendation=(
            "A profit factor this high is unusual and may indicate overfitting, "
            "insufficient sample size, or favorable market conditions that won't persist."
        ),
    )


def _check_trade_clustering(
    trades: list[dict], cfg: dict,
) -> AnomalyFlag | None:
    """> threshold% of trades in single calendar month -> WARNING."""
    threshold_pct = cfg["trade_clustering_pct"]
    total = len(trades)

    if total == 0:
        return None

    # Count trades per calendar month. Handles both ISO-string timestamps
    # (SQLite path) and int64 microsecond timestamps (direct Arrow path) —
    # previously the microsecond path was silently mis-bucketed into 1970-01.
    month_counts: Counter[str] = Counter()
    for t in trades:
        parsed = _parse_entry_time(t.get("entry_time"))
        if parsed is not None:
            month_counts[parsed.strftime("%Y-%m")] += 1

    if not month_counts:
        return None

    most_common_month, most_common_count = month_counts.most_common(1)[0]
    pct = most_common_count / total

    if pct <= threshold_pct:
        return None

    return AnomalyFlag(
        type=AnomalyType.TRADE_CLUSTERING,
        severity=Severity.WARNING,
        description=(
            f"{pct*100:.0f}% of trades ({most_common_count}/{total}) "
            f"occurred in {most_common_month} "
            f"(>{threshold_pct*100:.0f}% threshold)"
        ),
        evidence={
            "clustered_month": most_common_month,
            "clustered_count": most_common_count,
            "total_trades": total,
            "cluster_pct": round(pct, 4),
            "threshold_pct": threshold_pct,
        },
        recommendation=(
            "Trades are concentrated in a single month. Results may not be "
            "representative of different market conditions. Consider extending "
            "the backtest period."
        ),
    )


def _check_win_rate_extremes(
    trades: list[dict], cfg: dict,
) -> AnomalyFlag | None:
    """> high% or < low% win rate with > min_trades trades -> WARNING."""
    high = cfg["win_rate_high"]
    low = cfg["win_rate_low"]
    min_trades = cfg["win_rate_min_trades"]
    total = len(trades)

    if total <= min_trades:
        return None

    wins = sum(1 for t in trades if t["pnl_pips"] > 0.0)
    win_rate = wins / total

    if low <= win_rate <= high:
        return None

    if win_rate > high:
        desc = f"Unusually high win rate ({win_rate*100:.1f}%) with {total} trades"
        rec = (
            "Win rates above 90% are rare in legitimate strategies. "
            "Check for look-ahead bias or overly tight stop-losses with wide targets."
        )
    else:
        desc = f"Very low win rate ({win_rate*100:.1f}%) with {total} trades"
        rec = (
            "Win rates below 20% suggest the strategy may have fundamental issues. "
            "Review entry conditions and filter logic."
        )

    return AnomalyFlag(
        type=AnomalyType.WIN_RATE_EXTREME,
        severity=Severity.WARNING,
        description=desc,
        evidence={
            "win_rate": round(win_rate, 4),
            "winning_trades": wins,
            "total_trades": total,
            "threshold_high": high,
            "threshold_low": low,
        },
        recommendation=rec,
    )


def _estimate_period_years(run_meta: dict) -> float:
    """Estimate backtest period in years from run metadata."""
    started = run_meta.get("started_at")
    completed = run_meta.get("completed_at")
    if not started or not completed:
        return 0.0
    try:
        s = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        c = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        return (c - s).total_seconds() / (365.25 * 24 * 3600)
    except (ValueError, TypeError):
        return 0.0
