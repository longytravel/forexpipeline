"""StageExecutor for the BACKTEST_COMPLETE pipeline stage (Story 3.6).

Runs result processing (Arrow publish → SQLite ingest → Parquet archive →
manifest) as an internal step within the backtest-complete → review-pending
transition.  Registered with StageRunner for ``PipelineStage.BACKTEST_COMPLETE``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from logging_setup.setup import get_logger
from orchestrator.errors import PipelineError
from orchestrator.stage_runner import StageResult
from rust_bridge.result_processor import ProcessingResult, ResultProcessor, ResultProcessingError

logger = get_logger("pipeline.rust_bridge.result_executor")


class ResultExecutor:
    """StageExecutor for the backtest-complete → review-pending transition.

    Implements the ``StageExecutor`` protocol from Story 3-3:
    - ``execute(strategy_id, context)`` → ``StageResult``
    - ``validate_artifact(artifact_path, manifest_ref)`` → ``bool``
    """

    def __init__(self, processor: ResultProcessor) -> None:
        self._processor = processor

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Process backtest results using ResultProcessor.

        Expected context keys (populated by BACKTEST_RUNNING stage):
        - artifacts_dir: Root artifacts directory
        - config_hash: Pipeline config hash
        - data_hash: Dataset hash
        - cost_model_hash: Cost model hash
        - strategy_spec_hash: Strategy spec hash
        - rust_output_dir: Directory where Rust wrote Arrow IPC output
        - strategy_spec_version: e.g. "v001"
        - cost_model_version: e.g. "v001"

        Optional context keys:
        - fold_scores: list of fold score dicts
        - input_paths: dict mapping input names to paths
        """
        now = datetime.now(timezone.utc).isoformat()
        backtest_run_id = context.get(
            "backtest_run_id",
            f"{strategy_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{context.get('config_hash', 'unknown')[:8]}",
        )

        try:
            result: ProcessingResult = self._processor.process_backtest_results(
                strategy_id=strategy_id,
                backtest_run_id=backtest_run_id,
                config_hash=context.get("config_hash", ""),
                data_hash=context.get("data_hash", ""),
                cost_model_hash=context.get("cost_model_hash", ""),
                strategy_spec_hash=context.get("strategy_spec_hash", ""),
                rust_output_dir=Path(context["rust_output_dir"]),
                strategy_spec_version=context.get("strategy_spec_version", "v001"),
                cost_model_version=context.get("cost_model_version", "v001"),
                run_timestamp=now,
                fold_scores=context.get("fold_scores"),
                input_paths=context.get("input_paths"),
            )
        except ResultProcessingError as exc:
            return StageResult(
                outcome="failed",
                error=PipelineError(
                    code="RESULT_PROCESSING_FAILED",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.rust_bridge.result_executor",
                    msg=str(exc),
                    context={"stage": exc.stage, "strategy_id": strategy_id},
                ),
            )
        except FileNotFoundError as exc:
            return StageResult(
                outcome="failed",
                error=PipelineError(
                    code="RESULT_PROCESSING_MISSING_FILE",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.rust_bridge.result_executor",
                    msg=str(exc),
                    context={"strategy_id": strategy_id},
                ),
            )
        except Exception as exc:
            return StageResult(
                outcome="failed",
                error=PipelineError(
                    code="RESULT_PROCESSING_UNEXPECTED",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.rust_bridge.result_executor",
                    msg=str(exc),
                    context={"strategy_id": strategy_id},
                ),
            )

        return StageResult(
            artifact_path=str(result.artifact_dir),
            manifest_ref=str(result.manifest_path),
            outcome="success",
            metrics={
                "version": result.version,
                "trade_count": result.trade_count,
                "backtest_run_id": result.backtest_run_id,
            },
        )

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify artifact directory and manifest exist."""
        artifact_path = Path(artifact_path)
        if not artifact_path.exists():
            return False

        manifest_path = artifact_path / "manifest.json"
        if not manifest_path.exists():
            return False

        # Verify key files exist
        backtest_dir = artifact_path / "backtest"
        required = ["trade-log.arrow", "equity-curve.arrow", "metrics.arrow"]
        return all((backtest_dir / f).exists() for f in required)
