"""SelectionExecutor — StageExecutor protocol implementation (Story 5.6, Task 7).

Integrates the selection subsystem with the pipeline orchestrator's stage runner.
Follows the pattern established in confidence/executor.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artifacts.storage import crash_safe_write_json
from logging_setup.setup import get_logger
from orchestrator.pipeline_state import PipelineStage
from orchestrator.stage_runner import StageResult
from selection.config import selection_config_from_dict
from selection.orchestrator import SelectionOrchestrator

logger = get_logger("selection.executor")


class SelectionExecutor:
    """StageExecutor for the SELECTING pipeline stage.

    Implements the StageExecutor protocol from Story 3-3:
    - execute(strategy_id, context) -> StageResult
    - validate_artifact(artifact_path, manifest_ref) -> bool
    """

    stage = PipelineStage.SELECTING

    def __init__(self, config: dict[str, Any]):
        self._config = selection_config_from_dict(config.get("selection", config))
        self._hard_gate_config = config.get("hard_gates", config.get("confidence", {}).get("hard_gates", {
            "dsr_pass_required": True,
            "pbo_max_threshold": 0.40,
            "cost_stress_survival_multiplier": 1.5,
        }))

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Run advanced candidate selection pipeline.

        Expected context keys:
        - optimization_manifest: dict with candidates_path, optimization_run_id
        - scoring_manifest_path: (optional) Path to scoring manifest.json
        - artifacts_dir: Base artifacts directory
        - version_dir: Version directory path (e.g., artifacts/strategy_id/v001)
        """
        try:
            opt_manifest = context.get("optimization_manifest", {})
            candidates_path = Path(
                opt_manifest.get("candidates_path", "")
                or context.get("candidates_path", "")
            )
            optimization_run_id = str(
                opt_manifest.get("optimization_run_id", "")
                or context.get("optimization_run_id", "unknown")
            )

            scoring_manifest_path = None
            scoring_path_str = context.get("scoring_manifest_path")
            if scoring_path_str:
                scoring_manifest_path = Path(scoring_path_str)
                if not scoring_manifest_path.exists():
                    logger.info(
                        "Scoring manifest not found — proceeding without",
                        extra={"component": "selection.executor"},
                    )
                    scoring_manifest_path = None

            equity_curves_dir = None
            ec_dir_str = context.get("equity_curves_dir")
            if ec_dir_str:
                equity_curves_dir = Path(ec_dir_str)

            version_dir = Path(
                context.get("version_dir", f"artifacts/{strategy_id}/v001")
            )
            output_dir = version_dir / "selection"
            output_dir.mkdir(parents=True, exist_ok=True)

            orchestrator = SelectionOrchestrator()
            manifest, viz_data = orchestrator.run_selection(
                candidates_path=candidates_path,
                equity_curves_dir=equity_curves_dir,
                scoring_manifest_path=scoring_manifest_path,
                config=self._config,
                hard_gate_config=self._hard_gate_config,
                output_dir=output_dir,
                optimization_run_id=optimization_run_id,
                strategy_id=strategy_id,
            )

            # Write manifest via crash_safe_write
            manifest_path = output_dir / "manifest.json"
            crash_safe_write_json(manifest.to_json(), manifest_path)

            # Write visualization data
            viz_dir = output_dir / "viz"
            viz_dir.mkdir(parents=True, exist_ok=True)
            for viz_name, viz_content in viz_data.items():
                viz_path = viz_dir / f"{viz_name}.json"
                crash_safe_write_json(viz_content, viz_path)

            logger.info(
                "Selection executor complete",
                extra={
                    "component": "selection.executor",
                    "ctx": {
                        "strategy_id": strategy_id,
                        "selected": len(manifest.selected_candidates),
                        "manifest_path": str(manifest_path),
                    },
                },
            )

            return StageResult(
                artifact_path=str(output_dir),
                manifest_ref=str(manifest_path),
                outcome="success",
                metrics={
                    "selected_count": len(manifest.selected_candidates),
                    "cluster_count": len(manifest.clusters),
                    "archive_cells": len(manifest.diversity_archive),
                    "funnel_input": manifest.funnel_stats.total_input,
                    "funnel_output": manifest.funnel_stats.final_selected,
                },
            )

        except FileNotFoundError as e:
            logger.error(
                "Selection input not found",
                extra={"component": "selection.executor", "ctx": {"error": str(e)}},
            )
            return StageResult(outcome="failed", error=None, metrics={"error": str(e)})
        except Exception as e:
            logger.error(
                "Selection executor failed",
                extra={"component": "selection.executor", "ctx": {"error": str(e)}},
            )
            return StageResult(outcome="failed", error=None, metrics={"error": str(e)})

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify selection artifact integrity via manifest.

        Checks that all required manifest fields are populated.
        """
        try:
            with open(manifest_ref, "r", encoding="utf-8") as f:
                data = json.load(f)

            required_fields = [
                "strategy_id",
                "optimization_run_id",
                "selected_candidates",
                "clusters",
                "diversity_archive",
                "funnel_stats",
                "config_hash",
                "selected_at",
                "upstream_refs",
                "critic_weights",
                "gate_failure_summary",
                "random_seed_used",
            ]

            for field in required_fields:
                if field not in data:
                    logger.error(
                        f"Selection manifest missing required field: {field}",
                        extra={"component": "selection.executor"},
                    )
                    return False

            # Validate upstream refs are populated
            refs = data.get("upstream_refs", {})
            if not refs.get("candidates_path") or not refs.get("candidates_hash"):
                logger.error(
                    "Selection manifest has empty upstream_refs",
                    extra={"component": "selection.executor"},
                )
                return False

            return True

        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Failed to validate selection artifact",
                extra={"component": "selection.executor", "ctx": {"error": str(e)}},
            )
            return False
