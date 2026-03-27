"""Tests for narrative engine (Task 6)."""
import re

import pytest

from analysis.models import AnomalyFlag, AnomalyReport, AnomalyType, Severity
from confidence.anomaly_layer import run_layer_a, run_layer_b
from confidence.config import AnomalyConfig, ConfidenceConfig, HardGateConfig, ThresholdConfig, WeightConfig
from confidence.models import CandidateRating
from confidence.narrative_engine import generate_confidence_narrative
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
        "total_optimization_trials": 5000,
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
        "per_stage_metric_ids": {
            "walk_forward": "wf_42", "cpcv": "cpcv_42",
            "perturbation": "pert_42", "monte_carlo": "mc_42", "regime": "regime_42",
        },
        "chart_data_refs": {
            "equity_curves": "artifacts/.../equity-curves-42.arrow",
            "regime_results": "artifacts/.../regime-42.arrow",
        },
    }


def _red_manifest() -> dict:
    m = _green_manifest()
    m["candidate_id"] = 99
    m["gate_results"]["pbo_value"] = 0.55
    m["gate_results"]["pbo_passed"] = False
    m["per_stage_summaries"]["cpcv"]["pbo"] = 0.55
    m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 0.20
    m["per_stage_summaries"]["walk_forward"]["negative_windows"] = 5
    m["per_stage_summaries"]["monte_carlo"]["bootstrap_ci_lower"] = -0.05
    m["per_stage_summaries"]["monte_carlo"]["permutation_p_value"] = 0.15
    m["per_stage_summaries"]["regime"]["weakest_sharpe"] = 0.02
    m["per_stage_metric_ids"] = {
        "walk_forward": "wf_99", "cpcv": "cpcv_99",
        "perturbation": "pert_99", "monte_carlo": "mc_99", "regime": "regime_99",
    }
    return m


def _score_and_narrate(manifest: dict) -> tuple:
    config = _default_config()
    score = score_candidate(manifest, config)
    manifests = [manifest]
    layer_a = run_layer_a(manifests)
    reports = run_layer_b(manifests, layer_a)
    cid = manifest["candidate_id"]
    anomaly_report = reports[cid]
    narrative = generate_confidence_narrative(score, manifest, anomaly_report)
    return score, narrative


class TestNarrativeCitesMetricIds:
    def test_narrative_cites_metric_ids(self):
        """Every narrative section references metric IDs via [metric:...] pattern."""
        _, narrative = _score_and_narrate(_green_manifest())
        # Overview should cite a metric
        assert "[metric:" in narrative.overview
        # Metrics section should have metric_ref entries
        for comp_name, comp_data in narrative.metrics.items():
            if isinstance(comp_data, dict) and "metric_ref" in comp_data:
                assert "[metric:" in comp_data["metric_ref"]
        # Strengths should cite metrics
        for s in narrative.strengths:
            assert "[metric:" in s


class TestNarrativeNoUngroundedClaims:
    def test_narrative_no_ungrounded_claims(self):
        """No narrative string makes claims without a metric/chart reference."""
        _, narrative = _score_and_narrate(_green_manifest())

        # Check overview
        assert "[metric:" in narrative.overview or "[chart:" in narrative.overview

        # Check strengths
        for s in narrative.strengths:
            assert "[metric:" in s or "[chart:" in s

        # Check weaknesses
        for w in narrative.weaknesses:
            assert "[metric:" in w or "[chart:" in w


class TestNarrativeGreenCandidate:
    def test_narrative_green_candidate(self):
        score, narrative = _score_and_narrate(_green_manifest())
        assert score.rating == CandidateRating.GREEN
        assert "GREEN" in narrative.overview
        assert "42" in narrative.overview
        assert narrative.metrics["rating"] == "GREEN"
        assert narrative.metrics["hard_gates_passed"] is True
        # Should have strengths
        assert len(narrative.strengths) >= 1


class TestNarrativeRedCandidate:
    def test_narrative_red_candidate(self):
        score, narrative = _score_and_narrate(_red_manifest())
        assert score.rating == CandidateRating.RED
        assert "RED" in narrative.overview
        # Should have weaknesses (anomalies surfaced)
        assert len(narrative.weaknesses) >= 1
        # Risk assessment should mention anomalies
        assert "anomal" in narrative.risk_assessment.lower() or "risk" in narrative.risk_assessment.lower()


class TestNarrativeRiskAssessmentCitation:
    """Regression: every narrative string must cite a metric or chart ID (AC5)."""

    @pytest.mark.regression
    def test_risk_assessment_header_has_citation(self):
        """Risk assessment header line must include a [metric:...] citation."""
        _, narrative = _score_and_narrate(_red_manifest())
        # Risk assessment should contain citations in ALL lines
        for line in narrative.risk_assessment.split("\n"):
            line = line.strip()
            if line:
                assert "[metric:" in line or "[chart:" in line, (
                    f"Uncited risk assessment line: {line!r}"
                )

    @pytest.mark.regression
    def test_risk_assessment_no_anomalies_has_citation(self):
        """Empty risk assessment (no anomalies) must still cite a metric."""
        _, narrative = _score_and_narrate(_green_manifest())
        assert "[metric:" in narrative.risk_assessment or "[chart:" in narrative.risk_assessment

    @pytest.mark.regression
    def test_session_breakdown_has_citation(self):
        """Session breakdown must include chart or metric reference."""
        _, narrative = _score_and_narrate(_green_manifest())
        breakdown_str = str(narrative.session_breakdown)
        assert "[chart:" in breakdown_str or "[metric:" in breakdown_str
