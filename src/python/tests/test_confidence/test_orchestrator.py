"""Tests for confidence scoring orchestrator (Task 9)."""
import json
from pathlib import Path

import pytest

from confidence.config import AnomalyConfig, ConfidenceConfig, HardGateConfig, ThresholdConfig, WeightConfig
from confidence.models import CandidateRating, ValidationEvidencePack
from confidence.orchestrator import ConfidenceOrchestrator


def _default_config() -> ConfidenceConfig:
    return ConfidenceConfig(
        hard_gates=HardGateConfig(True, 0.40, 1.5),
        weights=WeightConfig(0.25, 0.15, 0.15, 0.15, 0.15, 0.15),
        thresholds=ThresholdConfig(0.70, 0.40),
        anomaly=AnomalyConfig(20),
    )


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
        "per_stage_metric_ids": {"walk_forward": f"wf_{cid}", "cpcv": f"cpcv_{cid}"},
        "chart_data_refs": {"equity_curves": f"artifacts/.../equity-{cid}.arrow"},
    }


def _short_circuited_manifest(cid: int = 88) -> dict:
    return {
        "candidate_id": cid,
        "optimization_run_id": "opt_test",
        "strategy_id": "ma_crossover",
        "total_optimization_trials": 5000,
        "candidate_rank": 5,
        "validation_config_hash": "sha256:val_abc",
        "research_brief_versions": {"5A": "v1"},
        "gate_results": {
            "dsr_passed": True, "dsr_value": 1.5,
            "pbo_value": 0.55, "pbo_passed": False, "short_circuited": True,
            "hard_gate_failures": ["pbo_threshold"],
        },
        "per_stage_summaries": {
            "walk_forward": {"median_oos_sharpe": 0.4, "window_count": 10, "negative_windows": 4},
            "cpcv": {"pbo": 0.55, "mean_oos_sharpe": 0.3, "mean_is_sharpe": 0.5},
        },
        "per_stage_metric_ids": {},
        "chart_data_refs": {},
    }


def _write_per_candidate_manifests(dir_path: Path, manifests: list[dict]) -> None:
    """Write per-candidate manifests to directory."""
    dir_path.mkdir(parents=True, exist_ok=True)
    for m in manifests:
        cid = m["candidate_id"]
        with open(dir_path / f"gauntlet-manifest-candidate-{cid}.json", "w") as f:
            json.dump(m, f)


class TestOrchestratorScoresMultiple:
    def test_orchestrator_scores_multiple_candidates(self, tmp_path):
        gauntlet_dir = tmp_path / "gauntlet"
        output_dir = tmp_path / "scoring"
        manifests = [_green_manifest(1), _green_manifest(2), _green_manifest(3)]
        _write_per_candidate_manifests(gauntlet_dir, manifests)

        orch = ConfidenceOrchestrator(_default_config())
        manifest_path = orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        assert manifest_path.exists()
        with open(manifest_path) as f:
            agg = json.load(f)
        assert len(agg["candidates"]) == 3
        assert agg["optimization_run_id"] == "opt_test"


class TestOrchestratorPersistsAll:
    def test_orchestrator_persists_all_artifacts(self, tmp_path):
        gauntlet_dir = tmp_path / "gauntlet"
        output_dir = tmp_path / "scoring"
        _write_per_candidate_manifests(gauntlet_dir, [_green_manifest(42)])

        orch = ConfidenceOrchestrator(_default_config())
        orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        # Evidence pack exists
        assert (output_dir / "evidence-pack-candidate-42.json").exists()
        # Triage summary exists
        assert (output_dir / "evidence-triage-candidate-42.json").exists()
        # Scoring manifest exists
        assert (output_dir / "scoring-manifest.json").exists()
        # No .partial files
        assert len(list(output_dir.glob("*.partial"))) == 0

        # Verify evidence pack round-trips
        with open(output_dir / "evidence-pack-candidate-42.json") as f:
            data = json.load(f)
        pack = ValidationEvidencePack.from_json(data)
        assert pack.candidate_id == 42
        assert pack.confidence_score.rating == CandidateRating.GREEN


class TestOrchestratorShortCircuited:
    def test_orchestrator_handles_short_circuited_candidates(self, tmp_path):
        gauntlet_dir = tmp_path / "gauntlet"
        output_dir = tmp_path / "scoring"
        manifests = [_green_manifest(1), _short_circuited_manifest(88)]
        _write_per_candidate_manifests(gauntlet_dir, manifests)

        orch = ConfidenceOrchestrator(_default_config())
        manifest_path = orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        with open(manifest_path) as f:
            agg = json.load(f)

        assert len(agg["candidates"]) == 2

        # Short-circuited candidate should be RED
        red_cand = next(c for c in agg["candidates"] if c["candidate_id"] == 88)
        assert red_cand["rating"] == "RED"
        assert red_cand["hard_gates_passed"] is False

        # Green candidate should still be GREEN
        green_cand = next(c for c in agg["candidates"] if c["candidate_id"] == 1)
        assert green_cand["rating"] == "GREEN"

        # Sorted by composite score descending
        assert agg["candidates"][0]["composite_score"] >= agg["candidates"][1]["composite_score"]

        # Evidence pack exists for short-circuited candidate too (anti-pattern #8)
        assert (output_dir / "evidence-pack-candidate-88.json").exists()
