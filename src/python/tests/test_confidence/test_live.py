"""Live integration tests for confidence scoring (Story 5.5).

These tests exercise REAL system behavior — write real files, verify real outputs.
No mocks for the system under test.

Run with: pytest -m live src/python/tests/test_confidence/test_live.py
"""
import json
import shutil
from pathlib import Path

import pytest

from confidence.config import load_confidence_config
from confidence.executor import ConfidenceExecutor, record_operator_review
from confidence.models import CandidateRating, ValidationEvidencePack
from confidence.orchestrator import ConfidenceOrchestrator

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gauntlet_output"
CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "base.toml"
PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _setup_gauntlet_dir(base_dir: Path, fixture_names: list[str]) -> Path:
    """Copy fixture files into a gauntlet results directory."""
    gauntlet_dir = base_dir / "gauntlet"
    gauntlet_dir.mkdir(parents=True, exist_ok=True)
    for name in fixture_names:
        data = _load_fixture(name)
        cid = data["candidate_id"]
        with open(gauntlet_dir / f"gauntlet-manifest-candidate-{cid}.json", "w") as f:
            json.dump(data, f, indent=2)
    return gauntlet_dir


@pytest.mark.live
def test_live_full_scoring_pipeline(tmp_path):
    """Live test: Load real config, score all fixture candidates, verify disk artifacts.

    Exercises the full pipeline from config loading through artifact persistence.
    """
    # Load REAL config from base.toml
    config = load_confidence_config(CONFIG_PATH)

    # Set up gauntlet directory with all fixture types
    gauntlet_dir = _setup_gauntlet_dir(tmp_path, [
        "gauntlet_manifest_green.json",
        "gauntlet_manifest_yellow.json",
        "gauntlet_manifest_red.json",
        "gauntlet_manifest_short_circuited.json",
    ])

    output_dir = tmp_path / "scoring_output"

    # Run scoring orchestrator with real config
    orch = ConfidenceOrchestrator(config)
    manifest_path = orch.score_all_candidates(
        gauntlet_dir,
        {"optimization_run_id": "opt_live_test"},
        output_dir,
    )

    # VERIFY: Scoring manifest exists on disk
    assert manifest_path.exists(), "Scoring manifest not written to disk"
    with open(manifest_path) as f:
        manifest = json.load(f)

    # VERIFY: All 4 candidates scored
    assert len(manifest["candidates"]) == 4
    assert manifest["optimization_run_id"] == "opt_live_test"
    assert manifest["confidence_config_hash"].startswith("sha256:")

    # VERIFY: Candidates sorted by composite score descending
    scores = [c["composite_score"] for c in manifest["candidates"]]
    assert scores == sorted(scores, reverse=True), "Candidates not sorted by composite score"

    # VERIFY: Expected ratings distribution
    ratings = {c["candidate_id"]: c["rating"] for c in manifest["candidates"]}
    assert ratings[1] == "GREEN", f"Candidate 1 should be GREEN, got {ratings[1]}"
    assert ratings[3] == "RED", f"Candidate 3 should be RED, got {ratings[3]}"
    assert ratings[4] == "RED", f"Candidate 4 should be RED, got {ratings[4]}"

    # VERIFY: Per-candidate artifacts exist on disk
    for cand in manifest["candidates"]:
        cid = cand["candidate_id"]
        pack_file = output_dir / f"evidence-pack-candidate-{cid}.json"
        triage_file = output_dir / f"evidence-triage-candidate-{cid}.json"
        assert pack_file.exists(), f"Evidence pack missing for candidate {cid}"
        assert triage_file.exists(), f"Triage summary missing for candidate {cid}"

    # VERIFY: No .partial files left on disk
    partials = list(output_dir.glob("*.partial"))
    assert len(partials) == 0, f"Partial files remain: {partials}"


@pytest.mark.live
def test_live_evidence_pack_content_validation(tmp_path):
    """Live test: Verify evidence pack content is complete and valid."""
    config = load_confidence_config(CONFIG_PATH)
    gauntlet_dir = _setup_gauntlet_dir(tmp_path, ["gauntlet_manifest_green.json"])
    output_dir = tmp_path / "scoring_output"

    orch = ConfidenceOrchestrator(config)
    orch.score_all_candidates(gauntlet_dir, {"optimization_run_id": "opt_live"}, output_dir)

    # Load and validate full evidence pack
    pack_path = output_dir / "evidence-pack-candidate-1.json"
    assert pack_path.exists()

    with open(pack_path) as f:
        data = json.load(f)

    # VERIFY: All required top-level fields
    required_fields = [
        "candidate_id", "optimization_run_id", "strategy_id",
        "confidence_score", "triage_summary", "decision_trace",
        "per_stage_results", "anomaly_report", "narrative",
        "visualization_refs", "metadata",
    ]
    for field in required_fields:
        assert field in data, f"Evidence pack missing field: {field}"

    # VERIFY: Confidence score structure
    cs = data["confidence_score"]
    assert cs["rating"] == "GREEN"
    assert 0.0 <= cs["composite_score"] <= 1.0
    assert len(cs["breakdown"]["components"]) == 6
    assert len(cs["breakdown"]["gates"]) == 3

    # VERIFY: Decision trace has config provenance
    dt = data["decision_trace"]
    assert dt["confidence_config_hash"].startswith("sha256:")
    assert "pbo_max_threshold" in dt["thresholds_snapshot"]

    # VERIFY: Narrative cites metrics
    assert "[metric:" in data["narrative"]["overview"]

    # VERIFY: Metadata completeness
    assert data["metadata"]["scored_at"]
    assert data["metadata"]["confidence_config_hash"].startswith("sha256:")

    # VERIFY: Round-trip deserialization
    pack = ValidationEvidencePack.from_json(data)
    assert pack.candidate_id == 1
    assert pack.confidence_score.rating == CandidateRating.GREEN


@pytest.mark.live
def test_live_operator_review_workflow(tmp_path):
    """Live test: Score candidates then record operator accept/reject decisions."""
    config = load_confidence_config(CONFIG_PATH)
    gauntlet_dir = _setup_gauntlet_dir(tmp_path, [
        "gauntlet_manifest_green.json",
        "gauntlet_manifest_red.json",
    ])
    output_dir = tmp_path / "scoring_output"

    # Score candidates
    orch = ConfidenceOrchestrator(config)
    orch.score_all_candidates(gauntlet_dir, {"optimization_run_id": "opt_live"}, output_dir)

    # Record operator decisions
    accept_path = record_operator_review(
        candidate_id=1,
        decision="accept",
        rationale="Strong GREEN metrics across all validation dimensions",
        operator_notes="Proceed to live paper trading",
        evidence_pack_path=str(output_dir / "evidence-pack-candidate-1.json"),
        output_dir=output_dir,
    )

    reject_path = record_operator_review(
        candidate_id=3,
        decision="reject",
        rationale="PBO gate failure indicates overfitting",
        operator_notes="Re-optimize with tighter regularization",
        evidence_pack_path=str(output_dir / "evidence-pack-candidate-3.json"),
        output_dir=output_dir,
    )

    # VERIFY: Review files exist on disk
    assert accept_path.exists(), "Accept review not written to disk"
    assert reject_path.exists(), "Reject review not written to disk"

    # VERIFY: Accept review content (file is a JSON array — append-only per AC8)
    with open(accept_path) as f:
        accept_reviews = json.load(f)
    assert isinstance(accept_reviews, list), "Review file should be a JSON array"
    assert len(accept_reviews) == 1
    assert accept_reviews[0]["candidate_id"] == 1
    assert accept_reviews[0]["decision"] == "accept"
    assert accept_reviews[0]["decision_timestamp"]  # Non-empty timestamp

    # VERIFY: Reject review content
    with open(reject_path) as f:
        reject_reviews = json.load(f)
    assert isinstance(reject_reviews, list), "Review file should be a JSON array"
    assert len(reject_reviews) == 1
    assert reject_reviews[0]["candidate_id"] == 3
    assert reject_reviews[0]["decision"] == "reject"

    # VERIFY: Evidence pack NOT mutated by review (immutability)
    with open(output_dir / "evidence-pack-candidate-1.json") as f:
        pack_after = json.load(f)
    assert "operator_review" not in pack_after  # Pack is immutable

    # VERIFY: No .partial files
    partials = list(output_dir.glob("*.partial"))
    assert len(partials) == 0
