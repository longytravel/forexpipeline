"""Data splitting manifest creation (Story 1.8, FR58/FR59).

Creates and writes JSON manifests that record dataset identity,
config hash, split metadata, and file paths for reproducibility.

Architecture references:
- FR58: Versioned artifacts at every stage
- FR59: Explicit configuration for traceability
- D7: Config hash embedded in every artifact manifest
- Crash-Safe Write Pattern: write -> flush -> fsync -> atomic rename
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from artifacts.storage import crash_safe_write

logger = logging.getLogger(__name__)


def create_data_manifest(
    dataset_id: str,
    config_hash: str,
    split_metadata: dict,
    file_paths: dict,
    pair: str,
    start_date: str,
    end_date: str,
    source: str,
    data_hash: str,
) -> dict:
    """Create a data manifest dict for a split dataset.

    Args:
        dataset_id: Full dataset identifier string.
        config_hash: SHA-256 hash of the config used.
        split_metadata: Dict from ``split_train_test``
            (split_timestamp_us, counts, ratios, etc.).
        file_paths: Dict with ``base_files`` and ``timeframes`` sub-dicts
            mapping role -> filename.
        pair: Currency pair (e.g. "EURUSD").
        start_date: ISO date string for data start.
        end_date: ISO date string for data end.
        source: Data source provider (e.g. "dukascopy").
        data_hash: Full SHA-256 hex digest of the M1 source data file.

    Returns:
        Manifest dict ready for JSON serialization.
    """
    manifest = {
        "dataset_id": dataset_id,
        "pair": pair,
        "start_date": start_date,
        "end_date": end_date,
        "source": source,
        "data_hash": data_hash,
        "config_hash": config_hash,
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "split": {
            "mode": split_metadata.get("split_mode", "ratio"),
            "configured_ratio": split_metadata.get("configured_ratio", 0.7),
            "actual_ratio": split_metadata.get("split_ratio_actual", 0.0),
            "split_timestamp_us": split_metadata.get("split_timestamp_us", 0),
            "split_date_iso": split_metadata.get("split_date_iso", ""),
            "train_bar_count": split_metadata.get("train_bar_count", 0),
            "test_bar_count": split_metadata.get("test_bar_count", 0),
        },
        "files": file_paths.get("base_files", {}),
        "timeframes": file_paths.get("timeframes", {}),
    }

    return manifest


def write_manifest(manifest: dict, storage_path: Path) -> Path:
    """Write manifest JSON using crash-safe pattern.

    File name: ``{dataset_id}_manifest.json``
    Location: *storage_path* (same directory as the data files).

    Returns:
        Path to the written manifest file.
    """
    storage_path = Path(storage_path)
    dataset_id = manifest["dataset_id"]
    manifest_path = storage_path / f"{dataset_id}_manifest.json"

    crash_safe_write(manifest_path, json.dumps(manifest, indent=2))

    logger.info(
        "Data manifest written: %s",
        manifest_path,
        extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
    )
    return manifest_path
