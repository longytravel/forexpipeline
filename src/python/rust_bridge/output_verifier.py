"""Verify Rust backtester output files exist and schemas match contracts (AC #3).

Returns file path references, NOT materialized tables — full ingestion and
manifest creation is Story 3.6's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from logging_setup.setup import get_logger

logger = get_logger("pipeline.rust_bridge")

# Expected deterministic output files from the Rust backtester.
EXPECTED_OUTPUT_FILES = [
    "trade-log.arrow",
    "equity-curve.arrow",
    "metrics.arrow",
]


@dataclass
class BacktestOutputRef:
    """Lightweight reference to backtest output files (no data materialized)."""

    output_dir: Path
    trade_log_path: Path
    equity_curve_path: Path
    metrics_path: Path
    config_hash: str


def verify_output(output_dir: Path, config_hash: str) -> BacktestOutputRef:
    """Verify expected output files exist in the output directory.

    Raises ``FileNotFoundError`` if any expected file is missing.
    Returns a ``BacktestOutputRef`` with paths to the verified output files.

    Note: Fold score verification is NOT done here automatically.
    Callers should invoke ``verify_fold_scores()`` separately when
    fold-aware evaluation was used.
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")

    missing = []
    for filename in EXPECTED_OUTPUT_FILES:
        path = output_dir / filename
        if not path.exists():
            missing.append(filename)
        elif path.stat().st_size == 0:
            missing.append(f"{filename} (empty)")

    if missing:
        raise FileNotFoundError(
            f"Missing or empty output files in {output_dir}: {', '.join(missing)}"
        )

    # Verify no .partial files remain (crash-safe write contract, AC #3)
    # Only flag actual files — the .partial/ directory is the Rust binary's
    # crash-safe checkpoint staging area and is expected to exist.
    partials = [p for p in output_dir.glob("*.partial") if p.is_file()]
    if partials:
        partial_names = [p.name for p in partials]
        raise FileNotFoundError(
            f"Partial files remain after completion (crash-safe write failed): "
            f"{', '.join(partial_names)}"
        )

    ref = BacktestOutputRef(
        output_dir=output_dir,
        trade_log_path=output_dir / "trade-log.arrow",
        equity_curve_path=output_dir / "equity-curve.arrow",
        metrics_path=output_dir / "metrics.arrow",
        config_hash=config_hash,
    )

    logger.info(
        "Backtest output verified",
        extra={
            "component": "pipeline.rust_bridge",
            "ctx": {
                "output_dir": str(output_dir),
                "config_hash": config_hash,
                "files": EXPECTED_OUTPUT_FILES,
            },
        },
    )

    return ref


def validate_schemas(output_dir: Path) -> bool:
    """Validate Arrow schemas against contracts/arrow_schemas.toml.

    Story 3-4 performs file existence and basic validation.
    Full schema validation using pyarrow will be enabled when Story 3-5
    writes real Arrow IPC files (currently stubs).

    Returns True if all files exist and are non-empty.
    """
    output_dir = Path(output_dir)
    for filename in EXPECTED_OUTPUT_FILES:
        path = output_dir / filename
        if not path.exists() or path.stat().st_size == 0:
            return False
    return True


def verify_fold_scores(output_dir: Path, expected_folds: int) -> bool:
    """Verify per-fold score output exists and has correct fold count.

    Research Update: When fold-aware evaluation is used, the Rust binary
    writes per-fold score files. This verifier checks they exist.

    Returns True if fold scores are present and count matches.
    """
    output_dir = Path(output_dir)
    fold_scores_path = output_dir / "fold-scores.json"

    if not fold_scores_path.exists():
        logger.warning(
            "fold-scores.json not found",
            extra={
                "component": "pipeline.rust_bridge",
                "ctx": {"output_dir": str(output_dir)},
            },
        )
        return False

    try:
        import json
        data = json.loads(fold_scores_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return False
        if len(data) != expected_folds:
            logger.warning(
                f"Fold count mismatch: expected {expected_folds}, got {len(data)}",
                extra={
                    "component": "pipeline.rust_bridge",
                    "ctx": {
                        "expected": expected_folds,
                        "actual": len(data),
                    },
                },
            )
            return False
        return True
    except (json.JSONDecodeError, OSError):
        return False
