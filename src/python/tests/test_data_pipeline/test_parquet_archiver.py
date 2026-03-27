"""Tests for parquet_archiver module (Story 1.6)."""
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_pipeline.parquet_archiver import ParquetArchiver
from data_pipeline.schema_loader import SchemaValidationError


def _make_test_table(n: int = 50) -> pa.Table:
    """Create a simple Arrow Table for testing."""
    schema = pa.schema([
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
    arrays = [
        pa.array(range(n), type=pa.int64()),
        pa.array([1.1] * n, type=pa.float64()),
        pa.array([1.2] * n, type=pa.float64()),
        pa.array([1.0] * n, type=pa.float64()),
        pa.array([1.15] * n, type=pa.float64()),
        pa.array([1.14] * n, type=pa.float64()),
        pa.array([1.16] * n, type=pa.float64()),
        pa.array(["asian"] * n, type=pa.utf8()),
        pa.array([False] * n, type=pa.bool_()),
    ]
    return pa.table(arrays, schema=schema)


@pytest.fixture
def archiver():
    logger = logging.getLogger("test_parquet_archiver")
    return ParquetArchiver({}, logger)


class TestWriteParquet:
    def test_write_parquet_roundtrip(self, tmp_path, archiver):
        """Write Parquet, read back, verify data and schema match."""
        table = _make_test_table(100)
        out_path = tmp_path / "test.parquet"

        archiver.write_parquet(table, out_path, compression="snappy")

        assert out_path.exists()
        read_back = pq.read_table(str(out_path))
        assert read_back.num_rows == 100
        assert read_back.schema.remove_metadata() == table.schema

    def test_parquet_compression(self, tmp_path, archiver):
        """Verify compressed file is smaller than uncompressed."""
        table = _make_test_table(500)

        compressed_path = tmp_path / "compressed.parquet"
        uncompressed_path = tmp_path / "uncompressed.parquet"

        archiver.write_parquet(table, compressed_path, compression="snappy")
        archiver.write_parquet(table, uncompressed_path, compression="none")

        compressed_size = compressed_path.stat().st_size
        uncompressed_size = uncompressed_path.stat().st_size
        assert compressed_size < uncompressed_size

    def test_parquet_crash_safe(self, tmp_path, archiver):
        """Verify no .partial file remains after write."""
        table = _make_test_table(10)
        out_path = tmp_path / "safe.parquet"

        archiver.write_parquet(table, out_path)

        partial = out_path.with_name(out_path.name + ".partial")
        assert not partial.exists()
        assert out_path.exists()

    def test_parquet_zstd_compression(self, tmp_path, archiver):
        """Verify zstd compression works."""
        table = _make_test_table(100)
        out_path = tmp_path / "zstd.parquet"

        archiver.write_parquet(table, out_path, compression="zstd")
        assert out_path.exists()

        read_back = pq.read_table(str(out_path))
        assert read_back.num_rows == 100


class TestVerifyParquet:
    def test_verify_parquet_success(self, tmp_path, archiver):
        """Verify passes on valid file."""
        table = _make_test_table(50)
        out_path = tmp_path / "valid.parquet"
        archiver.write_parquet(table, out_path)

        assert archiver.verify_parquet(out_path, table.schema, 50)

    def test_verify_parquet_wrong_row_count(self, tmp_path, archiver):
        """Verify fails on row count mismatch."""
        table = _make_test_table(50)
        out_path = tmp_path / "rows.parquet"
        archiver.write_parquet(table, out_path)

        with pytest.raises(ValueError, match="row count mismatch"):
            archiver.verify_parquet(out_path, table.schema, 999)

    def test_parquet_creates_parent_dirs(self, tmp_path, archiver):
        """Verify parent directories are created automatically."""
        table = _make_test_table(5)
        out_path = tmp_path / "deep" / "nested" / "dir" / "test.parquet"

        archiver.write_parquet(table, out_path)
        assert out_path.exists()


class TestParquetArchiverDelegation:
    """Regression: ParquetArchiver must delegate to shared safe_write_parquet,
    not reimplement crash-safe write logic (AC #4)."""

    @pytest.fixture
    def archiver(self):
        import logging
        return ParquetArchiver({}, logging.getLogger("test"))

    @pytest.mark.regression
    def test_uses_shared_safe_write(self, tmp_path, archiver, monkeypatch):
        """Verify ParquetArchiver.write_parquet delegates to safe_write_parquet."""
        table = _make_test_table(10)
        out_path = tmp_path / "delegated.parquet"

        calls = []
        original_safe_write = __import__(
            "data_pipeline.utils.safe_write", fromlist=["safe_write_parquet"]
        ).safe_write_parquet

        def tracking_safe_write(tbl, path, compression="snappy"):
            calls.append((path, compression))
            return original_safe_write(tbl, path, compression)

        monkeypatch.setattr(
            "data_pipeline.parquet_archiver.safe_write_parquet",
            tracking_safe_write,
        )

        archiver.write_parquet(table, out_path, "snappy")

        assert len(calls) == 1, "ParquetArchiver must delegate to safe_write_parquet"
        assert calls[0][0] == out_path

    @pytest.mark.regression
    def test_no_partial_files_after_write(self, tmp_path, archiver):
        """No .partial files should remain after successful write."""
        table = _make_test_table(10)
        out_path = tmp_path / "clean.parquet"

        archiver.write_parquet(table, out_path)

        partial_files = list(tmp_path.glob("*.partial"))
        assert partial_files == [], f"Leftover .partial files: {partial_files}"
        assert out_path.exists()

        # Verify data roundtrips correctly
        result = pq.read_table(str(out_path))
        assert result.num_rows == 10
