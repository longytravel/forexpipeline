"""Dukascopy data downloader (Story 1.4).

Downloads M1 bars or tick data from Dukascopy with incremental updates,
crash-safe writes, and versioned artifact storage.

Adapted from ClaudeBackTester's downloader.py — yearly chunking pattern,
bid+ask download, atomic writes. See Story 1.1 baseline mapping.
"""
import csv
import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import dukascopy_python as dk
import pandas as pd

from artifacts.storage import crash_safe_write, crash_safe_write_bytes


class DukascopyDownloader:
    """Downloads historical data from Dukascopy at M1 or tick resolution.

    Supports:
    - Bid+ask M1 bar download with separate bid/ask columns
    - Tick-level data download
    - Yearly chunking with resume support
    - Incremental updates (only download missing periods)
    - Crash-safe writes (.partial -> fsync -> os.replace)
    - Versioned artifact storage (never overwrites)
    - Graceful degradation on Dukascopy unavailability
    """

    def __init__(self, config: dict, logger: logging.Logger) -> None:
        pipeline_cfg = config["data_pipeline"]
        self._storage_path = Path(pipeline_cfg["storage_path"])
        self._default_resolution = pipeline_cfg["default_resolution"]
        self._delay = pipeline_cfg["request_delay_seconds"]
        self._max_retries = pipeline_cfg["max_retries"]

        dl_cfg = pipeline_cfg["download"]
        self._pairs = dl_cfg["pairs"]
        self._start_date = date.fromisoformat(dl_cfg["start_date"])
        self._end_date = date.fromisoformat(dl_cfg["end_date"])
        self._resolution = dl_cfg["resolution"]

        self._logger = logger
        self.failed_periods: list[str] = []

    # ------------------------------------------------------------------
    # Pair format conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dukascopy_format(pair: str) -> str:
        """Convert config pair format to Dukascopy API format.

        EURUSD -> EUR/USD, XAUUSD -> XAU/USD.
        If already contains '/', return as-is.
        """
        if "/" in pair:
            return pair
        # Standard forex pairs: 6 chars = XXX/YYY
        # Gold/silver: XAUUSD, XAGUSD — 3-char base
        if len(pair) == 6:
            return f"{pair[:3]}/{pair[3:]}"
        return pair

    @staticmethod
    def _to_filesystem_format(pair: str) -> str:
        """Convert pair to filesystem-safe format: EUR/USD -> EURUSD."""
        return pair.replace("/", "")

    # ------------------------------------------------------------------
    # Task 2: Download methods
    # ------------------------------------------------------------------

    def _download_year(
        self, pair: str, year: int, offer_side: str
    ) -> Optional[pd.DataFrame]:
        """Download one year of M1 data for a single offer side.

        Uses dukascopy_python.fetch() with INTERVAL_MIN_1.
        Handles date range clamping (no future dates).
        Pair is auto-converted to Dukascopy format (EURUSD -> EUR/USD).
        """
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if start > now:
            return None
        if end > now:
            end = now

        dk_pair = self._to_dukascopy_format(pair)

        self._logger.info(
            "Downloading %s side for %s year %d",
            offer_side, pair, year,
            extra={"ctx": {
                "pair": pair, "year": year, "offer_side": offer_side,
            }},
        )

        try:
            df = dk.fetch(
                instrument=dk_pair,
                interval=dk.INTERVAL_MIN_1,
                offer_side=offer_side,
                start=start,
                end=end,
                max_retries=self._max_retries,
            )
        except Exception as e:
            self._logger.warning(
                "Download failed for %s %s %d: %s",
                pair, offer_side, year, str(e),
                extra={"ctx": {
                    "pair": pair, "year": year, "offer_side": offer_side,
                    "error": str(e), "error_code": "EXTERNAL_DUKASCOPY_TIMEOUT",
                }},
            )
            return None

        if df is None or df.empty:
            return None

        # dukascopy-python returns timestamp as index — reset to column
        if df.index.name == "timestamp":
            df = df.reset_index()

        return df

    def _download_year_bidask(
        self, pair: str, year: int
    ) -> Optional[pd.DataFrame]:
        """Download both bid and ask sides for a year, combine into single DataFrame.

        Result columns: timestamp, open, high, low, close, volume (bid side),
        bid (bid close), ask (ask close).
        """
        bid_df = self._download_year(pair, year, dk.OFFER_SIDE_BID)

        if bid_df is None or bid_df.empty:
            self._logger.warning(
                "No bid data for %s year %d", pair, year,
                extra={"ctx": {"pair": pair, "year": year}},
            )
            return None

        # Delay between bid/ask requests to avoid rate limiting
        time.sleep(self._delay)

        ask_df = self._download_year(pair, year, dk.OFFER_SIDE_ASK)

        # Build result from bid side — _download_year already reset index
        result = bid_df.copy()

        # Add bid/ask close columns
        result["bid"] = result["close"].copy()

        if ask_df is not None and not ask_df.empty:
            # Align ask data by timestamp
            ask_merged = pd.merge(
                result[["timestamp"]],
                ask_df[["timestamp", "close"]].rename(columns={"close": "ask"}),
                on="timestamp",
                how="left",
            )
            result["ask"] = ask_merged["ask"]

            # Warn on partial alignment (>1% NaN ask values)
            nan_count = result["ask"].isna().sum()
            if nan_count > 0:
                mismatch_pct = nan_count / len(result) * 100
                if mismatch_pct > 1.0:
                    self._logger.warning(
                        "Bid/ask alignment mismatch for %s year %d: %d/%d (%.1f%%) ask values are NaN",
                        pair, year, nan_count, len(result), mismatch_pct,
                        extra={"ctx": {
                            "pair": pair, "year": year,
                            "nan_count": int(nan_count),
                            "total_rows": len(result),
                            "mismatch_pct": round(mismatch_pct, 1),
                        }},
                    )
        else:
            self._logger.warning(
                "No ask data for %s year %d — ask column will be NaN",
                pair, year,
                extra={"ctx": {"pair": pair, "year": year}},
            )
            result["ask"] = float("nan")

        self._logger.info(
            "Downloaded %s year %d: %d rows",
            pair, year, len(result),
            extra={"ctx": {"pair": pair, "year": year, "rows": len(result)}},
        )

        return result

    def _download_tick_data(
        self, pair: str, start: datetime, end: datetime
    ) -> Optional[pd.DataFrame]:
        """Download tick-level data using INTERVAL_TICK.

        Returns DataFrame with columns: timestamp, bid, ask, bid_volume, ask_volume.
        dukascopy-python returns bidPrice/askPrice/bidVolume/askVolume — normalized here.
        """
        dk_pair = self._to_dukascopy_format(pair)

        self._logger.info(
            "Downloading tick data for %s: %s to %s",
            pair, start.isoformat(), end.isoformat(),
            extra={"ctx": {"pair": pair, "start": start.isoformat(), "end": end.isoformat()}},
        )

        try:
            df = dk.fetch(
                instrument=dk_pair,
                interval=dk.INTERVAL_TICK,
                offer_side=dk.OFFER_SIDE_BID,
                start=start,
                end=end,
                max_retries=self._max_retries,
            )
        except Exception as e:
            self._logger.warning(
                "Tick download failed for %s: %s",
                pair, str(e),
                extra={"ctx": {
                    "pair": pair, "error": str(e),
                    "error_code": "EXTERNAL_DUKASCOPY_TIMEOUT",
                }},
            )
            return None

        if df is None or df.empty:
            return None

        # Reset timestamp from index to column
        if df.index.name == "timestamp":
            df = df.reset_index()

        # Normalize column names: bidPrice->bid, askPrice->ask, bidVolume->bid_volume, askVolume->ask_volume
        rename_map = {
            "bidPrice": "bid",
            "askPrice": "ask",
            "bidVolume": "bid_volume",
            "askVolume": "ask_volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        return df

    def download(
        self,
        pair: str,
        start_date: date,
        end_date: date,
        resolution: str,
    ) -> pd.DataFrame:
        """Main download method. Iterates years for M1, direct call for tick.

        Returns consolidated DataFrame. Logs progress with ETA.
        """
        if resolution == "tick":
            start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
            end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
            df = self._download_tick_data(pair, start_dt, end_dt)
            return df if df is not None else pd.DataFrame()

        # M1 mode: iterate over years
        start_year = start_date.year
        end_year = min(end_date.year, datetime.now(timezone.utc).year)
        years = list(range(start_year, end_year + 1))

        # Check which years already downloaded (resume support)
        existing = set(self._get_downloaded_years(pair, self._storage_path))
        current_year = datetime.now(timezone.utc).year

        years_to_download = [
            y for y in years
            if y not in existing or y == current_year
        ]

        self._logger.info(
            "Download plan for %s: %d years total, %d to download, %d cached",
            pair, len(years), len(years_to_download),
            len(years) - len(years_to_download),
            extra={"ctx": {
                "pair": pair,
                "years_total": len(years),
                "years_to_download": len(years_to_download),
                "years_cached": len(years) - len(years_to_download),
            }},
        )

        self.failed_periods = []
        t0 = time.time()

        for i, year in enumerate(years_to_download):
            elapsed = time.time() - t0
            if i > 0:
                eta = (elapsed / i) * (len(years_to_download) - i)
            else:
                eta = 0

            pct = ((i + 1) / len(years_to_download)) * 100

            self._logger.info(
                "Progress %s: %d/%d (%.0f%%) — ETA %.0fs",
                pair, i + 1, len(years_to_download), pct, eta,
                extra={"ctx": {
                    "pair": pair, "year": year,
                    "step": f"{i + 1}/{len(years_to_download)}",
                    "pct": round(pct, 1), "eta_seconds": round(eta),
                }},
            )

            df = self._download_year_bidask(pair, year)
            if df is not None and not df.empty:
                self._save_chunk(df, pair, year, self._storage_path)
            else:
                self.failed_periods.append(str(year))
                self._logger.warning(
                    "Failed to download %s year %d — continuing",
                    pair, year,
                    extra={"ctx": {
                        "pair": pair, "year": year,
                        "error_code": "EXTERNAL_DUKASCOPY_TIMEOUT",
                    }},
                )

        # Consolidate all chunks
        consolidated = self._consolidate_chunks(pair, self._storage_path)

        if self.failed_periods:
            self._logger.warning(
                "Download completed with %d failed periods: %s",
                len(self.failed_periods), ", ".join(self.failed_periods),
                extra={"ctx": {
                    "pair": pair, "failed_periods": self.failed_periods,
                }},
            )

        return consolidated

    # ------------------------------------------------------------------
    # Task 2: Chunk save and consolidation
    # ------------------------------------------------------------------

    def _chunk_dir(self, pair: str, storage_path: Path) -> Path:
        """Get the yearly chunks directory for a pair."""
        safe_pair = self._to_filesystem_format(pair)
        return storage_path / f"{safe_pair}_M1_chunks"

    def _save_chunk(
        self, df: pd.DataFrame, pair: str, year: int, storage_path: Path
    ) -> Path:
        """Save a yearly chunk as Parquet using crash-safe write.

        Pattern: write to .partial -> fsync -> os.replace().
        """
        chunk_d = self._chunk_dir(pair, storage_path)
        chunk_d.mkdir(parents=True, exist_ok=True)

        safe_pair = self._to_filesystem_format(pair)
        target = chunk_d / f"{safe_pair}_M1_{year}.parquet"
        partial = target.with_name(target.name + ".partial")

        # Write to .partial first
        df.to_parquet(str(partial), engine="pyarrow", compression="snappy")

        # fsync the partial file (open r+b for Windows compatibility)
        with open(partial, "r+b") as f:
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename
        os.replace(str(partial), str(target))

        self._logger.info(
            "Saved chunk %s year %d: %d rows",
            pair, year, len(df),
            extra={"ctx": {"pair": pair, "year": year, "rows": len(df), "path": str(target)}},
        )
        return target

    def _consolidate_chunks(
        self, pair: str, storage_path: Path
    ) -> pd.DataFrame:
        """Merge all yearly chunks into a single sorted, deduplicated DataFrame."""
        chunk_d = self._chunk_dir(pair, storage_path)
        if not chunk_d.exists():
            return pd.DataFrame()

        chunks = sorted(chunk_d.glob("*.parquet"))
        if not chunks:
            return pd.DataFrame()

        dfs = []
        for c in chunks:
            try:
                dfs.append(pd.read_parquet(c))
            except Exception as e:
                self._logger.warning(
                    "Corrupt chunk skipped: %s — %s", str(c), str(e),
                    extra={"ctx": {"path": str(c), "error": str(e)}},
                )
                continue

        if not dfs:
            return pd.DataFrame()

        df = pd.concat(dfs, ignore_index=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.drop_duplicates(subset=["timestamp"], keep="first")

        self._logger.info(
            "Consolidated %s: %d rows from %d chunks",
            pair, len(df), len(chunks),
            extra={"ctx": {"pair": pair, "rows": len(df), "chunks": len(chunks)}},
        )
        return df

    def _get_downloaded_years(self, pair: str, storage_path: Path) -> list[int]:
        """Return list of years already downloaded for a pair."""
        chunk_d = self._chunk_dir(pair, storage_path)
        if not chunk_d.exists():
            return []

        years = []
        for f in chunk_d.glob("*.parquet"):
            try:
                year = int(f.stem.split("_")[-1])
                years.append(year)
            except ValueError:
                continue
        return sorted(years)

    # ------------------------------------------------------------------
    # Task 4: Versioned artifact storage
    # ------------------------------------------------------------------

    def generate_dataset_id(
        self, pair: str, start_date: date, end_date: date, resolution: str
    ) -> str:
        """Generate dataset identifier: {pair}_{start}_{end}_{resolution}."""
        safe_pair = self._to_filesystem_format(pair)
        return f"{safe_pair}_{start_date.isoformat()}_{end_date.isoformat()}_{resolution}"

    def compute_data_hash(self, df: pd.DataFrame) -> str:
        """Compute SHA-256 hash of DataFrame content for reproducibility.

        For large DataFrames, hashes in chunks to avoid memory pressure.
        """
        # Sort and deduplicate before hashing
        if "timestamp" in df.columns:
            sorted_df = df.sort_values("timestamp").reset_index(drop=True)
        else:
            sorted_df = df

        # Convert all columns to stable string representations to avoid
        # Windows access violation in pandas _format_native_types during to_csv.
        # Bypass pandas CSV formatting entirely — use numpy bytes for hashing.
        hash_df = sorted_df.copy()
        for col in hash_df.columns:
            if pd.api.types.is_datetime64_any_dtype(hash_df[col]):
                hash_df[col] = hash_df[col].astype("int64")
            elif hasattr(hash_df[col], "dt"):
                # Catch timezone-aware datetimes that is_datetime64_any_dtype misses
                hash_df[col] = hash_df[col].astype("int64")

        hasher = hashlib.sha256()
        # Hash column names
        header = ",".join(hash_df.columns) + "\n"
        hasher.update(header.encode("utf-8"))
        # Hash raw numpy bytes in chunks — avoids pandas to_csv entirely
        chunk_size = 10_000
        for start in range(0, len(hash_df), chunk_size):
            chunk = hash_df.iloc[start:start + chunk_size]
            hasher.update(chunk.values.tobytes())
        return hasher.hexdigest()

    def save_raw_artifact(
        self,
        df: pd.DataFrame,
        pair: str,
        start_date: date,
        end_date: date,
        resolution: str,
        storage_path: Path,
    ) -> Path:
        """Save raw data as versioned CSV artifact. Never overwrites existing versions.

        Path: {storage_path}/raw/{dataset_id}/v{NNN}/{dataset_id}.csv
        """
        dataset_id = self.generate_dataset_id(pair, start_date, end_date, resolution)
        raw_dir = storage_path / "raw" / dataset_id

        # Find next version number
        version = 1
        if raw_dir.exists():
            existing_versions = sorted(
                [d for d in raw_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
                key=lambda d: int(d.name[1:]) if d.name[1:].isdigit() else 0,
            )
            if existing_versions:
                last_version = int(existing_versions[-1].name[1:])
                version = last_version + 1

        version_str = f"v{version:03d}"
        version_dir = raw_dir / version_str
        version_dir.mkdir(parents=True, exist_ok=True)

        target = version_dir / f"{dataset_id}.csv"
        partial = target.with_name(target.name + ".partial")

        # Bypass pandas C extension entirely to avoid Windows access violation
        # (segfault in block manager / get_values_for_csv on large mixed-dtype DFs).
        # Extract column-by-column via Series.tolist() then zip into rows.
        # Also convert pandas Timestamps to ISO strings — csv.writer's C internals
        # crash on Timestamp.__format__ with "More keyword list entries" SystemError.
        def _sanitize_list(values: list) -> list:
            """Convert pandas Timestamps to ISO strings for csv.writer compat."""
            if values and isinstance(values[0], pd.Timestamp):
                return [v.isoformat() if pd.notna(v) else "" for v in values]
            return values

        cols = df.columns.tolist()
        with open(str(partial), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            chunk_size = 10_000
            for start in range(0, len(df), chunk_size):
                chunk = df.iloc[start:start + chunk_size]
                col_lists = [_sanitize_list(chunk[c].tolist()) for c in cols]
                writer.writerows(zip(*col_lists))
        with open(partial, "r+b") as f:
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(partial), str(target))

        self._logger.info(
            "Saved raw artifact %s %s: %d rows",
            dataset_id, version_str, len(df),
            extra={"ctx": {
                "dataset_id": dataset_id, "version": version_str,
                "rows": len(df), "path": str(target),
            }},
        )

        return target

    def write_download_manifest(
        self,
        dataset_id: str,
        version: str,
        data_hash: str,
        pair: str,
        start_date: date,
        end_date: date,
        resolution: str,
        row_count: int,
        failed_periods: list[str],
        storage_path: Path,
        config_hash: str = "",
    ) -> Path:
        """Write manifest.json alongside the data file."""
        manifest = {
            "dataset_id": dataset_id,
            "version": version,
            "data_hash": data_hash,
            "pair": pair,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "resolution": resolution,
            "row_count": row_count,
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            "failed_periods": failed_periods,
            "config_hash": config_hash,
        }

        manifest_path = storage_path / "raw" / dataset_id / version / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        crash_safe_write(manifest_path, json.dumps(manifest, indent=2))

        self._logger.info(
            "Wrote manifest for %s %s", dataset_id, version,
            extra={"ctx": {"dataset_id": dataset_id, "version": version}},
        )

        return manifest_path
