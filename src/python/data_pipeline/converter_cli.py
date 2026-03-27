"""Conversion CLI entry point (Story 1.6).

Loads validated data from Story 1.5 output, runs Arrow IPC + Parquet
conversion, returns summary.
"""
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from data_pipeline.arrow_converter import ArrowConverter


def run_conversion(config: dict) -> dict:
    """Run Arrow IPC + Parquet conversion on validated data.

    Expects Story 1.5 output (validated CSV with quality report) in the
    configured storage path.

    Returns:
        Summary dict with conversion results or error.
    """
    logger = logging.getLogger("data_pipeline.converter")

    dp_cfg = config.get("data_pipeline", {})
    dl_cfg = dp_cfg.get("download", {})
    pair = dl_cfg.get("pairs", ["EURUSD"])[0]
    resolution = dl_cfg.get("resolution", "M1")
    start_str = dl_cfg.get("start_date", "2015-01-01")
    end_str = dl_cfg.get("end_date", "2025-12-31")
    start_date = date.fromisoformat(start_str)
    end_date = date.fromisoformat(end_str)

    storage_path = Path(dp_cfg.get(
        "storage_path", config.get("data", {}).get("storage_path", "")
    ))

    dataset_id = f"{pair}_{start_str}_{end_str}_{resolution}"
    version = "v001"

    # Load validated data from Story 1.5 output
    # Quality checker saves validated CSV to: validated/{dataset_id}/{version}/{dataset_id}_validated.csv
    validated_dir = storage_path / "validated" / dataset_id / version
    csv_path = validated_dir / f"{dataset_id}_validated.csv"

    if not csv_path.exists():
        logger.error("Validated data not found: %s", csv_path)
        return {"error": f"Validated data not found: {csv_path}"}

    logger.info(
        "Loading validated data: %s", csv_path,
        extra={"ctx": {"component": "converter", "stage": "data_pipeline"}},
    )
    df = pd.read_csv(csv_path)

    # Load quality info if available
    # Quality checker saves report to: raw/{dataset_id}/{version}/quality-report.json
    quality_report_path = storage_path / "raw" / dataset_id / version / "quality-report.json"
    quality_score = 0.0
    rating = "UNKNOWN"
    if quality_report_path.exists():
        import json
        with open(quality_report_path) as f:
            report = json.load(f)
        quality_score = report.get("quality_score", 0.0)
        rating = report.get("rating", "UNKNOWN")

    converter = ArrowConverter(config, logger)
    result = converter.convert(
        validated_df=df,
        pair=pair,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        dataset_id=dataset_id,
        version=version,
        quality_score=quality_score,
        rating=rating,
    )

    logger.info(
        "Conversion complete: %s %s → Arrow IPC (%.2fMB) + Parquet (%.2fMB)",
        pair, resolution, result.arrow_size_mb, result.parquet_size_mb,
        extra={"ctx": {"component": "converter", "stage": "data_pipeline"}},
    )

    return {
        "pair": pair,
        "resolution": resolution,
        "dataset_id": dataset_id,
        "version": version,
        "row_count": result.row_count,
        "arrow_path": str(result.arrow_path),
        "parquet_path": str(result.parquet_path),
        "manifest_path": str(result.manifest_path),
        "arrow_size_mb": result.arrow_size_mb,
        "parquet_size_mb": result.parquet_size_mb,
    }
