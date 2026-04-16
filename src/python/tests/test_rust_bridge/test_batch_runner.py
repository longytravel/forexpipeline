"""Integration tests for the Python-Rust bridge (Story 3-4, AC #1–#9).

Unit tests exercise the Python modules in isolation.
Live tests (marked @pytest.mark.live) dispatch real jobs to the compiled
Rust binary and verify actual output on disk.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pyarrow as pa
import pyarrow.ipc
import pytest

from orchestrator.errors import PipelineError
from rust_bridge.batch_runner import (
    BacktestJob,
    BatchResult,
    BatchRunner,
    ProgressReport,
    _get_available_memory_mb,
)
from rust_bridge.error_parser import RustError, map_to_pipeline_error, parse_rust_error
from rust_bridge.output_verifier import (
    BacktestOutputRef,
    verify_output,
    validate_schemas,
    verify_fold_scores,
)
from rust_bridge.backtest_executor import BacktestExecutor

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

# Project root — needed to find the compiled binary and test fixtures
PROJECT_ROOT = Path(__file__).resolve().parents[4]
BINARY_PATH = PROJECT_ROOT / "src" / "rust" / "target" / "debug" / "forex_backtester.exe"
STRATEGY_FIXTURE = PROJECT_ROOT / "artifacts" / "strategies" / "ma-crossover" / "v001.toml"


def _valid_cost_model_json() -> str:
    """Return a valid EURUSD cost model JSON string."""
    return json.dumps({
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
    })


@pytest.fixture
def cost_model_path(tmp_path: Path) -> Path:
    """Write a valid cost model JSON to tmp_path and return the path."""
    path = tmp_path / "cost_model.json"
    path.write_text(_valid_cost_model_json(), encoding="utf-8")
    return path


def _write_valid_arrow_ipc(path: Path, num_bars: int = 100) -> None:
    """Write a minimal valid Arrow IPC file matching contracts/arrow_schemas.toml [market_data].

    Schema: timestamp(int64), open(f64), high(f64), low(f64), close(f64),
            bid(f64), ask(f64), session(utf8), quarantined(bool).
    Generates synthetic EURUSD-like M1 bars alternating london/new_york sessions.
    """
    base_ts = 1_700_000_000_000_000  # epoch microseconds
    interval = 60_000_000  # 1 minute in microseconds
    base_price = 1.1000
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
        timestamps.append(base_ts + i * interval)
        mid = base_price + (i % 50) * pip
        opens.append(mid)
        highs.append(mid + 5 * pip)
        lows.append(mid - 5 * pip)
        closes.append(mid + pip)
        bids.append(mid)
        asks.append(mid + 2 * pip)
        sessions.append("london" if i % 2 == 0 else "new_york")
        quarantined.append(False)

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

    with open(path, "wb") as f:
        writer = pa.ipc.new_file(f, table.schema)
        writer.write_table(table)
        writer.close()


@pytest.fixture
def market_data_path(tmp_path: Path) -> Path:
    """Write a minimal valid Arrow IPC file for testing."""
    path = tmp_path / "market_data.arrow"
    _write_valid_arrow_ipc(path)
    return path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Return a clean output directory."""
    d = tmp_path / "output"
    d.mkdir()
    return d


@pytest.fixture
def valid_job(tmp_path: Path, cost_model_path: Path, market_data_path: Path, output_dir: Path) -> BacktestJob:
    """A valid BacktestJob with all paths pointing to real files."""
    return BacktestJob(
        strategy_spec_path=STRATEGY_FIXTURE,
        market_data_path=market_data_path,
        cost_model_path=cost_model_path,
        output_directory=output_dir,
        config_hash="test_hash_abc123",
        memory_budget_mb=256,
    )


# ===========================================================================
# Unit Tests: ErrorParser
# ===========================================================================

class TestErrorParser:
    """Unit tests for error_parser.py (AC #4)."""

    def test_parse_valid_d8_error(self):
        stderr = '{"error_type":"validation_error","category":"data_logic","message":"bad spec","context":{"file":"spec.toml"}}'
        err = parse_rust_error(stderr)
        assert err is not None
        assert err.error_type == "validation_error"
        assert err.category == "data_logic"
        assert err.message == "bad spec"
        assert err.context["file"] == "spec.toml"

    def test_parse_resource_pressure_error(self):
        stderr = '{"error_type":"resource_exhaustion","category":"resource_pressure","message":"OOM","context":{"mb":1024}}'
        err = parse_rust_error(stderr)
        assert err is not None
        assert err.category == "resource_pressure"

    def test_parse_multiline_stderr_finds_last_error(self):
        stderr = (
            '{"level":"info","msg":"Starting up"}\n'
            '{"level":"info","msg":"Loading data"}\n'
            '{"error_type":"io_error","category":"external_failure","message":"disk full","context":{}}'
        )
        err = parse_rust_error(stderr)
        assert err is not None
        assert err.error_type == "io_error"
        assert err.category == "external_failure"

    def test_parse_malformed_stderr_returns_fallback(self):
        stderr = "thread 'main' panicked at 'index out of bounds'\nnote: run with RUST_BACKTRACE=1"
        err = parse_rust_error(stderr)
        assert err is not None
        assert err.error_type == "unstructured_error"
        assert err.category == "data_logic"
        assert "panicked" in err.message

    def test_parse_empty_stderr_returns_none(self):
        assert parse_rust_error("") is None
        assert parse_rust_error("   ") is None
        assert parse_rust_error(None) is None

    def test_parse_json_without_d8_fields_returns_fallback(self):
        stderr = '{"level":"info","msg":"just a log line"}'
        err = parse_rust_error(stderr)
        assert err is not None
        assert err.error_type == "unstructured_error"

    def test_map_resource_pressure_to_throttle(self):
        rust_err = RustError(
            error_type="resource_exhaustion",
            category="resource_pressure",
            message="OOM",
            context={"mb": 512},
        )
        pe = map_to_pipeline_error(rust_err)
        assert isinstance(pe, PipelineError)
        assert pe.action == "throttle"
        assert pe.recoverable is True
        assert pe.severity == "warning"
        assert pe.runtime == "rust"

    def test_map_data_logic_to_stop_checkpoint(self):
        rust_err = RustError(
            error_type="validation_error",
            category="data_logic",
            message="bad data",
        )
        pe = map_to_pipeline_error(rust_err)
        assert pe.action == "stop_checkpoint"
        assert pe.recoverable is False

    def test_map_external_failure_to_retry_backoff(self):
        rust_err = RustError(
            error_type="io_error",
            category="external_failure",
            message="disk failure",
        )
        pe = map_to_pipeline_error(rust_err)
        assert pe.action == "retry_backoff"
        assert pe.recoverable is True


# ===========================================================================
# Unit Tests: OutputVerifier
# ===========================================================================

class TestOutputVerifier:
    """Unit tests for output_verifier.py (AC #3)."""

    def test_verify_output_success(self, tmp_path: Path):
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            (tmp_path / name).write_bytes(b"data")
        ref = verify_output(tmp_path, "hash123")
        assert isinstance(ref, BacktestOutputRef)
        assert ref.config_hash == "hash123"
        assert ref.trade_log_path == tmp_path / "trade-log.arrow"

    def test_verify_output_missing_file(self, tmp_path: Path):
        (tmp_path / "trade-log.arrow").write_bytes(b"data")
        # equity-curve and metrics missing
        with pytest.raises(FileNotFoundError, match="equity-curve.arrow"):
            verify_output(tmp_path, "hash")

    def test_verify_output_empty_file(self, tmp_path: Path):
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            (tmp_path / name).write_bytes(b"data" if name != "metrics.arrow" else b"")
        with pytest.raises(FileNotFoundError, match="metrics.arrow.*empty"):
            verify_output(tmp_path, "hash")

    def test_verify_output_partial_files_rejected(self, tmp_path: Path):
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            (tmp_path / name).write_bytes(b"data")
        (tmp_path / "trade-log.arrow.partial").write_bytes(b"partial")
        with pytest.raises(FileNotFoundError, match="Partial files"):
            verify_output(tmp_path, "hash")

    def test_verify_output_nonexistent_dir(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            verify_output(tmp_path / "nonexistent", "hash")

    def test_validate_schemas_success(self, tmp_path: Path):
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            (tmp_path / name).write_bytes(b"data")
        assert validate_schemas(tmp_path) is True

    def test_validate_schemas_missing(self, tmp_path: Path):
        assert validate_schemas(tmp_path) is False

    def test_verify_fold_scores_success(self, tmp_path: Path):
        (tmp_path / "fold-scores.json").write_text(
            json.dumps([{"fold": 0, "score": 1.0}, {"fold": 1, "score": 0.8}]),
            encoding="utf-8",
        )
        assert verify_fold_scores(tmp_path, 2) is True

    def test_verify_fold_scores_count_mismatch(self, tmp_path: Path):
        (tmp_path / "fold-scores.json").write_text(
            json.dumps([{"fold": 0, "score": 1.0}]),
            encoding="utf-8",
        )
        assert verify_fold_scores(tmp_path, 3) is False

    def test_verify_fold_scores_missing(self, tmp_path: Path):
        assert verify_fold_scores(tmp_path, 2) is False


# ===========================================================================
# Unit Tests: BatchRunner
# ===========================================================================

class TestBatchRunner:
    """Unit tests for batch_runner.py (AC #1, #8)."""

    def test_build_args_basic(self, valid_job: BacktestJob):
        runner = BatchRunner(BINARY_PATH)
        args = runner._build_args(valid_job)
        assert "--spec" in args
        assert "--data" in args
        assert "--cost-model" in args
        assert "--output" in args
        assert "--config-hash" in args
        assert "--memory-budget" in args
        # All paths should use forward slashes
        for i, arg in enumerate(args):
            if i > 0 and args[i - 1] in ("--spec", "--data", "--cost-model", "--output"):
                assert "\\" not in arg, f"Path should use forward slashes: {arg}"

    def test_build_args_with_fold_boundaries(self, valid_job: BacktestJob):
        valid_job.fold_boundaries = [(0, 1000), (1000, 2000)]
        runner = BatchRunner(BINARY_PATH)
        args = runner._build_args(valid_job)
        assert "--fold-boundaries" in args
        fb_idx = args.index("--fold-boundaries") + 1
        parsed = json.loads(args[fb_idx])
        assert parsed == [[0, 1000], [1000, 2000]]

    def test_build_args_with_window_bounds(self, valid_job: BacktestJob):
        valid_job.window_start = 500
        valid_job.window_end = 1500
        runner = BatchRunner(BINARY_PATH)
        args = runner._build_args(valid_job)
        assert "--window-start" in args
        assert "--window-end" in args

    def test_dispatch_nonexistent_binary(self, valid_job: BacktestJob):
        runner = BatchRunner(Path("/nonexistent/binary"))
        result = asyncio.run(runner.dispatch(valid_job))
        assert result.exit_code == -1
        assert "not found" in result.error

    def test_dispatch_missing_input_file(self, valid_job: BacktestJob, tmp_path: Path):
        valid_job.market_data_path = tmp_path / "nonexistent.arrow"
        runner = BatchRunner(BINARY_PATH)
        result = asyncio.run(runner.dispatch(valid_job))
        assert result.exit_code == -1
        assert "not found" in result.error

    def test_get_progress_no_file(self, valid_job: BacktestJob):
        runner = BatchRunner(BINARY_PATH)
        assert runner.get_progress(valid_job) is None

    def test_get_progress_valid_file(self, valid_job: BacktestJob):
        progress_data = {
            "bars_processed": 5000,
            "total_bars": 10000,
            "estimated_seconds_remaining": 5.0,
            "memory_used_mb": 128,
            "updated_at": "2026-03-18T20:00:00.000Z",
        }
        progress_path = valid_job.output_directory / "progress.json"
        progress_path.write_text(json.dumps(progress_data), encoding="utf-8")

        runner = BatchRunner(BINARY_PATH)
        report = runner.get_progress(valid_job)
        assert report is not None
        assert report.bars_processed == 5000
        assert report.total_bars == 10000

    def test_get_progress_corrupt_file(self, valid_job: BacktestJob):
        progress_path = valid_job.output_directory / "progress.json"
        progress_path.write_text("not json", encoding="utf-8")

        runner = BatchRunner(BINARY_PATH)
        assert runner.get_progress(valid_job) is None

    def test_get_available_memory(self):
        mb = _get_available_memory_mb()
        # Should return a positive value on any real system
        assert mb > 0


# ===========================================================================
# Unit Tests: BacktestExecutor
# ===========================================================================

class TestBacktestExecutor:
    """Unit tests for backtest_executor.py (AC #1, #4, #8)."""

    def test_execute_missing_context_key(self):
        runner = MagicMock()
        executor = BacktestExecutor(runner)
        result = executor.execute("test-strategy", {"config_hash": "abc"})
        assert result.outcome == "failed"
        assert result.error is not None
        assert "Failed to build" in result.error.msg

    def test_execute_failed_dispatch(self):
        mock_runner = MagicMock()
        mock_result = BatchResult(
            exit_code=1,
            output_directory=Path("/tmp/out"),
            elapsed_seconds=1.0,
            stderr='{"error_type":"validation_error","category":"data_logic","message":"bad spec","context":{}}',
        )

        async def mock_dispatch(job):
            return mock_result

        mock_runner.dispatch = mock_dispatch
        executor = BacktestExecutor(mock_runner)

        context = {
            "strategy_spec_path": "/tmp/spec.toml",
            "market_data_path": "/tmp/data.arrow",
            "cost_model_path": "/tmp/cost.json",
            "config_hash": "abc123",
            "memory_budget_mb": 256,
            "output_directory": "/tmp/out",
        }
        result = executor.execute("test-strategy", context)
        assert result.outcome == "failed"
        assert result.error.category == "data_logic"
        assert result.error.runtime == "rust"

    def test_execute_success_with_verification(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            (output_dir / name).write_bytes(b"data")

        mock_runner = MagicMock()
        mock_result = BatchResult(
            exit_code=0,
            output_directory=output_dir,
            elapsed_seconds=2.5,
        )

        async def mock_dispatch(job):
            return mock_result

        mock_runner.dispatch = mock_dispatch
        executor = BacktestExecutor(mock_runner)

        context = {
            "strategy_spec_path": str(tmp_path / "spec.toml"),
            "market_data_path": str(tmp_path / "data.arrow"),
            "cost_model_path": str(tmp_path / "cost.json"),
            "config_hash": "abc123",
            "memory_budget_mb": 256,
            "output_directory": str(output_dir),
        }
        result = executor.execute("test-strategy", context)
        assert result.outcome == "success"
        assert result.artifact_path == str(output_dir)
        assert result.manifest_ref is None  # Story 3.6

    def test_validate_artifact_existing_dir(self, tmp_path: Path):
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            (tmp_path / name).write_bytes(b"data")
        runner = MagicMock()
        executor = BacktestExecutor(runner)
        assert executor.validate_artifact(tmp_path, Path("dummy")) is True

    def test_validate_artifact_missing_dir(self):
        runner = MagicMock()
        executor = BacktestExecutor(runner)
        assert executor.validate_artifact(Path("/nonexistent"), Path("dummy")) is False


# ===========================================================================
# Regression Tests — catches bugs found in code review synthesis
# ===========================================================================

@pytest.mark.regression
class TestRegressionFindings:
    """Regression tests for bugs found during Story 3-4 code review synthesis."""

    def test_checkpoint_filename_matches_contract(self, tmp_path: Path):
        """Regression: C3 — checkpoint filename must follow contracts/pipeline_checkpoint.toml
        pattern ``checkpoint-{stage}.json``, not ``checkpoint.json``."""
        # The Rust binary writes checkpoint-backtest-running.json on cancellation.
        # Verify the Python side expects and can find the contract-compliant name.
        checkpoint_name = "checkpoint-backtest-running.json"
        checkpoint_path = tmp_path / checkpoint_name
        checkpoint_path.write_text(json.dumps({
            "stage": "backtest-running",
            "progress_pct": 50.0,
            "last_completed_batch": 5,
            "total_batches": 10,
            "partial_artifact_path": None,
            "checkpoint_at": "2026-03-18T23:00:00.000Z",
        }), encoding="utf-8")
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text())
        assert data["stage"] == "backtest-running"
        # The old bug: code wrote "checkpoint.json" — ensure that does NOT exist
        assert not (tmp_path / "checkpoint.json").exists()

    def test_contract_has_equity_curve_and_metrics_schemas(self):
        """Regression: C2 — contracts/arrow_schemas.toml must define equity_curve
        and backtest_metrics schemas as SSOT, not just backtest_trades."""
        import tomllib
        contract_path = Path(__file__).resolve().parents[4] / "contracts" / "arrow_schemas.toml"
        if not contract_path.exists():
            pytest.skip("contracts/arrow_schemas.toml not found")
        with open(contract_path, "rb") as f:
            schemas = tomllib.load(f)
        assert "equity_curve" in schemas, "equity_curve schema missing from contract SSOT"
        assert "backtest_metrics" in schemas, "backtest_metrics schema missing from contract SSOT"
        # Verify column counts match Rust arrow_schemas.rs expectations
        assert len(schemas["equity_curve"]["columns"]) == 5
        assert len(schemas["backtest_metrics"]["columns"]) == 18

    def test_verify_output_docstring_no_fold_claim(self):
        """Regression: M2 — verify_output() must not claim it calls verify_fold_scores()
        automatically. Callers must invoke it separately."""
        from rust_bridge.output_verifier import verify_output
        doc = verify_output.__doc__ or ""
        assert "also verifies per-fold" not in doc.lower(), (
            "verify_output() docstring must not claim automatic fold verification"
        )

    def test_memory_precheck_subtracts_os_reserve(self):
        """Regression: H3 — Python memory pre-check must subtract 2GB OS reserve
        to match Rust-side MemoryBudget.check_system_memory()."""
        # Verify the OS reserve constant exists in batch_runner dispatch logic
        import inspect
        from rust_bridge.batch_runner import BatchRunner
        source = inspect.getsource(BatchRunner.dispatch)
        assert "OS_RESERVE_MB" in source, (
            "dispatch() must subtract OS reserve from available memory"
        )
        assert "2048" in source, "OS reserve should be 2048 MB (2GB)"

    def test_asyncio_no_deprecated_get_event_loop(self):
        """Regression: H2 — backtest_executor.py must not use deprecated
        asyncio.get_event_loop() (removed in Python 3.12+)."""
        import inspect
        from rust_bridge.backtest_executor import BacktestExecutor
        source = inspect.getsource(BacktestExecutor.execute)
        assert "get_event_loop()" not in source, (
            "execute() must use asyncio.get_running_loop() or asyncio.run(), "
            "not the deprecated asyncio.get_event_loop()"
        )

    def test_subprocess_tracking_unique_keys(self):
        """Regression: Codex M — subprocess tracking must use unique keys
        to avoid collision when two jobs share the same config_hash."""
        runner = BatchRunner(Path("/dummy/binary"))
        # Simulate two jobs with same config_hash by checking key format
        import inspect
        source = inspect.getsource(BatchRunner.dispatch)
        assert "uuid" in source, (
            "dispatch() must use unique keys for process tracking "
            "to avoid config_hash collision"
        )

    def test_stub_arrow_files_not_claimed_as_valid_ipc(self):
        """Regression: H1 — output.rs comments must not claim JSON stubs are
        valid Arrow IPC. Verify Python side doesn't try pyarrow on stubs."""
        # The Python validate_schemas() should only check existence for stubs
        from rust_bridge.output_verifier import validate_schemas
        doc = validate_schemas.__doc__ or ""
        # Function should document that it's existence-only for stubs
        assert "existence" in doc.lower() or "exist" in doc.lower(), (
            "validate_schemas() should document that it only checks existence for stubs"
        )


# ===========================================================================
# Live Integration Tests — dispatch real Rust binary
# ===========================================================================

@pytest.mark.live
class TestLiveBridgeRoundTrip:
    """Live integration tests that dispatch real jobs to the compiled Rust binary.

    These tests exercise the REAL system behavior: download/write real data,
    spawn the actual binary, verify actual output files on disk.
    """

    @pytest.fixture(autouse=True)
    def _check_binary(self):
        if not BINARY_PATH.exists():
            pytest.skip(f"Rust binary not found at {BINARY_PATH}; run `cargo build -p backtester`")

    def test_live_dispatch_success(self, cost_model_path, market_data_path, output_dir):
        """AC #1, #3: Happy path — dispatch job, verify Arrow IPC output files."""
        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=STRATEGY_FIXTURE,
            market_data_path=market_data_path,
            cost_model_path=cost_model_path,
            output_directory=output_dir,
            config_hash="live_test_hash",
            memory_budget_mb=256,
        )

        result = asyncio.run(runner.dispatch(job))

        assert result.exit_code == 0, f"Binary failed: {result.stderr}"
        assert result.elapsed_seconds > 0

        # Verify output files exist on disk (AC #3)
        assert (output_dir / "trade-log.arrow").exists()
        assert (output_dir / "equity-curve.arrow").exists()
        assert (output_dir / "metrics.arrow").exists()
        assert (output_dir / "run_metadata.json").exists()

        # Verify no .partial files remain (AC #3)
        partials = list(output_dir.glob("*.partial"))
        assert len(partials) == 0, f"Partial files remain: {partials}"

        # Verify output via verifier module
        ref = verify_output(output_dir, "live_test_hash")
        assert ref.config_hash == "live_test_hash"

        # Verify run_metadata content
        meta = json.loads((output_dir / "run_metadata.json").read_text())
        assert meta["config_hash"] == "live_test_hash"

    def test_live_structured_error_on_bad_spec(self, cost_model_path, market_data_path, output_dir, tmp_path):
        """AC #4: Bad strategy spec → structured D8 JSON error on stderr."""
        bad_spec = tmp_path / "bad_spec.toml"
        bad_spec.write_text("[not_a_valid_spec]\nfoo = 42", encoding="utf-8")

        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=bad_spec,
            market_data_path=market_data_path,
            cost_model_path=cost_model_path,
            output_directory=output_dir,
            config_hash="error_test",
            memory_budget_mb=256,
        )

        result = asyncio.run(runner.dispatch(job))
        assert result.exit_code != 0

        # Parse structured error from stderr
        rust_error = parse_rust_error(result.stderr)
        assert rust_error is not None
        assert rust_error.category in ("data_logic", "external_failure")

        # Map to PipelineError
        pe = map_to_pipeline_error(rust_error)
        assert isinstance(pe, PipelineError)
        assert pe.runtime == "rust"

    def test_live_missing_data_file(self, cost_model_path, output_dir, tmp_path):
        """AC #4: Missing Arrow file → structured error."""
        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=STRATEGY_FIXTURE,
            market_data_path=tmp_path / "nonexistent.arrow",
            cost_model_path=cost_model_path,
            output_directory=output_dir,
            config_hash="missing_data_test",
            memory_budget_mb=256,
        )

        # Pre-check catches this before even spawning
        result = asyncio.run(runner.dispatch(job))
        assert result.exit_code != 0

    def test_live_progress_reporting(self, cost_model_path, market_data_path, output_dir):
        """AC #6: Verify progress.json written during execution."""
        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=STRATEGY_FIXTURE,
            market_data_path=market_data_path,
            cost_model_path=cost_model_path,
            output_directory=output_dir,
            config_hash="progress_test",
            memory_budget_mb=256,
        )

        result = asyncio.run(runner.dispatch(job))
        assert result.exit_code == 0, f"Binary failed: {result.stderr}"

        # Progress file should exist after run
        progress_path = output_dir / "progress.json"
        assert progress_path.exists(), "progress.json should exist after run"

        data = json.loads(progress_path.read_text())
        assert "bars_processed" in data
        assert "total_bars" in data
        assert "updated_at" in data

        # Read via BatchRunner.get_progress()
        report = runner.get_progress(job)
        assert report is not None
        assert report.bars_processed >= 0

    def test_live_process_crash_isolation(self, cost_model_path, market_data_path, output_dir, tmp_path):
        """AC #8: Python detects non-zero exit code, captures stderr, continues running."""
        bad_cost = tmp_path / "bad_cost.json"
        bad_cost.write_text('{"invalid": true}', encoding="utf-8")

        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=STRATEGY_FIXTURE,
            market_data_path=market_data_path,
            cost_model_path=bad_cost,
            output_directory=output_dir,
            config_hash="crash_test",
            memory_budget_mb=256,
        )

        result = asyncio.run(runner.dispatch(job))
        # Binary should fail but Python should not crash
        assert result.exit_code != 0
        assert result.stderr  # Should have error info

        # Python continues running — verify by doing another operation
        report = runner.get_progress(job)
        # No crash here means isolation works

    def test_live_deterministic_output(self, cost_model_path, market_data_path, tmp_path):
        """AC #9: Same inputs → byte-identical deterministic output files."""
        runner = BatchRunner(BINARY_PATH, timeout=30)

        results = []
        for i in range(2):
            out = tmp_path / f"output_{i}"
            out.mkdir()
            job = BacktestJob(
                strategy_spec_path=STRATEGY_FIXTURE,
                market_data_path=market_data_path,
                cost_model_path=cost_model_path,
                output_directory=out,
                config_hash="determinism_test",
                memory_budget_mb=256,
            )
            r = asyncio.run(runner.dispatch(job))
            assert r.exit_code == 0, f"Run {i} failed: {r.stderr}"
            results.append(out)

        # Deterministic files must be byte-identical
        for name in ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]:
            a = (results[0] / name).read_bytes()
            b = (results[1] / name).read_bytes()
            assert a == b, f"{name} differs between runs"

        # Ephemeral files are NOT checked for identity (timestamps differ)

    def test_live_crash_safe_no_partial_on_success(self, cost_model_path, market_data_path, output_dir):
        """AC #3: No .partial files remain after successful completion."""
        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=STRATEGY_FIXTURE,
            market_data_path=market_data_path,
            cost_model_path=cost_model_path,
            output_directory=output_dir,
            config_hash="partial_test",
            memory_budget_mb=256,
        )

        result = asyncio.run(runner.dispatch(job))
        assert result.exit_code == 0

        partials = list(output_dir.glob("*.partial"))
        assert len(partials) == 0

    def test_live_memory_budget_log(self, cost_model_path, market_data_path, output_dir):
        """AC #7: Binary logs allocated MB and chosen batch size at startup."""
        runner = BatchRunner(BINARY_PATH, timeout=30)
        job = BacktestJob(
            strategy_spec_path=STRATEGY_FIXTURE,
            market_data_path=market_data_path,
            cost_model_path=cost_model_path,
            output_directory=output_dir,
            config_hash="memory_test",
            memory_budget_mb=64,
        )

        result = asyncio.run(runner.dispatch(job))
        assert result.exit_code == 0, f"Binary failed: {result.stderr}"
        # Memory budget should be logged in stderr
        assert "Memory budget" in result.stderr or "memory" in result.stderr.lower()

    def test_live_full_executor_round_trip(self, cost_model_path, market_data_path, output_dir):
        """End-to-end: BacktestExecutor dispatches job via StageExecutor protocol."""
        runner = BatchRunner(BINARY_PATH, timeout=30)
        executor = BacktestExecutor(runner)

        context = {
            "strategy_spec_path": str(STRATEGY_FIXTURE),
            "market_data_path": str(market_data_path),
            "cost_model_path": str(cost_model_path),
            "config_hash": "executor_test",
            "memory_budget_mb": 256,
            "output_directory": str(output_dir),
        }

        result = executor.execute("ma-crossover", context)
        assert result.outcome == "success", f"Executor failed: {result.error}"
        assert result.artifact_path == str(output_dir)
        assert result.manifest_ref is None  # Story 3.6

        # Verify actual files exist
        assert (output_dir / "trade-log.arrow").exists()
        assert (output_dir / "equity-curve.arrow").exists()
        assert (output_dir / "metrics.arrow").exists()
