"""Chronological train/test data splitter and orchestrator (Story 1.8).

Core splitting (Task 3):
- split_train_test(): PyArrow table splitting with strict temporal guarantee
- No shuffle, no random sampling — chronological order is sacred
- Uses PyArrow table.slice() for zero-copy ratio splits

Orchestration (Task 7):
- run_data_splitting(): Full pipeline from source files to split outputs + manifest

Architecture references:
- FR7: Chronological train/test splitting at configurable split point
- FR8: Consistent data sourcing with hash-based identification
- D2: Arrow IPC (compute) + Parquet (archival) dual-format storage
- D3: Stages are stateless — all state in artifacts
- D8: Structured error handling at component boundaries
"""
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc
import pyarrow.parquet as pq

from artifacts.storage import crash_safe_write
from config_loader.hasher import compute_config_hash
from data_pipeline.data_manifest import create_data_manifest, write_manifest
from data_pipeline.dataset_hasher import (
    check_existing_dataset,
    compute_dataset_id,
    compute_file_hash,
    ensure_no_overwrite,
)

logger = logging.getLogger(__name__)


class SplitError(Exception):
    """Raised when data splitting fails."""


# ---------------------------------------------------------------------------
# Task 3: Core chronological splitting
# ---------------------------------------------------------------------------

def split_train_test(
    table: pa.Table,
    config: dict,
    split_timestamp_us: Optional[int] = None,
) -> tuple[pa.Table, pa.Table, dict]:
    """Split an Arrow table chronologically into train and test sets.

    Args:
        table: Arrow IPC table with int64 ``timestamp`` column (epoch microseconds).
        config: Full config dict (reads ``data_pipeline.splitting`` section)
            or a flat splitting config with ``split_ratio``, ``split_mode``, ``split_date``.
        split_timestamp_us: If provided, use this as the split boundary
            (for multi-timeframe consistency).  When *None*, compute from
            config (ratio or date mode).

    Returns:
        ``(train_table, test_table, split_metadata)``

    Raises:
        SplitError: If split produces invalid results or temporal guarantee
            is violated.
    """
    if table.num_rows == 0:
        raise SplitError("Cannot split empty table")

    # Resolve splitting config — support both nested and flat layouts
    if "data_pipeline" in config and "splitting" in config["data_pipeline"]:
        splitting_cfg = config["data_pipeline"]["splitting"]
    else:
        splitting_cfg = config

    split_mode = splitting_cfg.get("split_mode", "ratio")
    split_ratio = float(splitting_cfg.get("split_ratio", 0.7))

    ts_col = table.column("timestamp")

    configured_split_date = None

    if split_timestamp_us is not None:
        train, test, actual_split_ts = _split_by_timestamp(table, ts_col, split_timestamp_us)
    elif split_mode == "ratio":
        train, test, actual_split_ts = _split_by_ratio(table, ts_col, split_ratio)
    elif split_mode == "date":
        split_date_str = splitting_cfg.get("split_date", "")
        if not split_date_str:
            raise SplitError("split_mode='date' requires split_date to be set")
        train, test, actual_split_ts = _split_by_date(table, ts_col, split_date_str)
        configured_split_date = split_date_str
    else:
        raise SplitError(f"Unknown split_mode: {split_mode}")

    # Strict temporal guarantee (AC #2)
    _verify_temporal_guarantee(train, test)

    actual_ratio = train.num_rows / table.num_rows
    split_dt = datetime.fromtimestamp(actual_split_ts / 1_000_000, tz=timezone.utc)

    split_metadata = {
        "split_timestamp_us": actual_split_ts,
        "split_date_iso": split_dt.isoformat().replace("+00:00", "Z"),
        "train_bar_count": train.num_rows,
        "test_bar_count": test.num_rows,
        "split_ratio_actual": round(actual_ratio, 4),
        "split_mode": split_mode,
        "configured_ratio": split_ratio,
    }
    if configured_split_date is not None:
        split_metadata["configured_split_date"] = configured_split_date

    logger.info(
        "Split complete: %d train + %d test bars (ratio=%.4f, split=%s)",
        train.num_rows,
        test.num_rows,
        actual_ratio,
        split_dt.date(),
        extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
    )

    return train, test, split_metadata


def _split_by_ratio(
    table: pa.Table, ts_col: pa.ChunkedArray, ratio: float
) -> tuple[pa.Table, pa.Table, int]:
    """Split by ratio using table.slice() for zero-copy performance.

    Sorts by timestamp first to guarantee chronological order (AC #1).
    """
    # Sort by timestamp ascending — must be sorted before splitting (spec Task 3)
    sort_indices = pc.sort_indices(table, sort_keys=[("timestamp", "ascending")])
    table = table.take(sort_indices)

    split_index = int(math.floor(table.num_rows * ratio))

    if split_index == 0:
        raise SplitError(
            f"Split ratio {ratio} produces empty train set for {table.num_rows} rows"
        )
    if split_index >= table.num_rows:
        raise SplitError(
            f"Split ratio {ratio} produces empty test set for {table.num_rows} rows"
        )

    train = table.slice(0, split_index)
    test = table.slice(split_index)

    # Last timestamp in train set
    split_ts = train.column("timestamp")[-1].as_py()

    return train, test, split_ts


def _split_by_date(
    table: pa.Table, ts_col: pa.ChunkedArray, split_date_str: str
) -> tuple[pa.Table, pa.Table, int]:
    """Split by explicit date boundary."""
    split_dt = datetime.fromisoformat(split_date_str).replace(tzinfo=timezone.utc)
    split_us = int(split_dt.timestamp() * 1_000_000)
    return _split_by_timestamp(table, ts_col, split_us)


def _split_by_timestamp(
    table: pa.Table, ts_col: pa.ChunkedArray, split_us: int
) -> tuple[pa.Table, pa.Table, int]:
    """Split by explicit timestamp: train < split_us, test >= split_us."""
    train_mask = pc.less(ts_col, split_us)
    test_mask = pc.greater_equal(ts_col, split_us)

    train = table.filter(train_mask)
    test = table.filter(test_mask)

    if train.num_rows == 0:
        raise SplitError(
            f"Split at timestamp {split_us} produces empty train set"
        )
    if test.num_rows == 0:
        raise SplitError(
            f"Split at timestamp {split_us} produces empty test set"
        )

    actual_split_ts = train.column("timestamp")[-1].as_py()
    return train, test, actual_split_ts


def _verify_temporal_guarantee(train: pa.Table, test: pa.Table) -> None:
    """Verify strict temporal ordering: max(train.timestamp) < min(test.timestamp).

    AC #2: no future data leaks into the training set.
    """
    if train.num_rows == 0 or test.num_rows == 0:
        return

    train_max = pc.max(train.column("timestamp")).as_py()
    test_min = pc.min(test.column("timestamp")).as_py()

    if train_max >= test_min:
        raise SplitError(
            f"Temporal guarantee violated: max(train)={train_max} "
            f">= min(test)={test_min}. "
            "Data may contain duplicate timestamps or is not sorted."
        )


# ---------------------------------------------------------------------------
# Task 6: File writing helpers
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(
    r"^([A-Z]{6})_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_([A-Z0-9]+)$"
)
_KNOWN_TIMEFRAMES = frozenset({"M1", "M5", "H1", "D1", "W"})


def _write_arrow_ipc_crashsafe(table: pa.Table, output_path: Path) -> Path:
    """Write Arrow IPC file using shared crash-safe utility (D2, NFR15)."""
    from data_pipeline.utils.safe_write import safe_write_arrow_ipc

    output_path = Path(output_path)
    safe_write_arrow_ipc(table, output_path)

    logger.info(
        "Arrow IPC written: %s (%d rows)",
        output_path,
        table.num_rows,
        extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
    )
    return output_path


def _write_parquet_crashsafe(
    table: pa.Table, output_path: Path, compression: str = "snappy"
) -> Path:
    """Write Parquet file using shared crash-safe utility (D2, NFR15)."""
    from data_pipeline.utils.safe_write import safe_write_parquet

    output_path = Path(output_path)
    safe_write_parquet(table, output_path, compression)

    logger.info(
        "Parquet written: %s (%d rows)",
        output_path,
        table.num_rows,
        extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
    )
    return output_path


def _find_timeframe_files(pair: str, storage_path: Path) -> dict[str, Path]:
    """Find all Arrow IPC files for a pair in storage_path.

    Matches pattern ``{PAIR}_{start}_{end}_{TF}.arrow`` and excludes
    ``_train`` / ``_test`` split files.

    Returns:
        Dict mapping timeframe string -> file Path.
    """
    found: dict[str, Path] = {}
    for arrow_file in storage_path.glob(f"{pair}_*.arrow"):
        match = _FILENAME_RE.match(arrow_file.stem)
        if match:
            _, _, _, tf = match.groups()
            if tf in _KNOWN_TIMEFRAMES:
                found[tf] = arrow_file
    return found


def _build_split_filename(
    pair: str, start_date: str, end_date: str, timeframe: str, split: str, ext: str,
    data_hash8: str = "",
) -> str:
    """Build output filename for a split file.

    When *data_hash8* is provided the hash is embedded so that different
    downloads for the same pair/date range produce distinct filenames (AC #5).

    Example: EURUSD_2024-01-01_2024-12-31_a3b8f2c1_M1_train.arrow
    """
    if data_hash8:
        return f"{pair}_{start_date}_{end_date}_{data_hash8}_{timeframe}_{split}.{ext}"
    return f"{pair}_{start_date}_{end_date}_{timeframe}_{split}.{ext}"


# ---------------------------------------------------------------------------
# Task 7: Orchestration entry point
# ---------------------------------------------------------------------------

def run_data_splitting(pair: str, storage_path: Path, config: dict) -> dict:
    """Orchestrate the full data splitting pipeline.

    Steps:
        1. Load config including config_hash (from Story 1.3 config_loader)
        2. Locate all Arrow IPC files for the pair (M1, M5, H1, D1, W)
        3. Compute dataset hash from the M1 source file
        4. Generate dataset ID: ``{pair}_{start}_{end}_{source}_{download_hash}``
        5. Check if this dataset already exists (consistent sourcing)
        6. Split each timeframe at the same temporal boundary
        7. Write train/test Arrow IPC + Parquet files
        8. Create and write the manifest
        9. Return manifest dict for downstream use

    Args:
        pair: Currency pair (e.g. "EURUSD").
        storage_path: Directory containing source Arrow IPC files.
        config: Full project config dict.

    Returns:
        Manifest dict.

    Raises:
        SplitError: On splitting failures.
        FileNotFoundError: When required source files are missing.
    """
    storage_path = Path(storage_path)

    # 1. Config hash
    cfg_hash = compute_config_hash(config)

    # Parquet compression
    parquet_compression = (
        config.get("data_pipeline", {}).get("parquet", {}).get("compression", "snappy")
    )

    # Data source
    source = config.get("data", {}).get("download", {}).get("source", "dukascopy")

    logger.info(
        "Starting data splitting for %s in %s",
        pair,
        storage_path,
        extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
    )

    # 2. Locate all Arrow IPC files
    tf_files = _find_timeframe_files(pair, storage_path)
    if not tf_files:
        raise FileNotFoundError(
            f"No Arrow IPC files found for {pair} in {storage_path}"
        )

    if "M1" not in tf_files:
        raise FileNotFoundError(
            f"M1 Arrow IPC file required for {pair} in {storage_path}. "
            f"Found timeframes: {sorted(tf_files.keys())}"
        )

    logger.info(
        "Found %d timeframes: %s",
        len(tf_files),
        sorted(tf_files.keys()),
        extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
    )

    # 3. Compute dataset hash from M1 source file
    m1_path = tf_files["M1"]
    data_hash_full = compute_file_hash(m1_path)

    # Extract start_date and end_date from M1 filename
    m1_match = _FILENAME_RE.match(m1_path.stem)
    if not m1_match:
        raise SplitError(f"Cannot parse M1 filename: {m1_path.name}")
    _, start_date, end_date, _ = m1_match.groups()

    # 4. Generate dataset ID
    dataset_id = compute_dataset_id(pair, start_date, end_date, source, data_hash_full)

    logger.info(
        "Dataset ID: %s",
        dataset_id,
        extra={
            "ctx": {
                "component": "data_pipeline",
                "stage": "data_splitting",
                "dataset_id": dataset_id,
                "pair": pair,
                "config_hash": cfg_hash,
            }
        },
    )

    # 5. Check if this dataset already exists (consistent sourcing — re-use)
    #    Include config_hash so config changes invalidate cached splits (AC #3)
    existing = check_existing_dataset(dataset_id, storage_path, config_hash=cfg_hash)
    if existing is not None:
        logger.info(
            "Dataset already split — reusing existing artifacts: %s",
            existing,
            extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
        )
        with open(existing, "r") as f:
            return json.load(f)

    # 6. Split M1 first to determine the temporal split point
    m1_table = _read_arrow_ipc(m1_path)
    _, _, m1_split_meta = split_train_test(m1_table, config)
    split_timestamp_us = m1_split_meta["split_timestamp_us"]

    logger.info(
        "Split point determined from M1: %s (ts=%d)",
        m1_split_meta["split_date_iso"],
        split_timestamp_us,
        extra={
            "ctx": {
                "component": "data_pipeline",
                "stage": "data_splitting",
                "split_date": m1_split_meta["split_date_iso"],
                "train_bars": m1_split_meta["train_bar_count"],
                "test_bars": m1_split_meta["test_bar_count"],
            }
        },
    )

    # 6-7. Split each timeframe at the same temporal boundary and write output
    base_files: dict[str, str] = {}
    timeframes_files: dict[str, dict[str, str]] = {}
    all_split_meta = m1_split_meta  # Use M1 metadata as the primary
    data_hash8 = data_hash_full[:8]

    for tf in sorted(tf_files.keys()):
        tf_path = tf_files[tf]
        table = _read_arrow_ipc(tf_path) if tf != "M1" else m1_table

        # Split using the M1-determined timestamp for all timeframes
        if tf == "M1":
            train, test, _ = split_train_test(table, config)
        else:
            train, test, _ = split_train_test(
                table, config, split_timestamp_us=split_timestamp_us
            )

        # Build output filenames — hash embedded so new downloads get new files (AC #5)
        train_arrow_name = _build_split_filename(pair, start_date, end_date, tf, "train", "arrow", data_hash8)
        test_arrow_name = _build_split_filename(pair, start_date, end_date, tf, "test", "arrow", data_hash8)
        train_pq_name = _build_split_filename(pair, start_date, end_date, tf, "train", "parquet", data_hash8)
        test_pq_name = _build_split_filename(pair, start_date, end_date, tf, "test", "parquet", data_hash8)

        train_arrow_path = storage_path / train_arrow_name
        test_arrow_path = storage_path / test_arrow_name
        train_pq_path = storage_path / train_pq_name
        test_pq_path = storage_path / test_pq_name

        # Write each file independently (lesson from Story 1.7:
        # check and skip each paired artifact independently)
        if ensure_no_overwrite(train_arrow_path):
            _write_arrow_ipc_crashsafe(train, train_arrow_path)
        if ensure_no_overwrite(test_arrow_path):
            _write_arrow_ipc_crashsafe(test, test_arrow_path)
        if ensure_no_overwrite(train_pq_path):
            _write_parquet_crashsafe(train, train_pq_path, parquet_compression)
        if ensure_no_overwrite(test_pq_path):
            _write_parquet_crashsafe(test, test_pq_path, parquet_compression)

        # Record file paths
        tf_entry = {
            "train": train_arrow_name,
            "test": test_arrow_name,
            "train_parquet": train_pq_name,
            "test_parquet": test_pq_name,
        }

        if tf == "M1":
            # M1 goes into base_files with the source file too
            source_name = tf_path.name
            base_files = {
                "full": source_name,
                "train": train_arrow_name,
                "test": test_arrow_name,
                "full_parquet": source_name.replace(".arrow", ".parquet"),
                "train_parquet": train_pq_name,
                "test_parquet": test_pq_name,
            }
        else:
            timeframes_files[tf] = tf_entry

        logger.info(
            "Timeframe %s split: %d train + %d test",
            tf,
            train.num_rows,
            test.num_rows,
            extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
        )

    # 8. Create and write the manifest
    file_paths = {"base_files": base_files, "timeframes": timeframes_files}
    manifest = create_data_manifest(
        dataset_id=dataset_id,
        config_hash=cfg_hash,
        split_metadata=all_split_meta,
        file_paths=file_paths,
        pair=pair,
        start_date=start_date,
        end_date=end_date,
        source=source,
        data_hash=data_hash_full,
    )

    manifest_path = write_manifest(manifest, storage_path)

    logger.info(
        "Data splitting complete for %s: dataset_id=%s, manifest=%s",
        pair,
        dataset_id,
        manifest_path,
        extra={
            "ctx": {
                "component": "data_pipeline",
                "stage": "data_splitting",
                "dataset_id": dataset_id,
                "split_date": all_split_meta["split_date_iso"],
                "train_bars": all_split_meta["train_bar_count"],
                "test_bars": all_split_meta["test_bar_count"],
                "config_hash": cfg_hash,
            }
        },
    )

    # 9. Return manifest dict
    return manifest


def _read_arrow_ipc(path: Path) -> pa.Table:
    """Read an Arrow IPC file into a Table."""
    mmap = pa.memory_map(str(path), "r")
    reader = pa.ipc.open_file(mmap)
    table = reader.read_all()
    mmap.close()
    return table
