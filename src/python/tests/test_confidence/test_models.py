"""Tests for confidence scoring data models (Task 1)."""
import pytest

from analysis.models import AnomalyFlag, AnomalyReport, AnomalyType, NarrativeResult, Severity
from confidence.models import (
    CandidateRating,
    ComponentScore,
    ConfidenceBreakdown,
    ConfidenceScore,
    DecisionTrace,
    GateResult,
    OperatorReview,
    TriageSummary,
    ValidationEvidencePack,
)


def _make_gate_result(passed: bool = True) -> GateResult:
    return GateResult(
        gate_name="dsr_pass",
        threshold=0.05,
        actual_value=0.03 if passed else 0.08,
        passed=passed,
        description="DSR significance test",
    )


def _make_component_score() -> ComponentScore:
    return ComponentScore(
        component_name="walk_forward_oos_consistency",
        raw_value=0.85,
        normalized_score=0.72,
        weight=0.25,
        weighted_contribution=0.18,
        interpretation="Strong OOS consistency across windows",
        gate_result=None,
    )


def _make_breakdown() -> ConfidenceBreakdown:
    return ConfidenceBreakdown(
        components=[_make_component_score()],
        gates=[_make_gate_result()],
        hard_gate_passed=True,
        composite_score=0.72,
    )


def _make_confidence_score() -> ConfidenceScore:
    return ConfidenceScore(
        candidate_id=42,
        optimization_run_id="opt_20260322_abc123",
        rating=CandidateRating.GREEN,
        composite_score=0.72,
        breakdown=_make_breakdown(),
        scored_at="2026-03-22T10:00:00Z",
    )


def _make_triage_summary() -> TriageSummary:
    return TriageSummary(
        candidate_id=42,
        rating=CandidateRating.GREEN,
        composite_score=0.72,
        headline_metrics={"oos_sharpe": 0.85, "pbo": 0.18, "dsr_passed": True},
        dominant_edge="Strong walk-forward consistency with low parameter sensitivity",
        top_risks=["Regime concentration in London session", "Marginal Monte Carlo survival"],
        delta_vs_baseline={"sharpe_delta": 0.15},
    )


def _make_decision_trace() -> DecisionTrace:
    return DecisionTrace(
        gates_used=[_make_gate_result()],
        thresholds_snapshot={"pbo_max": 0.40, "green_minimum": 0.70},
        confidence_config_hash="sha256:abc123",
        validation_config_hash="sha256:def456",
        research_brief_versions={"5A": "v1", "5B": "v1", "5C": "v1"},
    )


def _make_anomaly_report() -> AnomalyReport:
    return AnomalyReport(
        backtest_id="cand_42",
        anomalies=[
            AnomalyFlag(
                type=AnomalyType.SENSITIVITY_CLIFF,
                severity=Severity.WARNING,
                description="Parameter cliff detected",
                evidence={"param": "sma_period", "delta": 0.3},
                recommendation="Review parameter stability",
            )
        ],
        run_timestamp="2026-03-22T10:00:00Z",
    )


def _make_narrative_result() -> NarrativeResult:
    return NarrativeResult(
        overview="Candidate 42 rated GREEN (composite: 0.72).",
        metrics={"walk_forward": 0.85, "pbo_margin": 0.55},
        strengths=["Strong OOS consistency [metric:wf_metrics_cand42]"],
        weaknesses=["Marginal regime uniformity [metric:regime_metrics_cand42]"],
        session_breakdown={"asian": {"sharpe": 0.45, "trades": 120}},
        risk_assessment="Low risk — all gates passed with comfortable margins.",
    )


def _make_evidence_pack() -> ValidationEvidencePack:
    return ValidationEvidencePack(
        candidate_id=42,
        optimization_run_id="opt_20260322_abc123",
        strategy_id="ma_crossover",
        confidence_score=_make_confidence_score(),
        triage_summary=_make_triage_summary(),
        decision_trace=_make_decision_trace(),
        per_stage_results={"walk_forward": {"median_oos_sharpe": 0.85}},
        anomaly_report=_make_anomaly_report(),
        narrative=_make_narrative_result(),
        visualization_refs={"equity_curves": "artifacts/.../equity-curves-cand42.arrow"},
        metadata={"scored_at": "2026-03-22T10:00:00Z"},
    )


def _make_operator_review() -> OperatorReview:
    return OperatorReview(
        candidate_id=42,
        decision="accept",
        rationale="Strong across all validation dimensions",
        operator_notes="Proceed to live testing",
        decision_timestamp="2026-03-22T11:00:00Z",
        evidence_pack_path="artifacts/ma_crossover/v001/validation/evidence-pack-candidate-42.json",
    )


# --- Round-trip serialization tests ---


class TestGateResultSerialization:
    def test_round_trip(self):
        original = _make_gate_result()
        restored = GateResult.from_json(original.to_json())
        assert restored.gate_name == original.gate_name
        assert restored.threshold == original.threshold
        assert restored.actual_value == original.actual_value
        assert restored.passed == original.passed
        assert restored.description == original.description

    def test_round_trip_failed_gate(self):
        original = _make_gate_result(passed=False)
        restored = GateResult.from_json(original.to_json())
        assert restored.passed is False


class TestComponentScoreSerialization:
    def test_round_trip(self):
        original = _make_component_score()
        restored = ComponentScore.from_json(original.to_json())
        assert restored.component_name == original.component_name
        assert restored.normalized_score == original.normalized_score
        assert restored.weight == original.weight
        assert restored.gate_result is None

    def test_round_trip_with_gate(self):
        original = ComponentScore(
            component_name="cpcv_pbo_margin",
            raw_value=0.18,
            normalized_score=0.55,
            weight=0.15,
            weighted_contribution=0.0825,
            interpretation="PBO margin comfortable",
            gate_result=_make_gate_result(),
        )
        restored = ComponentScore.from_json(original.to_json())
        assert restored.gate_result is not None
        assert restored.gate_result.gate_name == "dsr_pass"


class TestConfidenceBreakdownSerialization:
    def test_round_trip(self):
        original = _make_breakdown()
        restored = ConfidenceBreakdown.from_json(original.to_json())
        assert len(restored.components) == 1
        assert len(restored.gates) == 1
        assert restored.hard_gate_passed is True
        assert restored.composite_score == 0.72


class TestConfidenceScoreSerialization:
    def test_round_trip(self):
        original = _make_confidence_score()
        restored = ConfidenceScore.from_json(original.to_json())
        assert restored.candidate_id == 42
        assert restored.rating == CandidateRating.GREEN
        assert restored.composite_score == 0.72
        assert restored.breakdown.hard_gate_passed is True

    def test_all_ratings(self):
        for rating in CandidateRating:
            score = ConfidenceScore(
                candidate_id=1,
                optimization_run_id="test",
                rating=rating,
                composite_score=0.5,
                breakdown=_make_breakdown(),
                scored_at="2026-01-01T00:00:00Z",
            )
            restored = ConfidenceScore.from_json(score.to_json())
            assert restored.rating == rating


class TestTriageSummarySerialization:
    def test_round_trip(self):
        original = _make_triage_summary()
        restored = TriageSummary.from_json(original.to_json())
        assert restored.candidate_id == 42
        assert restored.rating == CandidateRating.GREEN
        assert restored.headline_metrics["oos_sharpe"] == 0.85
        assert len(restored.top_risks) == 2
        assert restored.delta_vs_baseline == {"sharpe_delta": 0.15}

    def test_round_trip_no_baseline(self):
        original = TriageSummary(
            candidate_id=1,
            rating=CandidateRating.YELLOW,
            composite_score=0.55,
            headline_metrics={"pbo": 0.30},
            dominant_edge="Moderate edge",
            top_risks=["Risk 1"],
            delta_vs_baseline=None,
        )
        restored = TriageSummary.from_json(original.to_json())
        assert restored.delta_vs_baseline is None


class TestDecisionTraceSerialization:
    def test_round_trip(self):
        original = _make_decision_trace()
        restored = DecisionTrace.from_json(original.to_json())
        assert len(restored.gates_used) == 1
        assert restored.confidence_config_hash == "sha256:abc123"
        assert restored.research_brief_versions["5C"] == "v1"


class TestValidationEvidencePackSerialization:
    def test_round_trip(self):
        original = _make_evidence_pack()
        data = original.to_json()
        restored = ValidationEvidencePack.from_json(data)
        assert restored.candidate_id == 42
        assert restored.strategy_id == "ma_crossover"
        assert restored.confidence_score.rating == CandidateRating.GREEN
        assert restored.triage_summary.composite_score == 0.72
        assert len(restored.anomaly_report.anomalies) == 1
        assert restored.narrative.overview.startswith("Candidate 42")
        assert "equity_curves" in restored.visualization_refs


class TestOperatorReviewSerialization:
    def test_round_trip(self):
        original = _make_operator_review()
        restored = OperatorReview.from_json(original.to_json())
        assert restored.candidate_id == 42
        assert restored.decision == "accept"
        assert restored.rationale == "Strong across all validation dimensions"
        assert restored.evidence_pack_path.endswith("candidate-42.json")
