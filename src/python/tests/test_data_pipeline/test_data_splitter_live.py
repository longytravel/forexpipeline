"""Live integration tests for data splitting pipeline (Story 1.8).

These tests exercise the REAL system: writing real Arrow IPC and Parquet files,
computing real hashes, creating real manifests, and verifying outputs on disk.

Run with: pytest -m live
"""
import json
import os

import pyarrow as pa
import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from config_loader.hasher import compute_config_hash
from data_pipeline.data_manifest import create_data_manifest, write_manifest
from data_pipeline.data_splitter import (
    SplitError,
    _write_arrow_ipc_crashsafe,
    _write_parquet_crashsafe,
    run_data_splitting,
    split_train_test,
)
from data_pipeline.dataset_hasher import compute_file_hash, ensure_no_overwrite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MARKET_SCHEMA = pa.schema([
    pa.field("timestamp", pa.int64(), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("bid", pa.float64(), nullable=False),
    pa.field("ask", pa.float64(), nullable=False),
    pa.field("session", pa.utf8(), nullable=False),
    pa.field("quarantined", pa.bool_(), nullable=False),
])


def _make_table(n_rows: int, start_ts_us: int = 1_704_067_200_000_000) -> pa.Table:
    """Create a realistic market_data Arrow table."""
    timestamps = [start_ts_us + i * 60_000_000 for i in range(n_rows)]
    return pa.table(
        {
            "timestamp": pa.array(timestamps, type=pa.int64()),
            "open": pa.array([1.1000 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "high": pa.array([1.1010 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "low": pa.array([1.0990 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "close": pa.array([1.1005 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "bid": pa.array([1.0999 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "ask": pa.array([1.1001 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "session": pa.array(["london"] * n_rows, type=pa.utf8()),
            "quarantined": pa.array([False] * n_rows, type=pa.bool_()),
        },
        schema=_MARKET_SCHEMA,
    )


def _write_source_arrow(table: pa.Table, path):
    """Write an Arrow IPC file as a 'source' from prior pipeline stage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer = pa.ipc.new_file(f, table.schema)
        writer.write_table(table)
        writer.close()


def _make_config(storage_path: str) -> dict:
    """Build a full config dict for live tests."""
    return {
        "project": {"name": "test-pipeline", "version": "0.1.0"},
        "data": {
            "storage_path": storage_path,
            "default_pair": "EURUSD",
            "default_timeframe": "M1",
            "supported_timeframes": ["M1", "M5", "H1"],
            "download": {"source": "dukascopy"},
        },
        "data_pipeline": {
            "storage_path": storage_path,
            "splitting": {
                "split_ratio": 0.7,
                "split_mode": "ratio",
                "split_date": "",
            },
            "parquet": {"compression": "snappy"},
        },
        "sessions": {"timezone": "UTC"},
        "logging": {"level": "INFO", "log_dir": "logs"},
    }


# ---------------------------------------------------------------------------
# Live tests
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveFullPipeline:
    """End-to-end: source files -> split -> verify output on disk."""

    def test_live_full_split_pipeline(self, tmp_path):
        """Run full split pipeline and verify all output artifacts exist."""
        pair = "EURUSD"
        start_date = "2024-01-01"
        end_date = "2024-06-30"
        n_m1 = 2000
        n_h1 = 200  # Coarser timeframe has fewer bars

        storage = tmp_path / "data-pipeline"
        storage.mkdir()

        # Create source M1 data
        m1_start_us = 1_704_067_200_000_000  # 2024-01-01 00:00 UTC
        m1_table = _make_table(n_m1, start_ts_us=m1_start_us)
        m1_path = storage / f"{pair}_{start_date}_{end_date}_M1.arrow"
        _write_source_arrow(m1_table, m1_path)

        # Create source H1 data (using H1-spaced timestamps: 3600s = 3_600_000_000 us)
        h1_timestamps = [m1_start_us + i * 3_600_000_000 for i in range(n_h1)]
        h1_table = pa.table(
            {
                "timestamp": pa.array(h1_timestamps, type=pa.int64()),
                "open": pa.array([1.1] * n_h1, type=pa.float64()),
                "high": pa.array([1.11] * n_h1, type=pa.float64()),
                "low": pa.array([1.09] * n_h1, type=pa.float64()),
                "close": pa.array([1.105] * n_h1, type=pa.float64()),
                "bid": pa.array([1.0999] * n_h1, type=pa.float64()),
                "ask": pa.array([1.1001] * n_h1, type=pa.float64()),
                "session": pa.array(["london"] * n_h1, type=pa.utf8()),
                "quarantined": pa.array([False] * n_h1, type=pa.bool_()),
            },
            schema=_MARKET_SCHEMA,
        )
        h1_path = storage / f"{pair}_{start_date}_{end_date}_H1.arrow"
        _write_source_arrow(h1_table, h1_path)

        config = _make_config(str(storage))

        # Run the full pipeline
        manifest = run_data_splitting(pair, storage, config)

        # Verify manifest structure
        assert manifest["dataset_id"].startswith(f"{pair}_{start_date}_{end_date}_dukascopy_")
        assert manifest["pair"] == pair
        assert manifest["config_hash"]  # non-empty
        assert manifest["data_hash"]  # non-empty
        assert manifest["split"]["train_bar_count"] > 0
        assert manifest["split"]["test_bar_count"] > 0

        # Extract hash from dataset_id for filename verification
        hash8 = manifest["dataset_id"].rsplit("_", 1)[-1]

        # Verify M1 split files exist on disk (hash embedded in filename per AC #5)
        for suffix in (f"{hash8}_M1_train.arrow", f"{hash8}_M1_test.arrow",
                       f"{hash8}_M1_train.parquet", f"{hash8}_M1_test.parquet"):
            fpath = storage / f"{pair}_{start_date}_{end_date}_{suffix}"
            assert fpath.exists(), f"Missing: {fpath}"
            assert fpath.stat().st_size > 0, f"Empty: {fpath}"

        # Verify H1 split files exist on disk
        for suffix in (f"{hash8}_H1_train.arrow", f"{hash8}_H1_test.arrow",
                       f"{hash8}_H1_train.parquet", f"{hash8}_H1_test.parquet"):
            fpath = storage / f"{pair}_{start_date}_{end_date}_{suffix}"
            assert fpath.exists(), f"Missing: {fpath}"

        # Verify manifest file on disk
        manifest_files = list(storage.glob("*_manifest.json"))
        assert len(manifest_files) == 1
        loaded = json.loads(manifest_files[0].read_text())
        assert loaded["dataset_id"] == manifest["dataset_id"]

    def test_live_arrow_ipc_readable_after_split(self, tmp_path):
        """Split Arrow IPC files are readable via mmap and have correct schema."""
        storage = tmp_path / "data"
        storage.mkdir()

        table = _make_table(1000)
        m1_path = storage / "EURUSD_2024-01-01_2024-06-30_M1.arrow"
        _write_source_arrow(table, m1_path)

        config = _make_config(str(storage))
        manifest = run_data_splitting("EURUSD", storage, config)
        hash8 = manifest["dataset_id"].rsplit("_", 1)[-1]

        # Read train Arrow IPC via mmap
        train_path = storage / f"EURUSD_2024-01-01_2024-06-30_{hash8}_M1_train.arrow"
        mmap = pa.memory_map(str(train_path), "r")
        reader = pa.ipc.open_file(mmap)
        train_table = reader.read_all()
        mmap.close()

        assert train_table.num_rows == 700
        assert train_table.schema == _MARKET_SCHEMA

        # Read test Parquet
        test_pq_path = storage / f"EURUSD_2024-01-01_2024-06-30_{hash8}_M1_test.parquet"
        test_table = pq.read_table(str(test_pq_path))
        assert test_table.num_rows == 300

    def test_live_temporal_guarantee_on_disk(self, tmp_path):
        """Verify strict temporal guarantee holds in files written to disk."""
        storage = tmp_path / "data"
        storage.mkdir()

        table = _make_table(500)
        m1_path = storage / "EURUSD_2024-01-01_2024-06-30_M1.arrow"
        _write_source_arrow(table, m1_path)

        config = _make_config(str(storage))
        manifest = run_data_splitting("EURUSD", storage, config)
        hash8 = manifest["dataset_id"].rsplit("_", 1)[-1]

        # Read both files from disk
        train_path = storage / f"EURUSD_2024-01-01_2024-06-30_{hash8}_M1_train.arrow"
        test_path = storage / f"EURUSD_2024-01-01_2024-06-30_{hash8}_M1_test.arrow"

        train_mmap = pa.memory_map(str(train_path), "r")
        train_t = pa.ipc.open_file(train_mmap).read_all()
        train_mmap.close()

        test_mmap = pa.memory_map(str(test_path), "r")
        test_t = pa.ipc.open_file(test_mmap).read_all()
        test_mmap.close()

        import pyarrow.compute as pc

        train_max = pc.max(train_t.column("timestamp")).as_py()
        test_min = pc.min(test_t.column("timestamp")).as_py()
        assert train_max < test_min


@pytest.mark.live
class TestLiveIdempotentRerun:
    """AC #4: Re-runs against the same data produce identical results."""

    def test_live_rerun_uses_cached_manifest(self, tmp_path):
        """Second run finds existing manifest and skips re-splitting."""
        storage = tmp_path / "data"
        storage.mkdir()

        table = _make_table(200)
        m1_path = storage / "EURUSD_2024-01-01_2024-06-30_M1.arrow"
        _write_source_arrow(table, m1_path)

        config = _make_config(str(storage))

        # First run — creates everything
        manifest1 = run_data_splitting("EURUSD", storage, config)

        # Second run — should reuse existing manifest
        manifest2 = run_data_splitting("EURUSD", storage, config)

        assert manifest1["dataset_id"] == manifest2["dataset_id"]
        assert manifest1["data_hash"] == manifest2["data_hash"]

    def test_live_deterministic_hashes(self, tmp_path):
        """Same data always produces the same file hash and dataset ID."""
        storage = tmp_path / "data"
        storage.mkdir()

        table = _make_table(100)
        path1 = storage / "file1.arrow"
        path2 = storage / "file2.arrow"

        _write_source_arrow(table, path1)
        _write_source_arrow(table, path2)

        hash1 = compute_file_hash(path1)
        hash2 = compute_file_hash(path2)
        assert hash1 == hash2


@pytest.mark.live
class TestLiveCrashSafeWrite:
    """Verify crash-safe write pattern produces valid files with no partials."""

    def test_live_crash_safe_arrow_write(self, tmp_path):
        """Arrow IPC write leaves no .partial files and produces valid output."""
        table = _make_table(500)
        out = tmp_path / "output.arrow"

        _write_arrow_ipc_crashsafe(table, out)

        assert out.exists()
        assert out.stat().st_size > 0
        assert list(tmp_path.glob("*.partial")) == []

        # Verify readable
        mmap = pa.memory_map(str(out), "r")
        reader = pa.ipc.open_file(mmap)
        assert reader.read_all().num_rows == 500
        mmap.close()

    def test_live_crash_safe_parquet_write(self, tmp_path):
        """Parquet write leaves no .partial files and produces valid output."""
        table = _make_table(500)
        out = tmp_path / "output.parquet"

        _write_parquet_crashsafe(table, out, compression="snappy")

        assert out.exists()
        assert out.stat().st_size > 0
        assert list(tmp_path.glob("*.partial")) == []

        # Verify readable
        loaded = pq.read_table(str(out))
        assert loaded.num_rows == 500

    def test_live_manifest_crash_safe(self, tmp_path):
        """Manifest write is crash-safe — no partials remain."""
        manifest = create_data_manifest(
            dataset_id="TEST_2024-01-01_2024-06-30_dukascopy_abcd1234",
            config_hash="test_hash",
            split_metadata={
                "split_mode": "ratio",
                "configured_ratio": 0.7,
                "split_ratio_actual": 0.7,
                "split_timestamp_us": 123,
                "split_date_iso": "2024-05-01T00:00:00Z",
                "train_bar_count": 70,
                "test_bar_count": 30,
            },
            file_paths={"base_files": {}, "timeframes": {}},
            pair="TEST",
            start_date="2024-01-01",
            end_date="2024-06-30",
            source="dukascopy",
            data_hash="abcd1234",
        )

        path = write_manifest(manifest, tmp_path)

        assert path.exists()
        assert list(tmp_path.glob("*.partial")) == []

        loaded = json.loads(path.read_text())
        assert loaded["dataset_id"] == manifest["dataset_id"]
