"""Live integration tests for Arrow IPC + Parquet conversion (Story 1.6).

These tests exercise REAL system behavior:
- Load real schema contracts from disk
- Build real DataFrames and convert them
- Write real Arrow IPC and Parquet files to disk
- Verify files exist, are readable, and mmap-friendly
- Validate manifest contents on disk

Marked @pytest.mark.live — run with: pytest -m live
"""
import json
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from data_pipeline.arrow_converter import ArrowConverter, ConversionResult
from data_pipeline.parquet_archiver import ParquetArchiver
from data_pipeline.schema_loader import load_arrow_schema

# Locate project root (walk up from test file)
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent.parent.parent  # tests -> python -> src -> project

CONTRACTS_PATH = _PROJECT_ROOT / "contracts"
CONFIG_PATH = _PROJECT_ROOT / "config"


def _load_real_config() -> dict:
    """Load real config/base.toml."""
    import tomllib
    with open(CONFIG_PATH / "base.toml", "rb") as f:
        return tomllib.load(f)


def _make_realistic_df(n: int = 1000) -> pd.DataFrame:
    """Create a realistic M1 bar DataFrame spanning multiple sessions."""
    timestamps = pd.date_range(
        "2020-06-01 00:00:00", periods=n, freq="min", tz="UTC"
    )
    import numpy as np
    rng = np.random.default_rng(42)

    base_price = 1.1000
    prices = base_price + rng.standard_normal(n).cumsum() * 0.0001

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": prices,
        "high": prices + rng.uniform(0.0001, 0.001, n),
        "low": prices - rng.uniform(0.0001, 0.001, n),
        "close": prices + rng.standard_normal(n) * 0.0002,
        "bid": prices,
        "ask": prices + rng.uniform(0.0001, 0.0005, n),
        "quarantined": [False] * n,
    })
    return df


@pytest.mark.live
class TestLiveFullConversion:
    """Live test: full conversion pipeline with real contracts and config."""

    @pytest.mark.live
    def test_live_full_conversion(self, tmp_path):
        """End-to-end conversion using real contracts and config.

        Writes Arrow IPC + Parquet + manifest to disk, verifies all exist
        and contain valid data.
        """
        config = _load_real_config()
        # Override storage paths to tmp_path for test isolation
        config["data_pipeline"]["storage"] = {
            "arrow_ipc_path": str(tmp_path / "arrow"),
            "parquet_path": str(tmp_path / "parquet"),
        }
        logger = logging.getLogger("live_test")

        # Use real contracts directory
        config["data_pipeline"]["contracts_path"] = str(CONTRACTS_PATH)
        converter = ArrowConverter(config, logger)

        df = _make_realistic_df(500)

        result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2020, 6, 1),
            end_date=date(2020, 6, 1),
            dataset_id="EURUSD_2020-06-01_2020-06-01_M1",
            version="v001",
            quality_score=0.97,
            rating="GREEN",
        )

        # Verify output files exist on disk
        assert Path(result.arrow_path).exists(), "Arrow IPC file must exist"
        assert Path(result.parquet_path).exists(), "Parquet file must exist"
        assert Path(result.manifest_path).exists(), "Manifest must exist"

        # Verify Arrow IPC is mmap-readable
        mmap = pa.memory_map(str(result.arrow_path), "r")
        reader = pa.ipc.open_file(mmap)
        table = reader.read_all()
        mmap.close()
        assert table.num_rows == 500

        # Verify schema matches real contract
        real_schema = load_arrow_schema(CONTRACTS_PATH, "market_data")
        assert table.schema.remove_metadata() == real_schema

        # Verify Parquet is readable
        pq_table = pq.read_table(str(result.parquet_path))
        assert pq_table.num_rows == 500

        # Verify timestamp column is int64 epoch microseconds
        ts_col = table.column("timestamp")
        assert ts_col.type == pa.int64()
        first_ts = ts_col[0].as_py()
        assert first_ts > 0, "Epoch micros must be positive"

        # Verify session column has valid values
        sessions = set(table.column("session").to_pylist())
        valid = {"asian", "london", "new_york", "london_ny_overlap", "off_hours"}
        assert sessions.issubset(valid), f"Invalid sessions: {sessions - valid}"

    @pytest.mark.live
    def test_live_manifest_integrity(self, tmp_path):
        """Verify manifest JSON on disk has all required fields and valid hashes."""
        config = _load_real_config()
        config["data_pipeline"]["storage"] = {
            "arrow_ipc_path": str(tmp_path / "arrow"),
            "parquet_path": str(tmp_path / "parquet"),
        }
        logger = logging.getLogger("live_test")
        config["data_pipeline"]["contracts_path"] = str(CONTRACTS_PATH)
        converter = ArrowConverter(config, logger)

        df = _make_realistic_df(200)
        result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2020, 6, 1),
            end_date=date(2020, 6, 1),
            dataset_id="EURUSD_live_test",
            version="v001",
            quality_score=0.95,
            rating="GREEN",
        )

        # Read manifest from disk
        with open(result.manifest_path) as f:
            manifest = json.load(f)

        # Verify all required fields
        assert manifest["dataset_id"] == "EURUSD_live_test"
        assert manifest["pair"] == "EURUSD"
        assert manifest["resolution"] == "M1"
        assert manifest["row_count"] == 200
        assert manifest["arrow_ipc"]["mmap_verified"] is True
        assert manifest["data_hash"].startswith("sha256:")
        assert manifest["config_hash"].startswith("sha256:")
        assert manifest["session_schedule_hash"].startswith("sha256:")
        assert "conversion_timestamp" in manifest
        assert isinstance(manifest["session_distribution"], dict)
        assert sum(manifest["session_distribution"].values()) == 200

    @pytest.mark.live
    def test_live_crash_safe_write(self, tmp_path):
        """Verify crash-safe write pattern: no .partial files remain."""
        config = _load_real_config()
        config["data_pipeline"]["storage"] = {
            "arrow_ipc_path": str(tmp_path / "arrow"),
            "parquet_path": str(tmp_path / "parquet"),
        }
        logger = logging.getLogger("live_test")
        config["data_pipeline"]["contracts_path"] = str(CONTRACTS_PATH)
        converter = ArrowConverter(config, logger)

        df = _make_realistic_df(50)
        result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2020, 6, 1),
            end_date=date(2020, 6, 1),
            dataset_id="crash_safe_test",
            version="v001",
            quality_score=0.90,
            rating="YELLOW",
        )

        # Scan entire output tree for .partial files
        partial_files = list(tmp_path.rglob("*.partial"))
        assert partial_files == [], f"Partial files should not remain: {partial_files}"

        # All output files should exist
        assert Path(result.arrow_path).exists()
        assert Path(result.parquet_path).exists()
        assert Path(result.manifest_path).exists()
