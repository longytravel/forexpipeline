"""Visualization data preparation for evidence packs (Story 5.5, Task 8).

Extracts layout metadata (axis labels, series names, chart titles) from
gauntlet manifest's per_stage_summaries. Does NOT read Arrow IPC files —
actual chart rendering is Epic 4 (Dashboard).
"""
from __future__ import annotations

from logging_setup.setup import get_logger

logger = get_logger("confidence.visualization")


def prepare_equity_curve_chart(gauntlet_manifest: dict) -> dict:
    """Per-fold equity curves + aggregate metadata."""
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    wf = gauntlet_manifest.get("per_stage_summaries", {}).get("walk_forward", {})
    return {
        "chart_type": "equity_curve",
        "title": "Equity Curve — Per-Fold and Aggregate",
        "data_ref": chart_refs.get("equity_curves", ""),
        "x_axis": "bar_index",
        "y_axis": "cumulative_pnl_pips",
        "series": {
            "window_count": wf.get("window_count", 0),
            "aggregate_sharpe": wf.get("median_oos_sharpe", 0.0),
        },
    }


def prepare_walk_forward_chart(gauntlet_manifest: dict) -> dict:
    """Per-window OOS Sharpe/PF with temporal markers."""
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    wf = gauntlet_manifest.get("per_stage_summaries", {}).get("walk_forward", {})
    return {
        "chart_type": "walk_forward_windows",
        "title": "Walk-Forward Analysis — Per-Window OOS Performance",
        "data_ref": chart_refs.get("walk_forward_windows", ""),
        "x_axis": "window_index",
        "y_axis": "oos_sharpe",
        "series": {
            "window_count": wf.get("window_count", 0),
            "negative_windows": wf.get("negative_windows", 0),
            "median_oos_sharpe": wf.get("median_oos_sharpe", 0.0),
        },
    }


def prepare_sensitivity_heatmap(gauntlet_manifest: dict) -> dict:
    """Parameter name × perturbation level → metric change matrix."""
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    pert = gauntlet_manifest.get("per_stage_summaries", {}).get("perturbation", {})
    return {
        "chart_type": "sensitivity_heatmap",
        "title": "Parameter Sensitivity Heatmap",
        "data_ref": chart_refs.get("perturbation_results", ""),
        "x_axis": "perturbation_level",
        "y_axis": "parameter_name",
        "value_axis": "metric_change",
        "series": {
            "max_sensitivity": pert.get("max_sensitivity", 0.0),
            "mean_sensitivity": pert.get("mean_sensitivity", 0.0),
            "cliff_count": pert.get("cliff_count", 0),
        },
    }


def prepare_monte_carlo_distribution(gauntlet_manifest: dict) -> dict:
    """PnL distribution from bootstrap/permutation/stress with CIs."""
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    mc = gauntlet_manifest.get("per_stage_summaries", {}).get("monte_carlo", {})
    return {
        "chart_type": "monte_carlo_distribution",
        "title": "Monte Carlo Distribution — Bootstrap PnL",
        "data_ref": chart_refs.get("monte_carlo_results", ""),
        "x_axis": "pnl_pips",
        "y_axis": "frequency",
        "series": {
            "bootstrap_ci_lower": mc.get("bootstrap_ci_lower", 0.0),
            "stress_survived": mc.get("stress_survived", False),
            "permutation_p_value": mc.get("permutation_p_value", 1.0),
        },
    }


def prepare_regime_breakdown(gauntlet_manifest: dict) -> dict:
    """Volatility tercile × session matrix with Sharpe, win rate, trade count."""
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    regime = gauntlet_manifest.get("per_stage_summaries", {}).get("regime", {})
    return {
        "chart_type": "regime_breakdown",
        "title": "Regime Performance — Volatility × Session",
        "data_ref": chart_refs.get("regime_results", ""),
        "x_axis": "session",
        "y_axis": "volatility_tercile",
        "value_axis": "sharpe_ratio",
        "series": {
            "weakest_sharpe": regime.get("weakest_sharpe", 0.0),
            "strongest_sharpe": regime.get("strongest_sharpe", 0.0),
            "insufficient_buckets": regime.get("insufficient_buckets", 0),
        },
    }


def prepare_all_visualizations(gauntlet_manifest: dict) -> dict[str, str]:
    """Return visualization_refs dict mapping chart names to Arrow IPC paths.

    Validates referenced paths exist in chart_data_refs and assembles the
    ref map. Does NOT read or transform Arrow data.
    """
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    viz_refs: dict[str, str] = {}

    expected_charts = {
        "equity_curves": "equity_curves",
        "walk_forward_windows": "walk_forward_windows",
        "sensitivity_heatmap": "perturbation_results",
        "monte_carlo_distribution": "monte_carlo_results",
        "regime_breakdown": "regime_results",
    }

    for chart_name, ref_key in expected_charts.items():
        ref_path = chart_refs.get(ref_key, "")
        if ref_path:
            viz_refs[chart_name] = ref_path
        else:
            logger.info(
                f"Chart data ref missing for {chart_name} (key: {ref_key})",
                extra={"component": "confidence.visualization", "ctx": {
                    "chart_name": chart_name,
                    "available_refs": list(chart_refs.keys()),
                }},
            )

    return viz_refs
