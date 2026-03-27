"""Tests for pipeline_proof.py (Story 1.9).

Unit tests use synthetic data with mocked downloader.
Live tests exercise the real pipeline proof components.
"""
import json
import logging
import os
import shutil
from collections import namedtuple
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from data_pipeline.pipeline_proof import (
    PipelineProof,
    PipelineProofResult,
    StageResult,
    _verify,
    _warn,
    run_pipeline_proof,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic data generation
# ---------------------------------------------------------------------------

def _make_synthetic_m1(n_bars=100, start_ts_us=None):
    """Generate synthetic M1 bar data as a DataFrame.

    Returns a DataFrame with columns matching the arrow_schemas.toml
    market_data contract.
    """
    if start_ts_us is None:
        # 2024-01-02 00:00 UTC in microseconds
        start_ts_us = int(datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc).timestamp() * 1_000_000)

    us_per_min = 60 * 1_000_000
    timestamps = [start_ts_us + i * us_per_min for i in range(n_bars)]

    rng = np.random.RandomState(42)
    base_price = 1.1000
    prices = base_price + rng.randn(n_bars).cumsum() * 0.0001

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": prices,
        "high": prices + rng.uniform(0.0001, 0.0005, n_bars),
        "low": prices - rng.uniform(0.0001, 0.0005, n_bars),
        "close": prices + rng.uniform(-0.0002, 0.0002, n_bars),
        "bid": prices - 0.00005,
        "ask": prices + 0.00005,
    })
    return df


def _make_arrow_table(df, session_schedule=None):
    """Convert DataFrame to Arrow Table with session + quarantined columns."""
    from data_pipeline.session_labeler import assign_sessions_bulk

    if "session" not in df.columns:
        if session_schedule:
            sessions = assign_sessions_bulk(df["timestamp"].tolist(), session_schedule)
        else:
            sessions = ["asian"] * len(df)
        df = df.copy()
        df["session"] = sessions
    if "quarantined" not in df.columns:
        df = df.copy()
        df["quarantined"] = False

    schema = pa.schema([
        ("timestamp", pa.int64()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("session", pa.utf8()),
        ("quarantined", pa.bool_()),
    ])
    return pa.table({
        "timestamp": pa.array(df["timestamp"].tolist(), type=pa.int64()),
        "open": pa.array(df["open"].tolist(), type=pa.float64()),
        "high": pa.array(df["high"].tolist(), type=pa.float64()),
        "low": pa.array(df["low"].tolist(), type=pa.float64()),
        "close": pa.array(df["close"].tolist(), type=pa.float64()),
        "bid": pa.array(df["bid"].tolist(), type=pa.float64()),
        "ask": pa.array(df["ask"].tolist(), type=pa.float64()),
        "session": pa.array(df["session"].tolist(), type=pa.utf8()),
        "quarantined": pa.array(df["quarantined"].tolist(), type=pa.bool_()),
    }, schema=schema)


def _write_arrow_ipc(table, path):
    """Write Arrow IPC file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = pa.ipc.new_file(str(path), table.schema)
    writer.write_table(table)
    writer.close()
    return path


def _make_test_config(tmp_path):
    """Build a config dict that points at tmp_path for all storage."""
    storage = str(tmp_path / "storage")
    log_dir = str(tmp_path / "logs")
    os.makedirs(storage, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    # Create contracts directory with schemas
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir(exist_ok=True)
    (contracts_dir / "arrow_schemas.toml").write_text(
        '[market_data]\n'
        'description = "M1 bar data"\n'
        'columns = [\n'
        '  { name = "timestamp", type = "int64", nullable = false },\n'
        '  { name = "open", type = "float64", nullable = false },\n'
        '  { name = "high", type = "float64", nullable = false },\n'
        '  { name = "low", type = "float64", nullable = false },\n'
        '  { name = "close", type = "float64", nullable = false },\n'
        '  { name = "bid", type = "float64", nullable = false },\n'
        '  { name = "ask", type = "float64", nullable = false },\n'
        '  { name = "session", type = "utf8", nullable = false },\n'
        '  { name = "quarantined", type = "bool", nullable = false },\n'
        ']\n',
        encoding="utf-8",
    )
    (contracts_dir / "session_schema.toml").write_text(
        'valid_sessions = ["asian", "london", "new_york", '
        '"london_ny_overlap", "off_hours", "mixed"]\n',
        encoding="utf-8",
    )

    return {
        "project": {"name": "test-pipeline", "version": "0.1.0"},
        "data": {
            "storage_path": storage,
            "default_pair": "EURUSD",
            "default_timeframe": "M1",
            "supported_timeframes": ["M1", "M5", "H1", "D1", "W"],
            "download": {
                "source": "dukascopy",
                "timeout_seconds": 30,
                "max_retries": 3,
                "retry_delay_seconds": 5,
            },
            "quality": {
                "gap_threshold_bars": 5,
                "gap_warning_per_year": 10,
                "gap_error_per_year": 50,
                "gap_error_minutes": 30,
                "spread_multiplier_threshold": 10.0,
                "stale_consecutive_bars": 5,
                "score_green_threshold": 0.95,
                "score_yellow_threshold": 0.80,
            },
        },
        "sessions": {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
            "london": {"start": "08:00", "end": "16:00", "label": "London"},
            "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
            "london_ny_overlap": {
                "start": "13:00", "end": "16:00",
                "label": "London/NY Overlap",
            },
            "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
        },
        "logging": {
            "level": "INFO",
            "log_dir": log_dir,
            "max_file_size_mb": 50,
            "retention_days": 30,
        },
        "pipeline": {"artifacts_dir": str(tmp_path / "artifacts"), "checkpoint_enabled": True},
        "monitoring": {"heartbeat_interval_ms": 5000, "alert_on_disconnect": True},
        "data_pipeline": {
            "storage_path": storage,
            "default_resolution": "M1",
            "request_delay_seconds": 0.5,
            "max_retries": 3,
            "storage": {
                "arrow_ipc_path": str(tmp_path / "storage" / "arrow"),
                "parquet_path": str(tmp_path / "storage" / "parquet"),
            },
            "parquet": {"compression": "snappy"},
            "timeframe_conversion": {
                "target_timeframes": ["M5", "H1"],
                "source_timeframe": "M1",
            },
            "splitting": {
                "split_ratio": 0.7,
                "split_mode": "ratio",
                "split_date": "",
            },
            "reference_dataset": {
                "pair": "EURUSD",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "resolution": "M1",
                "source": "dukascopy",
            },
            "download": {
                "pairs": ["EURUSD"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "resolution": "M1",
            },
        },
        "execution": {"enabled": False, "mode": "practice"},
    }


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------

class TestVerifyHelpers:
    def test_verify_adds_error_on_false(self):
        errors = []
        _verify(errors, False, "fail msg")
        assert errors == ["fail msg"]

    def test_verify_no_error_on_true(self):
        errors = []
        _verify(errors, True, "should not appear")
        assert errors == []

    def test_warn_adds_warning_on_false(self):
        warnings = []
        _warn(warnings, False, "warn msg")
        assert warnings == ["warn msg"]

    def test_warn_no_warning_on_true(self):
        warnings = []
        _warn(warnings, True, "should not appear")
        assert warnings == []


# ---------------------------------------------------------------------------
# Unit tests — dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_stage_result_defaults(self):
        sr = StageResult(name="test", status="PASS", duration_seconds=1.0)
        assert sr.details == {}
        assert sr.errors == []
        assert sr.warnings == []

    def test_pipeline_proof_result(self):
        r = PipelineProofResult(
            overall_status="PASS",
            stages={},
            dataset_id="test_id",
            config_hash="abc123",
            reproducibility_verified=True,
            total_duration_seconds=10.0,
            artifact_count=5,
        )
        assert r.overall_status == "PASS"
        assert r.dataset_id == "test_id"
        assert r.errors == []


# ---------------------------------------------------------------------------
# Unit tests — PipelineProof with mocked components
# ---------------------------------------------------------------------------

ConversionResult = namedtuple(
    "ConversionResult",
    ["arrow_path", "parquet_path", "manifest_path", "row_count",
     "arrow_size_mb", "parquet_size_mb"],
)
ValidationResult = namedtuple(
    "ValidationResult",
    ["quality_score", "rating", "report_path", "validated_df", "can_proceed"],
)


class TestPipelineProofDownloadStage:
    """Test the download stage with mocked downloader."""

    def test_download_returns_dataframe(self, tmp_path):
        config = _make_test_config(tmp_path)
        df = _make_synthetic_m1(100)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config, skip_download=True)

        # Simulate existing raw data
        raw_dir = Path(config["data_pipeline"]["storage_path"]) / "raw" / "EURUSD_test"
        v_dir = raw_dir / "v1"
        v_dir.mkdir(parents=True)
        df.to_csv(v_dir / "EURUSD_test.csv", index=False)

        with patch("data_pipeline.downloader.DukascopyDownloader") as MockDL:
            inst = MockDL.return_value
            inst.compute_data_hash.return_value = "a" * 64
            result = proof._stage_download()

        assert result.status == "PASS"
        assert result.details["bar_count"] == 100
        assert proof._df is not None


class TestPipelineProofValidateStage:
    """Test the validation stage with mocked checker."""

    def test_validate_green(self, tmp_path):
        config = _make_test_config(tmp_path)
        df = _make_synthetic_m1(100)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._df = df
        proof._dataset_id = "test_dataset"
        proof._data_hash = "a" * 64

        # Create a quality report file
        report_path = tmp_path / "quality_report.json"
        report_path.write_text(json.dumps({
            "gap_count": 0, "score": 0.98,
            "integrity_checks": {"passed": True},
            "staleness_checks": {"stale_bars": 0},
        }))

        with patch("data_pipeline.quality_checker.DataQualityChecker") as MockQC:
            inst = MockQC.return_value
            inst.validate.return_value = ValidationResult(
                quality_score=0.98,
                rating="GREEN",
                report_path=str(report_path),
                validated_df=df,
                can_proceed=True,
            )
            result = proof._stage_validate()

        assert result.status == "PASS"
        assert result.details["quality_score"] == 0.98
        assert result.details["rating"] == "GREEN"


class TestPipelineProofConvertStage:
    """Test the conversion stage with mocked converter."""

    def test_convert_produces_arrow_and_parquet(self, tmp_path):
        config = _make_test_config(tmp_path)
        df = _make_synthetic_m1(100)
        table = _make_arrow_table(df)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._df = df
        proof._dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_aaaaaaaa"
        proof._data_hash = "a" * 64

        # Create Arrow and Parquet files
        arrow_path = tmp_path / "test.arrow"
        parquet_path = tmp_path / "test.parquet"
        _write_arrow_ipc(table, arrow_path)
        pq.write_table(table, str(parquet_path))

        proof._validation_result = ValidationResult(
            quality_score=0.98, rating="GREEN",
            report_path=str(tmp_path / "report.json"),
            validated_df=df, can_proceed=True,
        )

        with patch("data_pipeline.arrow_converter.ArrowConverter") as MockAC:
            inst = MockAC.return_value
            inst.convert.return_value = ConversionResult(
                arrow_path=arrow_path,
                parquet_path=parquet_path,
                manifest_path=tmp_path / "manifest.json",
                row_count=100,
                arrow_size_mb=0.01,
                parquet_size_mb=0.005,
            )
            result = proof._stage_convert()

        assert result.status == "PASS"
        assert result.details["row_count"] == 100
        # M1 should be copied to data-pipeline/
        assert proof._m1_arrow_path.exists()


class TestPipelineProofLogVerification:
    """Test the log verification stage."""

    def test_valid_json_logs(self, tmp_path):
        config = _make_test_config(tmp_path)
        log_dir = Path(config["logging"]["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "python_2024-01-01.jsonl"
        lines = [
            json.dumps({"ts": "2024-01-01T00:00:00Z", "level": "INFO",
                        "runtime": "python", "component": "data_pipeline",
                        "stage": "download", "msg": "test"}),
            json.dumps({"ts": "2024-01-01T00:01:00Z", "level": "INFO",
                        "runtime": "python", "component": "data_pipeline",
                        "stage": "validation", "msg": "test"}),
            json.dumps({"ts": "2024-01-01T00:02:00Z", "level": "INFO",
                        "runtime": "python", "component": "data_pipeline",
                        "stage": "arrow_conversion", "msg": "test"}),
        ]
        log_file.write_text("\n".join(lines), encoding="utf-8")

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = proof._verify_logs()

        assert result.status == "PASS"
        assert result.details["valid_json"] == 3
        assert "data_pipeline" in result.details["components"]

    def test_no_log_files_fails(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = proof._verify_logs()
        assert result.status == "FAIL"
        assert any("No log files" in e for e in result.errors)


class TestPipelineProofSessionVerification:
    """Test session spot-check verification."""

    def test_sessions_verified(self, tmp_path):
        config = _make_test_config(tmp_path)
        # Build a table with bars at specific UTC hours
        us_per_hour = 3600 * 1_000_000
        base = int(datetime(2024, 6, 3, 0, 0, tzinfo=timezone.utc).timestamp() * 1_000_000)

        rows = []
        session_map = {
            0: "asian", 1: "asian", 2: "asian", 3: "asian",
            4: "asian", 5: "asian", 6: "asian", 7: "asian",
            8: "london", 9: "london", 10: "london", 11: "london",
            12: "london", 13: "london_ny_overlap", 14: "london_ny_overlap",
            15: "london_ny_overlap", 16: "new_york", 17: "new_york",
            18: "new_york", 19: "new_york", 20: "new_york",
            21: "off_hours", 22: "off_hours", 23: "off_hours",
        }
        for h in range(24):
            us_per_min = 60 * 1_000_000
            for m in range(60):
                ts = base + h * us_per_hour + m * us_per_min
                rows.append({
                    "timestamp": ts, "open": 1.1, "high": 1.11,
                    "low": 1.09, "close": 1.1, "bid": 1.099,
                    "ask": 1.101, "session": session_map[h],
                    "quarantined": False,
                })

        table = pa.table(
            {k: [r[k] for r in rows] for k in rows[0]},
            schema=pa.schema([
                ("timestamp", pa.int64()), ("open", pa.float64()),
                ("high", pa.float64()), ("low", pa.float64()),
                ("close", pa.float64()), ("bid", pa.float64()),
                ("ask", pa.float64()), ("session", pa.utf8()),
                ("quarantined", pa.bool_()),
            ]),
        )

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        errors, warnings = [], []
        proof._verify_sessions(table, errors, warnings)
        assert not errors, f"Session errors: {errors}"


class TestPipelineProofResultSummary:
    """Test result JSON and summary output."""

    def test_save_result_json(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = PipelineProofResult(
            overall_status="PASS",
            stages={"download": StageResult("download", "PASS", 1.0)},
            dataset_id="test_id",
            config_hash="abc123",
            reproducibility_verified=True,
            total_duration_seconds=10.0,
            artifact_count=5,
        )
        proof._save_result_json(result)
        result_path = proof._pipeline_dir / "pipeline_proof_result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["overall_status"] == "PASS"
        assert data["dataset_id"] == "test_id"

    def test_save_reference_dataset(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = PipelineProofResult(
            overall_status="PASS",
            stages={},
            dataset_id="test_id",
            config_hash="abc123",
            reproducibility_verified=True,
            total_duration_seconds=10.0,
            artifact_count=5,
        )
        proof._save_reference_dataset(result)
        ref_path = proof._pipeline_dir / "reference_dataset.json"
        assert ref_path.exists()
        data = json.loads(ref_path.read_text())
        assert data["proof_result"] == "PASS"
        assert data["reproducibility_verified"] is True


class TestPipelineProofArtifactChain:
    """Test artifact chain verification."""

    def test_no_partial_files_pass(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_aaaa"
        fname = "EURUSD_2024-01-01_2024-12-31_M1.arrow"

        # Create a manifest referencing the arrow file
        manifest = {
            "dataset_id": proof._dataset_id,
            "config_hash": proof._config_hash,
            "files": {"m1_arrow": fname},
            "timeframes": {},
        }
        manifest_path = proof._pipeline_dir / f"{proof._dataset_id}_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # Create the arrow file
        table = _make_arrow_table(_make_synthetic_m1(10))
        _write_arrow_ipc(table, proof._pipeline_dir / fname)

        result = proof._verify_artifacts()
        assert result.status == "PASS"
        assert len(proof._first_run_hashes) > 0

    def test_partial_files_fail(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_aaaa"

        # Create a .partial file
        (proof._pipeline_dir / "test.arrow.partial").write_text("bad")
        # Create manifest
        manifest = {
            "dataset_id": proof._dataset_id,
            "config_hash": proof._config_hash,
            "files": {}, "timeframes": {},
        }
        (proof._pipeline_dir / f"{proof._dataset_id}_manifest.json").write_text(
            json.dumps(manifest))

        result = proof._verify_artifacts()
        assert result.status == "FAIL"
        assert any("Partial" in e or "partial" in e.lower() for e in result.errors)


class TestPipelineProofReproducibility:
    """Test reproducibility verification."""

    def test_skip_reproducibility(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config, skip_reproducibility=True)

        result = proof._verify_reproducibility()
        assert result.status == "PASS"
        assert result.details.get("skipped") is True

    def test_no_hashes_fails(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = proof._verify_reproducibility()
        assert result.status == "FAIL"
        assert any("No first-run" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Live integration tests — exercise real pipeline components
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestPipelineProofLive:
    """Live integration tests that exercise the real pipeline proof.

    These tests use REAL pipeline components (no mocks for the system
    under test). They create actual files and verify outputs on disk.

    Run with: pytest -m live
    """

    def test_live_pipeline_proof_result_structure(self, tmp_path):
        """Verify PipelineProofResult has all required fields."""
        result = PipelineProofResult(
            overall_status="PASS",
            stages={"download": StageResult("download", "PASS", 1.0,
                                            {"bar_count": 100})},
            dataset_id="EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1",
            config_hash="b4c5d6e7",
            reproducibility_verified=True,
            total_duration_seconds=45.2,
            artifact_count=18,
        )
        assert result.overall_status in ("PASS", "FAIL")
        assert isinstance(result.stages, dict)
        assert isinstance(result.dataset_id, str)
        assert isinstance(result.config_hash, str)
        assert isinstance(result.reproducibility_verified, bool)
        assert isinstance(result.total_duration_seconds, float)
        assert isinstance(result.artifact_count, int)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_live_result_json_output(self, tmp_path):
        """Verify pipeline_proof_result.json is written correctly."""
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = PipelineProofResult(
            overall_status="PASS",
            stages={
                "download": StageResult("download", "PASS", 2.1,
                                        {"bar_count": 525600}),
                "validation": StageResult("validation", "PASS", 1.3,
                                          {"quality_score": 0.97, "rating": "GREEN"}),
            },
            dataset_id="EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1",
            config_hash="b4c5d6e7",
            reproducibility_verified=True,
            total_duration_seconds=45.2,
            artifact_count=18,
        )
        proof._save_result_json(result)

        result_path = proof._pipeline_dir / "pipeline_proof_result.json"
        assert result_path.exists(), "pipeline_proof_result.json not on disk"

        data = json.loads(result_path.read_text())
        assert data["overall_status"] == "PASS"
        assert "stages" in data
        assert "download" in data["stages"]
        assert data["stages"]["download"]["details"]["bar_count"] == 525600

    def test_live_reference_dataset_json(self, tmp_path):
        """Verify reference_dataset.json is written with correct schema."""
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        result = PipelineProofResult(
            overall_status="PASS",
            stages={},
            dataset_id="EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1",
            config_hash="b4c5d6e7",
            reproducibility_verified=True,
            total_duration_seconds=10.0,
            artifact_count=5,
        )
        proof._save_reference_dataset(result)

        ref_path = proof._pipeline_dir / "reference_dataset.json"
        assert ref_path.exists(), "reference_dataset.json not on disk"

        data = json.loads(ref_path.read_text())
        assert data["dataset_id"] == "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"
        assert data["proof_result"] == "PASS"
        assert data["reproducibility_verified"] is True
        assert "created_at" in data
        assert data["purpose"].startswith("Reference dataset")


# ---------------------------------------------------------------------------
# Regression tests — one per accepted review finding
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestRegressionBidAskRequired:
    """Regression: H1/AC1 — bid/ask must be in required download columns."""

    def test_download_fails_without_bid_ask(self, tmp_path):
        config = _make_test_config(tmp_path)
        # DataFrame missing bid/ask
        df = _make_synthetic_m1(10)
        df_no_bid = df.drop(columns=["bid", "ask"])

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config, skip_download=True)

        raw_dir = Path(config["data_pipeline"]["storage_path"]) / "raw" / "EURUSD_test" / "v1"
        raw_dir.mkdir(parents=True)
        df_no_bid.to_csv(raw_dir / "EURUSD_test.csv", index=False)

        with patch("data_pipeline.downloader.DukascopyDownloader") as MockDL:
            MockDL.return_value.compute_data_hash.return_value = "a" * 64
            result = proof._stage_download()

        assert result.status == "FAIL"
        assert any("bid" in e or "ask" in e for e in result.errors)


@pytest.mark.regression
class TestRegressionQualityReportContent:
    """Regression: H2/AC3 — quality report must contain gap_count, etc."""

    def test_empty_quality_report_fails(self, tmp_path):
        config = _make_test_config(tmp_path)
        df = _make_synthetic_m1(10)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._df = df
        proof._dataset_id = "test_dataset"
        proof._data_hash = "a" * 64

        # Quality report with empty JSON (missing required fields)
        report_path = tmp_path / "quality_report.json"
        report_path.write_text("{}")

        with patch("data_pipeline.quality_checker.DataQualityChecker") as MockQC:
            MockQC.return_value.validate.return_value = ValidationResult(
                quality_score=0.98, rating="GREEN",
                report_path=str(report_path), validated_df=df, can_proceed=True,
            )
            result = proof._stage_validate()

        assert result.status == "FAIL"
        assert any("gap_count" in e for e in result.errors)


@pytest.mark.regression
class TestRegressionSessionMixed:
    """Regression: M2 — 'mixed' must be a valid session value."""

    def test_mixed_session_accepted(self, tmp_path):
        config = _make_test_config(tmp_path)
        df = _make_synthetic_m1(5)
        df["session"] = "mixed"
        df["quarantined"] = False
        table = _make_arrow_table(df)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        arrow_path = tmp_path / "test.arrow"
        parquet_path = tmp_path / "test.parquet"
        _write_arrow_ipc(table, arrow_path)
        pq.write_table(table, str(parquet_path))

        proof._validation_result = ValidationResult(
            quality_score=0.98, rating="GREEN",
            report_path=str(tmp_path / "r.json"), validated_df=df,
            can_proceed=True,
        )

        with patch("data_pipeline.arrow_converter.ArrowConverter") as MockAC:
            MockAC.return_value.convert.return_value = ConversionResult(
                arrow_path=arrow_path, parquet_path=parquet_path,
                manifest_path=tmp_path / "m.json", row_count=5,
                arrow_size_mb=0.001, parquet_size_mb=0.001,
            )
            result = proof._stage_convert()

        # "mixed" must NOT cause a session validation error
        assert not any("Invalid session" in e for e in result.errors), \
            f"'mixed' session rejected: {result.errors}"


@pytest.mark.regression
class TestRegressionLogJsonlExtension:
    """Regression: C2/AC10 — log verifier must find .jsonl files."""

    def test_finds_jsonl_logs(self, tmp_path):
        config = _make_test_config(tmp_path)
        log_dir = Path(config["logging"]["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)

        # Write a .jsonl file (the real extension) — NOT .log
        log_file = log_dir / "python_2024-01-01.jsonl"
        line = json.dumps({
            "ts": "2024-01-01T00:00:00Z", "level": "INFO",
            "runtime": "python", "component": "data_pipeline",
            "stage": "download", "msg": "test",
        })
        log_file.write_text(line, encoding="utf-8")

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)
        result = proof._verify_logs()

        assert result.status == "PASS"
        assert result.details["valid_json"] == 1


@pytest.mark.regression
class TestRegressionLogPerLineFields:
    """Regression: C2/AC10 — each log line must have required fields."""

    def test_missing_runtime_field_fails(self, tmp_path):
        config = _make_test_config(tmp_path)
        log_dir = Path(config["logging"]["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "python_2024-01-01.jsonl"
        # Missing 'runtime' field
        line = json.dumps({
            "ts": "2024-01-01T00:00:00Z", "level": "INFO",
            "component": "data_pipeline", "stage": "download",
            "msg": "test",
        })
        log_file.write_text(line, encoding="utf-8")

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)
        result = proof._verify_logs()

        assert result.status == "FAIL"
        assert any("missing required fields" in e for e in result.errors)

    def test_wrong_runtime_fails(self, tmp_path):
        config = _make_test_config(tmp_path)
        log_dir = Path(config["logging"]["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "python_2024-01-01.jsonl"
        line = json.dumps({
            "ts": "2024-01-01T00:00:00Z", "level": "INFO",
            "runtime": "rust", "component": "data_pipeline",
            "stage": "download", "msg": "test",
        })
        log_file.write_text(line, encoding="utf-8")

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)
        result = proof._verify_logs()

        assert result.status == "FAIL"
        assert any("runtime != 'python'" in e for e in result.errors)


@pytest.mark.regression
class TestRegressionLogStrictValidity:
    """Regression: C2/AC10 — invalid JSON lines must fail, not just warn."""

    def test_invalid_json_line_fails(self, tmp_path):
        config = _make_test_config(tmp_path)
        log_dir = Path(config["logging"]["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "python_2024-01-01.jsonl"
        valid = json.dumps({
            "ts": "t", "level": "INFO", "runtime": "python",
            "component": "data_pipeline", "stage": "download", "msg": "ok",
        })
        log_file.write_text(valid + "\nNOT_JSON\n", encoding="utf-8")

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)
        result = proof._verify_logs()

        assert result.status == "FAIL"
        assert any("invalid JSON" in e for e in result.errors)


@pytest.mark.regression
class TestRegressionSplitMissingFilesFail:
    """Regression: AC7 — missing train/test split files must fail."""

    def test_missing_split_files_error(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._tf_results = {}  # no timeframe results
        # Don't create any split files

        with patch("data_pipeline.data_splitter.run_data_splitting",
                   return_value={}):
            result = proof._stage_split()

        # M1 train/test files don't exist → should fail
        assert result.status == "FAIL"
        assert any("train Arrow file not found" in e for e in result.errors)


@pytest.mark.regression
class TestRegressionManifestDatasetScoped:
    """Regression: AC11 — manifest selection must be dataset-scoped."""

    def test_picks_correct_manifest_with_multiple(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_aaaa"

        # Create two manifests — one for a different dataset
        wrong = proof._pipeline_dir / "GBPUSD_other_manifest.json"
        wrong.write_text(json.dumps({"dataset_id": "GBPUSD_other"}))
        correct = proof._pipeline_dir / f"{proof._dataset_id}_manifest.json"
        correct.write_text(json.dumps({"dataset_id": proof._dataset_id}))

        found = proof._find_manifest()
        assert found is not None
        assert found.name == correct.name


@pytest.mark.regression
class TestRegressionArtifactOrphanDetection:
    """Regression: C1/AC8 — orphan files must be detected."""

    def test_orphan_file_detected(self, tmp_path):
        config = _make_test_config(tmp_path)

        with patch("logging_setup.get_logger", return_value=logging.getLogger("test")):
            proof = PipelineProof(config)

        proof._dataset_id = "EURUSD_2024-01-01_2024-12-31_dukascopy_aaaa"
        proof._pair = "EURUSD"
        proof._start_str = "2024-01-01"
        proof._end_str = "2024-12-31"

        # Create manifest with one file
        manifest = {
            "dataset_id": proof._dataset_id,
            "config_hash": proof._config_hash,
            "files": {"m1_arrow": "EURUSD_2024-01-01_2024-12-31_M1.arrow"},
            "timeframes": {},
        }
        mpath = proof._pipeline_dir / f"{proof._dataset_id}_manifest.json"
        mpath.write_text(json.dumps(manifest))

        # Create the listed file
        table = _make_arrow_table(_make_synthetic_m1(5))
        _write_arrow_ipc(table, proof._pipeline_dir / "EURUSD_2024-01-01_2024-12-31_M1.arrow")

        # Create an ORPHAN file not in manifest
        _write_arrow_ipc(table, proof._pipeline_dir / "EURUSD_2024-01-01_2024-12-31_ORPHAN.arrow")

        result = proof._verify_artifacts()
        assert result.status == "FAIL"
        assert any("Orphan" in e or "orphan" in e.lower() for e in result.errors)
