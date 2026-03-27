"""Crash-safe write utilities for pipeline artifacts (Story 1.10).

Consolidates the three independent crash-safe write implementations
from 1-5, 1-6, and 1-7 into a single shared module.

Pattern: write to .partial -> flush -> fsync -> os.replace (atomic rename).

Re-exports the text/bytes helpers from artifacts.storage for convenience,
and adds safe_write_arrow_ipc / safe_write_parquet for binary artifact writes.
"""
import os
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.ipc
import pyarrow.parquet as pq

# Re-export existing utilities so callers can import from one place
from artifacts.storage import crash_safe_write, crash_safe_write_bytes  # noqa: F401


def safe_write_arrow_ipc(table: pa.Table, output_path: Path) -> Path:
    """Write Arrow IPC file using crash-safe pattern.

    No compression — output is mmap-friendly for Rust compute.

    Args:
        table: Arrow Table to write.
        output_path: Final destination path.

    Returns:
        The output_path after successful write.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(output_path.name + ".partial")

    with open(partial, "wb") as f:
        writer = pa.ipc.new_file(f, table.schema)
        writer.write_table(table)
        writer.close()
        f.flush()
        os.fsync(f.fileno())

    os.replace(str(partial), str(output_path))
    return output_path


def safe_write_parquet(
    table: pa.Table,
    output_path: Path,
    compression: str = "snappy",
) -> Path:
    """Write Parquet file using crash-safe pattern.

    Args:
        table: Arrow Table to write.
        output_path: Final destination path.
        compression: Parquet compression codec (default: snappy).

    Returns:
        The output_path after successful write.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(output_path.name + ".partial")

    pa_compression = None if compression == "none" else compression
    pq.write_table(table, str(partial), compression=pa_compression)

    with open(partial, "r+b") as f:
        f.flush()
        os.fsync(f.fileno())

    os.replace(str(partial), str(output_path))
    return output_path


def safe_write_csv(
    write_fn: Callable[[Path], None],
    output_path: Path,
) -> Path:
    """Write CSV (or any file) using crash-safe pattern via callback.

    The callback receives the partial path and should write the file there.
    After the callback returns, the partial file is fsynced and atomically
    renamed to the final path.

    Args:
        write_fn: Callable that writes content to the given Path.
        output_path: Final destination path.

    Returns:
        The output_path after successful write.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(output_path.name + ".partial")

    write_fn(partial)

    with open(partial, "r+b") as f:
        f.flush()
        os.fsync(f.fileno())

    os.replace(str(partial), str(output_path))
    return output_path
