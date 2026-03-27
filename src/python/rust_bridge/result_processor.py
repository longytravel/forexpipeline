"""Result processing orchestrator — full post-backtest flow (D2, D3).

Coordinates: Arrow IPC publishing → schema validation → SQLite ingest →
Parquet archival → consistency validation → manifest creation.

This is an internal step within the backtest-complete → review-pending
transition, NOT a separate pipeline stage.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.ipc
import pyarrow.parquet as pq

from artifacts.manifest import ManifestBuilder
from artifacts.parquet_archiver import ParquetArchiver
from artifacts.sqlite_manager import SQLiteManager
from artifacts.storage import ArtifactStorage, crash_safe_write_json
from logging_setup.setup import get_logger
from rust_bridge.result_ingester import ResultIngester

logger = get_logger("pipeline.rust_bridge.result_processor")


class ResultProcessingError(Exception):
    """Raised when result processing fails at a specific stage."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


@dataclass
class ProcessingResult:
    """Outcome of a successful result processing run."""

    version: int
    backtest_run_id: str
    trade_count: int
    artifact_dir: Path
    manifest_path: Path


# Arrow files expected from Rust backtester
_ARROW_FILES = ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]

# Schema names in contracts/arrow_schemas.toml
_SCHEMA_MAP = {
    "trade-log.arrow": "backtest_trades",
    "equity-curve.arrow": "equity_curve",
    "metrics.arrow": "backtest_metrics",
}


class ResultProcessor:
    """Orchestrates the full post-backtest result processing pipeline."""

    def __init__(
        self,
        artifacts_root: Path,
        sqlite_db_path: Path,
    ) -> None:
        self.artifacts_root = Path(artifacts_root)
        self.sqlite_db_path = Path(sqlite_db_path)

    def process_backtest_results(
        self,
        strategy_id: str,
        backtest_run_id: str,
        config_hash: str,
        data_hash: str,
        cost_model_hash: str,
        strategy_spec_hash: str,
        rust_output_dir: Path,
        strategy_spec_version: str,
        cost_model_version: str,
        run_timestamp: str,
        fold_scores: list[dict] | None = None,
        input_paths: dict[str, str] | None = None,
    ) -> ProcessingResult:
        """Execute the full result processing pipeline.

        Steps:
        1. Determine version (new vs existing)
        2. Create version directory
        3. Publish Arrow IPC files (crash-safe copy)
        4. Validate Arrow schemas
        5. Register backtest run + ingest trade log into SQLite
        6. Create Parquet archival copies
        7. Validate consistency (Arrow/SQLite/Parquet row counts)
        8. Complete backtest_run record
        9. Build and write manifest.json
        """
        rust_output_dir = Path(rust_output_dir)
        version_dir: Path | None = None
        checkpoint_path: Path | None = None
        checkpoint: dict = {}

        try:
            # Load or create checkpoint
            should_new = ArtifactStorage.should_create_new_version(
                strategy_id, config_hash, data_hash, cost_model_hash,
                self.artifacts_root,
            )

            if should_new:
                version = ArtifactStorage._next_version(
                    self.artifacts_root / strategy_id
                )
            else:
                existing = ArtifactStorage._existing_versions(
                    self.artifacts_root / strategy_id
                )
                version = existing[-1] if existing else 1

            version_dir = ArtifactStorage.create_version_dir(
                strategy_id, version, self.artifacts_root
            )
            backtest_dir = version_dir / "backtest"
            checkpoint_path = version_dir / "_processing_checkpoint.json"
            checkpoint = self._load_checkpoint(checkpoint_path)

            # Step 3: Publish Arrow IPC files
            if not checkpoint.get("arrow_published"):
                self._publish_arrow_files(rust_output_dir, backtest_dir)
                checkpoint["arrow_published"] = True
                self._save_checkpoint(checkpoint, checkpoint_path)

            # Step 4: Validate schemas
            if not checkpoint.get("schema_validated"):
                self._validate_schemas(backtest_dir)
                checkpoint["schema_validated"] = True
                self._save_checkpoint(checkpoint, checkpoint_path)

            # Step 5: SQLite ingest
            trade_count = 0
            if not checkpoint.get("sqlite_ingested"):
                trade_count = self._ingest_to_sqlite(
                    backtest_dir, strategy_id, backtest_run_id,
                    config_hash, data_hash, strategy_spec_version,
                    run_timestamp, fold_scores,
                )
                checkpoint["sqlite_ingested"] = True
                checkpoint["trade_count"] = trade_count
                checkpoint["backtest_run_id"] = backtest_run_id
                self._save_checkpoint(checkpoint, checkpoint_path)
            else:
                trade_count = checkpoint.get("trade_count", 0)

            # Use the run_id that was actually ingested (matters on reuse/resume)
            ingested_run_id = checkpoint.get("backtest_run_id", backtest_run_id)

            # Step 6: Parquet archival
            if not checkpoint.get("parquet_archived"):
                archiver = ParquetArchiver()
                archiver.archive_backtest_results(version_dir)
                checkpoint["parquet_archived"] = True
                self._save_checkpoint(checkpoint, checkpoint_path)

            # Step 7: Validate consistency
            self._validate_consistency(backtest_dir, trade_count, ingested_run_id)

            # Step 8: Complete backtest_run
            with SQLiteManager(self.sqlite_db_path) as mgr:
                ingester = ResultIngester(mgr.connection)
                ingester.complete_backtest_run(ingested_run_id, trade_count)

            # Step 9: Build and write manifest
            started_at = run_timestamp
            completed_at = datetime.now(timezone.utc).isoformat()

            metrics_summary = self._read_metrics_summary(backtest_dir)

            result_files = {
                "trade_log": "backtest/trade-log.arrow",
                "equity_curve": "backtest/equity-curve.arrow",
                "metrics": "backtest/metrics.arrow",
                "parquet_trade_log": "backtest/trade-log.parquet",
                "parquet_equity_curve": "backtest/equity-curve.parquet",
                "parquet_metrics": "backtest/metrics.parquet",
            }

            builder = ManifestBuilder(strategy_id, version, self.artifacts_root)
            manifest = builder.build(
                backtest_run_id=backtest_run_id,
                strategy_spec_version=strategy_spec_version,
                strategy_spec_hash=strategy_spec_hash,
                cost_model_version=cost_model_version,
                cost_model_hash=cost_model_hash,
                dataset_hash=data_hash,
                config_hash=config_hash,
                run_timestamp=run_timestamp,
                started_at=started_at,
                completed_at=completed_at,
                result_files=result_files,
                metrics_summary=metrics_summary,
                input_paths=input_paths,
            )
            manifest_path = builder.write(manifest)

            checkpoint["manifest_written"] = True
            self._save_checkpoint(checkpoint, checkpoint_path)

            logger.info(
                "Result processing complete",
                extra={
                    "component": "pipeline.rust_bridge.result_processor",
                    "ctx": {
                        "strategy_id": strategy_id,
                        "version": version,
                        "trade_count": trade_count,
                        "backtest_run_id": backtest_run_id,
                    },
                },
            )

            return ProcessingResult(
                version=version,
                backtest_run_id=backtest_run_id,
                trade_count=trade_count,
                artifact_dir=version_dir,
                manifest_path=manifest_path,
            )

        except Exception as exc:
            # Save checkpoint of completed steps, do NOT delete version dir
            if checkpoint_path is not None:
                try:
                    self._save_checkpoint(
                        checkpoint,
                        checkpoint_path,
                    )
                except Exception:
                    pass

            stage = getattr(exc, "stage", "unknown")
            logger.error(
                f"Result processing failed at stage: {stage}",
                extra={
                    "component": "pipeline.rust_bridge.result_processor",
                    "ctx": {
                        "strategy_id": strategy_id,
                        "backtest_run_id": backtest_run_id,
                        "error": str(exc),
                    },
                },
            )
            raise

    # ------------------------------------------------------------------
    # Internal pipeline steps
    # ------------------------------------------------------------------

    def _publish_arrow_files(
        self, rust_output_dir: Path, backtest_dir: Path
    ) -> None:
        """Crash-safe copy Arrow IPC files from Rust output to versioned dir."""
        for filename in _ARROW_FILES:
            src = rust_output_dir / filename
            dst = backtest_dir / filename

            if dst.exists():
                continue  # Resume case — already published

            if not src.exists():
                raise ResultProcessingError(
                    "arrow_publish",
                    f"Missing Arrow file: {src}",
                )

            partial = dst.with_name(dst.name + ".partial")
            shutil.copy2(str(src), str(partial))

            # fsync the partial file (open writable for Windows compat)
            with open(partial, "r+b") as f:
                f.flush()
                os.fsync(f.fileno())

            os.replace(str(partial), str(dst))

        logger.info(
            "Arrow files published",
            extra={
                "component": "pipeline.rust_bridge.result_processor",
                "ctx": {"source": str(rust_output_dir), "dest": str(backtest_dir)},
            },
        )

    def _validate_schemas(self, backtest_dir: Path) -> None:
        """Validate all Arrow files against contracts/arrow_schemas.toml."""
        for filename, schema_name in _SCHEMA_MAP.items():
            arrow_path = backtest_dir / filename
            if not ResultIngester.validate_schema_static(arrow_path, schema_name):
                raise ResultProcessingError(
                    "schema_validation",
                    f"Schema mismatch for {filename} (expected: {schema_name})",
                )

    def _ingest_to_sqlite(
        self,
        backtest_dir: Path,
        strategy_id: str,
        backtest_run_id: str,
        config_hash: str,
        data_hash: str,
        spec_version: str,
        started_at: str,
        fold_scores: list[dict] | None = None,
    ) -> int:
        """Register backtest run, clear existing data, ingest trade log."""
        with SQLiteManager(self.sqlite_db_path) as mgr:
            mgr.init_schema()
            ingester = ResultIngester(mgr.connection)

            ingester.register_backtest_run(
                run_id=backtest_run_id,
                strategy_id=strategy_id,
                config_hash=config_hash,
                data_hash=data_hash,
                spec_version=spec_version,
                started_at=started_at,
            )

            # Clear existing trades for idempotent re-ingest (AC #10)
            ingester.clear_run_data(backtest_run_id)

            trade_count = ingester.ingest_trade_log(
                arrow_path=backtest_dir / "trade-log.arrow",
                strategy_id=strategy_id,
                backtest_run_id=backtest_run_id,
            )

            # Ingest fold scores if fold-aware evaluation was used
            if fold_scores:
                ingester.ingest_fold_scores(backtest_run_id, fold_scores)

        return trade_count

    def _validate_consistency(
        self, backtest_dir: Path, sqlite_trade_count: int,
        backtest_run_id: str = "",
    ) -> None:
        """Validate Arrow/SQLite/Parquet trade counts and ordering match (AC #11)."""
        from rust_bridge.result_ingester import _ns_to_iso8601

        # Arrow count
        arrow_path = backtest_dir / "trade-log.arrow"
        reader = pyarrow.ipc.open_file(str(arrow_path))
        arrow_table = reader.read_all()
        arrow_count = arrow_table.num_rows

        if arrow_count != sqlite_trade_count:
            raise ResultProcessingError(
                "consistency_validation",
                f"Arrow trade count ({arrow_count}) != SQLite count ({sqlite_trade_count})",
            )

        # Arrow reference values for cross-format checks
        arrow_ids = arrow_table.column("trade_id").to_pylist()
        arrow_entry_times = arrow_table.column("entry_time").to_pylist()

        # SQLite cross-verification (trade_id ordering + first/last entry_time)
        with SQLiteManager(self.sqlite_db_path) as mgr:
            rows = mgr.connection.execute(
                "SELECT trade_id, entry_time FROM trades "
                "WHERE backtest_run_id = ? "
                "ORDER BY trade_id",
                (backtest_run_id,),
            ).fetchall()
            sqlite_ids = [r[0] for r in rows]
            if sqlite_ids != arrow_ids:
                raise ResultProcessingError(
                    "consistency_validation",
                    "trade_id ordering differs between Arrow and SQLite",
                )
            if rows:
                arrow_first_time = _ns_to_iso8601(arrow_entry_times[0])
                arrow_last_time = _ns_to_iso8601(arrow_entry_times[-1])
                sqlite_first_time = rows[0][1]
                sqlite_last_time = rows[-1][1]
                if arrow_first_time != sqlite_first_time:
                    raise ResultProcessingError(
                        "consistency_validation",
                        f"First entry_time differs: Arrow={arrow_first_time} vs SQLite={sqlite_first_time}",
                    )
                if arrow_last_time != sqlite_last_time:
                    raise ResultProcessingError(
                        "consistency_validation",
                        f"Last entry_time differs: Arrow={arrow_last_time} vs SQLite={sqlite_last_time}",
                    )

        # Parquet count
        parquet_path = backtest_dir / "trade-log.parquet"
        if parquet_path.exists():
            pq_table = pq.read_table(str(parquet_path))
            pq_count = pq_table.num_rows
            if pq_count != arrow_count:
                raise ResultProcessingError(
                    "consistency_validation",
                    f"Parquet trade count ({pq_count}) != Arrow count ({arrow_count})",
                )

            # Verify trade_id ordering and first/last entry_time match
            pq_ids = pq_table.column("trade_id").to_pylist()
            if arrow_ids != pq_ids:
                raise ResultProcessingError(
                    "consistency_validation",
                    "trade_id ordering differs between Arrow and Parquet",
                )

            pq_entry_times = pq_table.column("entry_time").to_pylist()
            if arrow_entry_times[0] != pq_entry_times[0]:
                raise ResultProcessingError(
                    "consistency_validation",
                    "First entry_time differs between Arrow and Parquet",
                )
            if arrow_entry_times[-1] != pq_entry_times[-1]:
                raise ResultProcessingError(
                    "consistency_validation",
                    "Last entry_time differs between Arrow and Parquet",
                )

        logger.info(
            "Consistency validation passed",
            extra={
                "component": "pipeline.rust_bridge.result_processor",
                "ctx": {"trade_count": arrow_count},
            },
        )

    def _read_metrics_summary(self, backtest_dir: Path) -> dict:
        """Read metrics.arrow and extract summary dict."""
        metrics_path = backtest_dir / "metrics.arrow"
        if not metrics_path.exists():
            return {}

        reader = pyarrow.ipc.open_file(str(metrics_path))
        table = reader.read_all()
        if table.num_rows == 0:
            return {}

        summary = {}
        for col_name in table.column_names:
            val = table.column(col_name)[0].as_py()
            summary[col_name] = val
        return summary

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_checkpoint(path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    @staticmethod
    def _save_checkpoint(checkpoint: dict, path: Path) -> None:
        crash_safe_write_json(checkpoint, path)
