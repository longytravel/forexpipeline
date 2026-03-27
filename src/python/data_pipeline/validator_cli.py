"""Validation CLI entry point (Story 1.5).

Loads raw data from Story 1.4 output, runs validation, returns summary.
"""
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from data_pipeline.quality_checker import DataQualityChecker


def run_validation(config: dict) -> dict:
    """Run data validation on downloaded raw data.

    Loads the latest raw CSV artifact, runs DataQualityChecker.validate(),
    and returns a summary dict.

    For RED: logs ERROR, returns can_proceed=False.
    For YELLOW: logs WARNING "operator review required", returns can_proceed="operator_review".
    For GREEN: logs INFO, returns can_proceed=True.
    """
    logger = logging.getLogger("data_pipeline.validator")

    pipeline_cfg = config["data_pipeline"]
    storage_path = Path(pipeline_cfg["storage_path"])
    dl_cfg = pipeline_cfg["download"]

    pairs = dl_cfg["pairs"]
    start_date = date.fromisoformat(dl_cfg["start_date"])
    end_date = date.fromisoformat(dl_cfg["end_date"])
    resolution = dl_cfg.get("resolution", "M1")

    checker = DataQualityChecker(config, logger)
    summary = {"pairs": {}, "overall_can_proceed": True}

    for pair in pairs:
        dataset_id = f"{pair}_{start_date.isoformat()}_{end_date.isoformat()}_{resolution}"

        # Find latest version
        raw_dir = storage_path / "raw" / dataset_id
        if not raw_dir.exists():
            logger.error(
                "No raw data found at %s", str(raw_dir),
                extra={"ctx": {
                    "component": "quality_checker",
                    "stage": "data_pipeline",
                    "pair": pair,
                    "error_code": "DATA_QUALITY_FAILED",
                }},
            )
            summary["pairs"][pair] = {"error": "No raw data found", "can_proceed": False}
            summary["overall_can_proceed"] = False
            continue

        versions = sorted(
            [d for d in raw_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
            key=lambda d: int(d.name[1:]) if d.name[1:].isdigit() else 0,
        )
        if not versions:
            logger.error("No versions found in %s", str(raw_dir))
            summary["pairs"][pair] = {"error": "No versions found", "can_proceed": False}
            summary["overall_can_proceed"] = False
            continue

        latest_version = versions[-1]
        version_str = latest_version.name

        # Load raw data
        csv_path = latest_version / f"{dataset_id}.csv"
        if not csv_path.exists():
            logger.error("Raw CSV not found: %s", str(csv_path))
            summary["pairs"][pair] = {"error": f"Raw CSV not found: {csv_path}", "can_proceed": False}
            summary["overall_can_proceed"] = False
            continue

        logger.info(
            "Loading raw data: %s", str(csv_path),
            extra={"ctx": {"component": "quality_checker", "stage": "data_pipeline", "pair": pair}},
        )
        df = pd.read_csv(csv_path)

        result = checker.validate(
            df=df,
            pair=pair,
            resolution=resolution,
            start_date=start_date,
            end_date=end_date,
            storage_path=storage_path,
            dataset_id=dataset_id,
            version=version_str,
        )

        # Log based on rating
        if result.rating == "RED":
            logger.error(
                "Data quality RED for %s — pipeline progression blocked. Score: %.4f",
                pair, result.quality_score,
                extra={"ctx": {
                    "component": "quality_checker",
                    "stage": "data_pipeline",
                    "pair": pair,
                    "error_code": "DATA_QUALITY_FAILED",
                    "quality_score": result.quality_score,
                    "rating": result.rating,
                }},
            )
        elif result.rating == "YELLOW":
            logger.warning(
                "Data quality YELLOW for %s — operator review required. Score: %.4f",
                pair, result.quality_score,
                extra={"ctx": {
                    "component": "quality_checker",
                    "stage": "data_pipeline",
                    "pair": pair,
                    "quality_score": result.quality_score,
                    "rating": result.rating,
                }},
            )
        else:
            logger.info(
                "Data quality GREEN for %s — pipeline can proceed. Score: %.4f",
                pair, result.quality_score,
                extra={"ctx": {
                    "component": "quality_checker",
                    "stage": "data_pipeline",
                    "pair": pair,
                    "quality_score": result.quality_score,
                    "rating": result.rating,
                }},
            )

        pair_result = {
            "quality_score": result.quality_score,
            "rating": result.rating,
            "report_path": str(result.report_path),
            "can_proceed": result.can_proceed,
            "quarantined_bars": int(result.validated_df["quarantined"].sum()),
            "total_bars": len(result.validated_df),
        }
        summary["pairs"][pair] = pair_result

        if result.can_proceed is False:
            summary["overall_can_proceed"] = False
        elif result.can_proceed == "operator_review" and summary["overall_can_proceed"] is True:
            summary["overall_can_proceed"] = "operator_review"

    return summary
