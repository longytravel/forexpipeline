"""Live integration tests for the full result processing pipeline.

These tests exercise REAL system behavior — write real files, create
real SQLite databases, and verify actual output files exist on disk.

Run with: pytest -m live
"""
import json
import shutil
from pathlib import Path

import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from artifacts.sqlite_manager import SQLiteManager
from artifacts.storage import ArtifactStorage
from rust_bridge.result_processor import ProcessingResult, ResultProcessor


@pytest.fixture
def fixtures_dir():
    """Path to backtest output fixtures."""
    d = Path(__file__).resolve().parents[1] / "fixtures" / "backtest_output"
    if not (d / "trade-log.arrow").exists():
        pytest.skip("Backtest fixtures not generated — run generate_backtest_fixtures.py")
    return d


@pytest.fixture
def live_workspace(tmp_path, fixtures_dir):
    """Create a complete workspace with Rust output, artifacts dir, and DB."""
    workspace = tmp_path / "live_workspace"
    workspace.mkdir()

    # Simulate Rust output
    rust_output = workspace / "rust_output"
    rust_output.mkdir()
    for f in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
        shutil.copy2(str(fixtures_dir / f), str(rust_output / f))

    artifacts_root = workspace / "artifacts"
    artifacts_root.mkdir()
    db_path = workspace / "pipeline.db"

    return {
        "workspace": workspace,
        "rust_output": rust_output,
        "artifacts_root": artifacts_root,
        "db_path": db_path,
    }


@pytest.mark.live
class TestLiveResultProcessing:
    """Live tests that exercise the full result processing pipeline."""

    def test_live_full_pipeline_end_to_end(self, live_workspace):
        """Full pipeline: Rust output → Arrow publish → SQLite → Parquet → manifest.

        Verifies:
        - All artifact files exist on disk
        - SQLite has correct trade count
        - Parquet files are readable
        - Manifest has all required fields
        - Version directory structure is correct
        """
        ws = live_workspace
        processor = ResultProcessor(ws["artifacts_root"], ws["db_path"])

        result = processor.process_backtest_results(
            strategy_id="EURUSD_ma_cross",
            backtest_run_id="live_run_001",
            config_hash="sha256:live_cfg_hash",
            data_hash="sha256:live_data_hash",
            cost_model_hash="sha256:live_cost_hash",
            strategy_spec_hash="sha256:live_spec_hash",
            rust_output_dir=ws["rust_output"],
            strategy_spec_version="v001",
            cost_model_version="v001",
            run_timestamp="2025-06-15T12:00:00Z",
        )

        # --- Verify ProcessingResult ---
        assert isinstance(result, ProcessingResult)
        assert result.version == 1
        assert result.trade_count == 50
        assert result.backtest_run_id == "live_run_001"

        # --- Verify directory structure (AC #2) ---
        version_dir = ws["artifacts_root"] / "EURUSD_ma_cross" / "v001"
        assert version_dir.is_dir()
        backtest_dir = version_dir / "backtest"
        assert backtest_dir.is_dir()

        # --- Verify Arrow IPC files on disk ---
        arrow_files = ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]
        for f in arrow_files:
            path = backtest_dir / f
            assert path.exists(), f"Missing: {f}"
            assert path.stat().st_size > 0, f"Empty: {f}"

        # --- Verify Parquet archival files on disk (AC #8) ---
        parquet_files = ["trade-log.parquet", "equity-curve.parquet", "metrics.parquet"]
        for f in parquet_files:
            path = backtest_dir / f
            assert path.exists(), f"Missing: {f}"
            assert path.stat().st_size > 0, f"Empty: {f}"

        # --- Verify Arrow data content ---
        reader = pyarrow.ipc.open_file(str(backtest_dir / "trade-log.arrow"))
        trade_table = reader.read_all()
        assert trade_table.num_rows == 50
        assert "trade_id" in trade_table.column_names
        assert "direction" in trade_table.column_names

        # --- Verify Parquet data content ---
        pq_trade = pq.read_table(str(backtest_dir / "trade-log.parquet"))
        assert pq_trade.num_rows == 50
        assert pq_trade.column("trade_id").to_pylist() == trade_table.column("trade_id").to_pylist()

        # --- Verify manifest.json (AC #4, #5) ---
        manifest_path = version_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema_version"] == "1.0"
        assert manifest["strategy_id"] == "EURUSD_ma_cross"
        assert manifest["version"] == 1
        assert manifest["provenance"]["config_hash"] == "sha256:live_cfg_hash"
        assert manifest["provenance"]["dataset_hash"] == "sha256:live_data_hash"
        assert manifest["metrics_summary"]["total_trades"] == 50

        # --- Verify SQLite database (AC #3, #9) ---
        assert ws["db_path"].exists()
        with SQLiteManager(ws["db_path"]) as mgr:
            # WAL mode (AC #9)
            mode = mgr.connection.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"

            # Trade count
            count = mgr.connection.execute(
                "SELECT COUNT(*) FROM trades WHERE backtest_run_id = ?",
                ("live_run_001",),
            ).fetchone()[0]
            assert count == 50

            # Backtest run record
            run = mgr.connection.execute(
                "SELECT status, total_trades, strategy_id FROM backtest_runs WHERE run_id = ?",
                ("live_run_001",),
            ).fetchone()
            assert run[0] == "completed"
            assert run[1] == 50
            assert run[2] == "EURUSD_ma_cross"

            # Verify trade data content
            row = mgr.connection.execute(
                "SELECT direction, entry_time, session FROM trades LIMIT 1"
            ).fetchone()
            assert row[0] in ("long", "short")
            assert "T" in row[1]  # ISO 8601 format
            assert row[2] in ("asian", "london", "new_york", "london_ny_overlap", "off_hours")

        # --- Verify no .partial files (AC #7) ---
        partials = list(version_dir.rglob("*.partial"))
        assert len(partials) == 0

        # --- Verify checkpoint file ---
        checkpoint_path = version_dir / "_processing_checkpoint.json"
        assert checkpoint_path.exists()
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        assert checkpoint["arrow_published"] is True
        assert checkpoint["sqlite_ingested"] is True
        assert checkpoint["parquet_archived"] is True
        assert checkpoint["manifest_written"] is True

    def test_live_version_increment_on_hash_change(self, live_workspace):
        """New version directory on input hash change (AC #6).

        Verifies that changing cost_model_hash creates v002 instead
        of overwriting v001.
        """
        ws = live_workspace
        processor = ResultProcessor(ws["artifacts_root"], ws["db_path"])

        # First run → v001
        result1 = processor.process_backtest_results(
            strategy_id="EURUSD_ma_cross",
            backtest_run_id="live_v1_run",
            config_hash="sha256:cfg1",
            data_hash="sha256:data1",
            cost_model_hash="sha256:cost_v1",
            strategy_spec_hash="sha256:spec1",
            rust_output_dir=ws["rust_output"],
            strategy_spec_version="v001",
            cost_model_version="v001",
            run_timestamp="2025-06-15T12:00:00Z",
        )
        assert result1.version == 1
        assert (ws["artifacts_root"] / "EURUSD_ma_cross" / "v001").is_dir()

        # Second run with changed cost model hash → v002
        result2 = processor.process_backtest_results(
            strategy_id="EURUSD_ma_cross",
            backtest_run_id="live_v2_run",
            config_hash="sha256:cfg1",
            data_hash="sha256:data1",
            cost_model_hash="sha256:cost_v2_CHANGED",
            strategy_spec_hash="sha256:spec1",
            rust_output_dir=ws["rust_output"],
            strategy_spec_version="v001",
            cost_model_version="v002",
            run_timestamp="2025-06-15T13:00:00Z",
        )
        assert result2.version == 2
        assert (ws["artifacts_root"] / "EURUSD_ma_cross" / "v002").is_dir()

        # Both versions exist independently
        assert (ws["artifacts_root"] / "EURUSD_ma_cross" / "v001" / "manifest.json").exists()
        assert (ws["artifacts_root"] / "EURUSD_ma_cross" / "v002" / "manifest.json").exists()

    def test_live_crash_safe_write_integrity(self, live_workspace):
        """Verify crash-safe write pattern leaves no partial artifacts (AC #7).

        Runs full processing and verifies:
        - No .partial files anywhere in the artifact tree
        - All files are complete and readable
        - Source Rust output dir is untouched
        """
        ws = live_workspace
        processor = ResultProcessor(ws["artifacts_root"], ws["db_path"])

        result = processor.process_backtest_results(
            strategy_id="EURUSD_ma_cross",
            backtest_run_id="live_crash_safe_run",
            config_hash="sha256:cfg1",
            data_hash="sha256:data1",
            cost_model_hash="sha256:cost1",
            strategy_spec_hash="sha256:spec1",
            rust_output_dir=ws["rust_output"],
            strategy_spec_version="v001",
            cost_model_version="v001",
            run_timestamp="2025-06-15T12:00:00Z",
        )

        # No .partial files anywhere
        all_partials = list(ws["artifacts_root"].rglob("*.partial"))
        assert len(all_partials) == 0, f"Found partial files: {all_partials}"

        # All Arrow files readable
        backtest_dir = result.artifact_dir / "backtest"
        for arrow_file in backtest_dir.glob("*.arrow"):
            reader = pyarrow.ipc.open_file(str(arrow_file))
            table = reader.read_all()
            assert table.num_rows > 0

        # All Parquet files readable
        for pq_file in backtest_dir.glob("*.parquet"):
            table = pq.read_table(str(pq_file))
            assert table.num_rows > 0

        # Source Rust output directory untouched
        for f in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            assert (ws["rust_output"] / f).exists()
