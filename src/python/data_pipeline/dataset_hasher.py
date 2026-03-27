"""Dataset identification and hashing for consistent sourcing (FR8).

Every dataset is identified by {pair}_{start_date}_{end_date}_{source}_{download_hash}.
Re-runs against the same date range MUST use the identical Arrow IPC file (same hash).
New downloads create new versioned artifacts, never overwrite existing.

Architecture references:
- FR8: Consistent data sourcing
- D2: Artifact Schema & Storage — immutable versioned artifacts
- FR61: Deterministic, consistent behavior
"""
import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def compute_dataset_id(
    pair: str,
    start_date: str,
    end_date: str,
    source: str,
    data_hash: str,
) -> str:
    """Generate a dataset identifier string.

    Format: {pair}_{start_date}_{end_date}_{source}_{data_hash_8chars}
    Example: EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1

    Args:
        pair: Currency pair (e.g. "EURUSD").
        start_date: ISO date string (e.g. "2024-01-01").
        end_date: ISO date string (e.g. "2024-12-31").
        source: Data source provider (e.g. "dukascopy").
        data_hash: Full SHA-256 hex digest of the source data file.

    Returns:
        Dataset identifier string.
    """
    truncated_hash = data_hash[:8]
    return f"{pair}_{start_date}_{end_date}_{source}_{truncated_hash}"


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file's content.

    Reads in 64KB chunks for memory efficiency on large files.

    Returns:
        Full hex digest (64 chars). For dataset IDs, callers
        truncate to first 8 chars.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    file_path = Path(file_path)
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65_536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def check_existing_dataset(
    dataset_id: str, storage_path: Path, config_hash: str = "",
) -> Optional[Path]:
    """Check if a manifest for this dataset ID already exists.

    If the manifest exists AND config_hash matches (when provided), the
    dataset has already been split and the caller should reuse the
    existing artifacts (consistent sourcing).

    When config changes (different parameters, walk-forward windows),
    the config_hash won't match and stale artifacts are not reused.

    Returns:
        Path to existing manifest if found and valid, None otherwise.
    """
    storage_path = Path(storage_path)
    manifest_name = f"{dataset_id}_manifest.json"
    manifest_path = storage_path / manifest_name

    if manifest_path.exists():
        # If config_hash provided, verify it matches the existing manifest
        if config_hash:
            import json
            try:
                with open(manifest_path, "r") as f:
                    existing_manifest = json.load(f)
                existing_config_hash = existing_manifest.get("config_hash", "")
                if existing_config_hash != config_hash:
                    logger.info(
                        "Existing dataset found but config_hash differs "
                        "(existing=%s, current=%s) — cache invalidated",
                        existing_config_hash[:16],
                        config_hash[:16],
                        extra={"ctx": {
                            "component": "data_pipeline",
                            "stage": "data_splitting",
                        }},
                    )
                    return None
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    "Could not read existing manifest for config_hash check: %s",
                    manifest_path,
                    extra={"ctx": {
                        "component": "data_pipeline",
                        "stage": "data_splitting",
                    }},
                )
                return None

        logger.info(
            "Existing dataset found: %s",
            manifest_path,
            extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
        )
        return manifest_path

    return None


def ensure_no_overwrite(
    file_path: Path, expected_hash: Optional[str] = None
) -> bool:
    """Check whether a file can be safely written without overwriting.

    Rules (AC #5 — never overwrite existing artifacts):
    - File does NOT exist: return True (safe to write).
    - File exists AND expected_hash matches actual: return False
      (idempotent re-run — skip writing).
    - File exists AND hash does NOT match: raise ValueError
      (should never happen for the same dataset ID).

    Args:
        file_path: Target output path.
        expected_hash: If provided, compare against actual file hash.

    Returns:
        True if the file should be written, False if it should be skipped.

    Raises:
        ValueError: If file exists with a different hash (corruption / collision).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return True

    if expected_hash is None:
        # File exists but no hash to compare — skip (assume idempotent)
        logger.info(
            "File already exists, skipping: %s",
            file_path,
            extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
        )
        return False

    actual_hash = compute_file_hash(file_path)
    if actual_hash == expected_hash:
        logger.info(
            "File exists with matching hash, skipping: %s",
            file_path,
            extra={"ctx": {"component": "data_pipeline", "stage": "data_splitting"}},
        )
        return False

    raise ValueError(
        f"File exists with DIFFERENT hash — refusing to overwrite.\n"
        f"  Path: {file_path}\n"
        f"  Expected hash: {expected_hash}\n"
        f"  Actual hash:   {actual_hash}\n"
        "This should never happen for the same dataset ID. "
        "Investigate data integrity."
    )
