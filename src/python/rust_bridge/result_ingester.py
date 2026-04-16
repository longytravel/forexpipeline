"""Arrow IPC trade-log ingestion into SQLite (D2 queryable index).

Reads Arrow IPC files produced by the Rust backtester and inserts
trade-level records into SQLite for efficient analytics queries.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pyarrow
import pyarrow.ipc

from logging_setup.setup import get_logger

logger = get_logger("pipeline.rust_bridge.ingester")


def _epoch_int_to_iso8601(value: int) -> str:
    """Convert an int64 epoch timestamp to ISO 8601, auto-detecting the unit.

    The Rust backtester forwards the input market-data ``timestamp`` column
    straight through into ``entry_time``/``exit_time`` without unit conversion.
    Depending on the data-pipeline build, that timestamp may be seconds,
    milliseconds, microseconds or nanoseconds since the Unix epoch. We mirror
    the auto-detection already used in ``orchestrator/signal_precompute.py``
    (see ``pd.to_datetime(..., unit=unit)``): values > 1e17 are nanoseconds,
    > 1e14 are microseconds, > 1e11 are milliseconds, otherwise seconds.

    Historical note: the previous implementation was named ``_ns_to_iso8601``
    and hard-coded ``// 1_000_000_000``. When the data pipeline migrated to
    microsecond timestamps, every ingested trade collapsed into 1970-01, which
    surfaced as a spurious TRADE_CLUSTERING anomaly on evidence packs.
    """
    v = int(value)
    abs_v = abs(v)
    if abs_v > 10**17:
        # nanoseconds
        seconds, remainder = divmod(v, 1_000_000_000)
        micros = remainder // 1_000
    elif abs_v > 10**14:
        # microseconds
        seconds, micros = divmod(v, 1_000_000)
    elif abs_v > 10**11:
        # milliseconds
        seconds, millis = divmod(v, 1_000)
        micros = millis * 1_000
    else:
        # seconds
        seconds = v
        micros = 0
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micros)
    return dt.isoformat()


# Backwards-compatible aliases for callers that imported the older names.
_us_to_iso8601 = _epoch_int_to_iso8601
_ns_to_iso8601 = _epoch_int_to_iso8601


def _load_schema_contract(schema_name: str) -> list[dict]:
    """Load column definitions from contracts/arrow_schemas.toml."""
    import tomllib

    candidates = [
        Path(__file__).resolve().parents[3] / "contracts" / "arrow_schemas.toml",
        Path.cwd() / "contracts" / "arrow_schemas.toml",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "rb") as f:
                schemas = tomllib.load(f)
            if schema_name not in schemas:
                raise ValueError(
                    f"Schema '{schema_name}' not found in {path}. "
                    f"Available: {list(schemas.keys())}"
                )
            return schemas[schema_name]["columns"]
    raise FileNotFoundError("Cannot find contracts/arrow_schemas.toml")


class ResultIngester:
    """Ingests Arrow IPC backtest results into SQLite."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        batch_size: int = 1000,
    ) -> None:
        self._conn = conn
        self._batch_size = batch_size

    def register_backtest_run(
        self,
        run_id: str,
        strategy_id: str,
        config_hash: str,
        data_hash: str,
        spec_version: str,
        started_at: str,
    ) -> None:
        """Insert a new backtest_runs record with status 'running'."""
        self._conn.execute(
            """INSERT OR REPLACE INTO backtest_runs
               (run_id, strategy_id, config_hash, data_hash, spec_version,
                started_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'running')""",
            (run_id, strategy_id, config_hash, data_hash, spec_version, started_at),
        )
        self._conn.commit()
        logger.info(
            "Backtest run registered",
            extra={
                "component": "pipeline.rust_bridge.ingester",
                "ctx": {"run_id": run_id, "strategy_id": strategy_id},
            },
        )

    def complete_backtest_run(
        self,
        run_id: str,
        total_trades: int,
    ) -> None:
        """Update backtest_runs with completion info."""
        completed_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """UPDATE backtest_runs
               SET completed_at = ?, total_trades = ?, status = 'completed'
               WHERE run_id = ?""",
            (completed_at, total_trades, run_id),
        )
        self._conn.commit()
        logger.info(
            "Backtest run completed",
            extra={
                "component": "pipeline.rust_bridge.ingester",
                "ctx": {"run_id": run_id, "total_trades": total_trades},
            },
        )

    def ingest_trade_log(
        self,
        arrow_path: Path,
        strategy_id: str,
        backtest_run_id: str,
    ) -> int:
        """Read trade-log.arrow and insert rows into SQLite trades table.

        Arrow→SQLite field mapping:
        - entry_time/exit_time Int64 (microseconds since Unix epoch, UTC) → TEXT (ISO 8601)
        - entry_price/exit_price Float64 → REAL (cost-adjusted)
        - entry_spread + exit_spread → spread_cost REAL (aggregated)
        - entry_slippage + exit_slippage → slippage_cost REAL (aggregated)
        - direction utf8 → TEXT (lowercased from Rust "Long"/"Short")
        - entry_session → session TEXT
        - pnl_pips Float64 → pnl_pips REAL
        - lot_size Float64 → lot_size REAL
        - trade_id Int64 → trade_id INTEGER

        Returns the number of rows ingested.
        """
        arrow_path = Path(arrow_path)
        reader = pyarrow.ipc.open_file(str(arrow_path))
        table = reader.read_all()

        row_count = 0
        cursor = self._conn.cursor()

        try:
            cursor.execute("BEGIN")

            batch_rows: list[tuple] = []
            for i in range(table.num_rows):
                row = self._map_trade_row(table, i, strategy_id, backtest_run_id)
                batch_rows.append(row)

                if len(batch_rows) >= self._batch_size:
                    cursor.executemany(
                        """INSERT OR REPLACE INTO trades
                           (trade_id, strategy_id, backtest_run_id, direction,
                            entry_time, exit_time, entry_price, exit_price,
                            spread_cost, slippage_cost, pnl_pips, session,
                            lot_size, candidate_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        batch_rows,
                    )
                    row_count += len(batch_rows)
                    batch_rows = []

            # Flush remaining rows
            if batch_rows:
                cursor.executemany(
                    """INSERT OR REPLACE INTO trades
                       (trade_id, strategy_id, backtest_run_id, direction,
                        entry_time, exit_time, entry_price, exit_price,
                        spread_cost, slippage_cost, pnl_pips, session,
                        lot_size, candidate_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    batch_rows,
                )
                row_count += len(batch_rows)

            cursor.execute("COMMIT")

        except Exception:
            cursor.execute("ROLLBACK")
            raise

        logger.info(
            "Trade log ingested",
            extra={
                "component": "pipeline.rust_bridge.ingester",
                "ctx": {
                    "arrow_path": str(arrow_path),
                    "row_count": row_count,
                    "backtest_run_id": backtest_run_id,
                },
            },
        )
        return row_count

    def ingest_fold_scores(
        self,
        backtest_run_id: str,
        fold_scores: list[dict],
    ) -> int:
        """Ingest per-fold scores into fold_scores table.

        Each dict in fold_scores must have: fold_id, fold_start_bar,
        fold_end_bar, and optional metric fields.
        """
        if not fold_scores:
            return 0

        cursor = self._conn.cursor()
        try:
            cursor.execute("BEGIN")
            rows = []
            for score in fold_scores:
                rows.append((
                    backtest_run_id,
                    score.get("candidate_id"),
                    score["fold_id"],
                    score["fold_start_bar"],
                    score["fold_end_bar"],
                    score.get("sharpe_ratio"),
                    score.get("profit_factor"),
                    score.get("max_drawdown_pips"),
                    score.get("total_trades"),
                    score.get("win_rate"),
                    score.get("total_pnl"),
                ))
            cursor.executemany(
                """INSERT INTO fold_scores
                   (backtest_run_id, candidate_id, fold_id, fold_start_bar,
                    fold_end_bar, sharpe_ratio, profit_factor, max_drawdown_pips,
                    total_trades, win_rate, total_pnl)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise

        count = len(rows)
        logger.info(
            "Fold scores ingested",
            extra={
                "component": "pipeline.rust_bridge.ingester",
                "ctx": {"backtest_run_id": backtest_run_id, "fold_count": count},
            },
        )
        return count

    def validate_schema(self, arrow_path: Path, expected_schema_name: str) -> bool:
        """Validate Arrow file schema against contracts/arrow_schemas.toml."""
        return ResultIngester.validate_schema_static(arrow_path, expected_schema_name)

    @staticmethod
    def validate_schema_static(arrow_path: Path, expected_schema_name: str) -> bool:
        """Validate Arrow file schema against contracts/arrow_schemas.toml.

        Checks both column presence and column types.
        Does not require a SQLite connection.
        """
        arrow_path = Path(arrow_path)
        reader = pyarrow.ipc.open_file(str(arrow_path))
        actual_schema = reader.schema

        expected_columns = _load_schema_contract(expected_schema_name)
        expected_names = {col["name"] for col in expected_columns}
        actual_names = set(actual_schema.names)

        missing = expected_names - actual_names
        if missing:
            logger.error(
                f"Schema validation failed: missing columns {missing}",
                extra={
                    "component": "pipeline.rust_bridge.ingester",
                    "ctx": {
                        "arrow_path": str(arrow_path),
                        "schema": expected_schema_name,
                        "missing": sorted(missing),
                    },
                },
            )
            return False

        # Validate column types match contract
        type_map = {
            "int64": pyarrow.int64(),
            "uint64": pyarrow.uint64(),
            "float64": pyarrow.float64(),
            "utf8": pyarrow.utf8(),
            "bool": pyarrow.bool_(),
        }
        for col in expected_columns:
            col_name = col["name"]
            expected_type_str = col.get("type")
            if expected_type_str and expected_type_str in type_map:
                expected_pa_type = type_map[expected_type_str]
                actual_field = actual_schema.field(col_name)
                if actual_field.type != expected_pa_type:
                    logger.error(
                        f"Schema type mismatch for column '{col_name}': "
                        f"expected {expected_type_str}, got {actual_field.type}",
                        extra={
                            "component": "pipeline.rust_bridge.ingester",
                            "ctx": {
                                "arrow_path": str(arrow_path),
                                "schema": expected_schema_name,
                                "column": col_name,
                                "expected_type": expected_type_str,
                                "actual_type": str(actual_field.type),
                            },
                        },
                    )
                    return False
        return True

    def clear_run_data(self, backtest_run_id: str) -> None:
        """Delete all trades for a specific backtest_run_id (safety fallback)."""
        self._conn.execute(
            "DELETE FROM trades WHERE backtest_run_id = ?", (backtest_run_id,)
        )
        self._conn.execute(
            "DELETE FROM fold_scores WHERE backtest_run_id = ?", (backtest_run_id,)
        )
        self._conn.commit()

    @staticmethod
    def _map_trade_row(
        table: pyarrow.Table,
        idx: int,
        strategy_id: str,
        backtest_run_id: str,
    ) -> tuple:
        """Map a single Arrow row to SQLite trades columns."""
        trade_id = table.column("trade_id")[idx].as_py()
        direction = table.column("direction")[idx].as_py().lower()
        entry_time = _epoch_int_to_iso8601(table.column("entry_time")[idx].as_py())
        exit_time = _epoch_int_to_iso8601(table.column("exit_time")[idx].as_py())
        entry_price = table.column("entry_price")[idx].as_py()
        exit_price = table.column("exit_price")[idx].as_py()
        entry_spread = table.column("entry_spread")[idx].as_py()
        exit_spread = table.column("exit_spread")[idx].as_py()
        entry_slippage = table.column("entry_slippage")[idx].as_py()
        exit_slippage = table.column("exit_slippage")[idx].as_py()
        spread_cost = entry_spread + exit_spread
        slippage_cost = entry_slippage + exit_slippage
        pnl_pips = table.column("pnl_pips")[idx].as_py()
        session = table.column("entry_session")[idx].as_py()
        lot_size = table.column("lot_size")[idx].as_py()
        # candidate_id is NULL for V1 single backtest
        candidate_id = None

        return (
            trade_id, strategy_id, backtest_run_id, direction,
            entry_time, exit_time, entry_price, exit_price,
            spread_cost, slippage_cost, pnl_pips, session,
            lot_size, candidate_id,
        )
