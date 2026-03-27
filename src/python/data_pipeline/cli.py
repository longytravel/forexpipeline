"""Data pipeline download orchestration (Story 1.4, Task 5).

Top-level entry point that loads config, runs downloads for each pair,
handles incremental logic, and saves versioned artifacts.
"""
import logging
from datetime import date
from pathlib import Path

from config_loader.hasher import compute_config_hash
from data_pipeline.downloader import DukascopyDownloader
from logging_setup import LogContext, get_logger


def run_download(config: dict) -> dict:
    """Execute data download pipeline for all configured pairs.

    Returns summary dict with: pairs downloaded, date ranges,
    row counts, versions created, any failed periods.
    """
    logger = get_logger("downloader")
    downloader = DukascopyDownloader(config, logger)

    pipeline_cfg = config["data_pipeline"]
    dl_cfg = pipeline_cfg["download"]
    pairs = dl_cfg["pairs"]
    start_date = date.fromisoformat(dl_cfg["start_date"])
    end_date = date.fromisoformat(dl_cfg["end_date"])
    resolution = dl_cfg["resolution"]
    storage_path = Path(pipeline_cfg["storage_path"])

    config_hash = compute_config_hash(config)

    with LogContext(stage="data_pipeline"):
        logger.info(
            "Starting data pipeline download",
            extra={"ctx": {
                "stage": "data_pipeline", "component": "downloader",
                "pairs": pairs, "resolution": resolution,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "config_hash": config_hash,
            }},
        )

        summary = {
            "pairs": {},
            "total_rows": 0,
            "failed_periods": [],
            "versions_created": [],
        }

        for i, pair in enumerate(pairs):
            logger.info(
                "Downloading pair %d/%d: %s",
                i + 1, len(pairs), pair,
                extra={"ctx": {
                    "stage": "data_pipeline", "component": "downloader",
                    "pair": pair, "step": f"{i + 1}/{len(pairs)}",
                }},
            )

            try:
                df = downloader.download(pair, start_date, end_date, resolution)

                if df.empty:
                    logger.warning(
                        "No data downloaded for %s", pair,
                        extra={"ctx": {"pair": pair}},
                    )
                    summary["pairs"][pair] = {"rows": 0, "status": "empty"}
                    continue

                # Save versioned artifact
                dataset_id = downloader.generate_dataset_id(
                    pair, start_date, end_date, resolution
                )
                data_hash = downloader.compute_data_hash(df)

                artifact_path = downloader.save_raw_artifact(
                    df, pair, start_date, end_date, resolution, storage_path
                )

                # Extract version from artifact path
                version = artifact_path.parent.name

                downloader.write_download_manifest(
                    dataset_id=dataset_id,
                    version=version,
                    data_hash=data_hash,
                    pair=pair,
                    start_date=start_date,
                    end_date=end_date,
                    resolution=resolution,
                    row_count=len(df),
                    failed_periods=downloader.failed_periods,
                    storage_path=storage_path,
                    config_hash=config_hash,
                )

                summary["pairs"][pair] = {
                    "rows": len(df),
                    "version": version,
                    "dataset_id": dataset_id,
                    "status": "success",
                }
                summary["total_rows"] += len(df)
                summary["versions_created"].append(f"{dataset_id}/{version}")

            except Exception as e:
                logger.error(
                    "Download failed for %s: %s", pair, str(e),
                    extra={"ctx": {
                        "pair": pair, "error": str(e),
                        "error_code": "EXTERNAL_DUKASCOPY_TIMEOUT",
                    }},
                )
                summary["pairs"][pair] = {"rows": 0, "status": "failed", "error": str(e)}
                summary["failed_periods"].append(pair)

        logger.info(
            "Data pipeline download complete",
            extra={"ctx": {
                "stage": "data_pipeline", "component": "downloader",
                "total_pairs": len(pairs),
                "successful": sum(1 for p in summary["pairs"].values() if p["status"] == "success"),
                "total_rows": summary["total_rows"],
            }},
        )

    return summary
