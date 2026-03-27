"""Tests for data_pipeline.converter_cli — Story 1.10 (PIR remediation).

Verifies the CLI path chain: quality_checker output → converter_cli input.
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_pipeline.converter_cli import run_conversion


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_config(tmp_path):
    """Config dict matching typical pipeline layout."""
    return {
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
        "sessions": {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00"},
            "london": {"start": "08:00", "end": "16:00"},
            "new_york": {"start": "13:00", "end": "21:00"},
            "london_ny_overlap": {"start": "13:00", "end": "16:00"},
            "off_hours": {"start": "21:00", "end": "00:00"},
        },
    }


@pytest.fixture
def sample_validated_df():
    """DataFrame matching quality_checker validated output."""
    n = 50
    timestamps = pd.date_range("2024-01-02 10:00", periods=n, freq="min")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [1.1000 + i * 0.0001 for i in range(n)],
        "high": [1.1005 + i * 0.0001 for i in range(n)],
        "low": [1.0995 + i * 0.0001 for i in range(n)],
        "close": [1.1001 + i * 0.0001 for i in range(n)],
        "volume": [100 + i for i in range(n)],
        "bid": [1.1000 + i * 0.0001 for i in range(n)],
        "ask": [1.1002 + i * 0.0001 for i in range(n)],
        "quarantined": [False] * n,
    })


# ---------------------------------------------------------------------------
# Task 1.2: Integration test — quality_checker output → converter CLI
# ---------------------------------------------------------------------------

class TestConverterCliPathChain:
    """Verify converter_cli reads from quality_checker's actual output path."""

    def test_cli_finds_validated_data_at_correct_path(
        self, base_config, sample_validated_df, tmp_path
    ):
        """Quality checker saves to validated/{dataset_id}/{version}/{dataset_id}_validated.csv.
        Converter CLI must read from that exact path.
        """
        dataset_id = "EURUSD_2024-01-01_2024-12-31_M1"
        version = "v001"

        # Simulate quality_checker output: validated CSV
        validated_dir = tmp_path / "validated" / dataset_id / version
        validated_dir.mkdir(parents=True)
        csv_path = validated_dir / f"{dataset_id}_validated.csv"
        sample_validated_df.to_csv(str(csv_path), index=False)

        # Simulate quality_checker output: quality report
        report_dir = tmp_path / "raw" / dataset_id / version
        report_dir.mkdir(parents=True)
        report_path = report_dir / "quality-report.json"
        report = {"quality_score": 0.98, "rating": "GREEN"}
        report_path.write_text(json.dumps(report))

        # Run converter — mock ArrowConverter.convert to verify df is loaded
        with patch("data_pipeline.converter_cli.ArrowConverter") as MockConverter:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.arrow_size_mb = 1.0
            mock_result.parquet_size_mb = 0.5
            mock_result.row_count = len(sample_validated_df)
            mock_result.arrow_path = tmp_path / "arrow" / "test.arrow"
            mock_result.parquet_path = tmp_path / "parquet" / "test.parquet"
            mock_result.manifest_path = tmp_path / "arrow" / "manifest.json"
            mock_instance.convert.return_value = mock_result
            MockConverter.return_value = mock_instance

            result = run_conversion(base_config)

        # Should NOT be an error
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result["row_count"] == len(sample_validated_df)

        # Verify convert was called with a DataFrame from the correct path
        call_args = mock_instance.convert.call_args
        loaded_df = call_args.kwargs.get("validated_df", call_args[1].get("validated_df"))
        if loaded_df is None:
            loaded_df = call_args[0][0]  # positional
        assert len(loaded_df) == len(sample_validated_df)

    def test_cli_errors_when_no_validated_data(self, base_config, tmp_path):
        """If quality_checker hasn't run, converter_cli should return error."""
        result = run_conversion(base_config)
        assert "error" in result
        assert "Validated data not found" in result["error"]

    def test_cli_reads_quality_report_from_raw_dir(
        self, base_config, sample_validated_df, tmp_path
    ):
        """Converter reads quality_score and rating from raw/{dataset_id}/{version}/quality-report.json."""
        dataset_id = "EURUSD_2024-01-01_2024-12-31_M1"
        version = "v001"

        # Place validated CSV
        validated_dir = tmp_path / "validated" / dataset_id / version
        validated_dir.mkdir(parents=True)
        csv_path = validated_dir / f"{dataset_id}_validated.csv"
        sample_validated_df.to_csv(str(csv_path), index=False)

        # Place quality report with specific values
        report_dir = tmp_path / "raw" / dataset_id / version
        report_dir.mkdir(parents=True)
        report_path = report_dir / "quality-report.json"
        report = {"quality_score": 0.87, "rating": "YELLOW"}
        report_path.write_text(json.dumps(report))

        with patch("data_pipeline.converter_cli.ArrowConverter") as MockConverter:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.arrow_size_mb = 1.0
            mock_result.parquet_size_mb = 0.5
            mock_result.row_count = len(sample_validated_df)
            mock_result.arrow_path = tmp_path / "test.arrow"
            mock_result.parquet_path = tmp_path / "test.parquet"
            mock_result.manifest_path = tmp_path / "manifest.json"
            mock_instance.convert.return_value = mock_result
            MockConverter.return_value = mock_instance

            run_conversion(base_config)

        # Verify the quality score/rating from report were passed to convert
        call_kwargs = mock_instance.convert.call_args[1]
        assert call_kwargs["quality_score"] == 0.87
        assert call_kwargs["rating"] == "YELLOW"
