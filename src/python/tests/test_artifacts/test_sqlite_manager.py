"""Unit tests for artifacts.sqlite_manager — SQLiteManager (Task 2)."""
import sqlite3
from pathlib import Path

import pytest

from artifacts.sqlite_manager import SQLiteManager


@pytest.fixture
def db_manager(tmp_path):
    """Create a SQLiteManager with a temp database."""
    db_path = tmp_path / "test_pipeline.db"
    mgr = SQLiteManager(db_path)
    yield mgr
    mgr.close()


@pytest.fixture
def ddl_path():
    """Path to the contracts/sqlite_ddl.sql file."""
    candidates = [
        Path(__file__).resolve().parents[4] / "contracts" / "sqlite_ddl.sql",
        Path.cwd() / "contracts" / "sqlite_ddl.sql",
    ]
    for p in candidates:
        if p.exists():
            return p
    pytest.skip("contracts/sqlite_ddl.sql not found")


class TestSQLiteManager:
    def test_init_creates_wal_mode(self, db_manager):
        """Verify WAL pragma is set."""
        result = db_manager.connection.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_init_creates_synchronous_normal(self, db_manager):
        """Verify synchronous=NORMAL pragma."""
        result = db_manager.connection.execute("PRAGMA synchronous").fetchone()
        # NORMAL = 1
        assert result[0] == 1

    def test_schema_creation_idempotent(self, db_manager, ddl_path):
        """Call init_schema twice, no errors."""
        db_manager.init_schema(ddl_path)
        db_manager.init_schema(ddl_path)  # Should not raise

    def test_tables_created(self, db_manager, ddl_path):
        """Verify all expected tables exist after schema init."""
        db_manager.init_schema(ddl_path)
        tables = {
            row[0]
            for row in db_manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "backtest_runs" in tables
        assert "trades" in tables
        assert "fold_scores" in tables

    def test_indexes_exist(self, db_manager, ddl_path):
        """Verify all four trade indexes + fold_scores indexes created."""
        db_manager.init_schema(ddl_path)
        indexes = {
            row[0]
            for row in db_manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_trades_strategy_id" in indexes
        assert "idx_trades_session" in indexes
        assert "idx_trades_entry_time" in indexes
        assert "idx_trades_candidate_id" in indexes
        assert "idx_fold_scores_run_id" in indexes
        assert "idx_fold_scores_candidate" in indexes

    def test_schema_matches_contracts_ddl(self, db_manager, ddl_path):
        """Verify table structure matches contracts/sqlite_ddl.sql."""
        db_manager.init_schema(ddl_path)

        # Check trades table columns
        columns = db_manager.connection.execute(
            "PRAGMA table_info(trades)"
        ).fetchall()
        col_names = {c[1] for c in columns}
        expected = {
            "trade_id", "strategy_id", "backtest_run_id", "direction",
            "entry_time", "exit_time", "entry_price", "exit_price",
            "spread_cost", "slippage_cost", "pnl_pips", "session",
            "lot_size", "candidate_id",
        }
        assert expected == col_names

        # Check backtest_runs columns
        columns = db_manager.connection.execute(
            "PRAGMA table_info(backtest_runs)"
        ).fetchall()
        col_names = {c[1] for c in columns}
        expected = {
            "run_id", "strategy_id", "config_hash", "data_hash",
            "spec_version", "started_at", "completed_at", "total_trades",
            "status",
        }
        assert expected == col_names

        # Check fold_scores columns
        columns = db_manager.connection.execute(
            "PRAGMA table_info(fold_scores)"
        ).fetchall()
        col_names = {c[1] for c in columns}
        expected = {
            "id", "backtest_run_id", "candidate_id", "fold_id",
            "fold_start_bar", "fold_end_bar", "sharpe_ratio",
            "profit_factor", "max_drawdown_pct", "total_trades",
            "win_rate", "total_pnl",
        }
        assert expected == col_names

    def test_close_checkpoints_wal(self, tmp_path):
        """Verify close() doesn't raise."""
        db_path = tmp_path / "close_test.db"
        mgr = SQLiteManager(db_path)
        mgr.init_schema()
        mgr.close()  # Should not raise

    def test_context_manager(self, tmp_path):
        """Verify context manager protocol works."""
        db_path = tmp_path / "ctx_test.db"
        with SQLiteManager(db_path) as mgr:
            mgr.init_schema()
            tables = {
                row[0]
                for row in mgr.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "trades" in tables
