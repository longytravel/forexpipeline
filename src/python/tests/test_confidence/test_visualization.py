"""Tests for visualization data preparation (Task 8)."""
import pytest

from confidence.visualization import (
    prepare_all_visualizations,
    prepare_equity_curve_chart,
    prepare_monte_carlo_distribution,
    prepare_regime_breakdown,
    prepare_sensitivity_heatmap,
    prepare_walk_forward_chart,
)


def _full_manifest() -> dict:
    return {
        "per_stage_summaries": {
            "walk_forward": {"median_oos_sharpe": 0.85, "window_count": 10, "negative_windows": 2},
            "perturbation": {"max_sensitivity": 0.23, "mean_sensitivity": 0.11, "cliff_count": 0},
            "monte_carlo": {"bootstrap_ci_lower": 0.15, "stress_survived": True, "permutation_p_value": 0.03},
            "regime": {"weakest_sharpe": 0.21, "strongest_sharpe": 1.45, "insufficient_buckets": 1},
        },
        "chart_data_refs": {
            "equity_curves": "artifacts/.../equity-curves-42.arrow",
            "walk_forward_windows": "artifacts/.../wf-windows-42.arrow",
            "perturbation_results": "artifacts/.../perturbation-42.arrow",
            "monte_carlo_results": "artifacts/.../mc-results-42.arrow",
            "regime_results": "artifacts/.../regime-42.arrow",
        },
    }


class TestEquityCurveChart:
    def test_equity_curve_chart_structure(self):
        chart = prepare_equity_curve_chart(_full_manifest())
        assert chart["chart_type"] == "equity_curve"
        assert chart["data_ref"] == "artifacts/.../equity-curves-42.arrow"
        assert chart["series"]["window_count"] == 10


class TestWalkForwardChart:
    def test_walk_forward_temporal_markers(self):
        chart = prepare_walk_forward_chart(_full_manifest())
        assert chart["chart_type"] == "walk_forward_windows"
        assert chart["series"]["negative_windows"] == 2
        assert chart["x_axis"] == "window_index"


class TestSensitivityHeatmap:
    def test_sensitivity_heatmap_dimensions(self):
        chart = prepare_sensitivity_heatmap(_full_manifest())
        assert chart["chart_type"] == "sensitivity_heatmap"
        assert chart["x_axis"] == "perturbation_level"
        assert chart["y_axis"] == "parameter_name"
        assert chart["series"]["cliff_count"] == 0


class TestMonteCarloDistribution:
    def test_monte_carlo_confidence_intervals(self):
        chart = prepare_monte_carlo_distribution(_full_manifest())
        assert chart["chart_type"] == "monte_carlo_distribution"
        assert chart["series"]["bootstrap_ci_lower"] == 0.15
        assert chart["series"]["stress_survived"] is True


class TestRegimeBreakdown:
    def test_regime_breakdown_insufficient_trades_handling(self):
        chart = prepare_regime_breakdown(_full_manifest())
        assert chart["chart_type"] == "regime_breakdown"
        assert chart["series"]["insufficient_buckets"] == 1
        assert chart["value_axis"] == "sharpe_ratio"

    def test_regime_breakdown_empty(self):
        manifest = {"per_stage_summaries": {}, "chart_data_refs": {}}
        chart = prepare_regime_breakdown(manifest)
        assert chart["series"]["weakest_sharpe"] == 0.0


class TestPrepareAllVisualizations:
    def test_all_refs_present(self):
        viz_refs = prepare_all_visualizations(_full_manifest())
        assert len(viz_refs) == 5
        assert "equity_curves" in viz_refs
        assert "regime_breakdown" in viz_refs

    def test_missing_refs_logged(self):
        manifest = {"chart_data_refs": {"equity_curves": "path/to/eq.arrow"}}
        viz_refs = prepare_all_visualizations(manifest)
        assert "equity_curves" in viz_refs
        assert len(viz_refs) == 1  # Only the one that exists

    def test_empty_refs(self):
        manifest = {"chart_data_refs": {}}
        viz_refs = prepare_all_visualizations(manifest)
        assert len(viz_refs) == 0
