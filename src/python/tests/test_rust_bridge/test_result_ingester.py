"""Unit tests for rust_bridge.result_ingester — Arrow→SQLite ingestion (Task 3)."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc
import pytest

from artifacts.sqlite_manager import SQLiteManager
from rust_bridge.result_ingester import ResultIngester, _ns_to_iso8601


@pytest.fixture
def fixtures_dir():
    """Path to backtest output fixtures."""
    d = Path(__file__).resolve().parents[1] / "fixtures" / "backtest_output"
    if not (d / "trade-log.arrow").exists():
        pytest.skip("Backtest fixtures not generated")
    return d


@pytest.fixture
def db_with_schema(tmp_path):
    """SQLiteManager with schema initialized."""
    db_path = tmp_path / "test.db"
    mgr = SQLiteManager(db_path)
    mgr.init_schema()
    yield mgr
    mgr.close()


@pytest.fixture
def ingester(db_with_schema):
    return ResultIngester(db_with_schema.connection)


class TestNsToIso8601:
    def test_basic_conversion(self):
        """Nanosecond timestamp converts to ISO 8601."""
        # 2025-01-02T08:00:00Z in nanoseconds
        ns = int(datetime(2025, 1, 2, 8, 0, 0, tzinfo=timezone.utc).timestamp()) * 1_000_000_000
        result = _ns_to_iso8601(ns)
        assert result.startswith("2025-01-02T08:00:00")
        assert "+00:00" in result or "Z" in result

    def test_preserves_microseconds(self):
        """Microsecond precision is preserved."""
        base_s = int(datetime(2025, 6, 15, 12, 30, 45, tzinfo=timezone.utc).timestamp())
        ns = base_s * 1_000_000_000 + 123_456_000  # 123456 microseconds
        result = _ns_to_iso8601(ns)
        assert "123456" in result


class TestResultIngester:
    def test_register_and_complete_backtest_run(self, db_with_schema, ingester):
        """Verify backtest_runs lifecycle."""
        ingester.register_backtest_run(
            run_id="run_001",
            strategy_id="test_strat",
            config_hash="sha256:abc",
            data_hash="sha256:def",
            spec_version="v001",
            started_at="2025-01-01T00:00:00Z",
        )

        row = db_with_schema.connection.execute(
            "SELECT * FROM backtest_runs WHERE run_id = ?", ("run_001",)
        ).fetchone()
        assert row is not None
        assert row[1] == "test_strat"  # strategy_id
        assert row[8] == "running"  # status

        ingester.complete_backtest_run("run_001", 50)

        row = db_with_schema.connection.execute(
            "SELECT status, total_trades FROM backtest_runs WHERE run_id = ?",
            ("run_001",),
        ).fetchone()
        assert row[0] == "completed"
        assert row[1] == 50

    def test_ingest_trade_log_correct_count(self, ingester, fixtures_dir, db_with_schema):
        """Ingest fixture, verify row count."""
        ingester.register_backtest_run(
            "run_001", "ma_crossover_v001", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        count = ingester.ingest_trade_log(
            fixtures_dir / "trade-log.arrow", "ma_crossover_v001", "run_001"
        )
        assert count == 50

        db_count = db_with_schema.connection.execute(
            "SELECT COUNT(*) FROM trades WHERE backtest_run_id = ?", ("run_001",)
        ).fetchone()[0]
        assert db_count == 50

    def test_ingest_trade_log_field_mapping(self, ingester, fixtures_dir, db_with_schema):
        """Verify Arrow→SQLite mapping (direction, cost aggregation)."""
        ingester.register_backtest_run(
            "run_002", "ma_crossover_v001", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        ingester.ingest_trade_log(
            fixtures_dir / "trade-log.arrow", "ma_crossover_v001", "run_002"
        )

        row = db_with_schema.connection.execute(
            "SELECT direction, spread_cost, slippage_cost FROM trades WHERE backtest_run_id = ? LIMIT 1",
            ("run_002",),
        ).fetchone()

        # Direction should be lowercase
        assert row[0] in ("long", "short")
        # spread_cost = entry_spread + exit_spread (aggregated)
        assert isinstance(row[1], float)
        assert row[1] > 0
        # slippage_cost = entry_slippage + exit_slippage (aggregated)
        assert isinstance(row[2], float)
        assert row[2] >= 0

    def test_ingest_trade_log_iso8601_timestamps(self, ingester, fixtures_dir, db_with_schema):
        """Verify nanosecond → ISO 8601 conversion."""
        ingester.register_backtest_run(
            "run_003", "ma_crossover_v001", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        ingester.ingest_trade_log(
            fixtures_dir / "trade-log.arrow", "ma_crossover_v001", "run_003"
        )

        row = db_with_schema.connection.execute(
            "SELECT entry_time, exit_time FROM trades WHERE backtest_run_id = ? LIMIT 1",
            ("run_003",),
        ).fetchone()

        # Should be ISO 8601 format
        assert "T" in row[0]
        assert "2025" in row[0]
        assert "T" in row[1]

    def test_ingest_rollback_on_error(self, db_with_schema, tmp_path):
        """Corrupt data triggers rollback, DB unchanged."""
        ingester = ResultIngester(db_with_schema.connection)
        ingester.register_backtest_run(
            "run_004", "test", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )

        # Write a file with wrong schema (missing columns)
        bad_table = pa.table({"wrong_col": [1, 2, 3]})
        bad_path = tmp_path / "bad-trade-log.arrow"
        with open(bad_path, "wb") as f:
            writer = pa.ipc.new_file(f, bad_table.schema)
            writer.write_table(bad_table)
            writer.close()

        with pytest.raises(KeyError):
            ingester.ingest_trade_log(bad_path, "test", "run_004")

        # No trades should have been inserted
        count = db_with_schema.connection.execute(
            "SELECT COUNT(*) FROM trades WHERE backtest_run_id = ?", ("run_004",)
        ).fetchone()[0]
        assert count == 0

    def test_validate_schema_mismatch(self, ingester, tmp_path):
        """Wrong schema raises clear error (returns False)."""
        bad_table = pa.table({"wrong_col": [1, 2, 3]})
        bad_path = tmp_path / "bad.arrow"
        with open(bad_path, "wb") as f:
            writer = pa.ipc.new_file(f, bad_table.schema)
            writer.write_table(bad_table)
            writer.close()

        result = ingester.validate_schema(bad_path, "backtest_trades")
        assert result is False

    def test_validate_schema_correct(self, ingester, fixtures_dir):
        """Correct schema returns True."""
        result = ingester.validate_schema(
            fixtures_dir / "trade-log.arrow", "backtest_trades"
        )
        assert result is True

    def test_ingest_idempotent_rerun(self, ingester, fixtures_dir, db_with_schema):
        """Ingest same data twice, verify no duplicate rows (AC #10)."""
        ingester.register_backtest_run(
            "run_005", "ma_crossover_v001", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        count1 = ingester.ingest_trade_log(
            fixtures_dir / "trade-log.arrow", "ma_crossover_v001", "run_005"
        )
        count2 = ingester.ingest_trade_log(
            fixtures_dir / "trade-log.arrow", "ma_crossover_v001", "run_005"
        )

        assert count1 == count2 == 50

        db_count = db_with_schema.connection.execute(
            "SELECT COUNT(*) FROM trades WHERE backtest_run_id = ?", ("run_005",)
        ).fetchone()[0]
        assert db_count == 50  # No duplicates

    def test_ingest_fold_scores(self, ingester, db_with_schema):
        """Ingest per-fold scores, verify fold_scores table populated."""
        ingester.register_backtest_run(
            "run_006", "test", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        scores = [
            {
                "fold_id": 0, "fold_start_bar": 0, "fold_end_bar": 1000,
                "sharpe_ratio": 0.8, "profit_factor": 1.2, "total_trades": 50,
            },
            {
                "fold_id": 1, "fold_start_bar": 1000, "fold_end_bar": 2000,
                "sharpe_ratio": 0.6, "profit_factor": 1.1, "total_trades": 45,
            },
        ]
        count = ingester.ingest_fold_scores("run_006", scores)
        assert count == 2

        rows = db_with_schema.connection.execute(
            "SELECT fold_id, sharpe_ratio FROM fold_scores WHERE backtest_run_id = ?",
            ("run_006",),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 0
        assert rows[0][1] == pytest.approx(0.8)

    def test_ingest_fold_scores_empty_for_single_run(self, ingester, db_with_schema):
        """Verify fold_scores table empty when no folds used."""
        ingester.register_backtest_run(
            "run_007", "test", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        count = ingester.ingest_fold_scores("run_007", [])
        assert count == 0

        db_count = db_with_schema.connection.execute(
            "SELECT COUNT(*) FROM fold_scores WHERE backtest_run_id = ?",
            ("run_007",),
        ).fetchone()[0]
        assert db_count == 0

    @pytest.mark.regression
    def test_validate_schema_static_no_connection(self, fixtures_dir):
        """Regression: M2 — validate_schema_static must work without a SQLite connection."""
        result = ResultIngester.validate_schema_static(
            fixtures_dir / "trade-log.arrow", "backtest_trades"
        )
        assert result is True

    @pytest.mark.regression
    def test_validate_schema_type_mismatch(self, tmp_path):
        """Regression: M4 — schema validation must check column types, not just names.
        An Arrow file with correct column names but wrong types must fail validation."""
        # Create an Arrow file with entry_time as Utf8 instead of Int64
        schema = pa.schema([
            pa.field("trade_id", pa.utf8()),  # Wrong type: should be int64
            pa.field("strategy_id", pa.utf8()),
            pa.field("direction", pa.utf8()),
            pa.field("entry_time", pa.utf8()),  # Wrong type: should be int64
            pa.field("exit_time", pa.int64()),
            pa.field("entry_price_raw", pa.float64()),
            pa.field("entry_price", pa.float64()),
            pa.field("exit_price_raw", pa.float64()),
            pa.field("exit_price", pa.float64()),
            pa.field("entry_spread", pa.float64()),
            pa.field("entry_slippage", pa.float64()),
            pa.field("exit_spread", pa.float64()),
            pa.field("exit_slippage", pa.float64()),
            pa.field("pnl_pips", pa.float64()),
            pa.field("entry_session", pa.utf8()),
            pa.field("exit_session", pa.utf8()),
            pa.field("signal_id", pa.int64()),
            pa.field("holding_duration_bars", pa.int64()),
            pa.field("exit_reason", pa.utf8()),
            pa.field("lot_size", pa.float64()),
        ])
        table = pa.table(
            {name: [] for name in schema.names},
            schema=schema,
        )
        bad_path = tmp_path / "type-mismatch.arrow"
        with open(bad_path, "wb") as f:
            writer = pa.ipc.new_file(f, schema)
            writer.write_table(table)
            writer.close()

        result = ResultIngester.validate_schema_static(bad_path, "backtest_trades")
        assert result is False, "Schema with wrong column types must fail validation"

    def test_clear_run_data(self, ingester, fixtures_dir, db_with_schema):
        """clear_run_data removes all trades and fold_scores for a run."""
        ingester.register_backtest_run(
            "run_008", "ma_crossover_v001", "h1", "h2", "v001", "2025-01-01T00:00:00Z"
        )
        ingester.ingest_trade_log(
            fixtures_dir / "trade-log.arrow", "ma_crossover_v001", "run_008"
        )
        ingester.ingest_fold_scores("run_008", [
            {"fold_id": 0, "fold_start_bar": 0, "fold_end_bar": 1000},
        ])

        ingester.clear_run_data("run_008")

        count = db_with_schema.connection.execute(
            "SELECT COUNT(*) FROM trades WHERE backtest_run_id = ?", ("run_008",)
        ).fetchone()[0]
        assert count == 0

        fold_count = db_with_schema.connection.execute(
            "SELECT COUNT(*) FROM fold_scores WHERE backtest_run_id = ?", ("run_008",)
        ).fetchone()[0]
        assert fold_count == 0
