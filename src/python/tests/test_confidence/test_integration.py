"""Integration tests for confidence scoring pipeline (Task 11)."""
import json
import shutil
from pathlib import Path

import pytest

from confidence.config import AnomalyConfig, ConfidenceConfig, HardGateConfig, ThresholdConfig, WeightConfig
from confidence.models import CandidateRating, ValidationEvidencePack
from confidence.orchestrator import ConfidenceOrchestrator

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gauntlet_output"


def _default_config() -> ConfidenceConfig:
    return ConfidenceConfig(
        hard_gates=HardGateConfig(True, 0.40, 1.5),
        weights=WeightConfig(0.25, 0.15, 0.15, 0.15, 0.15, 0.15),
        thresholds=ThresholdConfig(0.70, 0.40),
        anomaly=AnomalyConfig(20),
    )


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _setup_gauntlet_dir(tmp_path: Path, fixture_names: list[str]) -> Path:
    """Copy fixture files into a gauntlet results directory."""
    gauntlet_dir = tmp_path / "gauntlet"
    gauntlet_dir.mkdir()
    for name in fixture_names:
        data = _load_fixture(name)
        cid = data["candidate_id"]
        with open(gauntlet_dir / f"gauntlet-manifest-candidate-{cid}.json", "w") as f:
            json.dump(data, f)
    return gauntlet_dir


class TestFullScoringPipeline:
    def test_full_scoring_pipeline(self, tmp_path):
        """Mock gauntlet manifest → score → evidence pack → persist → verify."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_green.json"])
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        manifest_path = orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        # Manifest exists
        assert manifest_path.exists()
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert len(manifest["candidates"]) == 1

        # Evidence pack exists and round-trips
        pack_path = output_dir / "evidence-pack-candidate-1.json"
        assert pack_path.exists()
        with open(pack_path) as f:
            pack_data = json.load(f)
        pack = ValidationEvidencePack.from_json(pack_data)
        assert pack.candidate_id == 1
        assert pack.confidence_score.rating == CandidateRating.GREEN

        # Triage exists
        triage_path = output_dir / "evidence-triage-candidate-1.json"
        assert triage_path.exists()


class TestRedCandidateFullFlow:
    def test_red_candidate_full_flow(self, tmp_path):
        """Candidate fails PBO gate → RED → evidence pack still assembled."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_red.json"])
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        manifest_path = orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        with open(manifest_path) as f:
            manifest = json.load(f)
        cand = manifest["candidates"][0]
        assert cand["rating"] == "RED"
        assert cand["hard_gates_passed"] is False

        # Evidence pack still assembled (anti-pattern #8)
        pack_path = output_dir / "evidence-pack-candidate-3.json"
        assert pack_path.exists()
        with open(pack_path) as f:
            pack_data = json.load(f)
        assert pack_data["confidence_score"]["rating"] == "RED"


class TestGreenCandidateFullFlow:
    def test_green_candidate_full_flow(self, tmp_path):
        """Candidate passes all gates → GREEN → complete evidence pack."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_green.json"])
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        with open(output_dir / "evidence-pack-candidate-1.json") as f:
            pack_data = json.load(f)

        assert pack_data["confidence_score"]["rating"] == "GREEN"
        assert pack_data["confidence_score"]["breakdown"]["hard_gate_passed"] is True
        assert len(pack_data["confidence_score"]["breakdown"]["components"]) == 6
        assert pack_data["narrative"]["overview"]
        assert pack_data["decision_trace"]["confidence_config_hash"].startswith("sha256:")


class TestYellowMarginalCandidate:
    def test_yellow_marginal_candidate(self, tmp_path):
        """Passes gates but low composite → YELLOW with appropriate warnings."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_yellow.json"])
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        with open(output_dir / "evidence-pack-candidate-2.json") as f:
            pack_data = json.load(f)

        assert pack_data["confidence_score"]["rating"] == "YELLOW"
        assert pack_data["confidence_score"]["breakdown"]["hard_gate_passed"] is True
        # Should have weaknesses
        assert len(pack_data["narrative"]["weaknesses"]) >= 1


class TestMultipleCandidatesRanked:
    def test_multiple_candidates_ranked(self, tmp_path):
        """3+ candidates scored → sorted by composite → triage summaries."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, [
            "gauntlet_manifest_green.json",
            "gauntlet_manifest_yellow.json",
            "gauntlet_manifest_red.json",
        ])
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        manifest_path = orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        candidates = manifest["candidates"]
        assert len(candidates) == 3

        # Sorted by composite descending
        scores = [c["composite_score"] for c in candidates]
        assert scores == sorted(scores, reverse=True)

        # Triage summaries for all
        for c in candidates:
            triage_path = Path(c["triage_summary_path"])
            # Path is absolute to output_dir, check the filename
            triage_file = output_dir / f"evidence-triage-candidate-{c['candidate_id']}.json"
            assert triage_file.exists()


class TestShortCircuitedCandidateHandling:
    def test_short_circuited_candidate_handling(self, tmp_path):
        """Short-circuited candidate → RED evidence pack with available data."""
        gauntlet_dir = _setup_gauntlet_dir(
            tmp_path, ["gauntlet_manifest_short_circuited.json"],
        )
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        with open(output_dir / "evidence-pack-candidate-4.json") as f:
            pack_data = json.load(f)

        assert pack_data["confidence_score"]["rating"] == "RED"
        assert pack_data["confidence_score"]["breakdown"]["hard_gate_passed"] is False
        # Should still have component scores (some at 0.0 for skipped stages)
        components = pack_data["confidence_score"]["breakdown"]["components"]
        assert len(components) == 6


class TestEvidencePackTwoPassCompleteness:
    def test_evidence_pack_two_pass_completeness(self, tmp_path):
        """Triage summary has all required fields; full pack has all required fields."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_green.json"])
        output_dir = tmp_path / "scoring"

        orch = ConfidenceOrchestrator(_default_config())
        orch.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output_dir,
        )

        # Triage summary fields
        with open(output_dir / "evidence-triage-candidate-1.json") as f:
            triage = json.load(f)
        required_triage = ["candidate_id", "rating", "composite_score",
                          "headline_metrics", "dominant_edge", "top_risks"]
        for field in required_triage:
            assert field in triage, f"Triage missing field: {field}"

        # Full evidence pack fields
        with open(output_dir / "evidence-pack-candidate-1.json") as f:
            pack = json.load(f)
        required_pack = ["candidate_id", "optimization_run_id", "strategy_id",
                        "confidence_score", "triage_summary", "decision_trace",
                        "per_stage_results", "anomaly_report", "narrative",
                        "visualization_refs", "metadata"]
        for field in required_pack:
            assert field in pack, f"Pack missing field: {field}"


class TestDeterministicScoring:
    def test_deterministic_scoring(self, tmp_path):
        """Same gauntlet manifest + same config → identical scores (FR18)."""
        gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_green.json"])

        output1 = tmp_path / "scoring1"
        output2 = tmp_path / "scoring2"
        config = _default_config()

        orch1 = ConfidenceOrchestrator(config)
        orch1.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output1,
        )

        orch2 = ConfidenceOrchestrator(config)
        orch2.score_all_candidates(
            gauntlet_dir, {"optimization_run_id": "opt_test"}, output2,
        )

        with open(output1 / "evidence-pack-candidate-1.json") as f:
            pack1 = json.load(f)
        with open(output2 / "evidence-pack-candidate-1.json") as f:
            pack2 = json.load(f)

        # Same composite score
        assert pack1["confidence_score"]["composite_score"] == pack2["confidence_score"]["composite_score"]
        # Same rating
        assert pack1["confidence_score"]["rating"] == pack2["confidence_score"]["rating"]
        # Same config hash
        assert pack1["decision_trace"]["confidence_config_hash"] == pack2["decision_trace"]["confidence_config_hash"]
        # Same component scores
        for c1, c2 in zip(
            pack1["confidence_score"]["breakdown"]["components"],
            pack2["confidence_score"]["breakdown"]["components"],
        ):
            assert c1["normalized_score"] == c2["normalized_score"]
            assert c1["weighted_contribution"] == c2["weighted_contribution"]
