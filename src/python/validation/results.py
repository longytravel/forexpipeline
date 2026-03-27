"""Validation results writer — Arrow IPC artifacts + markdown summaries (Story 5.4, Task 10).

Each validation stage produces:
1. Arrow IPC artifact with structured results
2. Human-readable markdown summary
Both persisted via crash-safe write pattern.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyarrow as pa

from artifacts.storage import crash_safe_write, crash_safe_write_json
from data_pipeline.utils.safe_write import safe_write_arrow_ipc
from logging_setup.setup import get_logger

logger = get_logger("validation.results")


def write_stage_artifact(stage_name: str, result: Any, output_dir: Path) -> Path:
    """Write Arrow IPC artifact per stage using crash-safe write.

    Returns path to the written artifact.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / f"{stage_name}_results.arrow"

    table = _result_to_arrow(stage_name, result)
    safe_write_arrow_ipc(table, artifact_path)

    logger.info(
        f"Wrote {stage_name} artifact: {artifact_path}",
        extra={
            "component": "validation.results",
            "ctx": {"stage": stage_name, "path": str(artifact_path)},
        },
    )
    return artifact_path


def write_stage_summary(stage_name: str, result: Any, output_dir: Path) -> Path:
    """Write human-readable markdown summary per stage.

    Returns path to the written summary.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{stage_name}_summary.md"

    content = _result_to_markdown(stage_name, result)
    crash_safe_write(str(summary_path), content)

    logger.info(
        f"Wrote {stage_name} summary: {summary_path}",
        extra={
            "component": "validation.results",
            "ctx": {"stage": stage_name, "path": str(summary_path)},
        },
    )
    return summary_path


def write_gauntlet_manifest(
    results: Any,
    optimization_manifest: dict,
    output_dir: Path,
    validation_config: dict | None = None,
    artifact_paths: dict[int, dict[str, str]] | None = None,
) -> Path:
    """Write JSON manifest linking all artifacts.

    Includes all fields required by Story 5.5 downstream contract:
    optimization_run_id, total_optimization_trials, candidate_rank,
    per_stage_metric_ids, gate_results, chart_data_refs, config_hash,
    research_brief_versions.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "gauntlet_manifest.json"

    gate_results = {}
    candidate_summaries = []
    chart_data_refs = {}

    # Compute config hash for reproducibility proof
    config_hash = ""
    if validation_config:
        config_str = json.dumps(validation_config, sort_keys=True, default=str)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]

    for cv in results.candidates:
        # Per-stage metric IDs for evidence narrative citations
        per_stage_metric_ids = {}
        for stage_name, stage_output in cv.stages.items():
            per_stage_metric_ids[stage_name] = list(stage_output.metrics.keys())

        candidate_summary = {
            "candidate_id": cv.candidate_id,
            "candidate_rank": optimization_manifest.get(
                "candidate_ranks", {}
            ).get(str(cv.candidate_id), cv.candidate_id),
            "short_circuited": cv.short_circuited,
            "hard_gate_failures": cv.hard_gate_failures,
            "is_oos_divergence": cv.is_oos_divergence,
            "per_stage_metric_ids": per_stage_metric_ids,
            "stages": {},
        }
        for stage_name, stage_output in cv.stages.items():
            candidate_summary["stages"][stage_name] = {
                "passed": stage_output.passed,
                "metrics": stage_output.metrics,
            }
        candidate_summaries.append(candidate_summary)

        # Collect chart data refs from artifact paths
        if artifact_paths and cv.candidate_id in artifact_paths:
            chart_data_refs[str(cv.candidate_id)] = artifact_paths[cv.candidate_id]

    # Collect gate results
    for cv in results.candidates:
        for stage_name, stage_output in cv.stages.items():
            if stage_name not in gate_results:
                gate_results[stage_name] = {"pass_count": 0, "fail_count": 0}
            if stage_output.passed:
                gate_results[stage_name]["pass_count"] += 1
            else:
                gate_results[stage_name]["fail_count"] += 1

    manifest = {
        "optimization_run_id": optimization_manifest.get("run_id", ""),
        "total_optimization_trials": optimization_manifest.get("total_trials", 0),
        "n_candidates": len(results.candidates),
        "stages": results.run_manifest.get("stages", []),
        "gate_results": gate_results,
        "dsr": {
            "dsr": results.dsr.dsr if results.dsr else None,
            "p_value": results.dsr.p_value if results.dsr else None,
            "passed": results.dsr.passed if results.dsr else None,
            "num_trials": results.dsr.num_trials if results.dsr else None,
        },
        "candidates": candidate_summaries,
        "chart_data_refs": chart_data_refs,
        "config_hash": config_hash,
        "research_brief_versions": optimization_manifest.get(
            "research_brief_versions", {}
        ),
    }

    crash_safe_write_json(manifest, manifest_path)

    logger.info(
        f"Wrote gauntlet manifest: {manifest_path}",
        extra={
            "component": "validation.results",
            "ctx": {"path": str(manifest_path), "n_candidates": len(candidate_summaries)},
        },
    )
    return manifest_path


def _result_to_arrow(stage_name: str, result: Any) -> pa.Table:
    """Convert stage result to Arrow table."""
    from validation.walk_forward import WalkForwardResult
    from validation.cpcv import CPCVResult
    from validation.perturbation import PerturbationResult
    from validation.monte_carlo import MonteCarloResult
    from validation.regime_analysis import RegimeResult

    if isinstance(result, WalkForwardResult):
        # Include train/test boundaries for visualization data (AC12)
        windows = result.windows if result.windows else []
        specs = result.window_specs if hasattr(result, "window_specs") and result.window_specs else []
        if windows:
            data = {
                "window_id": [w.window_id for w in windows],
                "oos_sharpe": [w.oos_sharpe for w in windows],
                "oos_pf": [w.oos_pf for w in windows],
                "oos_drawdown": [w.oos_drawdown for w in windows],
                "oos_trades": [w.oos_trades for w in windows],
                "oos_pnl": [w.oos_pnl for w in windows],
                "is_sharpe": [w.is_sharpe for w in windows],
                "is_pf": [w.is_pf for w in windows],
            }
            # Add boundary data if window specs are available
            if specs and len(specs) == len(windows):
                data["train_start"] = [s.train_start for s in specs]
                data["train_end"] = [s.train_end for s in specs]
                data["test_start"] = [s.test_start for s in specs]
                data["test_end"] = [s.test_end for s in specs]
            return pa.table(data)
        return pa.table({
            "window_id": [0], "oos_sharpe": [0.0], "oos_pf": [0.0],
            "oos_drawdown": [0.0], "oos_trades": [0], "oos_pnl": [0.0],
            "is_sharpe": [0.0], "is_pf": [0.0],
        })

    if isinstance(result, CPCVResult):
        return pa.table({
            "combination_id": [c.combination_id for c in result.combinations] if result.combinations else [0],
            "oos_sharpe": [c.oos_sharpe for c in result.combinations] if result.combinations else [0.0],
            "oos_pf": [c.oos_pf for c in result.combinations] if result.combinations else [0.0],
            "oos_pnl": [c.oos_pnl for c in result.combinations] if result.combinations else [0.0],
        })

    if isinstance(result, PerturbationResult):
        rows_param = []
        rows_level = []
        rows_sensitivity = []
        for param, levels in result.sensitivities.items():
            for level, sens in levels.items():
                rows_param.append(param)
                rows_level.append(float(level))
                rows_sensitivity.append(sens)
        if not rows_param:
            rows_param, rows_level, rows_sensitivity = ["none"], [0.0], [0.0]
        return pa.table({
            "param_name": rows_param,
            "perturbation_level": rows_level,
            "sensitivity": rows_sensitivity,
        })

    if isinstance(result, MonteCarloResult):
        rows = []
        if result.bootstrap:
            rows.append({
                "simulation_type": "bootstrap",
                "metric_name": "sharpe_ci_lower",
                "metric_value": result.bootstrap.sharpe_ci_lower,
            })
            rows.append({
                "simulation_type": "bootstrap",
                "metric_name": "sharpe_ci_upper",
                "metric_value": result.bootstrap.sharpe_ci_upper,
            })
        if result.permutation:
            rows.append({
                "simulation_type": "permutation",
                "metric_name": "p_value",
                "metric_value": result.permutation.p_value,
            })
        if result.stress:
            for mult, survived in result.stress.survival.items():
                rows.append({
                    "simulation_type": "stress",
                    "metric_name": f"survival_{mult}x",
                    "metric_value": 1.0 if survived else 0.0,
                })
        if not rows:
            rows = [{"simulation_type": "none", "metric_name": "none", "metric_value": 0.0}]
        return pa.table({
            "simulation_type": [r["simulation_type"] for r in rows],
            "metric_name": [r["metric_name"] for r in rows],
            "metric_value": [r["metric_value"] for r in rows],
        })

    if isinstance(result, RegimeResult):
        return pa.table({
            "volatility_tercile": [b.volatility for b in result.buckets] if result.buckets else ["none"],
            "session": [b.session for b in result.buckets] if result.buckets else ["none"],
            "trade_count": [b.trade_count for b in result.buckets] if result.buckets else [0],
            "win_rate": [b.win_rate for b in result.buckets] if result.buckets else [0.0],
            "avg_pnl": [b.avg_pnl for b in result.buckets] if result.buckets else [0.0],
            "sharpe": [b.sharpe for b in result.buckets] if result.buckets else [0.0],
            "sufficient": [b.sufficient for b in result.buckets] if result.buckets else [False],
        })

    # Generic fallback
    return pa.table({"stage": [stage_name], "status": ["complete"]})


def _result_to_markdown(stage_name: str, result: Any) -> str:
    """Convert stage result to human-readable markdown."""
    from validation.walk_forward import WalkForwardResult
    from validation.cpcv import CPCVResult
    from validation.perturbation import PerturbationResult
    from validation.monte_carlo import MonteCarloResult
    from validation.regime_analysis import RegimeResult

    lines = [f"# Validation: {stage_name}", ""]

    if isinstance(result, WalkForwardResult):
        lines.append(f"**Aggregate OOS Sharpe:** {result.aggregate_sharpe:.4f}")
        lines.append(f"**Aggregate OOS Profit Factor:** {result.aggregate_pf:.4f}")
        lines.append(f"**IS/OOS Divergence:** {result.is_oos_divergence:.4f}")
        lines.append(f"**Windows:** {len(result.windows)}")
        lines.append("")
        lines.append("| Window | OOS Sharpe | OOS PF | OOS Trades | OOS PnL |")
        lines.append("|--------|-----------|--------|------------|---------|")
        for w in result.windows:
            lines.append(
                f"| {w.window_id} | {w.oos_sharpe:.4f} | {w.oos_pf:.4f} "
                f"| {w.oos_trades} | {w.oos_pnl:.2f} |"
            )

    elif isinstance(result, CPCVResult):
        lines.append(f"**PBO:** {result.pbo:.4f}")
        lines.append(f"**PBO Gate:** {'PASS' if result.pbo_gate_passed else 'FAIL (RED)'}")
        lines.append(f"**Mean OOS Sharpe:** {result.mean_oos_sharpe:.4f}")
        lines.append(f"**Combinations:** {len(result.combinations)}")

    elif isinstance(result, PerturbationResult):
        lines.append(f"**Max Sensitivity:** {result.max_sensitivity:.4f}")
        lines.append(f"**Fragile Parameters:** {result.fragile_params or 'None'}")
        lines.append("")
        for param, levels in result.sensitivities.items():
            lines.append(f"### {param}")
            for level, sens in sorted(levels.items()):
                lines.append(f"  - Level {level:+.0%}: sensitivity = {sens:.4f}")

    elif isinstance(result, MonteCarloResult):
        if result.bootstrap:
            lines.append(f"**Bootstrap Sharpe CI:** [{result.bootstrap.sharpe_ci_lower:.4f}, {result.bootstrap.sharpe_ci_upper:.4f}]")
        if result.permutation:
            lines.append(f"**Permutation p-value:** {result.permutation.p_value:.4f}")
        if result.stress:
            lines.append("**Stress Test Survival:**")
            for mult, survived in result.stress.survival.items():
                lines.append(f"  - {mult}x costs: {'SURVIVED' if survived else 'FAILED'}")

    elif isinstance(result, RegimeResult):
        lines.append(f"**Sufficient Buckets:** {result.sufficient_buckets}/{result.total_buckets}")
        lines.append(f"**Weakest Regime:** {result.weakest_regime}")
        lines.append("")
        lines.append("| Volatility | Session | Trades | Win Rate | Sharpe | Sufficient |")
        lines.append("|-----------|---------|--------|----------|--------|------------|")
        for b in result.buckets:
            lines.append(
                f"| {b.volatility} | {b.session} | {b.trade_count} "
                f"| {b.win_rate:.2%} | {b.sharpe:.4f} | {'Yes' if b.sufficient else 'No'} |"
            )

    else:
        lines.append(f"Stage completed. Result type: {type(result).__name__}")

    lines.append("")
    return "\n".join(lines)
