"""Shared test fixtures for analysis layer tests."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc
import pytest


# ---------------------------------------------------------------------------
# SQLite fixture helpers
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id          TEXT PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    data_hash       TEXT NOT NULL,
    spec_version    TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    total_trades    INTEGER,
    status          TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'checkpointed'))
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    backtest_run_id TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    entry_time      TEXT NOT NULL,
    exit_time       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL NOT NULL,
    spread_cost     REAL NOT NULL,
    slippage_cost   REAL NOT NULL,
    pnl_pips        REAL NOT NULL,
    session         TEXT NOT NULL,
    lot_size        REAL NOT NULL,
    candidate_id    INTEGER,
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
);
"""

BACKTEST_ID = "test-strategy_20260101_abc123"
STRATEGY_ID = "test-strategy"


def create_test_db(db_path: Path, trades: list[dict] | None = None) -> Path:
    """Create a SQLite database with test data.

    Args:
        db_path: Path for the database file.
        trades: List of trade dicts. If None, uses default 50-trade fixture.

    Returns:
        Path to created database.
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_DDL)

    conn.execute(
        "INSERT INTO backtest_runs (run_id, strategy_id, config_hash, data_hash, "
        "spec_version, started_at, completed_at, total_trades, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            BACKTEST_ID, STRATEGY_ID, "hash123", "data456", "v001",
            "2020-01-01T00:00:00Z", "2025-12-31T23:59:59Z",
            len(trades) if trades else 50, "completed",
        ),
    )

    if trades is None:
        trades = generate_default_trades()

    for t in trades:
        conn.execute(
            "INSERT INTO trades (trade_id, strategy_id, backtest_run_id, direction, "
            "entry_time, exit_time, entry_price, exit_price, spread_cost, "
            "slippage_cost, pnl_pips, session, lot_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                t["trade_id"], STRATEGY_ID, BACKTEST_ID,
                t.get("direction", "long"),
                t["entry_time"], t["exit_time"],
                t.get("entry_price", 1.1000), t.get("exit_price", 1.1010),
                t.get("spread_cost", 0.5), t.get("slippage_cost", 0.1),
                t["pnl_pips"], t["session"], t.get("lot_size", 0.1),
            ),
        )

    conn.commit()
    conn.close()
    return db_path


def generate_default_trades(count: int = 50) -> list[dict]:
    """Generate a realistic set of trades across sessions."""
    import random
    random.seed(42)

    sessions = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]
    start = datetime(2020, 3, 1, tzinfo=timezone.utc)
    trades = []

    for i in range(count):
        # Spread trades across months and sessions
        entry = start + timedelta(days=i * 30, hours=random.randint(0, 23))
        exit_ = entry + timedelta(hours=random.randint(1, 48))
        session = sessions[i % len(sessions)]
        # Mix of wins and losses with realistic PnL
        pnl = random.gauss(2.0, 15.0)

        trades.append({
            "trade_id": i + 1,
            "direction": "long" if random.random() > 0.5 else "short",
            "entry_time": entry.isoformat(),
            "exit_time": exit_.isoformat(),
            "entry_price": 1.1000 + random.gauss(0, 0.01),
            "exit_price": 1.1000 + random.gauss(0, 0.01),
            "spread_cost": 0.5,
            "slippage_cost": 0.1,
            "pnl_pips": round(pnl, 2),
            "session": session,
            "lot_size": 0.1,
        })

    return trades


def create_equity_curve_arrow(path: Path, num_points: int = 1000) -> Path:
    """Create an equity curve Arrow IPC file."""
    import random
    random.seed(42)

    timestamps = []
    equities = []
    unrealized = []
    drawdowns = []
    open_trades_col = []

    equity = 0.0
    peak = 0.0
    base_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000_000)

    for i in range(num_points):
        ts = base_ts + i * 60_000_000  # 1 minute apart in microseconds
        change = random.gauss(0.1, 2.0)
        equity += change
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0

        timestamps.append(ts)
        equities.append(round(equity, 4))
        unrealized.append(round(random.gauss(0, 1.0), 4))
        drawdowns.append(round(dd, 4))
        open_trades_col.append(1 if random.random() > 0.7 else 0)

    table = pa.table({
        "timestamp": pa.array(timestamps, type=pa.int64()),
        "equity_pips": pa.array(equities, type=pa.float64()),
        "unrealized_pnl": pa.array(unrealized, type=pa.float64()),
        "drawdown_pct": pa.array(drawdowns, type=pa.float64()),
        "open_trades": pa.array(open_trades_col, type=pa.int64()),
    })

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = pyarrow.ipc.new_file(str(path), table.schema)
    writer.write_table(table)
    writer.close()

    return path


def create_full_artifact_tree(
    tmp_path: Path,
    trades: list[dict] | None = None,
    num_equity_points: int = 1000,
) -> tuple[Path, Path, Path]:
    """Create a complete artifact tree with DB, Arrow files, and manifest.

    Returns:
        Tuple of (db_path, artifacts_root, backtest_dir).
    """
    artifacts_root = tmp_path / "artifacts"
    backtest_dir = artifacts_root / STRATEGY_ID / "v001" / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)

    # Create SQLite database
    db_path = artifacts_root / "backtest.db"
    create_test_db(db_path, trades)

    # Create equity curve Arrow IPC
    create_equity_curve_arrow(backtest_dir / "equity-curve.arrow", num_equity_points)

    # Create a minimal trade-log.arrow
    if trades is None:
        trades = generate_default_trades()
    _create_trade_log_arrow(backtest_dir / "trade-log.arrow", trades)

    # Create manifest
    manifest = {
        "backtest_run_id": BACKTEST_ID,
        "strategy_id": STRATEGY_ID,
        "version": 1,
        "provenance": {
            "config_hash": "hash123",
            "dataset_hash": "data456",
            "cost_model_hash": "cost789",
        },
    }
    (backtest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return db_path, artifacts_root, backtest_dir


def _create_trade_log_arrow(path: Path, trades: list[dict]) -> None:
    """Create a minimal trade-log Arrow IPC file."""
    table = pa.table({
        "trade_id": pa.array([t["trade_id"] for t in trades], type=pa.int64()),
        "pnl_pips": pa.array([t["pnl_pips"] for t in trades], type=pa.float64()),
    })

    writer = pyarrow.ipc.new_file(str(path), table.schema)
    writer.write_table(table)
    writer.close()


@pytest.fixture
def test_db(tmp_path):
    """Create a test SQLite database with default trades."""
    return create_test_db(tmp_path / "test.db")


@pytest.fixture
def artifact_tree(tmp_path):
    """Create a full artifact tree for evidence pack testing."""
    return create_full_artifact_tree(tmp_path)
