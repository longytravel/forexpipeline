"""Crash recovery — resume from checkpoint with safe partial cleanup (NFR11).

Startup ordering:
1. Load pipeline state
2. Read within-stage checkpoint to identify referenced partial files
3. Clean unreferenced .partial files (exclude checkpoint-referenced ones)
4. Verify last completed artifact via executor
5. Resume from next incomplete stage
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from artifacts.storage import clean_partial_files
from logging_setup.setup import get_logger
from orchestrator.pipeline_state import PipelineState, WithinStageCheckpoint

if TYPE_CHECKING:
    from orchestrator.stage_runner import StageExecutor

logger = get_logger("pipeline.recovery")


def verify_last_artifact(state: PipelineState, executor: StageExecutor) -> bool:
    """Verify the last completed artifact via the executor's validation.

    Single validation path — delegates to executor, no duplicate logic (anti-pattern #11).
    Returns True if valid or if no artifact to verify.
    """
    if not state.completed_stages:
        return True

    last = state.completed_stages[-1]

    if last.artifact_path is None or last.manifest_ref is None:
        logger.info(
            "No artifact to verify for last completed stage",
            extra={
                "component": "pipeline.recovery",
                "stage": last.stage,
                "strategy_id": state.strategy_id,
                "ctx": {"outcome": last.outcome},
            },
        )
        return True

    artifact_path = Path(last.artifact_path)
    manifest_path = Path(last.manifest_ref)

    valid = executor.validate_artifact(artifact_path, manifest_path)

    logger.info(
        f"Artifact verification: {'valid' if valid else 'INVALID'}",
        extra={
            "component": "pipeline.recovery",
            "stage": last.stage,
            "strategy_id": state.strategy_id,
            "ctx": {
                "artifact": str(artifact_path),
                "manifest": str(manifest_path),
                "valid": valid,
            },
        },
    )

    return valid


def recover_from_checkpoint(
    strategy_id: str, artifacts_dir: Path
) -> WithinStageCheckpoint | None:
    """Read and validate within-stage checkpoint for a strategy.

    Checkpoint file: ``artifacts/{strategy_id}/checkpoint-{stage}.json``
    Returns the checkpoint if valid, None otherwise.
    """
    strategy_dir = artifacts_dir / strategy_id

    # Find any checkpoint files for this strategy
    if not strategy_dir.exists():
        return None

    checkpoint_files = list(strategy_dir.glob("checkpoint-*.json"))
    if not checkpoint_files:
        return None

    # Use the most recently modified checkpoint
    latest = max(checkpoint_files, key=lambda p: p.stat().st_mtime)

    try:
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)

        checkpoint = WithinStageCheckpoint.from_dict(data)

        logger.info(
            f"Within-stage checkpoint recovered: {checkpoint.stage}",
            extra={
                "component": "pipeline.recovery",
                "stage": checkpoint.stage,
                "strategy_id": strategy_id,
                "ctx": {
                    "progress_pct": checkpoint.progress_pct,
                    "last_batch": checkpoint.last_completed_batch,
                    "total_batches": checkpoint.total_batches,
                    "checkpoint_file": str(latest),
                },
            },
        )

        return checkpoint

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning(
            f"Invalid checkpoint file {latest}: {exc}",
            extra={
                "component": "pipeline.recovery",
                "strategy_id": strategy_id,
                "ctx": {"file": str(latest), "error": str(exc)},
            },
        )
        return None


def startup_cleanup(
    strategy_id: str, artifacts_dir: Path, state: PipelineState | None = None,
) -> list[str]:
    """Safe startup cleanup: clean .partial files excluding checkpoint-referenced ones.

    Ordering:
    1. Read checkpoint to identify referenced partial files.
    2. Clean only unreferenced .partial files.

    Returns list of deleted partial file paths.
    """
    strategy_dir = artifacts_dir / strategy_id

    # Step 1: Identify checkpoint-referenced partial files
    exclude: set[str] = set()

    # From pipeline state checkpoint
    if state and state.checkpoint and state.checkpoint.partial_artifact_path:
        exclude.add(str((strategy_dir / state.checkpoint.partial_artifact_path).resolve()))

    # From within-stage checkpoint files
    checkpoint = recover_from_checkpoint(strategy_id, artifacts_dir)
    if checkpoint and checkpoint.partial_artifact_path:
        partial_path = Path(checkpoint.partial_artifact_path)
        if not partial_path.is_absolute():
            partial_path = strategy_dir / partial_path
        exclude.add(str(partial_path.resolve()))

    # Step 2: Clean unreferenced partials
    deleted = clean_partial_files(strategy_dir, exclude=exclude)

    if deleted:
        logger.info(
            f"Startup cleanup: removed {len(deleted)} unreferenced .partial files",
            extra={
                "component": "pipeline.recovery",
                "strategy_id": strategy_id,
                "ctx": {"deleted": deleted, "excluded": list(exclude)},
            },
        )

    return deleted
