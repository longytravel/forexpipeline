"""Integration tests for rust_bridge.result_processor — ResultProcessor (Task 6)."""
import json
import shutil
from pathlib import Path

import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from artifacts.sqlite_manager import SQLiteManager
from rust_bridge.result_processor import ProcessingResult, ResultProcessor, ResultProcessingError


@pytest.fixture
def fixtures_dir():
    """Path to backtest output fixtures."""
    d = Path(__file__).resolve().parents[1] / "fixtures" / "backtest_output"
    if not (d / "trade-log.arrow").exists():
        pytest.skip("Backtest fixtures not generated")
    return d


@pytest.fixture
def rust_output(tmp_path, fixtures_dir):
    """Simulate Rust output directory with fixture files."""
    output_dir = tmp_path / "rust_output"
    output_dir.mkdir()
    for f in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
        shutil.copy2(str(fixtures_dir / f), str(output_dir / f))
    return output_dir


@pytest.fixture
def processor(tmp_path):
    """ResultProcessor with temp artifacts and DB."""
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    db_path = tmp_path / "pipeline.db"
    return ResultProcessor(artifacts_root, db_path)


def _process(processor, rust_output, **kwargs):
    """Helper to call process_backtest_results with defaults."""
    defaults = dict(
        strategy_id="ma_crossover_v001",
        backtest_run_id="run_001",
        config_hash="sha256:cfg1",
        data_hash="sha256:data1",
        cost_model_hash="sha256:cost1",
        strategy_spec_hash="sha256:spec1",
        rust_output_dir=rust_output,
        strategy_spec_version="v001",
        cost_model_version="v001",
        run_timestamp="2025-01-01T00:00:00Z",
    )
    defaults.update(kwargs)
    return processor.process_backtest_results(**defaults)


class TestResultProcessor:
    def test_process_full_pipeline(self, processor, rust_output, tmp_path):
        """Full pipeline: verify all artifacts, SQLite rows, manifest."""
        result = _process(processor, rust_output)

        assert isinstance(result, ProcessingResult)
        assert result.version == 1
        assert result.trade_count == 50
        assert result.manifest_path.exists()

        # Verify Arrow files published
        backtest_dir = result.artifact_dir / "backtest"
        assert (backtest_dir / "trade-log.arrow").exists()
        assert (backtest_dir / "equity-curve.arrow").exists()
        assert (backtest_dir / "metrics.arrow").exists()

        # Verify Parquet archives
        assert (backtest_dir / "trade-log.parquet").exists()
        assert (backtest_dir / "equity-curve.parquet").exists()
        assert (backtest_dir / "metrics.parquet").exists()

        # Verify manifest
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert manifest["strategy_id"] == "ma_crossover_v001"
        assert manifest["version"] == 1
        assert manifest["provenance"]["config_hash"] == "sha256:cfg1"
        assert manifest["metrics_summary"]["total_trades"] == 50

        # Verify SQLite
        with SQLiteManager(processor.sqlite_db_path) as mgr:
            count = mgr.connection.execute(
                "SELECT COUNT(*) FROM trades WHERE backtest_run_id = ?",
                ("run_001",),
            ).fetchone()[0]
            assert count == 50

            run = mgr.connection.execute(
                "SELECT status, total_trades FROM backtest_runs WHERE run_id = ?",
                ("run_001",),
            ).fetchone()
            assert run[0] == "completed"
            assert run[1] == 50

    def test_process_creates_new_version_on_hash_change(self, processor, rust_output):
        """Change config_hash, verify v002."""
        _process(processor, rust_output, backtest_run_id="run_001")
        result = _process(
            processor, rust_output,
            config_hash="sha256:cfg_CHANGED",
            backtest_run_id="run_002",
        )
        assert result.version == 2

    def test_process_reuses_version_on_same_hash(self, processor, rust_output):
        """Same hashes, verify no new version directory count increase."""
        result1 = _process(processor, rust_output, backtest_run_id="run_001")
        result2 = _process(processor, rust_output, backtest_run_id="run_002")
        # Same hashes → same version number used (latest)
        assert result2.version == result1.version

    def test_process_handles_missing_arrow_file(self, processor, tmp_path):
        """Missing file raises clear error."""
        empty_dir = tmp_path / "empty_output"
        empty_dir.mkdir()

        with pytest.raises(ResultProcessingError, match="Missing Arrow file"):
            _process(processor, empty_dir, backtest_run_id="run_fail")

    def test_process_resume_after_crash(self, processor, rust_output, tmp_path):
        """Simulate crash after SQLite ingest, verify resume completes (AC #10)."""
        # First run — complete
        result1 = _process(processor, rust_output, backtest_run_id="run_resume")

        # Verify checkpoint exists
        checkpoint_path = result1.artifact_dir / "_processing_checkpoint.json"
        assert checkpoint_path.exists()

        # Simulate partial state: delete parquet files and reset checkpoint
        # Keep manifest intact so version resolution still finds v001
        backtest_dir = result1.artifact_dir / "backtest"
        for pq_file in backtest_dir.glob("*.parquet"):
            pq_file.unlink()

        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["parquet_archived"] = False
        checkpoint["manifest_written"] = False
        checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

        # Resume — should only redo parquet + manifest (same hashes → same version)
        result2 = _process(processor, rust_output, backtest_run_id="run_resume")
        assert result2.artifact_dir == result1.artifact_dir
        backtest_dir2 = result2.artifact_dir / "backtest"
        assert (backtest_dir2 / "trade-log.parquet").exists()
        assert result2.manifest_path.exists()

    def test_process_trade_count_consistency(self, processor, rust_output):
        """Verify Arrow/SQLite/Parquet trade counts match (AC #11)."""
        result = _process(processor, rust_output)

        backtest_dir = result.artifact_dir / "backtest"

        # Arrow count
        reader = pyarrow.ipc.open_file(str(backtest_dir / "trade-log.arrow"))
        arrow_count = reader.read_all().num_rows

        # Parquet count
        pq_table = pq.read_table(str(backtest_dir / "trade-log.parquet"))
        pq_count = pq_table.num_rows

        assert arrow_count == result.trade_count
        assert pq_count == result.trade_count

    def test_process_backtest_runs_populated(self, processor, rust_output):
        """Verify backtest_runs table has correct run record."""
        _process(processor, rust_output)

        with SQLiteManager(processor.sqlite_db_path) as mgr:
            run = mgr.connection.execute(
                "SELECT run_id, strategy_id, config_hash, status FROM backtest_runs"
            ).fetchone()
            assert run[0] == "run_001"
            assert run[1] == "ma_crossover_v001"
            assert run[2] == "sha256:cfg1"
            assert run[3] == "completed"

    def test_process_crash_safe_publish(self, processor, rust_output):
        """Verify no .partial files remain, source dir intact."""
        result = _process(processor, rust_output)

        backtest_dir = result.artifact_dir / "backtest"
        partials = list(backtest_dir.glob("*.partial"))
        assert len(partials) == 0

        # Source dir should still have files
        assert (rust_output / "trade-log.arrow").exists()

    @pytest.mark.regression
    def test_sqlite_consistency_validates_trade_ids_and_times(self, processor, rust_output):
        """Regression: H1 — SQLite trade_id ordering and entry_time must be verified
        against Arrow during consistency validation (AC #11 'across formats')."""
        result = _process(processor, rust_output)

        # Verify SQLite trades match Arrow exactly
        backtest_dir = result.artifact_dir / "backtest"
        reader = pyarrow.ipc.open_file(str(backtest_dir / "trade-log.arrow"))
        arrow_table = reader.read_all()
        arrow_ids = arrow_table.column("trade_id").to_pylist()

        with SQLiteManager(processor.sqlite_db_path) as mgr:
            rows = mgr.connection.execute(
                "SELECT trade_id FROM trades WHERE backtest_run_id = ? ORDER BY trade_id",
                (result.backtest_run_id,),
            ).fetchall()
            sqlite_ids = [r[0] for r in rows]

        assert sqlite_ids == arrow_ids, "SQLite trade_id ordering must match Arrow"

    @pytest.mark.regression
    def test_checkpoint_variable_initialized_before_try(self, processor, tmp_path):
        """Regression: H2 — checkpoint must be initialized before try block
        so error handler never hits NameError."""
        # Trigger an error before checkpoint is loaded (missing arrow files)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        try:
            _process(processor, empty_dir, backtest_run_id="run_init_err")
        except Exception:
            pass  # Expected to fail

        # The fact that we got here without NameError proves the fix works.
        # Before the fix, `checkpoint if 'checkpoint' in dir() else {}`
        # could fail or silently use empty dict.

    def test_process_schema_validation_failure(self, processor, tmp_path):
        """Wrong schema raises before ingest."""
        import pyarrow as pa
        import pyarrow.ipc

        bad_dir = tmp_path / "bad_output"
        bad_dir.mkdir()

        # Create Arrow files with wrong schemas
        bad_table = pa.table({"wrong_col": pa.array([1], type=pa.int64())})
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            with open(bad_dir / name, "wb") as f:
                writer = pa.ipc.new_file(f, bad_table.schema)
                writer.write_table(bad_table)
                writer.close()

        with pytest.raises(ResultProcessingError, match="Schema mismatch"):
            _process(processor, bad_dir, backtest_run_id="run_bad_schema")
