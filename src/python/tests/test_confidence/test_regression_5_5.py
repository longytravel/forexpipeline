"""Regression tests for Story 5-5 review synthesis findings.

Each test is marked @pytest.mark.regression and targets a specific
accepted finding from the BMAD/Codex review synthesis.
"""
import json
import re
from pathlib import Path

import pytest

from analysis.models import AnomalyFlag, AnomalyReport, AnomalyType, Severity
from confidence.anomaly_layer import run_layer_a, run_layer_b
from confidence.config import (
    AnomalyConfig,
    ConfidenceConfig,
    HardGateConfig,
    ThresholdConfig,
    WeightConfig,
)
from confidence.evidence_builder import build_triage_summary
from confidence.executor import record_operator_review
from confidence.models import CandidateRating, OperatorReview
from confidence.narrative_engine import generate_confidence_narrative
from confidence.scorer import compute_component_scores, score_candidate
from orchestrator.pipeline_state import (
    PipelineStage,
    STAGE_GRAPH,
    TransitionType,
)


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
            "equity_curves": "artifacts/.../equity-42.arrow",
            "regime_results": "artifacts/.../regime-42.arrow",
        },
    }


# -------------------------------------------------------------------------
# Regression: IS-OOS coherence must use mean_is_sharpe (Codex H3)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestISOOSCoherenceUsesISMetric:
    """IS-OOS coherence must compare IS Sharpe (from CPCV) to OOS Sharpe
    (from walk-forward), not OOS-vs-OOS."""

    def test_scorer_uses_mean_is_sharpe(self):
        """When mean_is_sharpe differs from median_oos_sharpe, coherence
        should reflect that divergence."""
        m = _green_manifest()
        # Set a large IS-OOS gap: IS=2.0, OOS=0.5
        m["per_stage_summaries"]["cpcv"]["mean_is_sharpe"] = 2.0
        m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 0.5

        config = _default_config()
        components = compute_component_scores(
            m, config.weights,
            hard_gate_config=config.hard_gates,
        )
        coherence = next(c for c in components if c.component_name == "in_sample_oos_coherence")
        # Large divergence → low score
        assert coherence.normalized_score < 0.5

    def test_scorer_ignores_mean_oos_sharpe_for_coherence(self):
        """mean_oos_sharpe in CPCV should NOT affect coherence score."""
        m = _green_manifest()
        m["per_stage_summaries"]["cpcv"]["mean_is_sharpe"] = 1.2  # Close to OOS
        m["per_stage_summaries"]["cpcv"]["mean_oos_sharpe"] = 5.0  # Very different
        m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 1.2

        config = _default_config()
        components = compute_component_scores(
            m, config.weights,
            hard_gate_config=config.hard_gates,
        )
        coherence = next(c for c in components if c.component_name == "in_sample_oos_coherence")
        # IS and OOS are close → high coherence despite mean_oos_sharpe being far off
        assert coherence.normalized_score > 0.8

    def test_anomaly_layer_uses_mean_is_sharpe(self):
        """Anomaly detection IS-OOS divergence must use mean_is_sharpe."""
        m = _green_manifest()
        m["per_stage_summaries"]["cpcv"]["mean_is_sharpe"] = 2.5
        m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 0.3

        scores = run_layer_a([m])
        flags = scores[42]
        assert any(f.type == AnomalyType.IS_OOS_DIVERGENCE for f in flags)


# -------------------------------------------------------------------------
# Regression: Layer B must count distinct detectors (Codex H4)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestLayerBCountsDistinctDetectors:
    """Layer B must require ≥2 distinct detector TYPES, not ≥2 raw flags."""

    def test_single_detector_two_flags_not_surfaced(self):
        """Monte Carlo can emit 2 flags (ci_lower<0 + p_value>0.10) but
        is a single detector — should NOT trigger Layer B surfacing."""
        m = _green_manifest()
        # Only Monte Carlo anomalies: ci_lower < 0 AND p_value > 0.10
        m["per_stage_summaries"]["monte_carlo"]["bootstrap_ci_lower"] = -0.05
        m["per_stage_summaries"]["monte_carlo"]["permutation_p_value"] = 0.15
        # All other detectors clean
        m["per_stage_summaries"]["perturbation"]["cliff_count"] = 0
        m["per_stage_summaries"]["perturbation"]["max_sensitivity"] = 0.10
        m["per_stage_summaries"]["regime"]["weakest_sharpe"] = 0.80
        m["per_stage_summaries"]["walk_forward"]["negative_windows"] = 1

        layer_a = run_layer_a([m])
        flags = layer_a[42]
        # Monte Carlo should produce ≥2 flags
        mc_flags = [f for f in flags if f.type == AnomalyType.MONTE_CARLO_TAIL_RISK]
        assert len(mc_flags) >= 2, "Monte Carlo should emit 2+ flags"
        # But only 1 distinct detector type
        distinct_types = {f.type for f in flags}
        assert len(distinct_types) == 1, "Only MONTE_CARLO_TAIL_RISK should fire"

        reports = run_layer_b([m], layer_a)
        # Should NOT be surfaced (single detector, not tier-1 academic)
        assert len(reports[42].anomalies) == 0


# -------------------------------------------------------------------------
# Regression: Triage headline metrics must include spec fields (Both H2/M1)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestTriageHeadlineMetrics:
    """Triage summary must include max_drawdown, win_rate, profit_factor."""

    def test_triage_has_required_headline_metrics(self):
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        triage = build_triage_summary(score, _green_manifest())

        required = {"oos_sharpe", "pbo", "dsr_passed", "max_drawdown", "win_rate", "profit_factor"}
        actual = set(triage.headline_metrics.keys())
        missing = required - actual
        assert not missing, f"Triage missing required headline metrics: {missing}"

    def test_triage_no_longer_has_unspecified_fields(self):
        """stress_survived, window_count, negative_windows were not in the spec."""
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        triage = build_triage_summary(score, _green_manifest())

        unspecified = {"stress_survived", "window_count", "negative_windows"}
        actual = set(triage.headline_metrics.keys())
        leaked = unspecified & actual
        assert not leaked, f"Triage contains unspecified fields: {leaked}"


# -------------------------------------------------------------------------
# Regression: Narrative citations must reference correct component (Codex H2)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestNarrativeCitationsCorrect:
    """Overview must cite the metric ID of the actual strongest/weakest
    component, not always walk_forward."""

    def test_overview_cites_correct_strongest_component(self):
        m = _green_manifest()
        config = _default_config()
        score = score_candidate(m, config)
        anomaly_report = AnomalyReport(
            backtest_id="cand_42", anomalies=[], run_timestamp="2026-03-22T10:00:00Z",
        )
        narrative = generate_confidence_narrative(score, m, anomaly_report)

        # Find the actual strongest component
        best = max(score.breakdown.components, key=lambda c: c.normalized_score)
        # The overview should cite that component's metric, not always wf_42
        expected_stage_map = {
            "walk_forward_oos_consistency": "walk_forward",
            "cpcv_pbo_margin": "cpcv",
            "parameter_stability": "perturbation",
            "monte_carlo_stress_survival": "monte_carlo",
            "regime_uniformity": "regime",
            "in_sample_oos_coherence": "walk_forward",
        }
        expected_stage = expected_stage_map[best.component_name]
        expected_metric_id = m["per_stage_metric_ids"].get(expected_stage, "n/a")
        assert f"[metric:{expected_metric_id}]" in narrative.overview

    def test_all_narrative_strings_have_citations(self):
        """Every narrative string must have a [metric:...] or [chart:...] reference."""
        m = _green_manifest()
        config = _default_config()
        score = score_candidate(m, config)
        anomaly_report = AnomalyReport(
            backtest_id="cand_42", anomalies=[], run_timestamp="2026-03-22T10:00:00Z",
        )
        narrative = generate_confidence_narrative(score, m, anomaly_report)

        assert "[metric:" in narrative.overview or "[chart:" in narrative.overview
        for s in narrative.strengths:
            assert "[metric:" in s or "[chart:" in s, f"Uncited strength: {s}"
        for w in narrative.weaknesses:
            assert "[metric:" in w or "[chart:" in w, f"Uncited weakness: {w}"
        assert "[metric:" in narrative.risk_assessment or "[chart:" in narrative.risk_assessment


# -------------------------------------------------------------------------
# Regression: PBO threshold must come from config (Codex M4)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestPBOThresholdFromConfig:
    """PBO margin normalization must use config threshold, not hardcoded 0.40."""

    def test_pbo_score_changes_with_threshold(self):
        m = _green_manifest()
        m["per_stage_summaries"]["cpcv"]["pbo"] = 0.25

        # With threshold=0.40, margin = (0.40-0.25)/0.40 = 0.375
        config_040 = _default_config()
        components_040 = compute_component_scores(
            m, config_040.weights,
            hard_gate_config=HardGateConfig(True, 0.40, 1.5),
        )
        pbo_040 = next(c for c in components_040 if c.component_name == "cpcv_pbo_margin")

        # With threshold=0.50, margin = (0.50-0.25)/0.50 = 0.50
        components_050 = compute_component_scores(
            m, config_040.weights,
            hard_gate_config=HardGateConfig(True, 0.50, 1.5),
        )
        pbo_050 = next(c for c in components_050 if c.component_name == "cpcv_pbo_margin")

        assert pbo_050.normalized_score > pbo_040.normalized_score


# -------------------------------------------------------------------------
# Regression: ComponentScore.gate_result must be populated (Codex M3)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestComponentGateResultPopulated:
    """Components with associated gates must have gate_result set."""

    def test_pbo_component_has_gate_result(self):
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        pbo_comp = next(
            c for c in score.breakdown.components
            if c.component_name == "cpcv_pbo_margin"
        )
        assert pbo_comp.gate_result is not None
        assert pbo_comp.gate_result.gate_name == "pbo_threshold"

    def test_mc_component_has_gate_result(self):
        config = _default_config()
        score = score_candidate(_green_manifest(), config)
        mc_comp = next(
            c for c in score.breakdown.components
            if c.component_name == "monte_carlo_stress_survival"
        )
        assert mc_comp.gate_result is not None
        assert mc_comp.gate_result.gate_name == "cost_stress_survival"


# -------------------------------------------------------------------------
# Regression: Short-circuit messages must include gate name (Codex H1)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestShortCircuitGateName:
    """Short-circuited stage interpretations must name the failing gate."""

    def test_short_circuit_interpretation_names_gate(self):
        m = _green_manifest()
        m["gate_results"]["short_circuited"] = True
        m["gate_results"]["pbo_passed"] = False
        m["gate_results"]["pbo_value"] = 0.55
        m["per_stage_summaries"]["cpcv"]["pbo"] = 0.55
        # Remove monte_carlo to trigger short-circuit interpretation
        del m["per_stage_summaries"]["monte_carlo"]
        del m["per_stage_summaries"]["regime"]

        config = _default_config()
        score = score_candidate(m, config)

        # Find components that were short-circuited
        for comp in score.breakdown.components:
            if "gate failure" in comp.interpretation:
                # Must name a specific gate, not just "unknown"
                assert "pbo_threshold" in comp.interpretation or \
                       "cost_stress_survival" in comp.interpretation or \
                       "dsr_pass" in comp.interpretation, \
                    f"Short-circuit message lacks gate name: {comp.interpretation}"


# -------------------------------------------------------------------------
# Regression: Operator review must be append-only (Codex H5 / AC8)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestOperatorReviewAppendOnly:
    """Multiple reviews for same candidate must append, not overwrite."""

    def test_multiple_reviews_append(self, tmp_path):
        for decision in ("reject", "refine", "accept"):
            record_operator_review(
                candidate_id=42,
                decision=decision,
                rationale=f"Review: {decision}",
                operator_notes="",
                evidence_pack_path="path/to/pack.json",
                output_dir=tmp_path,
            )

        review_path = tmp_path / "operator-review-candidate-42.json"
        with open(review_path) as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["decision"] == "reject"
        assert data[1]["decision"] == "refine"
        assert data[2]["decision"] == "accept"


# -------------------------------------------------------------------------
# Regression: OperatorReview.decision must be validated (BMAD L2)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestOperatorReviewDecisionValidation:
    """OperatorReview.decision must be one of accept/reject/refine."""

    def test_valid_decisions_accepted(self):
        for d in ("accept", "reject", "refine"):
            review = OperatorReview(
                candidate_id=1, decision=d, rationale="", operator_notes="",
                decision_timestamp="2026-01-01T00:00:00Z", evidence_pack_path="",
            )
            assert review.decision == d

    def test_invalid_decision_rejected(self):
        with pytest.raises(ValueError, match="Invalid review decision"):
            OperatorReview(
                candidate_id=1, decision="approved", rationale="", operator_notes="",
                decision_timestamp="2026-01-01T00:00:00Z", evidence_pack_path="",
            )


# -------------------------------------------------------------------------
# Regression: SCORING_COMPLETE must have gated transition (BMAD M3)
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestScoringCompleteGatedTransition:
    """SCORING_COMPLETE must have a GATED transition in the STAGE_GRAPH."""

    def test_scoring_complete_in_stage_graph(self):
        assert PipelineStage.SCORING_COMPLETE in STAGE_GRAPH

    def test_scoring_complete_is_gated(self):
        transition = STAGE_GRAPH[PipelineStage.SCORING_COMPLETE]
        assert transition.transition_type == TransitionType.GATED
