"""Signal cache for joint entry+exit optimization.

Caches enriched Arrow IPC files keyed by entry-param hash + data hash.
When the optimizer proposes candidates with different entry params,
the cache avoids redundant signal precomputation.

Atomic writes (tmp+rename) prevent corrupt cache entries on failure.
LRU eviction keeps disk usage bounded.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow.ipc as ipc

from logging_setup.setup import get_logger
from optimization.param_classifier import build_override_spec, ParamClassification
from orchestrator.signal_precompute import precompute_signals_from_spec

logger = get_logger("optimization.signal_cache")


@dataclass
class CacheStats:
    """Accumulated cache statistics."""
    hits: int = 0
    misses: int = 0
    errors: int = 0
    total_precompute_s: float = 0.0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class SignalCacheManager:
    """Disk-backed cache of enriched Arrow files keyed by signal param hash.

    Each unique set of signal-affecting parameters (e.g., swing_bars=5,
    atr_period=20) produces a different enriched Arrow file. This cache
    stores and reuses those files across generations.

    Cache key = SHA256(data_hash + sorted signal params JSON)[:16].
    The data_hash ensures invalidation when market data changes.
    """

    def __init__(
        self,
        cache_dir: Path,
        strategy_spec: dict,
        market_data_path: Path,
        data_hash: str,
        classification: ParamClassification,
        session_schedule: dict | None = None,
        max_entries: int = 256,
        max_cache_bytes: int = 80_000_000_000,
        parallelism: int = 4,
        log_stats_interval: int = 10,
        year_range: tuple[int, int] | None = None,
        output_resolution: str = "M1",
    ):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._strategy_spec = strategy_spec
        self._market_data_path = Path(market_data_path)
        self._data_hash = data_hash
        self._classification = classification
        self._session_schedule = session_schedule
        self._max_entries = max_entries
        self._max_cache_bytes = max_cache_bytes
        self._parallelism = parallelism
        self._log_stats_interval = log_stats_interval
        self._year_range = year_range
        self._output_resolution = output_resolution

        # In-memory index: signal_hash -> Path
        self._index: dict[str, Path] = {}
        # LRU tracking: signal_hash -> last access time
        self._access_times: dict[str, float] = {}
        self._stats = CacheStats()

        # Rebuild index from existing cache files on disk
        self._rebuild_index()

    def get_or_compute(self, signal_params: dict[str, Any]) -> Path:
        """Get cached enriched Arrow or compute and cache it.

        Args:
            signal_params: Signal-affecting param values
                (e.g., {"swing_bars": 5, "atr_period": 20}).

        Returns:
            Path to enriched Arrow IPC file.

        Raises:
            Exception from precompute_signals_from_spec on failure.
        """
        cache_key = self.compute_cache_key(signal_params)

        # Check cache
        if cache_key in self._index:
            cached_path = self._index[cache_key]
            if cached_path.exists() and self._validate_arrow(cached_path):
                self._access_times[cache_key] = time.monotonic()
                self._stats.hits += 1
                return cached_path
            else:
                # Corrupt or missing — remove from index
                del self._index[cache_key]
                if cache_key in self._access_times:
                    del self._access_times[cache_key]

        # Cache miss — compute
        self._stats.misses += 1
        path = self._compute_and_store(signal_params, cache_key)
        return path

    def get_or_compute_batch(
        self, signal_param_sets: list[dict[str, Any]]
    ) -> dict[str, Path]:
        """Batch version: compute all unique signal param sets, return hash->path.

        Deduplicates across the batch and computes missing entries in parallel.

        Args:
            signal_param_sets: List of signal param dicts.

        Returns:
            dict mapping signal_hash -> enriched Arrow path.
        """
        # Deduplicate
        unique: dict[str, dict[str, Any]] = {}
        for params in signal_param_sets:
            key = self.compute_cache_key(params)
            if key not in unique:
                unique[key] = params

        result: dict[str, Path] = {}
        to_compute: dict[str, dict[str, Any]] = {}

        # Check cache for each unique set
        for key, params in unique.items():
            if key in self._index:
                cached_path = self._index[key]
                if cached_path.exists() and self._validate_arrow(cached_path):
                    self._access_times[key] = time.monotonic()
                    self._stats.hits += 1
                    result[key] = cached_path
                    continue
                else:
                    del self._index[key]
                    if key in self._access_times:
                        del self._access_times[key]

            self._stats.misses += 1
            to_compute[key] = params

        if not to_compute:
            return result

        # Compute missing entries in parallel
        n_workers = min(self._parallelism, len(to_compute))
        if n_workers <= 1:
            # Sequential for single item
            for key, params in to_compute.items():
                path = self._compute_and_store(params, key)
                result[key] = path
        else:
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                futures = {
                    pool.submit(self._compute_and_store, params, key): key
                    for key, params in to_compute.items()
                }
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        path = future.result()
                        result[key] = path
                    except Exception:
                        self._stats.errors += 1
                        raise  # Propagate — orchestrator handles generation failure

        return result

    def cache_stats(self) -> dict:
        """Return cache statistics for structured logging."""
        return {
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "errors": self._stats.errors,
            "hit_rate": round(self._stats.hit_rate, 3),
            "cached_entries": len(self._index),
            "total_precompute_s": round(self._stats.total_precompute_s, 2),
        }

    def compute_cache_key(self, signal_params: dict[str, Any]) -> str:
        """Deterministic cache key for a signal param set.

        Includes data_hash, year_range, and output_resolution to prevent
        cache collisions between filtered/unfiltered and M1/H1 variants.
        """
        canonical = json.dumps(signal_params, sort_keys=True, default=str)
        yr_tag = f":{self._year_range[0]}-{self._year_range[1]}" if self._year_range else ""
        res_tag = f":{self._output_resolution}" if self._output_resolution != "M1" else ""
        payload = f"{self._data_hash}:{canonical}{yr_tag}{res_tag}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _compute_and_store(
        self, signal_params: dict[str, Any], cache_key: str
    ) -> Path:
        """Compute enriched data and store in cache with atomic write."""
        start = time.monotonic()

        # Build override spec with these signal params
        override_spec = build_override_spec(
            base_spec=self._strategy_spec,
            signal_params=signal_params,
            spec_override_params={},  # Signal cache only varies signal params
            classification=self._classification,
        )

        # Compute to tmp path, then atomic rename
        final_path = self._cache_dir / f"{cache_key}.arrow"
        tmp_path = self._cache_dir / f"{cache_key}.arrow.tmp"

        try:
            precompute_signals_from_spec(
                strategy_spec=override_spec,
                market_data_path=self._market_data_path,
                output_path=tmp_path,
                session_schedule=self._session_schedule,
                year_range=self._year_range,
                output_resolution=self._output_resolution,
            )

            # Atomic rename
            os.replace(str(tmp_path), str(final_path))

            # Update index
            self._index[cache_key] = final_path
            self._access_times[cache_key] = time.monotonic()

            elapsed = time.monotonic() - start
            self._stats.total_precompute_s += elapsed

            logger.info(
                f"Signal cache: computed {cache_key} in {elapsed:.1f}s",
                extra={
                    "component": "optimization.signal_cache",
                    "ctx": {"signal_params": signal_params, "elapsed_s": elapsed},
                },
            )

            # Evict if needed
            self._evict_if_needed()

            return final_path

        except Exception:
            # Clean up tmp file on failure
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            self._stats.errors += 1
            raise

    def _validate_arrow(self, path: Path) -> bool:
        """Validate that a cached file is a readable Arrow IPC file."""
        try:
            reader = ipc.open_file(str(path))
            _ = reader.schema
            return True
        except Exception:
            return False

    def _evict_if_needed(self) -> None:
        """LRU eviction if cache exceeds limits."""
        # Entry count eviction
        while len(self._index) > self._max_entries:
            self._evict_oldest()

        # Byte-based eviction
        total_bytes = sum(
            p.stat().st_size for p in self._index.values() if p.exists()
        )
        while total_bytes > self._max_cache_bytes and len(self._index) > 1:
            evicted_path = self._evict_oldest()
            if evicted_path and evicted_path.exists():
                total_bytes -= evicted_path.stat().st_size

    def _evict_oldest(self) -> Path | None:
        """Remove the least recently used cache entry."""
        if not self._access_times:
            return None

        oldest_key = min(self._access_times, key=self._access_times.get)
        path = self._index.pop(oldest_key, None)
        self._access_times.pop(oldest_key, None)

        if path and path.exists():
            try:
                path.unlink()
                logger.info(
                    f"Signal cache: evicted {oldest_key}",
                    extra={"component": "optimization.signal_cache"},
                )
            except OSError:
                pass

        return path

    def _rebuild_index(self) -> None:
        """Rebuild in-memory index from existing cache files on disk."""
        if not self._cache_dir.exists():
            return

        # Use monotonic base so rebuilt entries are comparable with new ones
        # (st_mtime is epoch time, but _compute_and_store uses time.monotonic())
        base_time = time.monotonic()

        for arrow_file in self._cache_dir.glob("*.arrow"):
            # Skip tmp files
            if arrow_file.name.endswith(".arrow.tmp"):
                continue
            cache_key = arrow_file.stem  # filename without .arrow
            if len(cache_key) == 16 and self._validate_arrow(arrow_file):
                self._index[cache_key] = arrow_file
                self._access_times[cache_key] = base_time

        if self._index:
            logger.info(
                f"Signal cache: rebuilt index with {len(self._index)} entries",
                extra={"component": "optimization.signal_cache"},
            )
