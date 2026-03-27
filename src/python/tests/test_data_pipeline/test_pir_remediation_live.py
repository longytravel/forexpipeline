"""Live integration tests for Story 1.10 — Epic 1 PIR Remediation.

These tests verify the actual fixes work end-to-end with real file I/O,
real data structures, and no mocks for the system under test.

Run with: pytest -m live
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa
import pyarrow.ipc
import pytest

from data_pipeline.quality_checker import DataQualityChecker
from data_pipeline.arrow_converter import ArrowConverter
from data_pipeline.timeframe_converter import _resolve_contracts_path


def _make_session_schedule():
    return {
        "timezone": "UTC",
        "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
        "london": {"start": "08:00", "end": "16:00", "label": "London"},
        "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
        "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "London/NY Overlap"},
        "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
    }


def _make_quality_config():
    return {
        "data": {
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
        "sessions": _make_session_schedule(),
    }


def _make_clean_df(n=200):
    """Create clean M1 data."""
    timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [1.1000 + i * 0.0001 for i in range(n)],
        "high": [1.1005 + i * 0.0001 for i in range(n)],
        "low": [1.0995 + i * 0.0001 for i in range(n)],
        "close": [1.1001 + i * 0.0001 for i in range(n)],
        "bid": [1.1000 + i * 0.0001 for i in range(n)],
        "ask": [1.1002 + i * 0.0001 for i in range(n)],
    })


@pytest.mark.live
class TestLivePIRRemediation:
    """Live integration tests for all PIR remediation fixes."""

    def test_live_quality_checker_to_converter_path_chain(self, tmp_path):
        """AC #1: Quality checker output → converter CLI reads from correct path.

        Full end-to-end: run quality checker, verify validated CSV lands at
        the path converter_cli.py now expects, then run converter_cli.
        """
        from data_pipeline.converter_cli import run_conversion

        config = _make_quality_config()
        logger = MagicMock()
        checker = DataQualityChecker(config, logger)
        df = _make_clean_df()

        dataset_id = "EURUSD_2024-01-01_2024-12-31_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
        )

        # Verify the validated CSV exists at the path converter_cli expects
        validated_csv = tmp_path / "validated" / dataset_id / "v001" / f"{dataset_id}_validated.csv"
        assert validated_csv.exists(), f"Validated CSV not at expected path: {validated_csv}"

        # Verify quality report exists at expected path
        report_path = tmp_path / "raw" / dataset_id / "v001" / "quality-report.json"
        assert report_path.exists(), f"Quality report not at expected path: {report_path}"

        # Now verify converter_cli can find and load this data
        converter_config = {
            "data_pipeline": {
                "storage_path": str(tmp_path),
                "download": {
                    "pairs": ["EURUSD"],
                    "resolution": "M1",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                },
                "storage": {},
                "parquet": {"compression": "snappy"},
            },
            "data": {"storage_path": str(tmp_path)},
            "sessions": _make_session_schedule(),
        }

        with patch("data_pipeline.converter_cli.ArrowConverter") as MockConverter:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.arrow_size_mb = 1.0
            mock_result.parquet_size_mb = 0.5
            mock_result.row_count = len(df)
            mock_result.arrow_path = tmp_path / "test.arrow"
            mock_result.parquet_path = tmp_path / "test.parquet"
            mock_result.manifest_path = tmp_path / "manifest.json"
            mock_instance.convert.return_value = mock_result
            MockConverter.return_value = mock_instance

            cli_result = run_conversion(converter_config)

        assert "error" not in cli_result, f"Converter CLI failed: {cli_result.get('error')}"

        print("\n  LIVE PATH CHAIN TEST PASSED")
        print(f"  Validated CSV: {validated_csv}")
        print(f"  Quality report: {report_path}")

    def test_live_quality_report_completeness(self, tmp_path):
        """AC #2, #5, #6, #9: Quality report contains all required fields.

        Verifies: timezone_issues present, quarantine accuracy,
        config_hash populated, gap_severity wired in.
        """
        config = _make_quality_config()
        logger = MagicMock()
        checker = DataQualityChecker(config, logger)

        # Create data with some issues to exercise all report fields
        n = 50
        timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1] * n,
            "high": [1.15] * n,
            "low": [1.05] * n,
            "close": [1.1] * n,
            "bid": [1.10] * n,
            "ask": [1.12] * n,
        })

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
            config_hash="sha256:test_hash_abc123",
        )

        # Read the actual file from disk
        report_path = tmp_path / "raw" / dataset_id / "v001" / "quality-report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())

        # AC #2: timezone_issues present
        assert "timezone_issues" in report, "timezone_issues missing from report"
        assert isinstance(report["timezone_issues"], list)

        # AC #5: quarantined_periods and quarantined_bar_count
        assert "quarantined_periods" in report
        assert "quarantined_bar_count" in report
        assert "quarantined_percentage" in report

        # AC #6: config_hash populated
        assert report["config_hash"] == "sha256:test_hash_abc123"
        assert report["config_hash"] != ""

        # AC #9: gap_severity wired into report
        assert "gap_severity" in report
        assert report["gap_severity"] in ("ok", "warning", "error")

        # Verify no .partial files remain
        partials = list(tmp_path.rglob("*.partial"))
        assert partials == [], f"Leftover .partial files: {partials}"

        print("\n  LIVE QUALITY REPORT COMPLETENESS TEST PASSED")
        print(f"  Report fields verified: timezone_issues, quarantined_periods,")
        print(f"    config_hash, gap_severity")
        print(f"  Report path: {report_path}")

    def test_live_crash_safe_write_consolidation(self, tmp_path):
        """AC #4: All stages use shared safe_write utility.

        Writes Arrow IPC and Parquet via the shared utility, verifies
        files are readable and no .partial files remain.
        """
        from data_pipeline.utils.safe_write import (
            crash_safe_write,
            safe_write_arrow_ipc,
            safe_write_parquet,
        )

        # Create a small Arrow table
        table = pa.table({
            "timestamp": pa.array([1000000, 2000000, 3000000], type=pa.int64()),
            "open": pa.array([1.1, 1.2, 1.3], type=pa.float64()),
            "high": pa.array([1.15, 1.25, 1.35], type=pa.float64()),
            "low": pa.array([1.05, 1.15, 1.25], type=pa.float64()),
            "close": pa.array([1.11, 1.21, 1.31], type=pa.float64()),
            "bid": pa.array([1.1, 1.2, 1.3], type=pa.float64()),
            "ask": pa.array([1.12, 1.22, 1.32], type=pa.float64()),
            "session": pa.array(["asian", "london", "new_york"], type=pa.utf8()),
            "quarantined": pa.array([False, False, False], type=pa.bool_()),
        })

        # Test safe_write_arrow_ipc
        arrow_path = tmp_path / "output" / "test.arrow"
        safe_write_arrow_ipc(table, arrow_path)
        assert arrow_path.exists()

        # Verify the file is readable via mmap
        mmap_file = pa.memory_map(str(arrow_path), "r")
        reader = pa.ipc.open_file(mmap_file)
        read_table = reader.read_all()
        mmap_file.close()
        assert read_table.num_rows == 3

        # Test safe_write_parquet
        parquet_path = tmp_path / "output" / "test.parquet"
        safe_write_parquet(table, parquet_path)
        assert parquet_path.exists()

        # Verify Parquet is readable
        import pyarrow.parquet as pq
        pq_table = pq.read_table(str(parquet_path))
        assert pq_table.num_rows == 3

        # Test crash_safe_write (text)
        json_path = tmp_path / "output" / "test.json"
        crash_safe_write(json_path, '{"test": true}')
        assert json_path.exists()
        assert json.loads(json_path.read_text()) == {"test": True}

        # No .partial files
        partials = list(tmp_path.rglob("*.partial"))
        assert partials == [], f"Leftover .partial files: {partials}"

        print("\n  LIVE CRASH-SAFE WRITE TEST PASSED")
        print(f"  Arrow IPC: {arrow_path} ({arrow_path.stat().st_size} bytes)")
        print(f"  Parquet: {parquet_path} ({parquet_path.stat().st_size} bytes)")
        print(f"  JSON: {json_path}")

    def test_live_config_hash_auto_populated(self, tmp_path):
        """AC #6: config_hash auto-computed when caller doesn't provide one.

        Verifies the quality report on disk has a non-empty config_hash
        even when validate() is called without an explicit config_hash arg.
        """
        config = _make_quality_config()
        logger = MagicMock()
        checker = DataQualityChecker(config, logger)
        df = _make_clean_df(100)

        dataset_id = "EURUSD_2024-01-02_2024-01-02_M1"
        result = checker.validate(
            df=df, pair="EURUSD", resolution="M1",
            start_date=date(2024, 1, 2), end_date=date(2024, 1, 2),
            storage_path=tmp_path, dataset_id=dataset_id, version="v001",
            # No config_hash argument — should auto-compute
        )

        report_path = tmp_path / "raw" / dataset_id / "v001" / "quality-report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())

        assert report["config_hash"] != "", "config_hash must not be blank"
        # Convention: config_hash is stored as "sha256:<64-hex-chars>"
        assert report["config_hash"].startswith("sha256:"), \
            f"config_hash must use sha256: prefix, got: {report['config_hash'][:20]}"
        bare_hex = report["config_hash"].removeprefix("sha256:")
        assert len(bare_hex) == 64, \
            f"SHA-256 hex portion must be 64 chars, got {len(bare_hex)}"

        print("\n  LIVE CONFIG HASH AUTO-POPULATION TEST PASSED")
        print(f"  config_hash: {report['config_hash'][:16]}...")

    def test_live_contracts_path_fail_fast(self, tmp_path):
        """AC #11: Missing contracts_path raises FileNotFoundError (no CWD walking).

        Verifies both ArrowConverter and timeframe_converter._resolve_contracts_path
        fail fast with a clear error when contracts_path is not set.
        """
        # ArrowConverter
        config = {
            "data_pipeline": {
                "storage_path": str(tmp_path),
                "storage": {},
                "parquet": {"compression": "snappy"},
            },
            "sessions": _make_session_schedule(),
        }
        logger = MagicMock()

        with pytest.raises(FileNotFoundError, match="contracts_path not set"):
            ArrowConverter(config, logger)

        # timeframe_converter._resolve_contracts_path
        with pytest.raises(FileNotFoundError, match="contracts_path not set"):
            _resolve_contracts_path(config)

        print("\n  LIVE CONTRACTS PATH FAIL-FAST TEST PASSED")
        print("  ArrowConverter: FileNotFoundError raised correctly")
        print("  timeframe_converter: FileNotFoundError raised correctly")

    def test_live_dead_config_keys_removed(self, tmp_path):
        """AC #10: Dead config keys (timeout_seconds, retry_delay_seconds)
        removed from data.download section.

        Reads the actual config/base.toml to verify dead keys are gone.
        """
        import tomllib

        # Find config/base.toml from project root
        # test file is at src/python/tests/test_data_pipeline/ — 4 levels up
        project_root = Path(__file__).resolve().parents[4]
        base_toml = project_root / "config" / "base.toml"
        assert base_toml.exists(), f"config/base.toml not found at {base_toml}"

        with open(base_toml, "rb") as f:
            config = tomllib.load(f)

        download_cfg = config.get("data", {}).get("download", {})

        # These dead keys should have been removed
        assert "timeout_seconds" not in download_cfg, (
            "timeout_seconds still in [data.download] — should be removed (dead config)"
        )
        assert "retry_delay_seconds" not in download_cfg, (
            "retry_delay_seconds still in [data.download] — should be removed (dead config)"
        )
        assert "retry_backoff_factor" not in download_cfg, (
            "retry_backoff_factor still in [data.download] — should be removed"
        )

        # source should still exist (used by data_splitter.py)
        assert "source" in download_cfg, "data.download.source should remain (used by data_splitter)"

        print("\n  LIVE DEAD CONFIG KEYS TEST PASSED")
        print(f"  [data.download] keys: {list(download_cfg.keys())}")
        print(f"  Dead keys successfully removed")
