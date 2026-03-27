"""Tests for two-pass evidence pack builder (Task 7)."""
import json
from pathlib import Path

import pytest

from analysis.models import AnomalyFlag, AnomalyReport, AnomalyType, NarrativeResult, Severity
from confidence.config import AnomalyConfig, ConfidenceConfig, HardGateConfig, ThresholdConfig, WeightConfig
from confidence.evidence_builder import (
    build_decision_trace,
    build_evidence_pack,
    build_triage_summary,
    persist_evidence_pack,
)
from confidence.models import (
    CandidateRating,
    ConfidenceScore,
    TriageSummary,
    ValidationEvidencePack,
)
from confidence.scorer import score_candidate


def _default_config() -> ConfidenceConfig:
    return ConfidenceConfig(
        hard_gates=HardGateConfig(True, 0.40, 1.5),
        weights=WeightConfig(0.25, 0.15, 0.15, 0.15, 0.15, 0.15),
        thresholds=ThresholdConfig(0.70, 0.40),
        anomaly=AnomalyConfig(20),
    )


def _green_manifest() -> dict:
    return {
        "candidate_id": 42,
        "optimization_run_id": "opt_test",
        "strategy_id": "ma_crossover",
        "total_optimization_trials": 5000,
        "candidate_rank": 1,
        "validation_config_hash": "sha256:val_abc",
        "research_brief_versions": {"5A": "v1", "5C": "v1"},
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
        "per_stage_metric_ids": {"walk_forward": "wf_42", "cpcv": "cpcv_42"},
        "chart_data_refs": {"equity_curves": "artifacts/.../equity-42.arrow"},
    }


def _make_anomaly_report() -> AnomalyReport:
    return AnomalyReport(backtest_id="cand_42", anomalies=[], run_timestamp="2026-03-22T10:00:00Z")


def _make_narrative() -> NarrativeResult:
    return NarrativeResult(
        overview="Candidate 42 rated GREEN.",
        metrics={"composite": 0.72},
        strengths=["Strong walk-forward"],
        weaknesses=["None"],
        session_breakdown={},
        risk_assessment="Low risk.",
    )


class TestTriageSummary:
    def test_triage_summary_content(self):
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        triage = build_triage_summary(score, _green_manifest())

        assert triage.candidate_id == 42
        assert triage.rating == CandidateRating.GREEN
        assert "oos_sharpe" in triage.headline_metrics
        assert "pbo" in triage.headline_metrics
        assert "dsr_passed" in triage.headline_metrics
        assert len(triage.top_risks) <= 3
        assert triage.delta_vs_baseline is None

    @pytest.mark.regression
    def test_triage_headline_metrics_complete(self):
        """Regression: all 6 AC4 headline metrics must be present."""
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        triage = build_triage_summary(score, _green_manifest())

        required_metrics = {"oos_sharpe", "pbo", "dsr_passed", "max_drawdown", "win_rate", "profit_factor"}
        actual_metrics = set(triage.headline_metrics.keys())
        missing = required_metrics - actual_metrics
        assert not missing, f"Triage summary missing AC4 headline metrics: {missing}"


class TestDecisionTrace:
    def test_decision_trace_completeness(self):
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        trace = build_decision_trace(score, config, _green_manifest())

        assert trace.confidence_config_hash.startswith("sha256:")
        assert trace.validation_config_hash == "sha256:val_abc"
        assert "5A" in trace.research_brief_versions
        assert "pbo_max_threshold" in trace.thresholds_snapshot
        assert len(trace.gates_used) == 3  # DSR, PBO, cost stress


class TestEvidencePackRoundTrip:
    def test_evidence_pack_round_trip(self):
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        triage = build_triage_summary(score, _green_manifest())
        trace = build_decision_trace(score, config, _green_manifest())
        pack = build_evidence_pack(
            candidate_id=42,
            confidence_score=score,
            triage_summary=triage,
            decision_trace=trace,
            gauntlet_manifest=_green_manifest(),
            anomaly_report=_make_anomaly_report(),
            narrative=_make_narrative(),
            visualization_refs={"equity_curves": "artifacts/.../eq-42.arrow"},
        )

        data = pack.to_json()
        restored = ValidationEvidencePack.from_json(data)
        assert restored.candidate_id == 42
        assert restored.strategy_id == "ma_crossover"
        assert restored.confidence_score.rating == CandidateRating.GREEN
        assert restored.metadata["candidate_rank"] == 1


class TestCrashSafePersistence:
    def test_crash_safe_persistence(self, tmp_path):
        config = _default_config()
        manifest = _green_manifest()
        score = score_candidate(manifest, config)
        triage = build_triage_summary(score, manifest)
        trace = build_decision_trace(score, config, manifest)
        pack = build_evidence_pack(
            candidate_id=42,
            confidence_score=score,
            triage_summary=triage,
            decision_trace=trace,
            gauntlet_manifest=manifest,
            anomaly_report=_make_anomaly_report(),
            narrative=_make_narrative(),
            visualization_refs={},
        )

        output_dir = tmp_path / "validation"
        pack_path = persist_evidence_pack(pack, output_dir)

        # Full pack exists
        assert pack_path.exists()
        assert pack_path.name == "evidence-pack-candidate-42.json"

        # Triage exists
        triage_path = output_dir / "evidence-triage-candidate-42.json"
        assert triage_path.exists()

        # No .partial files remain
        partials = list(output_dir.glob("*.partial"))
        assert len(partials) == 0

        # Content is valid JSON and round-trips
        with open(pack_path) as f:
            data = json.load(f)
        assert data["candidate_id"] == 42
        restored = ValidationEvidencePack.from_json(data)
        assert restored.confidence_score.composite_score == pack.confidence_score.composite_score

        # Triage is valid
        with open(triage_path) as f:
            triage_data = json.load(f)
        assert triage_data["candidate_id"] == 42
        assert triage_data["rating"] == "GREEN"
