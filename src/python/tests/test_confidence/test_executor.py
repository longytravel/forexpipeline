"""Tests for pipeline state machine extensions and executor (Task 10)."""
import json
from pathlib import Path

import pytest

from confidence.executor import ConfidenceExecutor, record_operator_review
from orchestrator.pipeline_state import (
    PipelineStage,
    STAGE_GRAPH,
    STAGE_ORDER,
    TransitionType,
)


def _confidence_config_dict() -> dict:
    return {
        "hard_gates": {
            "dsr_pass_required": True,
            "pbo_max_threshold": 0.40,
            "cost_stress_survival_multiplier": 1.5,
        },
        "weights": {
            "walk_forward_oos_consistency": 0.25,
            "cpcv_pbo_margin": 0.15,
            "parameter_stability": 0.15,
            "monte_carlo_stress_survival": 0.15,
            "regime_uniformity": 0.15,
            "in_sample_oos_coherence": 0.15,
        },
        "thresholds": {"green_minimum": 0.70, "yellow_minimum": 0.40},
        "anomaly": {"min_population_size": 20},
    }


def _green_manifest(cid: int = 42) -> dict:
    return {
        "candidate_id": cid,
        "optimization_run_id": "opt_test",
        "strategy_id": "ma_crossover",
        "total_optimization_trials": 5000,
        "candidate_rank": 1,
        "validation_config_hash": "sha256:val_abc",
        "research_brief_versions": {"5A": "v1"},
        "gate_results": {
            "dsr_passed": True, "dsr_value": 2.31,
            "pbo_value": 0.18, "pbo_passed": True, "short_circuited": False,
        },
        "per_stage_summaries": {
            "walk_forward": {"median_oos_sharpe": 1.2, "window_count": 10, "negative_windows": 1},
            "cpcv": {"pbo": 0.18, "mean_oos_sharpe": 1.1, "mean_is_sharpe": 1.3},
            "perturbation": {"max_sensitivity": 0.20, "mean_sensitivity": 0.11, "cliff_count": 0},
            "monte_carlo": {"bootstrap_ci_lower": 0.15, "stress_survived": True, "permutation_p_value": 0.03},
            "regime": {"weakest_sharpe": 0.60, "strongest_sharpe": 1.20, "insufficient_buckets": 0},
        },
        "per_stage_metric_ids": {},
        "chart_data_refs": {},
    }


class TestPipelineStateScoringStages:
    def test_scoring_stage_exists(self):
        assert PipelineStage.SCORING == "scoring"
        assert PipelineStage.SCORING_COMPLETE == "scoring-complete"

    def test_scoring_in_stage_order(self):
        assert PipelineStage.SCORING in STAGE_ORDER
        assert PipelineStage.SCORING_COMPLETE in STAGE_ORDER

    def test_validation_complete_transitions_to_scoring(self):
        transition = STAGE_GRAPH[PipelineStage.VALIDATION_COMPLETE]
        assert transition.to_stage == PipelineStage.SCORING
        assert transition.transition_type == TransitionType.AUTOMATIC

    def test_scoring_transitions_to_scoring_complete(self):
        transition = STAGE_GRAPH[PipelineStage.SCORING]
        assert transition.to_stage == PipelineStage.SCORING_COMPLETE
        assert transition.transition_type == TransitionType.AUTOMATIC


class TestScoringExecutorProtocol:
    def test_scoring_executor_protocol(self, tmp_path):
        """ConfidenceExecutor follows StageExecutor protocol."""
        gauntlet_dir = tmp_path / "gauntlet"
        gauntlet_dir.mkdir()
        with open(gauntlet_dir / "gauntlet-manifest-candidate-42.json", "w") as f:
            json.dump(_green_manifest(), f)

        output_dir = tmp_path / "scoring"
        executor = ConfidenceExecutor(_confidence_config_dict())
        result = executor.execute("ma_crossover", {
            "validation_artifact_path": str(gauntlet_dir),
            "optimization_manifest": {"optimization_run_id": "opt_test"},
            "output_dir": str(output_dir),
        })

        assert result.outcome == "success"
        assert result.artifact_path == str(output_dir)
        assert result.metrics["n_candidates"] == 1
        assert result.metrics["n_green"] == 1

    def test_scoring_executor_validate_artifact(self, tmp_path):
        """validate_artifact checks manifest completeness."""
        manifest_path = tmp_path / "scoring-manifest.json"
        manifest_path.write_text(json.dumps({
            "optimization_run_id": "opt_test",
            "confidence_config_hash": "sha256:abc",
            "scored_at": "2026-03-22T10:00:00Z",
            "candidates": [],
        }))

        executor = ConfidenceExecutor(_confidence_config_dict())
        assert executor.validate_artifact(tmp_path, manifest_path) is True

    def test_scoring_executor_validate_missing_field(self, tmp_path):
        """validate_artifact rejects manifest with missing fields."""
        manifest_path = tmp_path / "scoring-manifest.json"
        manifest_path.write_text(json.dumps({"optimization_run_id": "test"}))

        executor = ConfidenceExecutor(_confidence_config_dict())
        assert executor.validate_artifact(tmp_path, manifest_path) is False


class TestOperatorDecisions:
    def test_operator_accept_decision(self, tmp_path):
        review_path = record_operator_review(
            candidate_id=42,
            decision="accept",
            rationale="Strong metrics across all dimensions",
            operator_notes="Proceed to live",
            evidence_pack_path="artifacts/.../evidence-pack-candidate-42.json",
            output_dir=tmp_path,
        )
        assert review_path.exists()
        with open(review_path) as f:
            data = json.load(f)
        # Append-only: stored as list
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["candidate_id"] == 42
        assert data[0]["decision"] == "accept"
        assert data[0]["decision_timestamp"]  # Not empty

    def test_operator_reject_decision(self, tmp_path):
        review_path = record_operator_review(
            candidate_id=99,
            decision="reject",
            rationale="Regime concentration too severe",
            operator_notes="Re-optimize with session filter",
            evidence_pack_path="artifacts/.../evidence-pack-candidate-99.json",
            output_dir=tmp_path,
        )
        assert review_path.exists()
        with open(review_path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert data[0]["decision"] == "reject"
        assert "Regime concentration" in data[0]["rationale"]
