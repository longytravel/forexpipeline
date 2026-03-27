"""ConfidenceExecutor — StageExecutor protocol implementation (Story 5.5, Task 10).

Integrates confidence scoring with the pipeline orchestrator's stage runner.
Implements the StageExecutor protocol from Story 3-3.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from artifacts.storage import crash_safe_write_json
from confidence.config import confidence_config_from_dict
from confidence.models import OperatorReview, ValidationEvidencePack
from confidence.orchestrator import ConfidenceOrchestrator
from logging_setup.setup import get_logger
from orchestrator.pipeline_state import PipelineStage
from orchestrator.stage_runner import StageResult

logger = get_logger("confidence.executor")


class ConfidenceExecutor:
    """StageExecutor for the SCORING pipeline stage.

    Implements the StageExecutor protocol from Story 3-3:
    - execute(strategy_id, context) -> StageResult
    - validate_artifact(artifact_path, manifest_ref) -> bool
    """

    stage = PipelineStage.SCORING

    def __init__(self, config: dict):
        self._config = confidence_config_from_dict(config)

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Load gauntlet results, run confidence scoring, write evidence packs.

        Expected context keys:
        - validation_artifact_path: Path to validation gauntlet output
        - optimization_manifest: dict of optimization manifest
        - output_dir: Path for scoring output (optional)
        """
        try:
            validation_path = Path(context.get("validation_artifact_path", ""))
            optimization_manifest = context.get("optimization_manifest", {})
            version = context.get("version", "v001")
            output_dir = Path(context.get(
                "output_dir",
                f"artifacts/{strategy_id}/{version}/validation",
            ))

            orchestrator = ConfidenceOrchestrator(self._config)
            manifest_path = orchestrator.score_all_candidates(
                gauntlet_results_dir=validation_path,
                optimization_manifest=optimization_manifest,
                output_dir=output_dir,
            )

            # Load manifest to extract metrics
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            candidates = manifest_data.get("candidates", [])
            n_green = sum(1 for c in candidates if c["rating"] == "GREEN")
            n_yellow = sum(1 for c in candidates if c["rating"] == "YELLOW")
            n_red = sum(1 for c in candidates if c["rating"] == "RED")

            return StageResult(
                artifact_path=str(output_dir),
                manifest_ref=str(manifest_path),
                outcome="success",
                metrics={
                    "n_candidates": len(candidates),
                    "n_green": n_green,
                    "n_yellow": n_yellow,
                    "n_red": n_red,
                },
            )

        except Exception as e:
            logger.error(
                f"Confidence scoring failed: {e}",
                extra={
                    "component": "confidence.executor",
                    "ctx": {"strategy_id": strategy_id, "error": str(e)},
                },
            )
            return StageResult(
                outcome="failed",
                error=str(e),
                metrics={},
            )

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify scoring artifacts via manifest check."""
        if not manifest_ref.exists():
            return False

        try:
            manifest = json.loads(manifest_ref.read_text(encoding="utf-8"))
            required_fields = [
                "optimization_run_id",
                "confidence_config_hash",
                "scored_at",
                "candidates",
            ]
            for field_name in required_fields:
                if field_name not in manifest:
                    logger.warning(
                        f"Scoring manifest missing required field: {field_name}",
                        extra={"component": "confidence.executor"},
                    )
                    return False
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                f"Failed to validate scoring artifact: {e}",
                extra={"component": "confidence.executor"},
            )
            return False


def record_operator_review(
    candidate_id: int,
    decision: str,
    rationale: str,
    operator_notes: str,
    evidence_pack_path: str,
    output_dir: Path,
    strategy_id: str = "unknown",
) -> Path:
    """Record an operator review decision as a separate append-only artifact.

    Does NOT mutate the immutable evidence pack. Appends to the existing
    review list (AC8: append-only, not overwrite).
    """
    review = OperatorReview(
        candidate_id=candidate_id,
        decision=decision,
        rationale=rationale,
        operator_notes=operator_notes,
        decision_timestamp=datetime.now(timezone.utc).isoformat(),
        evidence_pack_path=evidence_pack_path,
    )

    review_path = output_dir / f"operator-review-candidate-{candidate_id}.json"

    # Append-only: read existing reviews and add new one
    existing_reviews: list[dict] = []
    if review_path.exists():
        try:
            data = json.loads(review_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existing_reviews = data
            else:
                # Migrate single-review format to list
                existing_reviews = [data]
        except (json.JSONDecodeError, OSError):
            existing_reviews = []

    existing_reviews.append(review.to_json())
    crash_safe_write_json(existing_reviews, review_path)

    logger.info(
        f"Operator review recorded: candidate {candidate_id} → {decision} "
        f"(review #{len(existing_reviews)})",
        extra={"component": "confidence.executor", "stage": "SCORING", "strategy_id": strategy_id, "ctx": {
            "candidate_id": candidate_id,
            "decision": decision,
            "review_count": len(existing_reviews),
        }},
    )

    return review_path
