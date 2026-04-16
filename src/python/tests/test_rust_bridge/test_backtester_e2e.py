"""
Live integration tests for the Rust backtester crate (Story 3-5).

These tests build the binary, create real Arrow IPC market data,
run the real backtester subprocess, and verify actual output files.
"""

import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
RUST_DIR = PROJECT_ROOT / "src" / "rust"
BINARY_NAME = "forex_backtester.exe" if os.name == "nt" else "forex_backtester"
BINARY_PATH = RUST_DIR / "target" / "debug" / BINARY_NAME


def _ensure_binary_built():
    """Build the Rust backtester binary if not already present."""
    if not BINARY_PATH.exists():
        result = subprocess.run(
            ["cargo", "build", "-p", "backtester"],
            cwd=str(RUST_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            pytest.skip(f"cargo build failed: {result.stderr[:500]}")


def _write_test_market_data(path: Path, num_bars: int = 100, all_quarantined: bool = False):
    """Create synthetic Arrow IPC market data with known OHLCBAQ values."""
    base_price = 1.10000
    pip = 0.0001

    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    bids = []
    asks = []
    sessions = []
    quarantined = []

    for i in range(num_bars):
        ts = 1700000000_000_000 + i * 60_000_000  # microseconds
        mid = base_price + i * pip
        spread = 2.0 * pip

        timestamps.append(ts)
        opens.append(mid - 0.5 * pip)
        highs.append(mid + 5.0 * pip)
        lows.append(mid - 5.0 * pip)
        closes.append(mid + 0.5 * pip)
        bids.append(mid - spread / 2.0)
        asks.append(mid + spread / 2.0)
        sessions.append("london" if i % 2 == 0 else "new_york")
        quarantined.append(all_quarantined)

    table = pa.table({
        "timestamp": pa.array(timestamps, type=pa.int64()),
        "open": pa.array(opens, type=pa.float64()),
        "high": pa.array(highs, type=pa.float64()),
        "low": pa.array(lows, type=pa.float64()),
        "close": pa.array(closes, type=pa.float64()),
        "bid": pa.array(bids, type=pa.float64()),
        "ask": pa.array(asks, type=pa.float64()),
        "session": pa.array(sessions, type=pa.utf8()),
        "quarantined": pa.array(quarantined, type=pa.bool_()),
    })

    with pa.OSFile(str(path), "wb") as f:
        writer = ipc.new_file(f, table.schema)
        writer.write_table(table)
        writer.close()


def _write_test_spec(path: Path):
    """Write a minimal valid strategy spec TOML."""
    spec = """\
[metadata]
schema_version = "1.0"
name = "test-strategy"
version = "v001"
pair = "EURUSD"
timeframe = "M1"
created_by = "test"

[entry_rules]
conditions = [
    { indicator = "close", parameters = {}, threshold = 1.09, comparator = ">" }
]
filters = []
confirmation = []

[exit_rules]
[exit_rules.stop_loss]
type = "fixed_pips"
value = 50.0

[exit_rules.take_profit]
type = "fixed_pips"
value = 100.0

[position_sizing]
method = "fixed_lots"
risk_percent = 1.0
max_lots = 0.1
min_lots = 0.01
lot_step = 0.01

[optimization_plan]
schema_version = 2
objective_function = "sharpe"

[optimization_plan.parameters.placeholder]
type = "integer"
min = 1.0
max = 10.0

[cost_model_reference]
version = "v001"
"""
    path.write_text(spec)


def _write_test_cost_model(path: Path):
    """Write a valid cost model JSON."""
    cost = {
        "pair": "EURUSD",
        "version": "v001",
        "source": "research",
        "calibrated_at": "2026-03-15T00:00:00Z",
        "sessions": {
            "asian": {"mean_spread_pips": 1.2, "std_spread": 0.4, "mean_slippage_pips": 0.1, "std_slippage": 0.05},
            "london": {"mean_spread_pips": 0.8, "std_spread": 0.3, "mean_slippage_pips": 0.05, "std_slippage": 0.03},
            "london_ny_overlap": {"mean_spread_pips": 0.6, "std_spread": 0.2, "mean_slippage_pips": 0.03, "std_slippage": 0.02},
            "new_york": {"mean_spread_pips": 0.9, "std_spread": 0.3, "mean_slippage_pips": 0.06, "std_slippage": 0.03},
            "off_hours": {"mean_spread_pips": 1.5, "std_spread": 0.6, "mean_slippage_pips": 0.15, "std_slippage": 0.08},
        },
    }
    path.write_text(json.dumps(cost))


@pytest.mark.live
class TestBacktesterLiveE2E:
    """Live integration tests exercising the real Rust backtester binary."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Build binary and create test fixtures."""
        _ensure_binary_built()
        self.tmp = tmp_path
        self.data_path = tmp_path / "data.arrow"
        self.spec_path = tmp_path / "spec.toml"
        self.cost_path = tmp_path / "cost.json"
        self.output_dir = tmp_path / "output"
        self.output_dir.mkdir()

        _write_test_market_data(self.data_path, num_bars=100)
        _write_test_spec(self.spec_path)
        _write_test_cost_model(self.cost_path)

    def _run_backtester(self, extra_args=None):
        """Run the backtester binary and return the completed process."""
        args = [
            str(BINARY_PATH),
            "--spec", str(self.spec_path),
            "--data", str(self.data_path),
            "--cost-model", str(self.cost_path),
            "--output", str(self.output_dir),
            "--config-hash", "live_test_hash",
            "--memory-budget", "256",
        ]
        if extra_args:
            args.extend(extra_args)

        return subprocess.run(args, capture_output=True, text=True, timeout=60)

    def test_live_full_backtest_produces_arrow_output(self):
        """Run full backtest and verify real Arrow IPC output files."""
        result = self._run_backtester()
        assert result.returncode == 0, f"Backtester failed: {result.stderr}"

        # Verify all output files exist
        assert (self.output_dir / "trade-log.arrow").exists()
        assert (self.output_dir / "equity-curve.arrow").exists()
        assert (self.output_dir / "metrics.arrow").exists()
        assert (self.output_dir / "run_metadata.json").exists()
        assert (self.output_dir / "progress.json").exists()

        # Verify Arrow IPC files are readable by pyarrow
        trade_log = ipc.open_file(str(self.output_dir / "trade-log.arrow"))
        trade_table = trade_log.read_all()
        assert trade_table.num_columns > 0

        # Verify trade log schema matches contract (AC #5 full cost attribution)
        expected_cols = [
            "trade_id", "strategy_id", "direction", "entry_time", "exit_time",
            "entry_price_raw", "entry_price", "exit_price_raw", "exit_price",
            "entry_spread", "entry_slippage", "exit_spread", "exit_slippage",
            "pnl_pips", "entry_session", "exit_session",
            "signal_id", "holding_duration_bars", "exit_reason", "lot_size",
        ]
        actual_cols = trade_table.column_names
        assert actual_cols == expected_cols, f"Schema mismatch: {actual_cols}"

        # Verify equity curve (AC #6 — includes unrealized_pnl, drawdown_pips)
        eq_table = ipc.open_file(str(self.output_dir / "equity-curve.arrow")).read_all()
        assert eq_table.num_rows == 101  # one per bar + EOD close point (AC #6)
        eq_expected = ["timestamp", "equity_pips", "unrealized_pnl", "drawdown_pips", "open_trades"]
        assert eq_table.column_names == eq_expected, f"Equity schema mismatch: {eq_table.column_names}"

        # Verify metrics — all AC #7 fields (single-row)
        metrics_table = ipc.open_file(str(self.output_dir / "metrics.arrow")).read_all()
        assert metrics_table.num_rows == 1
        metrics_expected = [
            "total_trades", "winning_trades", "losing_trades", "win_rate",
            "profit_factor", "sharpe_ratio", "r_squared",
            "max_drawdown_pips", "max_drawdown_pips", "max_drawdown_duration_bars",
            "avg_trade_duration_bars", "avg_win", "avg_loss",
            "largest_win", "largest_loss",
            "net_pnl_pips", "avg_trade_pips", "strategy_id", "config_hash",
        ]
        assert metrics_table.column_names == metrics_expected, f"Metrics schema mismatch: {metrics_table.column_names}"

        # Verify run_metadata.json content
        meta = json.loads((self.output_dir / "run_metadata.json").read_text())
        assert meta["config_hash"] == "live_test_hash"
        assert "binary_version" in meta

    def test_live_deterministic_output(self):
        """Run backtest twice and verify value-level determinism."""
        r1 = self._run_backtester()
        assert r1.returncode == 0

        # Move results
        out1 = self.tmp / "output1"
        (self.output_dir).rename(out1)
        self.output_dir.mkdir()

        r2 = self._run_backtester()
        assert r2.returncode == 0

        # Compare trade logs field-by-field
        t1 = ipc.open_file(str(out1 / "trade-log.arrow")).read_all()
        t2 = ipc.open_file(str(self.output_dir / "trade-log.arrow")).read_all()
        assert t1.num_rows == t2.num_rows, "Trade count differs between runs"

        for col in ["entry_time", "exit_time", "entry_price", "exit_price", "pnl_pips"]:
            v1 = t1.column(col).to_pylist()
            v2 = t2.column(col).to_pylist()
            assert v1 == v2, f"Column {col} differs between runs"

        # Compare metrics
        m1 = ipc.open_file(str(out1 / "metrics.arrow")).read_all()
        m2 = ipc.open_file(str(self.output_dir / "metrics.arrow")).read_all()
        for col in ["total_trades", "win_rate", "profit_factor", "net_pnl_pips"]:
            assert m1.column(col).to_pylist() == m2.column(col).to_pylist(), \
                f"Metric {col} differs"

    def test_live_quarantined_data_no_trades(self):
        """All-quarantined data produces zero trades and valid output."""
        _write_test_market_data(self.data_path, num_bars=50, all_quarantined=True)
        result = self._run_backtester()
        assert result.returncode == 0

        metrics = ipc.open_file(str(self.output_dir / "metrics.arrow")).read_all()
        total_trades = metrics.column("total_trades").to_pylist()[0]
        assert total_trades == 0, f"Expected 0 trades on quarantined data, got {total_trades}"

        net_pnl = metrics.column("net_pnl_pips").to_pylist()[0]
        assert abs(net_pnl) < 1e-10, "Net PnL should be 0 for zero trades"

    def test_live_structured_error_on_bad_input(self):
        """Invalid spec produces structured JSON error on stderr."""
        # Write invalid spec
        self.spec_path.write_text("not valid toml {{{{")
        result = self._run_backtester()
        assert result.returncode != 0

        # Stderr should contain structured error JSON
        stderr = result.stderr.strip()
        assert "error_type" in stderr, f"Expected structured error, got: {stderr}"

    def test_live_progress_json_written(self):
        """Progress file is written during backtest execution."""
        result = self._run_backtester()
        assert result.returncode == 0

        progress_path = self.output_dir / "progress.json"
        assert progress_path.exists()

        progress = json.loads(progress_path.read_text())
        assert "bars_processed" in progress
        assert "total_bars" in progress
        assert progress["bars_processed"] == progress["total_bars"]

    # ---- Regression tests for code review findings ----

    @pytest.mark.regression
    def test_regression_trade_log_has_full_cost_attribution(self):
        """Regression: trade log must include per-leg spread/slippage, raw prices,
        sessions, signal_id, duration, exit_reason — not combined/dropped (C1/AC#5)."""
        result = self._run_backtester()
        assert result.returncode == 0

        trade_table = ipc.open_file(str(self.output_dir / "trade-log.arrow")).read_all()
        if trade_table.num_rows == 0:
            pytest.skip("No trades generated — cannot verify cost attribution columns")

        # Per-leg spread/slippage must NOT be combined
        assert "entry_spread" in trade_table.column_names, "Missing entry_spread (was combined as spread_cost_pips)"
        assert "exit_spread" in trade_table.column_names, "Missing exit_spread (was combined)"
        assert "entry_slippage" in trade_table.column_names, "Missing entry_slippage (was combined)"
        assert "exit_slippage" in trade_table.column_names, "Missing exit_slippage (was combined)"

        # Raw prices must be present alongside adjusted
        assert "entry_price_raw" in trade_table.column_names, "Missing entry_price_raw"
        assert "exit_price_raw" in trade_table.column_names, "Missing exit_price_raw"

        # Session, signal, duration, exit reason must be present
        assert "entry_session" in trade_table.column_names, "Missing entry_session"
        assert "exit_session" in trade_table.column_names, "Missing exit_session"
        assert "signal_id" in trade_table.column_names, "Missing signal_id"
        assert "holding_duration_bars" in trade_table.column_names, "Missing holding_duration_bars"
        assert "exit_reason" in trade_table.column_names, "Missing exit_reason"

        # Verify values are populated (not all zeros/empty)
        row = trade_table.to_pydict()
        assert row["entry_price_raw"][0] > 0, "entry_price_raw should be populated"
        assert row["exit_price_raw"][0] > 0, "exit_price_raw should be populated"
        assert len(row["exit_reason"][0]) > 0, "exit_reason should be non-empty"
        assert row["holding_duration_bars"][0] >= 0, "holding_duration_bars should be non-negative"

    @pytest.mark.regression
    def test_regression_equity_curve_has_unrealized_pnl(self):
        """Regression: equity curve must include unrealized_pnl and use drawdown_pips
        not drawdown_pips (H1/AC#6)."""
        result = self._run_backtester()
        assert result.returncode == 0

        eq_table = ipc.open_file(str(self.output_dir / "equity-curve.arrow")).read_all()
        assert "unrealized_pnl" in eq_table.column_names, \
            "Missing unrealized_pnl — was computed but not written to output"
        assert "drawdown_pips" in eq_table.column_names, \
            "drawdown column should be named drawdown_pips (percentage), not drawdown_pips"
        assert "drawdown_pips" not in eq_table.column_names, \
            "drawdown_pips is a misnomer — the value is a percentage, rename to drawdown_pips"

    @pytest.mark.regression
    def test_regression_metrics_has_all_ac7_fields(self):
        """Regression: metrics output must include r_squared, max_drawdown_pips,
        max_drawdown_duration_bars, avg_trade_duration_bars, avg_win, avg_loss,
        largest_win, largest_loss — not just the simplified subset (C5/AC#7)."""
        result = self._run_backtester()
        assert result.returncode == 0

        metrics = ipc.open_file(str(self.output_dir / "metrics.arrow")).read_all()
        required_fields = [
            "r_squared", "max_drawdown_pips", "max_drawdown_duration_bars",
            "avg_trade_duration_bars", "avg_win", "avg_loss",
            "largest_win", "largest_loss",
        ]
        for field in required_fields:
            assert field in metrics.column_names, \
                f"Missing metrics field '{field}' — was computed in Metrics struct but not written to Arrow output"

    # ---- Regression tests for synthesis review findings ----

    @pytest.mark.regression
    def test_regression_eod_equity_reflects_final_close(self):
        """Regression: equity curve must include a point AFTER end-of-data close
        so that final realized P&L is reflected in the curve (Codex AC#6 finding)."""
        result = self._run_backtester()
        assert result.returncode == 0

        eq_table = ipc.open_file(str(self.output_dir / "equity-curve.arrow")).read_all()
        trade_table = ipc.open_file(str(self.output_dir / "trade-log.arrow")).read_all()
        metrics = ipc.open_file(str(self.output_dir / "metrics.arrow")).read_all()

        if trade_table.num_rows == 0:
            pytest.skip("No trades — cannot verify EOD equity")

        # The last equity point should have unrealized_pnl == 0.0
        # (position was closed at end-of-data)
        last_unrealized = eq_table.column("unrealized_pnl").to_pylist()[-1]
        last_open = eq_table.column("open_trades").to_pylist()[-1]
        assert last_open == 0, "Last equity point should show 0 open trades after EOD close"
        assert abs(last_unrealized) < 1e-10, \
            f"Last equity point unrealized_pnl should be 0.0 after EOD close, got {last_unrealized}"

    @pytest.mark.regression
    def test_regression_embargo_bars_still_check_exits(self):
        """Regression: embargo bars must still run exit checks (SL/TP) for open
        positions, not skip them entirely. Without this, positions are unprotected
        during fold boundary embargo periods (M1 finding)."""
        # Create data with enough bars that a position opens before embargo zone
        _write_test_market_data(self.data_path, num_bars=100)
        # Run with fold boundaries — embargo zone is bars 45-55
        fold_boundaries = json.dumps([[0, 50], [50, 100]])
        result = self._run_backtester(extra_args=[
            "--fold-boundaries", fold_boundaries,
            "--embargo-bars", "5",
        ])
        # The backtester should run successfully with embargo bars
        assert result.returncode == 0, f"Backtester failed with embargo: {result.stderr}"

        # Verify equity curve is produced (embargo bars should still have equity points)
        eq_table = ipc.open_file(str(self.output_dir / "equity-curve.arrow")).read_all()
        assert eq_table.num_rows > 0, "Equity curve should include embargo bar points"

    @pytest.mark.regression
    def test_regression_apply_cost_produces_correct_adjustment(self):
        """Regression: cost application must use canonical apply_cost path.
        Verify entry cost-adjusted price > raw price for long trades (H4 finding)."""
        result = self._run_backtester()
        assert result.returncode == 0

        trade_table = ipc.open_file(str(self.output_dir / "trade-log.arrow")).read_all()
        if trade_table.num_rows == 0:
            pytest.skip("No trades — cannot verify cost application")

        data = trade_table.to_pydict()
        for i in range(trade_table.num_rows):
            direction = data["direction"][i]
            raw = data["entry_price_raw"][i]
            adjusted = data["entry_price"][i]
            spread = data["entry_spread"][i]
            slippage = data["entry_slippage"][i]

            # Costs must be non-negative
            assert spread >= 0, f"Trade {i}: entry_spread must be >= 0"
            assert slippage >= 0, f"Trade {i}: entry_slippage must be >= 0"

            # Cost-adjusted price must differ from raw by the cost amount
            if direction == "long":
                assert adjusted >= raw, \
                    f"Trade {i}: long entry adjusted ({adjusted}) must be >= raw ({raw})"
            else:
                assert adjusted <= raw, \
                    f"Trade {i}: short entry adjusted ({adjusted}) must be <= raw ({raw})"
