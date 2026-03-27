"""ValidationExecutor — StageExecutor protocol implementation (Story 5.4, Task 11).

Integrates the validation gauntlet with the pipeline orchestrator's
stage runner. Implements the StageExecutor protocol from Story 3-3.
"""
from __future__ import annotations

import json
from pathlib import Path

from logging_setup.setup import get_logger
from orchestrator.pipeline_state import PipelineStage
from orchestrator.stage_runner import StageResult
from validation.config import ValidationConfig
from validation.gauntlet import ValidationGauntlet
from validation.results import write_gauntlet_manifest, write_stage_artifact, write_stage_summary

logger = get_logger("validation.executor")


class ValidationExecutor:
    """StageExecutor for the VALIDATING pipeline stage.

    Implements the StageExecutor protocol from Story 3-3:
    - execute(strategy_id, context) -> StageResult
    - validate_artifact(artifact_path, manifest_ref) -> bool
    """

    stage = PipelineStage.VALIDATING

    def __init__(self, config: dict):
        self._config = ValidationConfig.from_dict(config)

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Load promoted candidates from context, run gauntlet, write results.

        Expected context keys:
        - optimization_artifact_path: Path to optimization output
        - market_data_path: Path to market data Arrow IPC
        - strategy_spec: dict of strategy specification
        - cost_model: dict of cost model
        - config: full pipeline config dict
        """
        try:
            optimization_artifact_path = Path(context.get("optimization_artifact_path", ""))
            market_data_path = Path(context.get("market_data_path", ""))
            strategy_spec = context.get("strategy_spec", {})
            cost_model = context.get("cost_model", {})
            output_dir = Path(context.get("output_dir", f"artifacts/{strategy_id}/validation"))

            # Load promoted candidates from optimization output
            candidates, optimization_manifest = _load_optimization_output(
                optimization_artifact_path
            )

            # Build dispatcher from context (uses Rust bridge)
            dispatcher = context.get("dispatcher")

            gauntlet = ValidationGauntlet(
                config=self._config,
                dispatcher=dispatcher,
            )

            results = gauntlet.run(
                candidates=candidates,
                market_data_path=market_data_path,
                strategy_spec=strategy_spec,
                cost_model=cost_model,
                optimization_manifest=optimization_manifest,
                output_dir=output_dir,
            )

            # Write artifacts for each candidate's stages
            artifact_paths = {}
            for cv in results.candidates:
                candidate_dir = output_dir / f"candidate_{cv.candidate_id:03d}"
                cand_artifacts = {}
                for stage_name, stage_output in cv.stages.items():
                    if stage_output.result is not None:
                        art_path = write_stage_artifact(stage_name, stage_output.result, candidate_dir)
                        write_stage_summary(stage_name, stage_output.result, candidate_dir)
                        cand_artifacts[stage_name] = str(art_path)
                artifact_paths[cv.candidate_id] = cand_artifacts

            # Write gauntlet manifest with full downstream contract fields
            manifest_path = write_gauntlet_manifest(
                results, optimization_manifest, output_dir,
                validation_config=context.get("config", {}).get("validation", {}),
                artifact_paths=artifact_paths,
            )

            return StageResult(
                artifact_path=str(output_dir),
                manifest_ref=str(manifest_path),
                outcome="success",
                metrics={
                    "n_candidates": len(results.candidates),
                    "dsr_passed": results.dsr.passed if results.dsr else None,
                    "short_circuited": sum(
                        1 for c in results.candidates if c.short_circuited
                    ),
                },
            )

        except Exception as e:
            logger.error(
                f"Validation execution failed: {e}",
                extra={
                    "component": "validation.executor",
                    "ctx": {"strategy_id": strategy_id, "error": str(e)},
                },
            )
            return StageResult(
                outcome="failed",
                error=str(e),
                metrics={},
            )

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify validation artifacts via manifest hash."""
        if not manifest_ref.exists():
            return False

        try:
            manifest = json.loads(manifest_ref.read_text(encoding="utf-8"))
            # Verify manifest has all required downstream contract fields
            required_fields = [
                "optimization_run_id",
                "total_optimization_trials",
                "n_candidates",
                "stages",
                "gate_results",
                "dsr",
                "candidates",
                "chart_data_refs",
                "config_hash",
            ]
            for field_name in required_fields:
                if field_name not in manifest:
                    logger.warning(
                        f"Manifest missing required field: {field_name}",
                        extra={"component": "validation.executor"},
                    )
                    return False
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                f"Failed to validate artifact: {e}",
                extra={"component": "validation.executor"},
            )
            return False


def _load_optimization_output(
    optimization_artifact_path: Path,
) -> tuple[list[dict], dict]:
    """Load promoted candidates and manifest from optimization output.

    Returns (candidates_list, optimization_manifest).
    """
    if not optimization_artifact_path.exists():
        logger.warning(
            f"Optimization artifact not found: {optimization_artifact_path}",
            extra={"component": "validation.executor"},
        )
        return [], {"run_id": "", "total_trials": 0}

    # Try loading promoted candidates from Arrow IPC
    promoted_path = optimization_artifact_path / "promoted_candidates.arrow"
    manifest_path = optimization_artifact_path / "optimization_manifest.json"

    candidates = []
    manifest = {"run_id": "", "total_trials": 0}

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if promoted_path.exists():
        import pyarrow.ipc
        reader = pyarrow.ipc.open_file(str(promoted_path))
        table = reader.read_all()
        if "params_json" in table.column_names:
            for row_idx in range(len(table)):
                params = json.loads(table.column("params_json")[row_idx].as_py())
                candidates.append(params)

    return candidates, manifest
