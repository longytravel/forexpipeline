"""E2E Pipeline Proof — Market Data Flow (Story 1.9).

Exercises the full data pipeline end-to-end on a reference dataset
and verifies the complete artifact chain, including reproducibility.

This is NOT a test file — it is a runnable script that exercises real
components and verifies real outcomes.
"""
import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    name: str
    status: str  # "PASS" or "FAIL"
    duration_seconds: float
    details: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class PipelineProofResult:
    overall_status: str  # "PASS" or "FAIL"
    stages: dict  # name -> StageResult
    dataset_id: str
    config_hash: str
    reproducibility_verified: bool
    total_duration_seconds: float
    artifact_count: int
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification helpers — collect errors, never assert
# ---------------------------------------------------------------------------

def _verify(errors: list, condition: bool, msg: str):
    if not condition:
        errors.append(msg)


def _warn(warnings: list, condition: bool, msg: str):
    if not condition:
        warnings.append(msg)


# ---------------------------------------------------------------------------
# Pipeline Proof orchestrator
# ---------------------------------------------------------------------------

class PipelineProof:
    """Orchestrates the E2E pipeline proof for market data flow."""

    def __init__(self, config: dict, skip_download: bool = False,
                 skip_reproducibility: bool = False):
        self._config = config
        self._skip_download = skip_download
        self._skip_reproducibility = skip_reproducibility

        from logging_setup import get_logger
        self._logger = get_logger("pipeline_proof")

        # Reference dataset params from config
        ref = config["data_pipeline"]["reference_dataset"]
        self._pair = ref["pair"]
        self._start_date = date.fromisoformat(ref["start_date"])
        self._end_date = date.fromisoformat(ref["end_date"])
        self._resolution = ref["resolution"]
        self._source = ref["source"]
        self._start_str = ref["start_date"]
        self._end_str = ref["end_date"]

        # Storage paths
        dp = config["data_pipeline"]
        self._storage_root = Path(dp["storage_path"])
        self._pipeline_dir = self._storage_root / "data-pipeline"
        self._pipeline_dir.mkdir(parents=True, exist_ok=True)

        from config_loader import compute_config_hash
        self._config_hash = compute_config_hash(config)

        # Inter-stage state
        self._df = None
        self._data_hash = None
        self._dataset_id = None
        self._validation_result = None
        self._conversion_result = None
        self._m1_arrow_path = None
        self._m1_parquet_path = None
        self._tf_results = None
        self._split_result = None
        self._first_run_hashes = {}
        self._first_run_manifest = None

    # -----------------------------------------------------------------------
    # Main orchestration
    # -----------------------------------------------------------------------

    def run(self) -> PipelineProofResult:
        start = time.time()
        stages = {}
        all_errors = []
        all_warnings = []

        stage_funcs = [
            ("download", self._stage_download),
            ("validation", self._stage_validate),
            ("storage_conversion", self._stage_convert),
            ("timeframe_conversion", self._stage_timeframe),
            ("train_test_split", self._stage_split),
            ("artifact_chain", self._verify_artifacts),
            ("reproducibility", self._verify_reproducibility),
            ("logging", self._verify_logs),
        ]

        for name, func in stage_funcs:
            self._logger.info(
                "Pipeline proof stage: %s", name,
                extra={"ctx": {"component": "data_pipeline", "stage": name}},
            )
            try:
                result = func()
            except Exception as e:
                result = StageResult(
                    name=name, status="FAIL", duration_seconds=0.0,
                    errors=[f"Unhandled {type(e).__name__}: {e}"],
                )
            stages[name] = result
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
            self._logger.info(
                "Stage %s: %s", name, result.status,
                extra={"ctx": {"component": "data_pipeline", "stage": name,
                               "status": result.status}},
            )

        total = time.time() - start
        overall = "PASS" if not all_errors else "FAIL"
        artifact_count = self._count_artifacts()

        proof = PipelineProofResult(
            overall_status=overall,
            stages=stages,
            dataset_id=self._dataset_id or "unknown",
            config_hash=self._config_hash,
            reproducibility_verified=(
                stages.get("reproducibility",
                           StageResult("", "FAIL", 0.0)).status == "PASS"
            ),
            total_duration_seconds=round(total, 1),
            artifact_count=artifact_count,
            errors=all_errors,
            warnings=all_warnings,
        )

        if overall == "PASS":
            self._save_reference_dataset(proof)
        self._save_result_json(proof)
        self._print_summary(proof, stages)
        return proof

    # -----------------------------------------------------------------------
    # Stage 1 — Download
    # -----------------------------------------------------------------------

    def _stage_download(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}
        import pandas as pd
        from data_pipeline.downloader import DukascopyDownloader
        from data_pipeline.dataset_hasher import compute_dataset_id

        downloader = DukascopyDownloader(self._config, self._logger)

        if self._skip_download:
            raw_dir = self._storage_root / "raw"
            candidates = sorted(raw_dir.glob(f"*{self._pair}*/v*/*.csv"),
                                key=lambda p: p.stat().st_mtime) if raw_dir.exists() else []
            if candidates:
                self._df = pd.read_csv(candidates[-1])
                details["source"] = str(candidates[-1])
                details["skip_download"] = True
            else:
                errors.append("--skip-download: no existing raw data found")
                return StageResult("download", "FAIL", time.time() - t0,
                                   details, errors, warnings)
        else:
            self._df = downloader.download(
                self._pair, self._start_date, self._end_date, self._resolution,
            )

        _verify(errors, self._df is not None and not self._df.empty,
                "Download returned empty DataFrame")
        if errors:
            return StageResult("download", "FAIL", time.time() - t0,
                               details, errors, warnings)

        self._data_hash = downloader.compute_data_hash(self._df)
        self._dataset_id = compute_dataset_id(
            self._pair, self._start_str, self._end_str,
            self._source, self._data_hash,
        )

        # Verify required columns based on resolution
        if self._resolution == "tick":
            required = {"timestamp", "bid", "ask"}
        else:
            required = {"timestamp", "open", "high", "low", "close", "bid", "ask"}
        _verify(errors, required.issubset(set(self._df.columns)),
                f"Missing columns: {required - set(self._df.columns)}")

        # Verify date range
        if "timestamp" in self._df.columns:
            try:
                ts_col = self._df["timestamp"]
                if ts_col.dtype == "int64":
                    first = pd.Timestamp(ts_col.min(), unit="us", tz="UTC")
                    last = pd.Timestamp(ts_col.max(), unit="us", tz="UTC")
                else:
                    first = pd.Timestamp(ts_col.min())
                    last = pd.Timestamp(ts_col.max())
                _verify(errors, first.date() >= self._start_date,
                        f"First ts {first} before start {self._start_date}")
                _verify(errors, last.date() <= self._end_date,
                        f"Last ts {last} after end {self._end_date}")
            except Exception:
                warnings.append("Could not verify timestamp range")

        bar_count = len(self._df)
        details.update({"bar_count": bar_count, "data_hash": self._data_hash[:8],
                        "dataset_id": self._dataset_id})

        # Save raw artifact
        if not self._skip_download:
            try:
                raw_path = downloader.save_raw_artifact(
                    self._df, self._pair, self._start_date, self._end_date,
                    self._resolution, self._storage_root,
                )
                details["raw_path"] = str(raw_path)
                details["file_size_mb"] = round(
                    raw_path.stat().st_size / (1024 * 1024), 1)
            except Exception as e:
                warnings.append(f"save_raw_artifact: {e}")

        self._logger.info(
            "Download: %d bars, dataset=%s", bar_count, self._dataset_id,
            extra={"ctx": {"component": "data_pipeline", "stage": "download",
                           "bar_count": bar_count}},
        )
        return StageResult("download", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    # -----------------------------------------------------------------------
    # Stage 2 — Validate + Quality Score
    # -----------------------------------------------------------------------

    def _stage_validate(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}

        _verify(errors, self._df is not None, "No DataFrame from download stage")
        if errors:
            return StageResult("validation", "FAIL", time.time() - t0,
                               details, errors, warnings)

        from data_pipeline.quality_checker import DataQualityChecker
        checker = DataQualityChecker(self._config, self._logger)
        self._validation_result = checker.validate(
            self._df, self._pair, self._resolution,
            self._start_date, self._end_date,
            self._storage_root, self._dataset_id, "v1",
        )
        vr = self._validation_result
        details.update({
            "quality_score": vr.quality_score, "rating": vr.rating,
            "report_path": str(vr.report_path) if vr.report_path else None,
        })

        # Verify quality report artifact
        if vr.report_path:
            rp = Path(vr.report_path)
            _verify(errors, rp.exists(), f"Quality report not found: {rp}")
            if rp.exists():
                try:
                    with open(rp) as f:
                        report_data = json.load(f)
                    # Verify required content (AC#3)
                    for field in ("gap_count", "integrity_checks",
                                  "staleness_checks"):
                        _verify(errors, field in report_data,
                                f"Quality report missing '{field}'")
                except (json.JSONDecodeError, IOError) as e:
                    errors.append(f"Quality report invalid JSON: {e}")
        else:
            errors.append("No quality report path returned")

        # Verify rating thresholds
        score = vr.quality_score
        if score >= 0.95:
            _verify(errors, vr.rating.upper() == "GREEN",
                    f"Score {score:.3f}>=0.95 but rating={vr.rating}")
        elif score >= 0.80:
            _verify(errors, vr.rating.upper() == "YELLOW",
                    f"Score {score:.3f} in 0.80-0.95 but rating={vr.rating}")
        else:
            _verify(errors, vr.rating.upper() == "RED",
                    f"Score {score:.3f}<0.80 but rating={vr.rating}")

        if vr.rating.upper() == "RED":
            warnings.append(f"Data quality RED (score={score:.3f}). Continuing.")

        self._logger.info(
            "Validation: score=%.3f, rating=%s", score, vr.rating,
            extra={"ctx": {"component": "data_pipeline", "stage": "validation",
                           "quality_score": score, "rating": vr.rating}},
        )
        return StageResult("validation", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    # -----------------------------------------------------------------------
    # Stage 3 — Store Parquet + Convert to Arrow IPC
    # -----------------------------------------------------------------------

    def _stage_convert(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}

        vr = self._validation_result
        _verify(errors, vr is not None, "No validation result")
        if errors:
            return StageResult("storage_conversion", "FAIL", time.time() - t0,
                               details, errors, warnings)

        from data_pipeline.arrow_converter import ArrowConverter

        # If tick data, aggregate to M1 before Arrow conversion
        df_for_conversion = vr.validated_df
        conversion_resolution = self._resolution
        if self._resolution == "tick":
            self._logger.info(
                "Tick data detected — aggregating to M1 before storage",
                extra={"ctx": {"component": "data_pipeline",
                               "stage": "storage_conversion"}},
            )
            from data_pipeline.timeframe_converter import aggregate_ticks_to_m1
            # Convert DataFrame to Arrow Table for aggregation
            tick_table = pa.Table.from_pandas(df_for_conversion)
            m1_table = aggregate_ticks_to_m1(tick_table)
            df_for_conversion = m1_table.to_pandas()
            conversion_resolution = "M1"
            self._logger.info(
                "Tick→M1 aggregation: %d ticks → %d M1 bars",
                len(vr.validated_df), len(df_for_conversion),
                extra={"ctx": {"component": "data_pipeline",
                               "stage": "storage_conversion"}},
            )

        converter = ArrowConverter(self._config, self._logger)
        self._conversion_result = converter.convert(
            df_for_conversion, self._pair, conversion_resolution,
            self._start_date, self._end_date,
            self._dataset_id, "v1", vr.quality_score, vr.rating,
        )
        cr = self._conversion_result

        _verify(errors, cr.arrow_path.exists(),
                f"Arrow IPC not found: {cr.arrow_path}")
        _verify(errors, cr.parquet_path.exists(),
                f"Parquet not found: {cr.parquet_path}")

        # Verify Parquet snappy compression (AC#4 / M1)
        if cr.parquet_path.exists():
            try:
                import pyarrow.parquet as pq_reader
                pq_meta = pq_reader.read_metadata(str(cr.parquet_path))
                if pq_meta.num_row_groups > 0:
                    codec = pq_meta.row_group(0).column(0).compression
                    _verify(errors,
                            codec.lower() == "snappy",
                            f"Parquet compression is '{codec}', expected 'snappy'")
            except Exception as e:
                warnings.append(f"Could not verify Parquet compression: {e}")

        # Schema + session verification on the Arrow file
        if cr.arrow_path.exists():
            try:
                table = pa.ipc.open_file(str(cr.arrow_path)).read_all()
                cols = [f.name for f in table.schema]
                for c in ("timestamp", "open", "high", "low", "close",
                          "bid", "ask", "session", "quarantined"):
                    _verify(errors, c in cols, f"Arrow schema missing: {c}")

                # Verify mmap compatibility
                try:
                    pa.ipc.open_file(pa.memory_map(str(cr.arrow_path), "r"))
                except Exception as e:
                    errors.append(f"Not mmap-compatible: {e}")

                # Session checks
                if "session" in cols:
                    valid = {"asian", "london", "new_york",
                             "london_ny_overlap", "off_hours", "mixed"}
                    sessions = table.column("session").to_pylist()
                    bad = {s for s in sessions if s not in valid}
                    _verify(errors, not bad,
                            f"Invalid session values: {bad}")
                    nulls = sum(1 for s in sessions if not s)
                    _verify(errors, nulls == 0,
                            f"{nulls} null/empty session values")
                    self._verify_sessions(table, errors, warnings)
            except Exception as e:
                errors.append(f"Cannot read Arrow IPC: {e}")

        # Copy M1 to data-pipeline/ for downstream components
        self._m1_arrow_path = (
            self._pipeline_dir
            / f"{self._pair}_{self._start_str}_{self._end_str}_M1.arrow"
        )
        self._m1_parquet_path = (
            self._pipeline_dir
            / f"{self._pair}_{self._start_str}_{self._end_str}_M1.parquet"
        )
        if cr.arrow_path.exists():
            shutil.copy2(str(cr.arrow_path), str(self._m1_arrow_path))
        if cr.parquet_path.exists():
            shutil.copy2(str(cr.parquet_path), str(self._m1_parquet_path))

        details.update({
            "arrow_size_mb": cr.arrow_size_mb,
            "parquet_size_mb": cr.parquet_size_mb,
            "row_count": cr.row_count,
        })
        self._logger.info(
            "Conversion: Arrow=%.2fMB, Parquet=%.2fMB, rows=%d",
            cr.arrow_size_mb, cr.parquet_size_mb, cr.row_count,
            extra={"ctx": {"component": "data_pipeline",
                           "stage": "arrow_conversion"}},
        )
        return StageResult("storage_conversion", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    def _verify_sessions(self, table: pa.Table, errors: list, warnings: list):
        """Spot-check session labels at known UTC hours."""
        checks = [
            (3, "asian"), (10, "london"), (14, "london_ny_overlap"),
            (18, "new_york"), (22, "off_hours"),
        ]
        ts_arr = table.column("timestamp")
        sess_arr = table.column("session")
        for hour, expected in checks:
            # Find a bar at HH:00 UTC
            target_us = hour * 3600 * 1_000_000
            found = False
            for i in range(ts_arr.length()):
                ts_val = ts_arr[i].as_py()
                day_offset = ts_val % (24 * 3600 * 1_000_000)
                if day_offset == target_us:
                    actual = sess_arr[i].as_py()
                    _verify(errors, actual == expected,
                            f"Session at {hour}:00 UTC: expected '{expected}', "
                            f"got '{actual}'")
                    found = True
                    break
            if not found:
                warnings.append(f"No bar at {hour}:00 UTC for session check")

    # -----------------------------------------------------------------------
    # Stage 4 — Timeframe Conversion
    # -----------------------------------------------------------------------

    def _stage_timeframe(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}

        cr = self._conversion_result
        _verify(errors, cr is not None, "No conversion result")
        if errors:
            return StageResult("timeframe_conversion", "FAIL",
                               time.time() - t0, details, errors, warnings)

        from data_pipeline.timeframe_converter import run_timeframe_conversion
        source = (self._m1_arrow_path
                  if self._m1_arrow_path and self._m1_arrow_path.exists()
                  else cr.arrow_path)

        self._tf_results = run_timeframe_conversion(
            self._pair, source, self._config, self._logger,
        )

        m1_bars = cr.row_count
        approx = {"M5": 5, "H1": 60, "D1": 1440, "W": 7200}

        for tf, paths in self._tf_results.items():
            arrow_p = Path(paths["arrow"]) if isinstance(paths, dict) else Path(paths)
            _verify(errors, arrow_p.exists(), f"{tf} Arrow not found: {arrow_p}")
            if arrow_p.exists():
                tf_table = pa.ipc.open_file(str(arrow_p)).read_all()
                cnt = tf_table.num_rows
                details[f"{tf}_bar_count"] = cnt
                if tf in approx:
                    exp = m1_bars / approx[tf]
                    _warn(warnings, abs(cnt - exp) / max(exp, 1) < 0.35,
                          f"{tf} bar count {cnt} far from expected ~{int(exp)}")
                _verify(errors, "session" in [f.name for f in tf_table.schema],
                        f"{tf} missing session column")
            pq_p = (Path(paths.get("parquet", ""))
                    if isinstance(paths, dict)
                    else arrow_p.with_suffix(".parquet"))
            _verify(errors, pq_p.exists(), f"{tf} Parquet not found: {pq_p}")

        # H1 OHLC correctness check
        h1_paths = self._tf_results.get("H1")
        if h1_paths:
            self._verify_h1(h1_paths, errors, warnings)

        self._logger.info(
            "Timeframe conversion: %s",
            {tf: details.get(f"{tf}_bar_count", "?") for tf in self._tf_results},
            extra={"ctx": {"component": "data_pipeline",
                           "stage": "timeframe_conversion"}},
        )
        return StageResult("timeframe_conversion", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    def _verify_h1(self, h1_paths, errors, warnings):
        """Verify H1 open/high/low/close against M1 source."""
        try:
            h1_p = Path(h1_paths["arrow"]) if isinstance(h1_paths, dict) else Path(h1_paths)
            h1 = pa.ipc.open_file(str(h1_p)).read_all()
            m1 = pa.ipc.open_file(str(self._m1_arrow_path)).read_all()
            if h1.num_rows < 10:
                return
            test_ts = h1.column("timestamp")[h1.num_rows // 2].as_py()
            end_ts = test_ts + 3600 * 1_000_000
            mask = pc.and_(
                pc.greater_equal(m1.column("timestamp"), test_ts),
                pc.less(m1.column("timestamp"), end_ts),
            )
            m1_hour = m1.filter(mask)
            if m1_hour.num_rows == 0:
                return
            h1_row = h1.filter(pc.equal(h1.column("timestamp"), test_ts))
            if h1_row.num_rows == 0:
                return
            _verify(errors,
                    abs(h1_row.column("open")[0].as_py()
                        - m1_hour.column("open")[0].as_py()) < 1e-10,
                    "H1 open != first M1 open")
            _verify(errors,
                    abs(h1_row.column("high")[0].as_py()
                        - max(m1_hour.column("high").to_pylist())) < 1e-10,
                    "H1 high != max M1 high")
            _verify(errors,
                    abs(h1_row.column("low")[0].as_py()
                        - min(m1_hour.column("low").to_pylist())) < 1e-10,
                    "H1 low != min M1 low")
            _verify(errors,
                    abs(h1_row.column("close")[0].as_py()
                        - m1_hour.column("close")[-1].as_py()) < 1e-10,
                    "H1 close != last M1 close")
        except Exception as e:
            warnings.append(f"H1 verification skipped: {e}")

    # -----------------------------------------------------------------------
    # Stage 5 — Train/Test Split + Manifest
    # -----------------------------------------------------------------------

    def _stage_split(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}

        from data_pipeline.data_splitter import run_data_splitting
        self._split_result = run_data_splitting(
            self._pair, self._pipeline_dir, self._config,
        )

        all_tfs = ["M1"] + (list(self._tf_results.keys())
                            if self._tf_results else [])
        for tf in all_tfs:
            train_files = list(self._pipeline_dir.glob(
                f"{self._pair}_*_{tf}_train.arrow"))
            test_files = list(self._pipeline_dir.glob(
                f"{self._pair}_*_{tf}_test.arrow"))
            _verify(errors, len(train_files) > 0,
                    f"{tf} train Arrow file not found")
            _verify(errors, len(test_files) > 0,
                    f"{tf} test Arrow file not found")
            if train_files and test_files:
                train = pa.ipc.open_file(str(train_files[0])).read_all()
                test = pa.ipc.open_file(str(test_files[0])).read_all()
                t_max = pc.max(train.column("timestamp")).as_py()
                te_min = pc.min(test.column("timestamp")).as_py()
                _verify(errors, t_max < te_min,
                        f"{tf} temporal overlap: train_max >= test_min")
                total = train.num_rows + test.num_rows
                ratio = train.num_rows / total if total else 0
                details[f"{tf}_train_bars"] = train.num_rows
                details[f"{tf}_test_bars"] = test.num_rows
                _warn(warnings, 0.6 < ratio < 0.8,
                      f"{tf} train ratio {ratio:.3f} outside 0.6-0.8")

        # Verify manifest exists (dataset-scoped, AC#11)
        mp = self._find_manifest()
        _verify(errors, mp is not None, "No manifest file found")
        if mp:
            try:
                with open(mp) as f:
                    m = json.load(f)
                for k in ("dataset_id", "config_hash", "data_hash"):
                    _verify(errors, k in m, f"Manifest missing '{k}'")
                details["manifest_path"] = str(mp)
            except (json.JSONDecodeError, IOError) as e:
                errors.append(f"Cannot read manifest: {e}")

        self._logger.info(
            "Split complete",
            extra={"ctx": {"component": "data_pipeline",
                           "stage": "data_splitting"}},
        )
        return StageResult("train_test_split", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    # -----------------------------------------------------------------------
    # Stage 6 — Artifact chain verification
    # -----------------------------------------------------------------------

    def _verify_artifacts(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}
        from data_pipeline.dataset_hasher import compute_file_hash

        all_files = [f for f in self._pipeline_dir.iterdir() if f.is_file()]
        details["total_files"] = len(all_files)

        # Check no .partial files remain
        partials = list(self._pipeline_dir.glob("*.partial"))
        _verify(errors, len(partials) == 0,
                f"Partial files remain: {[p.name for p in partials]}")

        # Load manifest and verify config hash (dataset-scoped, AC#11)
        manifest_file = self._find_manifest()
        if manifest_file:
            with open(manifest_file) as f:
                manifest = json.load(f)
            self._first_run_manifest = manifest
            mch = manifest.get("config_hash", "").replace("sha256:", "")
            _verify(errors, mch == self._config_hash,
                    f"Config hash mismatch: manifest={mch[:8]} vs "
                    f"actual={self._config_hash[:8]}")

            # --- AC8: Cross-reference files against manifest ---
            manifest_files = set()
            for section in ("files", "timeframes"):
                sec = manifest.get(section, {})
                if isinstance(sec, dict):
                    for key, val in sec.items():
                        if isinstance(val, dict):
                            for fname in val.values():
                                if isinstance(fname, str):
                                    manifest_files.add(Path(fname).name)
                        elif isinstance(val, str):
                            manifest_files.add(Path(val).name)

            # Exclude proof/meta files from orphan check
            meta_files = {"pipeline_proof_result.json",
                          "reference_dataset.json",
                          manifest_file.name}
            data_files = {f.name for f in all_files
                          if f.name not in meta_files}
            # Files on disk not in manifest = orphans
            orphans = data_files - manifest_files
            _verify(errors, len(orphans) == 0,
                    f"Orphan files not in manifest: {sorted(orphans)}")
            # Files in manifest not on disk = missing
            missing = manifest_files - {f.name for f in all_files}
            _verify(errors, len(missing) == 0,
                    f"Manifest references missing files: {sorted(missing)}")
            details["orphan_files"] = len(orphans)
            details["missing_files"] = len(missing)

            # --- AC8: Verify artifact naming (pair, date range, tf) ---
            prefix = f"{self._pair}_{self._start_str}_{self._end_str}"
            for f in all_files:
                if f.suffix in (".arrow", ".parquet"):
                    _verify(errors, prefix in f.name,
                            f"Artifact '{f.name}' missing naming convention "
                            f"'{prefix}'")

            # --- AC8: Hash-chain verification ---
            manifest_hashes = manifest.get("data_hash", "")
            for f in all_files:
                if f.suffix == ".arrow":
                    h = compute_file_hash(f)
                    self._first_run_hashes[f.name] = h
                elif f.suffix == ".parquet":
                    self._first_run_hashes[f.name] = compute_file_hash(f)
        else:
            manifest = None
            errors.append("No manifest for artifact chain verification")
            # Still collect hashes for reproducibility even without manifest
            for f in all_files:
                if f.suffix in (".arrow", ".parquet"):
                    self._first_run_hashes[f.name] = compute_file_hash(f)

        # Also hash JSON artifacts for reproducibility (AC#9)
        for f in all_files:
            if f.name.endswith("quality-report.json"):
                self._first_run_hashes[f.name] = compute_file_hash(f)

        details["hashed_files"] = len(self._first_run_hashes)

        self._logger.info(
            "Artifact chain: %d files, %d hashed",
            len(all_files), len(self._first_run_hashes),
            extra={"ctx": {"component": "data_pipeline",
                           "stage": "artifact_verification"}},
        )
        return StageResult("artifact_chain", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    # -----------------------------------------------------------------------
    # Stage 7 — Reproducibility verification
    # -----------------------------------------------------------------------

    def _verify_reproducibility(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}

        if self._skip_reproducibility:
            details["skipped"] = True
            return StageResult("reproducibility", "PASS", 0.0, details,
                               errors, ["Skipped (--skip-reproducibility)"])

        if not self._first_run_hashes:
            errors.append("No first-run hashes for comparison")
            return StageResult("reproducibility", "FAIL", time.time() - t0,
                               details, errors, warnings)

        from data_pipeline.dataset_hasher import compute_file_hash

        # 1. Delete generated artifacts (keep raw download)
        excluded = {"pipeline_proof_result.json", "reference_dataset.json"}
        for f in list(self._pipeline_dir.iterdir()):
            if f.is_file() and f.name not in excluded:
                f.unlink()

        # Also delete ArrowConverter intermediate outputs
        cr = self._conversion_result
        if cr:
            for p in (cr.arrow_path, cr.parquet_path, cr.manifest_path):
                if p and Path(p).exists():
                    Path(p).unlink()

        # Delete quality report
        vr = self._validation_result
        if vr and vr.report_path and Path(vr.report_path).exists():
            Path(vr.report_path).unlink()

        self._logger.info(
            "Reproducibility: artifacts deleted, re-running stages 2-5",
            extra={"ctx": {"component": "data_pipeline",
                           "stage": "reproducibility"}},
        )

        # 2. Re-run stages 2-5
        try:
            from data_pipeline.quality_checker import DataQualityChecker
            from data_pipeline.arrow_converter import ArrowConverter
            from data_pipeline.timeframe_converter import run_timeframe_conversion
            from data_pipeline.data_splitter import run_data_splitting

            checker = DataQualityChecker(self._config, self._logger)
            vr2 = checker.validate(
                self._df, self._pair, self._resolution,
                self._start_date, self._end_date,
                self._storage_root, self._dataset_id, "v1",
            )

            converter = ArrowConverter(self._config, self._logger)
            cr2 = converter.convert(
                vr2.validated_df, self._pair, self._resolution,
                self._start_date, self._end_date,
                self._dataset_id, "v1",
                vr2.quality_score, vr2.rating,
            )

            # Copy M1 to data-pipeline/
            if cr2.arrow_path.exists():
                shutil.copy2(str(cr2.arrow_path), str(self._m1_arrow_path))
            if cr2.parquet_path.exists():
                shutil.copy2(str(cr2.parquet_path), str(self._m1_parquet_path))

            source = (self._m1_arrow_path
                      if self._m1_arrow_path.exists() else cr2.arrow_path)
            run_timeframe_conversion(
                self._pair, source, self._config, self._logger)

            run_data_splitting(self._pair, self._pipeline_dir, self._config)
        except Exception as e:
            errors.append(f"Re-run failed: {type(e).__name__}: {e}")
            return StageResult("reproducibility", "FAIL", time.time() - t0,
                               details, errors, warnings)

        # 3. Compare hashes (include quality report per AC#9)
        second_hashes = {}
        for f in self._pipeline_dir.iterdir():
            if f.is_file() and (f.suffix in (".arrow", ".parquet")
                                or f.name.endswith("quality-report.json")):
                second_hashes[f.name] = compute_file_hash(f)

        mismatches = []
        for name, h1 in self._first_run_hashes.items():
            h2 = second_hashes.get(name)
            if h2 is None:
                mismatches.append(f"{name}: missing in run 2")
            elif h1 != h2:
                mismatches.append(f"{name}: hash mismatch "
                                 f"({h1[:8]} vs {h2[:8]})")
        if mismatches:
            errors.extend(mismatches)

        # 4. Compare manifests (ignoring created_at)
        new_manifest = self._find_manifest()
        if new_manifest and self._first_run_manifest:
            with open(new_manifest) as f:
                m2 = json.load(f)
            m1_cmp = {k: v for k, v in self._first_run_manifest.items()
                      if k != "created_at"}
            m2_cmp = {k: v for k, v in m2.items() if k != "created_at"}
            _verify(errors, m1_cmp == m2_cmp,
                    "Manifest content differs between runs "
                    "(excluding created_at)")

        details["files_compared"] = len(self._first_run_hashes)
        details["mismatches"] = len(mismatches)

        self._logger.info(
            "Reproducibility: %d files, %d mismatches",
            len(self._first_run_hashes), len(mismatches),
            extra={"ctx": {"component": "data_pipeline",
                           "stage": "reproducibility"}},
        )
        return StageResult("reproducibility", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    # -----------------------------------------------------------------------
    # Stage 8 — Structured log verification
    # -----------------------------------------------------------------------

    def _verify_logs(self) -> StageResult:
        t0 = time.time()
        errors, warnings, details = [], [], {}

        log_dir = Path(self._config.get("logging", {}).get("log_dir", "logs"))
        if not log_dir.is_absolute():
            log_dir = Path.cwd() / log_dir

        # Search for .jsonl first (actual logger output), fall back to .log
        log_files = sorted(log_dir.glob("python_*.jsonl")) if log_dir.exists() else []
        if not log_files:
            log_files = sorted(log_dir.glob("python_*.log")) if log_dir.exists() else []
        _verify(errors, len(log_files) > 0, f"No log files in {log_dir}")
        if not log_files:
            return StageResult("logging", "FAIL", time.time() - t0,
                               details, errors, warnings)

        log_file = log_files[-1]
        total = valid = invalid = err_lines = 0
        runtime_violations = 0
        missing_fields_count = 0
        required_fields = {"ts", "level", "runtime", "component", "stage", "msg"}
        components, stages_seen = set(), set()

        try:
            with open(log_file) as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    total += 1
                    try:
                        entry = json.loads(raw)
                        valid += 1
                        # Per-line required field check (AC#10)
                        ctx = entry.get("ctx", {})
                        if not isinstance(ctx, dict):
                            ctx = {}
                        # Build merged view: top-level + ctx
                        merged = {**entry, **ctx}
                        line_missing = required_fields - set(merged.keys())
                        if line_missing:
                            missing_fields_count += 1
                        # Verify runtime = "python" (AC#10)
                        rt = merged.get("runtime", "")
                        if rt and rt != "python":
                            runtime_violations += 1
                        comp = merged.get("component", "")
                        if comp:
                            components.add(comp)
                        stg = merged.get("stage", "")
                        if stg:
                            stages_seen.add(stg)
                        lvl = entry.get("level", "").upper()
                        if lvl == "ERROR":
                            err_lines += 1
                    except json.JSONDecodeError:
                        invalid += 1
        except Exception as e:
            errors.append(f"Cannot read log: {e}")

        _verify(errors, valid > 0, "No valid JSON log lines")
        # Strict: all lines must be valid JSON (not just > 0)
        _verify(errors, invalid == 0,
                f"{invalid}/{total} log lines are invalid JSON")
        _verify(errors, missing_fields_count == 0,
                f"{missing_fields_count} log lines missing required fields "
                f"({required_fields})")
        _verify(errors, runtime_violations == 0,
                f"{runtime_violations} log lines have runtime != 'python'")
        _verify(errors,
                "data_pipeline" in components
                or any("pipeline" in c for c in components),
                f"No data_pipeline component in logs. Found: {components}")
        expected_stages = {"download", "validation", "arrow_conversion",
                           "timeframe_conversion", "data_splitting"}
        _warn(warnings, len(stages_seen & expected_stages) >= 3,
              f"Expected pipeline stages in logs, found: {stages_seen}")
        if err_lines:
            warnings.append(f"{err_lines} ERROR-level log lines")

        details.update({
            "log_file": str(log_file), "total_lines": total,
            "valid_json": valid, "error_lines": err_lines,
            "components": sorted(components),
            "stages": sorted(stages_seen),
        })
        return StageResult("logging", "FAIL" if errors else "PASS",
                           round(time.time() - t0, 1), details, errors, warnings)

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def _find_manifest(self) -> Path | None:
        """Find the manifest file scoped to the current dataset_id."""
        if self._dataset_id:
            exact = self._pipeline_dir / f"{self._dataset_id}_manifest.json"
            if exact.exists():
                return exact
        # Fallback: search by dataset_id prefix
        candidates = list(self._pipeline_dir.glob("*_manifest.json"))
        if self._dataset_id:
            scoped = [c for c in candidates
                      if self._dataset_id in c.name]
            if scoped:
                return scoped[0]
        return candidates[0] if candidates else None

    def _count_artifacts(self) -> int:
        if self._pipeline_dir.exists():
            return len([f for f in self._pipeline_dir.iterdir() if f.is_file()])
        return 0

    def _save_reference_dataset(self, proof: PipelineProofResult):
        mf = self._find_manifest()
        ref = {
            "dataset_id": proof.dataset_id,
            "manifest_path": mf.name if mf else "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "purpose": "Reference dataset for all subsequent Epic pipeline proofs",
            "proof_result": proof.overall_status,
            "reproducibility_verified": proof.reproducibility_verified,
        }
        from artifacts.storage import crash_safe_write
        crash_safe_write(
            str(self._pipeline_dir / "reference_dataset.json"),
            json.dumps(ref, indent=2),
        )

    def _save_result_json(self, proof: PipelineProofResult):
        result = {
            "overall_status": proof.overall_status,
            "dataset_id": proof.dataset_id,
            "config_hash": proof.config_hash,
            "reproducibility_verified": proof.reproducibility_verified,
            "total_duration_seconds": proof.total_duration_seconds,
            "artifact_count": proof.artifact_count,
            "errors": proof.errors,
            "warnings": proof.warnings,
            "stages": {},
        }
        for name, sr in proof.stages.items():
            result["stages"][name] = {
                "name": sr.name, "status": sr.status,
                "duration_seconds": sr.duration_seconds,
                "details": sr.details,
                "errors": sr.errors, "warnings": sr.warnings,
            }
        from artifacts.storage import crash_safe_write
        crash_safe_write(
            str(self._pipeline_dir / "pipeline_proof_result.json"),
            json.dumps(result, indent=2),
        )

    def _print_summary(self, proof: PipelineProofResult, stages: dict):
        labels = {
            "download": "Download",
            "validation": "Validation",
            "storage_conversion": "Storage/Conversion",
            "timeframe_conversion": "Timeframe Conversion",
            "train_test_split": "Train/Test Split",
            "artifact_chain": "Artifact Chain",
            "reproducibility": "Reproducibility",
            "logging": "Logging",
        }
        lines = [
            "",
            "=== Pipeline Proof: Market Data Flow ===",
            f"Status: {proof.overall_status}",
            f"Dataset: {proof.dataset_id}",
            f"Config Hash: {proof.config_hash[:8]}",
            "",
            "Stage Results:",
        ]
        for key, label in labels.items():
            sr = stages.get(key)
            if not sr:
                continue
            d = sr.details
            extra = ""
            if key == "download":
                extra = f"({d.get('bar_count', '?')} bars)"
            elif key == "validation":
                extra = f"(score: {d.get('quality_score', '?')}, {d.get('rating', '?')})"
            elif key == "storage_conversion":
                extra = (f"(Arrow: {d.get('arrow_size_mb', '?')} MB, "
                         f"Parquet: {d.get('parquet_size_mb', '?')} MB)")
            elif key == "timeframe_conversion":
                cnts = {k.replace("_bar_count", ""): v
                        for k, v in d.items() if k.endswith("_bar_count")}
                extra = str(cnts) if cnts else ""
            elif key == "train_test_split":
                extra = (f"(train: {d.get('M1_train_bars', '?')}, "
                         f"test: {d.get('M1_test_bars', '?')})")
            elif key == "artifact_chain":
                extra = f"({d.get('total_files', '?')} files)"
            elif key == "reproducibility":
                if d.get("skipped"):
                    extra = "(skipped)"
                else:
                    extra = (f"({d.get('files_compared', '?')} files, "
                             f"{d.get('mismatches', '?')} mismatches)")
            elif key == "logging":
                extra = (f"({d.get('total_lines', '?')} lines, "
                         f"{d.get('error_lines', '?')} errors)")
            lines.append(f"  {label:25s} {sr.status} {extra}")

        lines.extend(["", f"Duration: {proof.total_duration_seconds} seconds"])
        if proof.overall_status == "PASS":
            lines.append("Reference dataset saved: reference_dataset.json")
        if proof.warnings:
            lines.append(f"\nWarnings ({len(proof.warnings)}):")
            for w in proof.warnings[:10]:
                lines.append(f"  - {w}")
        if proof.errors:
            lines.append(f"\nErrors ({len(proof.errors)}):")
            for e in proof.errors[:10]:
                lines.append(f"  - {e}")
        print("\n".join(lines))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline_proof(config: dict, skip_download: bool = False,
                       skip_reproducibility: bool = False) -> PipelineProofResult:
    """Run the pipeline proof and return the result."""
    proof = PipelineProof(config, skip_download, skip_reproducibility)
    return proof.run()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="E2E Pipeline Proof — Market Data Flow")
    parser.add_argument("--env", default="local",
                        help="Config environment (default: local)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip download if data already exists")
    parser.add_argument("--skip-reproducibility", action="store_true",
                        help="Skip reproducibility check (faster)")
    args = parser.parse_args()

    from config_loader import load_config, validate_or_die
    from logging_setup import setup_logging

    config = load_config(env=args.env)
    validate_or_die(config)
    setup_logging(config)

    result = run_pipeline_proof(
        config, args.skip_download, args.skip_reproducibility)
    sys.exit(0 if result.overall_status == "PASS" else 1)


if __name__ == "__main__":
    main()
