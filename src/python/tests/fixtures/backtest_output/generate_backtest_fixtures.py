"""Generate Arrow IPC test fixtures matching contracts/arrow_schemas.toml.

Produces:
- trade-log.arrow: 50 sample trades with realistic field values
- equity-curve.arrow: 1000 sample equity points
- metrics.arrow: single-row summary metrics
- run_metadata.json: sample metadata

Schemas MUST match contracts/arrow_schemas.toml (SSOT).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc

# Seed for reproducible fixtures
random.seed(42)

OUTPUT_DIR = Path(__file__).parent

# -----------------------------------------------------------------------
# Trade log: 50 sample trades matching [backtest_trades] schema
# -----------------------------------------------------------------------

_SESSIONS = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]
_DIRECTIONS = ["long", "short"]
_EXIT_REASONS = [
    "StopLoss", "TakeProfit", "TrailingStop", "SignalReversal", "EndOfData",
]
_STRATEGY_ID = "ma_crossover_v001"
_CONFIG_HASH = "sha256:abc123def456"


def _ns_timestamp(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    """Create a nanosecond UTC timestamp."""
    import datetime
    dt = datetime.datetime(year, month, day, hour, minute, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def generate_trade_log(n_trades: int = 50) -> pa.Table:
    """Generate a trade log table with n_trades rows."""
    base_ts = _ns_timestamp(2025, 1, 2, 8, 0)
    hour_ns = 3_600_000_000_000

    trade_ids = list(range(1, n_trades + 1))
    strategy_ids = [_STRATEGY_ID] * n_trades
    directions = [random.choice(_DIRECTIONS) for _ in range(n_trades)]
    entry_times = [base_ts + i * hour_ns for i in range(n_trades)]
    exit_times = [et + random.randint(1, 10) * hour_ns for et in entry_times]
    entry_price_raws = [1.1000 + random.uniform(-0.005, 0.005) for _ in range(n_trades)]
    entry_spreads = [random.uniform(0.5, 2.0) for _ in range(n_trades)]
    entry_slippages = [random.uniform(0.0, 0.5) for _ in range(n_trades)]
    entry_prices = [
        raw + (sp + sl) * 0.0001 if d == "long" else raw - (sp + sl) * 0.0001
        for raw, sp, sl, d in zip(entry_price_raws, entry_spreads, entry_slippages, directions)
    ]
    exit_price_raws = [ep + random.uniform(-0.003, 0.003) for ep in entry_price_raws]
    exit_spreads = [random.uniform(0.5, 2.0) for _ in range(n_trades)]
    exit_slippages = [random.uniform(0.0, 0.5) for _ in range(n_trades)]
    exit_prices = [
        raw - (sp + sl) * 0.0001 if d == "long" else raw + (sp + sl) * 0.0001
        for raw, sp, sl, d in zip(exit_price_raws, exit_spreads, exit_slippages, directions)
    ]
    pnl_pips_values = [
        (exp - enp) / 0.0001 if d == "long" else (enp - exp) / 0.0001
        for enp, exp, d in zip(entry_prices, exit_prices, directions)
    ]
    entry_sessions = [random.choice(_SESSIONS) for _ in range(n_trades)]
    exit_sessions = [random.choice(_SESSIONS) for _ in range(n_trades)]
    signal_ids = list(range(100, 100 + n_trades))
    holding_durations = [random.randint(1, 50) for _ in range(n_trades)]
    exit_reasons = [random.choice(_EXIT_REASONS) for _ in range(n_trades)]
    lot_sizes = [1.0] * n_trades

    schema = pa.schema([
        ("trade_id", pa.int64()),
        ("strategy_id", pa.utf8()),
        ("direction", pa.utf8()),
        ("entry_time", pa.int64()),
        ("exit_time", pa.int64()),
        ("entry_price_raw", pa.float64()),
        ("entry_price", pa.float64()),
        ("exit_price_raw", pa.float64()),
        ("exit_price", pa.float64()),
        ("entry_spread", pa.float64()),
        ("entry_slippage", pa.float64()),
        ("exit_spread", pa.float64()),
        ("exit_slippage", pa.float64()),
        ("pnl_pips", pa.float64()),
        ("entry_session", pa.utf8()),
        ("exit_session", pa.utf8()),
        ("signal_id", pa.int64()),
        ("holding_duration_bars", pa.int64()),
        ("exit_reason", pa.utf8()),
        ("lot_size", pa.float64()),
    ])

    return pa.table(
        {
            "trade_id": trade_ids,
            "strategy_id": strategy_ids,
            "direction": directions,
            "entry_time": entry_times,
            "exit_time": exit_times,
            "entry_price_raw": entry_price_raws,
            "entry_price": entry_prices,
            "exit_price_raw": exit_price_raws,
            "exit_price": exit_prices,
            "entry_spread": entry_spreads,
            "entry_slippage": entry_slippages,
            "exit_spread": exit_spreads,
            "exit_slippage": exit_slippages,
            "pnl_pips": pnl_pips_values,
            "entry_session": entry_sessions,
            "exit_session": exit_sessions,
            "signal_id": signal_ids,
            "holding_duration_bars": holding_durations,
            "exit_reason": exit_reasons,
            "lot_size": lot_sizes,
        },
        schema=schema,
    )


def generate_equity_curve(n_points: int = 1000) -> pa.Table:
    """Generate equity curve table matching [equity_curve] schema."""
    base_ts = _ns_timestamp(2025, 1, 2, 8, 0)
    bar_ns = 60_000_000_000  # 1 minute bars

    equity = 0.0
    timestamps = []
    equities = []
    unrealized = []
    drawdowns = []
    open_trades_list = []
    peak = 0.0

    for i in range(n_points):
        timestamps.append(base_ts + i * bar_ns)
        change = random.uniform(-2.0, 2.5)
        equity += change
        peak = max(peak, equity)
        dd = (peak - equity) / max(peak, 1.0) * 100 if peak > 0 else 0.0
        equities.append(equity)
        unrealized.append(random.uniform(-1.0, 1.0) if random.random() > 0.7 else 0.0)
        drawdowns.append(dd)
        open_trades_list.append(1 if random.random() > 0.7 else 0)

    schema = pa.schema([
        ("timestamp", pa.int64()),
        ("equity_pips", pa.float64()),
        ("unrealized_pnl", pa.float64()),
        ("drawdown_pips", pa.float64()),
        ("open_trades", pa.int64()),
    ])

    return pa.table(
        {
            "timestamp": timestamps,
            "equity_pips": equities,
            "unrealized_pnl": unrealized,
            "drawdown_pips": drawdowns,
            "open_trades": open_trades_list,
        },
        schema=schema,
    )


def generate_metrics() -> pa.Table:
    """Generate single-row metrics table matching [backtest_metrics] schema."""
    schema = pa.schema([
        ("total_trades", pa.int64()),
        ("winning_trades", pa.int64()),
        ("losing_trades", pa.int64()),
        ("win_rate", pa.float64()),
        ("profit_factor", pa.float64()),
        ("sharpe_ratio", pa.float64()),
        ("r_squared", pa.float64()),
        ("max_drawdown_pips", pa.float64()),
        ("max_drawdown_duration_bars", pa.int64()),
        ("avg_trade_duration_bars", pa.float64()),
        ("avg_win", pa.float64()),
        ("avg_loss", pa.float64()),
        ("largest_win", pa.float64()),
        ("largest_loss", pa.float64()),
        ("net_pnl_pips", pa.float64()),
        ("avg_trade_pips", pa.float64()),
        ("strategy_id", pa.utf8()),
        ("config_hash", pa.utf8()),
    ])

    return pa.table(
        {
            "total_trades": [50],
            "winning_trades": [28],
            "losing_trades": [22],
            "win_rate": [0.56],
            "profit_factor": [1.35],
            "sharpe_ratio": [0.82],
            "r_squared": [0.65],
            "max_drawdown_pips": [150.5],
            "max_drawdown_duration_bars": [240],
            "avg_trade_duration_bars": [15.2],
            "avg_win": [25.3],
            "avg_loss": [-18.7],
            "largest_win": [85.2],
            "largest_loss": [-62.1],
            "net_pnl_pips": [295.4],
            "avg_trade_pips": [5.9],
            "strategy_id": [_STRATEGY_ID],
            "config_hash": [_CONFIG_HASH],
        },
        schema=schema,
    )


def write_fixtures() -> None:
    """Generate and write all fixture files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Trade log
    trade_log = generate_trade_log()
    with open(OUTPUT_DIR / "trade-log.arrow", "wb") as f:
        writer = pa.ipc.new_file(f, trade_log.schema)
        writer.write_table(trade_log)
        writer.close()

    # Equity curve
    equity = generate_equity_curve()
    with open(OUTPUT_DIR / "equity-curve.arrow", "wb") as f:
        writer = pa.ipc.new_file(f, equity.schema)
        writer.write_table(equity)
        writer.close()

    # Metrics
    metrics = generate_metrics()
    with open(OUTPUT_DIR / "metrics.arrow", "wb") as f:
        writer = pa.ipc.new_file(f, metrics.schema)
        writer.write_table(metrics)
        writer.close()

    # Run metadata
    metadata = {
        "config_hash": _CONFIG_HASH,
        "binary_version": "0.1.0",
        "timestamp": "2025-01-02T08:00:00Z",
        "strategy_id": _STRATEGY_ID,
    }
    (OUTPUT_DIR / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    print(f"Fixtures written to {OUTPUT_DIR}")
    for f in sorted(OUTPUT_DIR.glob("*")):
        if f.name != "__pycache__" and not f.name.endswith(".py"):
            print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    write_fixtures()
