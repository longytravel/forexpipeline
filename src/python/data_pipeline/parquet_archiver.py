"""Parquet archival writer (Story 1.6).

Writes compressed Parquet files for long-term cold storage.
Delegates to shared safe_write_parquet for crash-safe semantics (AC #4).

Architecture references:
- D2: Parquet for archival — compressed cold storage
- NFR15: Crash-safe write semantics
"""
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.schema_loader import SchemaValidationError
from data_pipeline.utils.safe_write import safe_write_parquet


class ParquetArchiver:
    """Writes and verifies Parquet archival files."""

    def __init__(self, config: dict, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger

    def write_parquet(
        self,
        table: pa.Table,
        output_path: Path,
        compression: str = "snappy",
    ) -> Path:
        """Write Parquet file using shared crash-safe utility.

        Args:
            table: PyArrow Table to write.
            output_path: Target file path.
            compression: Compression codec — snappy, zstd, gzip, or none.

        Returns:
            The output path on success.
        """
        output_path = Path(output_path)

        safe_write_parquet(table, output_path, compression)

        file_size = output_path.stat().st_size
        size_mb = file_size / (1024 * 1024)

        # Compute approximate compression ratio
        uncompressed_estimate = table.nbytes
        ratio = uncompressed_estimate / file_size if file_size > 0 else 0

        self._logger.info(
            "Parquet written: %s (%.2f MB, %d rows, compression=%s, ratio=%.1fx)",
            output_path, size_mb, table.num_rows, compression, ratio,
            extra={"ctx": {"component": "parquet_archiver", "stage": "data_pipeline"}},
        )
        return output_path

    def verify_parquet(
        self,
        path: Path,
        expected_schema: pa.Schema,
        expected_rows: int,
    ) -> bool:
        """Verify written Parquet file: schema and row count."""
        pf = pq.read_table(str(path))
        actual_schema = pf.schema.remove_metadata()

        if actual_schema != expected_schema:
            raise SchemaValidationError(
                f"Parquet verification failed — schema mismatch.\n"
                f"  Expected: {expected_schema}\n"
                f"  Got: {actual_schema}"
            )

        if pf.num_rows != expected_rows:
            raise ValueError(
                f"Parquet row count mismatch: expected {expected_rows}, got {pf.num_rows}"
            )

        self._logger.info(
            "Parquet verified: schema OK, %d rows", pf.num_rows,
            extra={"ctx": {"component": "parquet_archiver", "stage": "data_pipeline"}},
        )
        return True
