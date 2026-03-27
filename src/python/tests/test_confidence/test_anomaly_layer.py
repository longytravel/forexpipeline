"""Tests for two-tier anomaly detection (Task 5)."""
import pytest

from analysis.models import AnomalyType, Severity
from confidence.anomaly_layer import run_layer_a, run_layer_b


def _clean_manifest(candidate_id: int = 42) -> dict:
    """Manifest with no anomalies."""
    return {
        "candidate_id": candidate_id,
        "per_stage_summaries": {
            "walk_forward": {"median_oos_sharpe": 0.85, "window_count": 10, "negative_windows": 1},
            "cpcv": {"pbo": 0.18, "mean_oos_sharpe": 0.82, "mean_is_sharpe": 0.85},
            "perturbation": {"max_sensitivity": 0.20, "mean_sensitivity": 0.11, "cliff_count": 0},
            "monte_carlo": {"bootstrap_ci_lower": 0.15, "stress_survived": True, "permutation_p_value": 0.03},
            "regime": {"weakest_sharpe": 0.60, "strongest_sharpe": 1.20, "insufficient_buckets": 0},
        },
        "per_stage_metric_ids": {
            "walk_forward": "wf_42",
            "cpcv": "cpcv_42",
            "perturbation": "pert_42",
            "monte_carlo": "mc_42",
            "regime": "regime_42",
        },
    }


def _anomalous_manifest(candidate_id: int = 99) -> dict:
    """Manifest triggering multiple anomalies."""
    return {
        "candidate_id": candidate_id,
        "per_stage_summaries": {
            "walk_forward": {"median_oos_sharpe": 0.20, "window_count": 10, "negative_windows": 5},
            "cpcv": {"pbo": 0.35, "mean_oos_sharpe": 1.50, "mean_is_sharpe": 1.50},
            "perturbation": {"max_sensitivity": 0.65, "mean_sensitivity": 0.40, "cliff_count": 3},
            "monte_carlo": {"bootstrap_ci_lower": -0.05, "stress_survived": False, "permutation_p_value": 0.15},
            "regime": {"weakest_sharpe": 0.02, "strongest_sharpe": 1.80, "insufficient_buckets": 2},
        },
        "per_stage_metric_ids": {
            "walk_forward": "wf_99",
            "cpcv": "cpcv_99",
            "perturbation": "pert_99",
            "monte_carlo": "mc_99",
            "regime": "regime_99",
        },
    }


class TestLayerASilentScoring:
    def test_layer_a_silent_scoring_clean(self):
        """Clean manifest produces no anomaly flags."""
        scores = run_layer_a([_clean_manifest()])
        assert len(scores[42]) == 0

    def test_layer_a_silent_scoring_anomalous(self):
        """Anomalous manifest produces multiple flags."""
        scores = run_layer_a([_anomalous_manifest()])
        flags = scores[99]
        assert len(flags) >= 3  # At least IS_OOS_DIVERGENCE, CLIFF, TAIL_RISK, WF_DEGRAD, REGIME

    def test_layer_a_multiple_candidates(self):
        """Scores computed for each candidate independently."""
        manifests = [_clean_manifest(1), _anomalous_manifest(2)]
        scores = run_layer_a(manifests)
        assert len(scores[1]) == 0
        assert len(scores[2]) >= 3


class TestLayerBSurfacingThreshold:
    def test_layer_b_surfacing_threshold(self):
        """Flags surfaced when ≥2 detectors agree."""
        manifests = [_anomalous_manifest()]
        layer_a = run_layer_a(manifests)
        reports = run_layer_b(manifests, layer_a)
        report = reports[99]
        assert len(report.anomalies) >= 3  # All flags surfaced when ≥2 agree

    def test_no_false_surfacing_single_detector(self):
        """Single detector firing does not surface (unless tier-1 academic)."""
        # Create manifest with exactly one non-academic anomaly
        m = _clean_manifest(50)
        m["per_stage_summaries"]["perturbation"]["cliff_count"] = 3
        m["per_stage_summaries"]["perturbation"]["max_sensitivity"] = 0.60
        manifests = [m]
        layer_a = run_layer_a(manifests)
        # Exactly 1 flag from perturbation cliff
        assert len(layer_a[50]) == 1
        reports = run_layer_b(manifests, layer_a)
        # Single non-academic detector → NOT surfaced
        assert len(reports[50].anomalies) == 0


class TestLayerBAcademicTrigger:
    def test_layer_b_academic_trigger(self):
        """Tier-1 academic test ERROR flags surfaced even with single detector."""
        m = _clean_manifest(77)
        # Create large IS-OOS divergence that triggers ERROR severity
        m["per_stage_summaries"]["cpcv"]["mean_is_sharpe"] = 2.5
        m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 0.3
        manifests = [m]
        layer_a = run_layer_a(manifests)
        # Should have IS_OOS_DIVERGENCE flag
        assert any(f.type == AnomalyType.IS_OOS_DIVERGENCE for f in layer_a[77])
        reports = run_layer_b(manifests, layer_a)
        # Academic trigger surfaced even with single detector
        assert any(
            f.type == AnomalyType.IS_OOS_DIVERGENCE
            for f in reports[77].anomalies
        )


class TestAnomalyReportSerialization:
    def test_anomaly_report_serialization(self):
        manifests = [_anomalous_manifest()]
        layer_a = run_layer_a(manifests)
        reports = run_layer_b(manifests, layer_a)
        report = reports[99]
        data = report.to_json()
        from analysis.models import AnomalyReport
        restored = AnomalyReport.from_json(data)
        assert restored.backtest_id == report.backtest_id
        assert len(restored.anomalies) == len(report.anomalies)


class TestPopulationTestGating:
    def test_population_tests_skipped_below_threshold(self):
        """Population tests skipped when < min_population_size."""
        manifests = [_clean_manifest(i) for i in range(5)]
        scores = run_layer_a(manifests, min_population_size=20)
        # Should complete without error — population tests skipped
        assert len(scores) == 5

    def test_population_tests_run_above_threshold(self):
        """Population tests run when >= min_population_size."""
        manifests = [_clean_manifest(i) for i in range(25)]
        scores = run_layer_a(manifests, min_population_size=20)
        assert len(scores) == 25


class TestPopulationTestWarning:
    """Regression: population tests must warn when triggered but not implemented."""

    @pytest.mark.regression
    def test_population_tests_log_warning_when_triggered(self, caplog):
        """V1 population tests must emit a WARNING log, not silently no-op."""
        import logging
        manifests = [_clean_manifest(i) for i in range(25)]
        with caplog.at_level(logging.WARNING, logger="confidence.anomaly"):
            run_layer_a(manifests, min_population_size=20)
        # Must warn about not-yet-implemented
        assert any("not yet implemented" in r.message.lower() for r in caplog.records), (
            f"Expected warning about unimplemented population tests, got: "
            f"{[r.message for r in caplog.records]}"
        )


class TestLayerBDistinctDetectors:
    """Regression: Layer B must count distinct detector types, not raw flag count."""

    @pytest.mark.regression
    def test_single_detector_two_flags_not_surfaced(self):
        """One detector emitting two same-type flags must NOT satisfy >=2 detectors."""
        # Create manifest that triggers ONLY monte carlo (2 flags: ci_lower<0 + p>0.10)
        m = _clean_manifest(88)
        m["per_stage_summaries"]["monte_carlo"]["bootstrap_ci_lower"] = -0.15
        m["per_stage_summaries"]["monte_carlo"]["permutation_p_value"] = 0.20
        manifests = [m]
        layer_a = run_layer_a(manifests)
        mc_flags = [f for f in layer_a[88] if f.type == AnomalyType.MONTE_CARLO_TAIL_RISK]
        assert len(mc_flags) == 2, "Monte Carlo should produce 2 flags"
        # All flags from same detector type
        all_types = {f.type for f in layer_a[88]}
        assert len(all_types) == 1, "All flags should be from single detector type"
        # Layer B should NOT surface since only 1 distinct detector
        reports = run_layer_b(manifests, layer_a)
        assert len(reports[88].anomalies) == 0, (
            "Single detector (even with 2 flags) should NOT trigger Layer B surfacing"
        )
