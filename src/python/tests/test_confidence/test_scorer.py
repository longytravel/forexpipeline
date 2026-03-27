"""Tests for weighted composite scorer (Task 4)."""
import pytest

from confidence.config import ConfidenceConfig, HardGateConfig, ThresholdConfig, WeightConfig, AnomalyConfig
from confidence.models import CandidateRating
from confidence.scorer import (
    assign_rating,
    compute_component_scores,
    compute_composite_score,
    score_candidate,
)


def _default_config() -> ConfidenceConfig:
    return ConfidenceConfig(
        hard_gates=HardGateConfig(
            dsr_pass_required=True,
            pbo_max_threshold=0.40,
            cost_stress_survival_multiplier=1.5,
        ),
        weights=WeightConfig(
            walk_forward_oos_consistency=0.25,
            cpcv_pbo_margin=0.15,
            parameter_stability=0.15,
            monte_carlo_stress_survival=0.15,
            regime_uniformity=0.15,
            in_sample_oos_coherence=0.15,
        ),
        thresholds=ThresholdConfig(green_minimum=0.70, yellow_minimum=0.40),
        anomaly=AnomalyConfig(min_population_size=20),
    )


def _green_manifest() -> dict:
    return {
        "candidate_id": 42,
        "optimization_run_id": "opt_test",
        "total_optimization_trials": 5000,
        "gate_results": {
            "dsr_passed": True,
            "dsr_value": 2.31,
            "pbo_value": 0.18,
            "pbo_passed": True,
            "short_circuited": False,
        },
        "per_stage_summaries": {
            "walk_forward": {"median_oos_sharpe": 1.2, "window_count": 10, "negative_windows": 1},
            "cpcv": {"pbo": 0.18, "mean_oos_sharpe": 1.1, "mean_is_sharpe": 1.3, "combination_count": 45},
            "perturbation": {"max_sensitivity": 0.23, "mean_sensitivity": 0.11, "cliff_count": 0},
            "monte_carlo": {"bootstrap_ci_lower": 0.15, "stress_survived": True, "permutation_p_value": 0.03},
            "regime": {"weakest_sharpe": 0.80, "strongest_sharpe": 1.45, "insufficient_buckets": 0},
        },
    }


def _yellow_manifest() -> dict:
    m = _green_manifest()
    # Weaken a few components to push composite into 0.40–0.70 range
    m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 0.5
    m["per_stage_summaries"]["regime"]["weakest_sharpe"] = 0.20
    m["per_stage_summaries"]["perturbation"]["mean_sensitivity"] = 0.50
    return m


def _red_manifest() -> dict:
    m = _green_manifest()
    m["gate_results"]["pbo_value"] = 0.55
    m["gate_results"]["pbo_passed"] = False
    m["per_stage_summaries"]["cpcv"]["pbo"] = 0.55
    return m


class TestScoreAllGreen:
    def test_score_all_green(self):
        score = score_candidate(_green_manifest(), _default_config())
        assert score.rating == CandidateRating.GREEN
        assert score.composite_score >= 0.70
        assert score.breakdown.hard_gate_passed is True

    def test_component_count(self):
        score = score_candidate(_green_manifest(), _default_config())
        assert len(score.breakdown.components) == 6


class TestScoreYellowMarginal:
    def test_score_yellow_marginal(self):
        score = score_candidate(_yellow_manifest(), _default_config())
        assert score.rating == CandidateRating.YELLOW
        assert 0.40 <= score.composite_score < 0.70


class TestScoreRedGateFailure:
    def test_score_red_gate_failure(self):
        score = score_candidate(_red_manifest(), _default_config())
        assert score.rating == CandidateRating.RED
        assert score.breakdown.hard_gate_passed is False


class TestScoreRedLowComposite:
    def test_score_red_low_composite(self):
        m = _green_manifest()
        m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = -0.3
        m["per_stage_summaries"]["cpcv"]["pbo"] = 0.38
        m["per_stage_summaries"]["perturbation"]["mean_sensitivity"] = 0.90
        m["per_stage_summaries"]["monte_carlo"]["stress_survived"] = False
        m["per_stage_summaries"]["monte_carlo"]["permutation_p_value"] = 0.50
        m["per_stage_summaries"]["monte_carlo"]["bootstrap_ci_lower"] = -0.10
        m["per_stage_summaries"]["regime"]["weakest_sharpe"] = 0.01
        score = score_candidate(m, _default_config())
        assert score.rating == CandidateRating.RED
        assert score.composite_score < 0.40


class TestComponentNormalizationBounds:
    def test_component_normalization_bounds(self):
        config = _default_config()
        components = compute_component_scores(_green_manifest(), config.weights)
        for c in components:
            assert 0.0 <= c.normalized_score <= 1.0, (
                f"{c.component_name} normalized_score {c.normalized_score} out of bounds"
            )

    def test_extreme_values_clamped(self):
        m = _green_manifest()
        m["per_stage_summaries"]["walk_forward"]["median_oos_sharpe"] = 10.0  # Way above ceiling
        m["per_stage_summaries"]["perturbation"]["mean_sensitivity"] = -0.5  # Below 0
        components = compute_component_scores(m, _default_config().weights)
        for c in components:
            assert 0.0 <= c.normalized_score <= 1.0


class TestWeightsAppliedCorrectly:
    def test_weights_applied_correctly(self):
        config = _default_config()
        components = compute_component_scores(_green_manifest(), config.weights)
        for c in components:
            expected = c.normalized_score * c.weight
            assert abs(c.weighted_contribution - expected) < 1e-9, (
                f"{c.component_name}: expected {expected}, got {c.weighted_contribution}"
            )

    def test_composite_is_sum_of_weighted(self):
        config = _default_config()
        components = compute_component_scores(_green_manifest(), config.weights)
        composite = compute_composite_score(components)
        expected = sum(c.weighted_contribution for c in components)
        assert abs(composite - expected) < 1e-9


class TestAssignRating:
    def test_green(self):
        assert assign_rating(0.75, True, ThresholdConfig(0.70, 0.40)) == CandidateRating.GREEN

    def test_yellow(self):
        assert assign_rating(0.55, True, ThresholdConfig(0.70, 0.40)) == CandidateRating.YELLOW

    def test_red_low_score(self):
        assert assign_rating(0.30, True, ThresholdConfig(0.70, 0.40)) == CandidateRating.RED

    def test_red_gate_failure(self):
        assert assign_rating(0.90, False, ThresholdConfig(0.70, 0.40)) == CandidateRating.RED

    def test_boundary_green(self):
        assert assign_rating(0.70, True, ThresholdConfig(0.70, 0.40)) == CandidateRating.GREEN

    def test_boundary_yellow(self):
        assert assign_rating(0.40, True, ThresholdConfig(0.70, 0.40)) == CandidateRating.YELLOW


class TestPBOThresholdFromConfig:
    """Regression: PBO threshold must come from config, not a hardcoded 0.40."""

    @pytest.mark.regression
    def test_pbo_score_changes_with_config_threshold(self):
        """Varying pbo_max_threshold in config must change the PBO component score."""
        manifest = _green_manifest()
        # PBO value is 0.18

        config_strict = ConfidenceConfig(
            hard_gates=HardGateConfig(True, pbo_max_threshold=0.20, cost_stress_survival_multiplier=1.5),
            weights=WeightConfig(0.25, 0.15, 0.15, 0.15, 0.15, 0.15),
            thresholds=ThresholdConfig(0.70, 0.40),
            anomaly=AnomalyConfig(20),
        )
        config_lenient = ConfidenceConfig(
            hard_gates=HardGateConfig(True, pbo_max_threshold=0.80, cost_stress_survival_multiplier=1.5),
            weights=WeightConfig(0.25, 0.15, 0.15, 0.15, 0.15, 0.15),
            thresholds=ThresholdConfig(0.70, 0.40),
            anomaly=AnomalyConfig(20),
        )

        from confidence.scorer import compute_component_scores
        from confidence.gates import evaluate_hard_gates

        gates_strict = evaluate_hard_gates(manifest, config_strict.hard_gates)
        components_strict = compute_component_scores(
            manifest, config_strict.weights,
            hard_gate_config=config_strict.hard_gates,
            gate_results=gates_strict,
        )
        gates_lenient = evaluate_hard_gates(manifest, config_lenient.hard_gates)
        components_lenient = compute_component_scores(
            manifest, config_lenient.weights,
            hard_gate_config=config_lenient.hard_gates,
            gate_results=gates_lenient,
        )

        pbo_strict = next(c for c in components_strict if c.component_name == "cpcv_pbo_margin")
        pbo_lenient = next(c for c in components_lenient if c.component_name == "cpcv_pbo_margin")

        # With threshold=0.20, margin is (0.20-0.18)/0.20 = 0.10
        # With threshold=0.80, margin is (0.80-0.18)/0.80 = 0.775
        assert pbo_strict.normalized_score < pbo_lenient.normalized_score, (
            f"PBO score should differ with config: strict={pbo_strict.normalized_score} "
            f"vs lenient={pbo_lenient.normalized_score}"
        )
