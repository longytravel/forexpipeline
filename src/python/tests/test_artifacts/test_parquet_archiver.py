"""Unit tests for artifacts.parquet_archiver — ParquetArchiver (Task 5)."""
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from artifacts.parquet_archiver import ParquetArchiver


@pytest.fixture
def archiver():
    return ParquetArchiver()


@pytest.fixture
def sample_arrow(tmp_path):
    """Create a sample Arrow IPC file."""
    table = pa.table({
        "trade_id": pa.array([1, 2, 3], type=pa.int64()),
        "pnl_pips": pa.array([10.5, -5.2, 3.1], type=pa.float64()),
        "direction": pa.array(["long", "short", "long"], type=pa.utf8()),
    })
    arrow_path = tmp_path / "test.arrow"
    with open(arrow_path, "wb") as f:
        writer = pa.ipc.new_file(f, table.schema)
        writer.write_table(table)
        writer.close()
    return arrow_path, table


class TestParquetArchiver:
    def test_archive_roundtrip(self, archiver, sample_arrow, tmp_path):
        """Arrow → Parquet → read back, verify identical data."""
        arrow_path, original = sample_arrow
        parquet_path = tmp_path / "test.parquet"

        archiver.archive_arrow_to_parquet(arrow_path, parquet_path)

        loaded = pq.read_table(str(parquet_path))
        assert loaded.num_rows == original.num_rows
        assert loaded.column_names == original.column_names
        assert loaded.column("trade_id").to_pylist() == original.column("trade_id").to_pylist()
        assert loaded.column("direction").to_pylist() == original.column("direction").to_pylist()

    def test_archive_compression(self, archiver, tmp_path):
        """Parquet file smaller than Arrow IPC."""
        # Create a larger table for meaningful compression
        n = 1000
        table = pa.table({
            "trade_id": pa.array(list(range(n)), type=pa.int64()),
            "pnl_pips": pa.array([float(i) for i in range(n)], type=pa.float64()),
            "direction": pa.array(["long" if i % 2 == 0 else "short" for i in range(n)], type=pa.utf8()),
        })
        arrow_path = tmp_path / "large.arrow"
        with open(arrow_path, "wb") as f:
            writer = pa.ipc.new_file(f, table.schema)
            writer.write_table(table)
            writer.close()

        parquet_path = tmp_path / "large.parquet"
        archiver.archive_arrow_to_parquet(arrow_path, parquet_path)

        # Parquet with zstd should be smaller or comparable
        arrow_size = arrow_path.stat().st_size
        parquet_size = parquet_path.stat().st_size
        # For repetitive data, Parquet should compress well
        assert parquet_size <= arrow_size

    def test_archive_crash_safe(self, archiver, sample_arrow, tmp_path):
        """No .partial files after success."""
        arrow_path, _ = sample_arrow
        parquet_path = tmp_path / "test.parquet"

        archiver.archive_arrow_to_parquet(arrow_path, parquet_path)

        partial = parquet_path.with_name("test.parquet.partial")
        assert not partial.exists()
        assert parquet_path.exists()

    def test_archive_backtest_results(self, archiver, tmp_path):
        """Archive all .arrow files in backtest/ directory."""
        version_dir = tmp_path / "v001"
        backtest_dir = version_dir / "backtest"
        backtest_dir.mkdir(parents=True)

        # Create two Arrow files
        for name in ["trade-log", "equity-curve"]:
            table = pa.table({"val": pa.array([1, 2, 3], type=pa.int64())})
            with open(backtest_dir / f"{name}.arrow", "wb") as f:
                writer = pa.ipc.new_file(f, table.schema)
                writer.write_table(table)
                writer.close()

        archived = archiver.archive_backtest_results(version_dir)
        assert len(archived) == 2
        assert (backtest_dir / "trade-log.parquet").exists()
        assert (backtest_dir / "equity-curve.parquet").exists()

    def test_archive_skips_existing(self, archiver, tmp_path):
        """Existing .parquet files are skipped (resume-safe)."""
        version_dir = tmp_path / "v001"
        backtest_dir = version_dir / "backtest"
        backtest_dir.mkdir(parents=True)

        table = pa.table({"val": pa.array([1], type=pa.int64())})
        arrow_path = backtest_dir / "trade-log.arrow"
        with open(arrow_path, "wb") as f:
            writer = pa.ipc.new_file(f, table.schema)
            writer.write_table(table)
            writer.close()

        # Pre-create parquet
        parquet_path = backtest_dir / "trade-log.parquet"
        pq.write_table(table, str(parquet_path))

        archived = archiver.archive_backtest_results(version_dir)
        assert len(archived) == 0  # Nothing new archived
