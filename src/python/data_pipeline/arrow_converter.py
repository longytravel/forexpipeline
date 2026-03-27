"""Arrow IPC converter (Story 1.6).

Converts validated DataFrames to Arrow IPC format with contract schema
enforcement, session stamping, and mmap-verified output.

Architecture references:
- D1: Arrow IPC files are mmap-friendly for Rust batch compute
- D2: Three-format storage (Arrow IPC for compute, Parquet for archival)
- Crash-safe write pattern for all artifact writes
- Timestamps as int64 epoch microseconds (not Arrow native timestamp)
"""
import hashlib
import json
import logging
import os
from collections import namedtuple
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.ipc

from data_pipeline.utils.safe_write import crash_safe_write, safe_write_arrow_ipc
from config_loader.hasher import compute_config_hash
from data_pipeline.schema_loader import (
    SchemaValidationError,
    load_allowed_values,
    load_arrow_schema,
    validate_dataframe_against_schema,
)
from data_pipeline.session_labeler import assign_sessions_bulk

ConversionResult = namedtuple(
    "ConversionResult",
    ["arrow_path", "parquet_path", "manifest_path", "row_count",
     "arrow_size_mb", "parquet_size_mb"],
)

# VALID_SESSIONS loaded lazily from contracts/arrow_schemas.toml (single source of truth)
_VALID_SESSIONS_CACHE: frozenset | None = None


class ArrowConverter:
    """Converts validated market data to Arrow IPC format.

    Handles:
    - Session column stamping/verification
    - Timestamp conversion to epoch microseconds
    - Arrow Table construction with contract schema
    - Crash-safe Arrow IPC file writing
    - mmap verification of written files
    """

    def __init__(self, config: dict, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger

        # Load session schedule from config
        self._session_schedule = config.get("sessions", {})

        # Storage paths
        dp_cfg = config.get("data_pipeline", {})
        storage_cfg = dp_cfg.get("storage", {})
        base_storage = dp_cfg.get("storage_path", config.get("data", {}).get("storage_path", ""))
        self._arrow_base = Path(storage_cfg.get("arrow_ipc_path", str(Path(base_storage) / "arrow")))
        self._parquet_base = Path(storage_cfg.get("parquet_path", str(Path(base_storage) / "parquet")))

        # Parquet compression
        parquet_cfg = dp_cfg.get("parquet", {})
        self._parquet_compression = parquet_cfg.get("compression", "snappy")

        # Contracts path — resolve relative to project root if not absolute
        contracts_override = dp_cfg.get("contracts_path", "")
        if contracts_override:
            cp = Path(contracts_override)
            if not cp.is_absolute():
                # Walk up from this module to find project root
                module_dir = Path(__file__).resolve().parent
                for parent in [module_dir, *module_dir.parents]:
                    candidate = parent / cp
                    if candidate.is_dir():
                        cp = candidate
                        break
            if cp.is_dir():
                self._contracts_path = cp
            else:
                raise FileNotFoundError(
                    f"data_pipeline.contracts_path '{contracts_override}' not found. "
                    "Set it to an absolute path or relative to the project root."
                )
        else:
            raise FileNotFoundError(
                "data_pipeline.contracts_path not set. "
                "Set it explicitly in config to point to the contracts/ folder."
            )

    # --- Task 2: Session column stamping ---

    def _get_valid_sessions(self) -> frozenset:
        """Load valid session values from contracts/arrow_schemas.toml."""
        global _VALID_SESSIONS_CACHE
        if _VALID_SESSIONS_CACHE is None:
            _VALID_SESSIONS_CACHE = load_allowed_values(
                self._contracts_path, "market_data", "session"
            )
        return _VALID_SESSIONS_CACHE

    def _ensure_session_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure session column exists and contains valid values.

        If session column already exists, validates values.
        If missing, computes using assign_sessions_bulk().
        """
        valid_sessions = self._get_valid_sessions()
        if "session" in df.columns:
            # Validate existing session values
            unique_sessions = set(df["session"].unique())
            invalid = unique_sessions - valid_sessions
            if invalid:
                raise ValueError(
                    f"Invalid session values found: {invalid}. "
                    f"Allowed: {sorted(valid_sessions)}"
                )
            self._logger.info(
                "Session column already present — validated %d unique values",
                len(unique_sessions),
                extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
            )
        else:
            if not self._session_schedule:
                raise ValueError(
                    "No session schedule in config — cannot compute session column"
                )
            df = df.copy()
            df["session"] = assign_sessions_bulk(df, self._session_schedule)
            self._logger.info(
                "Session column computed from config schedule",
                extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
            )

        return df

    # --- Task 2: Quarantined column ---

    @staticmethod
    def _ensure_quarantined_column(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure quarantined column exists, defaulting to False."""
        if "quarantined" not in df.columns:
            df = df.copy() if "session" in df.columns else df
            df["quarantined"] = False
        return df

    # --- Task 3: Timestamp conversion ---

    @staticmethod
    def _convert_timestamps_to_epoch_micros(df: pd.DataFrame) -> pd.Series:
        """Convert pandas datetime64 timestamps to int64 epoch microseconds.

        Per architecture: Arrow IPC columns use int64 epoch microseconds.
        Formula: microseconds since 1970-01-01 UTC.

        Handles both pandas <3.0 (datetime64[ns]) and >=3.0 (datetime64[us]).
        """
        timestamps = pd.to_datetime(df["timestamp"], utc=True)
        resolution = str(timestamps.dtype)
        raw = timestamps.astype("int64")
        if "ns" in resolution:
            # Nanoseconds → microseconds
            return raw // 1_000
        # datetime64[us] — already in microseconds
        return raw

    # --- Task 4: Arrow Table construction ---

    def _prepare_arrow_table(
        self, df: pd.DataFrame, schema: pa.Schema
    ) -> pa.Table:
        """Convert validated DataFrame to Arrow Table with exact contract schema.

        Steps:
        1. Ensure timestamp is int64 epoch microseconds
        2. Ensure session is utf8 string
        3. Ensure quarantined is bool
        4. Cast all numeric columns to float64
        5. Apply schema via pa.Table.from_pandas
        6. Validate resulting schema matches contract
        """
        df = df.copy()

        # Convert timestamps — handle datetime64, numeric, or string (from CSV)
        ts_col = df["timestamp"]
        if pd.api.types.is_datetime64_any_dtype(ts_col):
            df["timestamp"] = self._convert_timestamps_to_epoch_micros(df)
        elif pd.api.types.is_numeric_dtype(ts_col):
            # Already numeric (int64 epoch microseconds) — cast directly
            df["timestamp"] = ts_col.astype("int64")
        else:
            # String timestamps (e.g., from CSV deserialization) — parse then convert
            df["timestamp"] = self._convert_timestamps_to_epoch_micros(df)

        # Ensure session is string
        df["session"] = df["session"].astype(str)

        # Ensure quarantined is bool
        df["quarantined"] = df["quarantined"].astype(bool)

        # Cast OHLC + bid/ask to float64
        for col in ("open", "high", "low", "close", "bid", "ask"):
            if col in df.columns:
                df[col] = df[col].astype("float64")

        # Select and order columns to match schema
        ordered_cols = [f.name for f in schema]
        df = df[ordered_cols]

        # Build Arrow Table with exact schema — will raise on type mismatch
        table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

        # Verify schema matches contract exactly
        if table.schema.remove_metadata() != schema:
            raise SchemaValidationError(
                f"Arrow Table schema does not match contract.\n"
                f"  Expected: {schema}\n"
                f"  Got: {table.schema.remove_metadata()}"
            )

        return table

    # --- Task 4: Arrow IPC writer ---

    def _write_arrow_ipc(self, table: pa.Table, output_path: Path) -> Path:
        """Write Arrow IPC file using shared crash-safe utility.

        Uses IPC file format (not stream) for mmap compatibility.
        """
        safe_write_arrow_ipc(table, output_path)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        self._logger.info(
            "Arrow IPC written: %s (%.2f MB, %d rows)",
            output_path, size_mb, table.num_rows,
            extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
        )
        return output_path

    # --- Task 4: Arrow IPC verification ---

    def _verify_arrow_ipc(
        self, path: Path, expected_schema: pa.Schema, expected_rows: Optional[int] = None
    ) -> bool:
        """Verify written Arrow IPC file is mmap-friendly and schema-correct.

        Re-reads via memory_map to prove Rust can mmap it.
        """
        mmap = pa.memory_map(str(path), "r")
        reader = pa.ipc.open_file(mmap)

        actual_schema = reader.schema.remove_metadata()
        if actual_schema != expected_schema:
            raise SchemaValidationError(
                f"Arrow IPC verification failed — schema mismatch.\n"
                f"  Expected: {expected_schema}\n"
                f"  Got: {actual_schema}"
            )

        total_rows = sum(
            reader.get_batch(i).num_rows for i in range(reader.num_record_batches)
        )
        if expected_rows is not None and total_rows != expected_rows:
            raise ValueError(
                f"Arrow IPC row count mismatch: expected {expected_rows}, got {total_rows}"
            )

        mmap.close()

        self._logger.info(
            "Arrow IPC verified: mmap OK, schema OK, %d rows", total_rows,
            extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
        )
        return True

    # --- Task 8: Data hash computation ---

    @staticmethod
    def _compute_data_hash(table: pa.Table) -> str:
        """Compute SHA-256 hash of Arrow Table data for reproducibility (FR8)."""
        hasher = hashlib.sha256()
        # Hash each record batch serialized
        sink = pa.BufferOutputStream()
        writer = pa.ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()
        buf = sink.getvalue()
        hasher.update(buf)
        return f"sha256:{hasher.hexdigest()}"

    @staticmethod
    def _compute_session_schedule_hash(session_schedule: dict) -> str:
        """Hash the session schedule config for change detection."""
        canonical = json.dumps(session_schedule, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"sha256:{h}"

    # --- Task 6: Conversion manifest ---

    def _write_conversion_manifest(
        self,
        dataset_id: str,
        version: str,
        pair: str,
        resolution: str,
        start_date: date,
        end_date: date,
        row_count: int,
        arrow_path: Path,
        parquet_path: Path,
        quality_score: float,
        rating: str,
        data_hash: str,
        config_hash: str,
        session_schedule_hash: str,
        quarantined_count: int,
        session_distribution: dict,
    ) -> Path:
        """Write conversion manifest with crash-safe pattern."""
        manifest_dir = arrow_path.parent
        manifest_path = manifest_dir / "manifest.json"

        # Compute relative parquet path from arrow dir
        try:
            rel_parquet = os.path.relpath(parquet_path, manifest_dir)
        except ValueError:
            rel_parquet = str(parquet_path)

        manifest = {
            "dataset_id": dataset_id,
            "version": version,
            "pair": pair,
            "resolution": resolution,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "row_count": row_count,
            "arrow_ipc": {
                "path": arrow_path.name,
                "size_bytes": arrow_path.stat().st_size,
                "schema_contract": "contracts/arrow_schemas.toml#market_data",
                "mmap_verified": True,
            },
            "parquet": {
                "path": rel_parquet.replace("\\", "/"),
                "size_bytes": parquet_path.stat().st_size,
                "compression": self._parquet_compression,
            },
            "quality_score": quality_score,
            "quality_rating": rating,
            "data_hash": data_hash,
            "config_hash": config_hash,
            "session_schedule_hash": session_schedule_hash,
            "conversion_timestamp": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z"),
            "quarantined_bar_count": quarantined_count,
            "session_distribution": session_distribution,
        }

        crash_safe_write(manifest_path, json.dumps(manifest, indent=2))

        self._logger.info(
            "Conversion manifest written: %s", manifest_path,
            extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
        )
        return manifest_path

    # --- Task 6: Full conversion pipeline ---

    def convert(
        self,
        validated_df: pd.DataFrame,
        pair: str,
        resolution: str,
        start_date: date,
        end_date: date,
        dataset_id: str,
        version: str,
        quality_score: float,
        rating: str,
    ) -> ConversionResult:
        """Full conversion pipeline: DataFrame -> Arrow IPC + Parquet + manifest.

        Steps:
        1. Load schema from contracts/arrow_schemas.toml
        2. Ensure session column
        3. Ensure quarantined column
        4. Convert timestamps to epoch microseconds
        5. Build Arrow Table with contract schema
        6. Validate schema match
        7. Write Arrow IPC
        8. Write Parquet (via ParquetArchiver)
        9. Verify both files
        10. Write conversion manifest
        """
        from data_pipeline.parquet_archiver import ParquetArchiver

        self._logger.info(
            "Starting conversion: %s %s (%s → %s)",
            pair, resolution, start_date, end_date,
            extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
        )

        # 1. Load schema
        schema = load_arrow_schema(self._contracts_path, "market_data")

        # 2. Ensure session column
        validated_df = self._ensure_session_column(validated_df)

        # 3. Ensure quarantined column
        validated_df = self._ensure_quarantined_column(validated_df)

        # 4-6. Build Arrow Table (handles timestamp conversion + schema enforcement)
        table = self._prepare_arrow_table(validated_df, schema)

        # 7. Write Arrow IPC
        arrow_dir = self._arrow_base / dataset_id / version
        arrow_path = arrow_dir / "market-data.arrow"
        self._write_arrow_ipc(table, arrow_path)

        # 8. Write Parquet
        archiver = ParquetArchiver(self._config, self._logger)
        parquet_dir = self._parquet_base / dataset_id / version
        parquet_path = parquet_dir / "market-data.parquet"
        archiver.write_parquet(table, parquet_path, self._parquet_compression)

        # 9. Verify both files
        self._verify_arrow_ipc(arrow_path, schema, expected_rows=table.num_rows)
        archiver.verify_parquet(parquet_path, schema, table.num_rows)

        # 10. Write manifest
        quarantined_count = int(
            table.column("quarantined").to_pandas().sum()
        )
        session_col = table.column("session").to_pandas()
        session_distribution = session_col.value_counts().to_dict()

        data_hash = self._compute_data_hash(table)
        config_hash = f"sha256:{compute_config_hash(self._config)}"
        session_hash = self._compute_session_schedule_hash(self._session_schedule)

        manifest_path = self._write_conversion_manifest(
            dataset_id=dataset_id,
            version=version,
            pair=pair,
            resolution=resolution,
            start_date=start_date,
            end_date=end_date,
            row_count=table.num_rows,
            arrow_path=arrow_path,
            parquet_path=parquet_path,
            quality_score=quality_score,
            rating=rating,
            data_hash=data_hash,
            config_hash=config_hash,
            session_schedule_hash=session_hash,
            quarantined_count=quarantined_count,
            session_distribution=session_distribution,
        )

        arrow_size = arrow_path.stat().st_size / (1024 * 1024)
        parquet_size = parquet_path.stat().st_size / (1024 * 1024)

        self._logger.info(
            "Conversion complete: %s %s → Arrow IPC (%.2fMB) + Parquet (%.2fMB)",
            pair, resolution, arrow_size, parquet_size,
            extra={"ctx": {"component": "arrow_converter", "stage": "data_pipeline"}},
        )

        return ConversionResult(
            arrow_path=arrow_path,
            parquet_path=parquet_path,
            manifest_path=manifest_path,
            row_count=table.num_rows,
            arrow_size_mb=round(arrow_size, 2),
            parquet_size_mb=round(parquet_size, 2),
        )
