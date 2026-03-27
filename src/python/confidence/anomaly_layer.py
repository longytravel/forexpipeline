"""Two-tier anomaly detection for confidence scoring (Story 5.5, Task 5).

Layer A: Per-candidate silent anomaly scoring (always runs).
Layer B: Surface flags when ≥2 detectors agree or tier-1 academic tests trigger.

Reuses AnomalyType, AnomalyFlag, AnomalyReport, Severity from analysis/models.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from analysis.models import AnomalyFlag, AnomalyReport, AnomalyType, Severity
from logging_setup.setup import get_logger

logger = get_logger("confidence.anomaly")


def run_layer_a(
    candidates_manifests: list[dict],
    min_population_size: int = 20,
) -> dict[int, list[AnomalyFlag]]:
    """Layer A: per-candidate anomaly scoring (silent — not surfaced yet).

    Per-candidate detectors (always run):
    - IS-OOS divergence
    - Regime concentration
    - Perturbation cliff clusters
    - Walk-forward degradation
    - Monte Carlo tail risk

    Cross-candidate population tests (only when len(candidates) >= min_population_size):
    - Sharpe distribution shape, parameter clustering, OOS return correlation
    - Skipped in V1 if below threshold.
    """
    scores: dict[int, list[AnomalyFlag]] = {}

    for manifest in candidates_manifests:
        cid = manifest.get("candidate_id", 0)
        flags: list[AnomalyFlag] = []

        flags.extend(_detect_is_oos_divergence(manifest))
        flags.extend(_detect_regime_concentration(manifest))
        flags.extend(_detect_perturbation_cliff_cluster(manifest))
        flags.extend(_detect_walk_forward_degradation(manifest))
        flags.extend(_detect_monte_carlo_tail_risk(manifest))

        scores[cid] = flags

    # Cross-candidate population tests
    if len(candidates_manifests) >= min_population_size:
        _run_population_tests(candidates_manifests, scores)
    else:
        logger.info(
            f"Skipping cross-population anomaly tests: "
            f"{len(candidates_manifests)} candidates < {min_population_size} minimum",
            extra={"component": "confidence.anomaly", "ctx": {
                "n_candidates": len(candidates_manifests),
                "min_population_size": min_population_size,
            }},
        )

    return scores


def run_layer_b(
    candidates_manifests: list[dict],
    layer_a_scores: dict[int, list[AnomalyFlag]],
) -> dict[int, AnomalyReport]:
    """Layer B: surface flags when criteria met.

    Surface when:
    - ≥2 Layer A detectors agree for a candidate, OR
    - Tier-1 academic tests trigger (DSR/PBO already in hard gates)
    """
    reports: dict[int, AnomalyReport] = {}
    now = datetime.now(timezone.utc).isoformat()

    for manifest in candidates_manifests:
        cid = manifest.get("candidate_id", 0)
        all_flags = layer_a_scores.get(cid, [])

        surfaced: list[AnomalyFlag] = []

        # Surface if ≥2 distinct detectors fired (AC7: "multiple detectors agree")
        distinct_detector_types = {f.type for f in all_flags}
        if len(distinct_detector_types) >= 2:
            surfaced.extend(all_flags)
        # Also surface tier-1 academic triggers individually
        else:
            tier1_types = {
                AnomalyType.IS_OOS_DIVERGENCE,
                AnomalyType.WALK_FORWARD_DEGRADATION,
                AnomalyType.REGIME_CONCENTRATION,
            }
            for flag in all_flags:
                if flag.type in tier1_types and flag.severity == Severity.ERROR:
                    surfaced.append(flag)

        reports[cid] = AnomalyReport(
            backtest_id=f"cand_{cid}",
            anomalies=surfaced,
            run_timestamp=now,
        )

    return reports


# ---------------------------------------------------------------------------
# Per-candidate detectors (Layer A)
# ---------------------------------------------------------------------------

def _detect_is_oos_divergence(manifest: dict) -> list[AnomalyFlag]:
    """IS vs OOS performance divergence (FR35)."""
    summaries = manifest.get("per_stage_summaries", {})
    wf = summaries.get("walk_forward", {})
    cpcv = summaries.get("cpcv", {})

    oos_sharpe = wf.get("median_oos_sharpe", 0.0)
    is_sharpe = cpcv.get("mean_is_sharpe", oos_sharpe)

    if abs(is_sharpe) < 1e-9 and abs(oos_sharpe) < 1e-9:
        return []

    max_val = max(abs(is_sharpe), abs(oos_sharpe), 0.01)
    divergence = abs(is_sharpe - oos_sharpe) / max_val

    if divergence > 0.5:
        severity = Severity.ERROR if divergence > 0.8 else Severity.WARNING
        return [AnomalyFlag(
            type=AnomalyType.IS_OOS_DIVERGENCE,
            severity=severity,
            description=(
                f"IS-OOS Sharpe divergence of {divergence:.1%}: "
                f"IS={is_sharpe:.2f}, OOS={oos_sharpe:.2f}"
            ),
            evidence={
                "is_sharpe": is_sharpe,
                "oos_sharpe": oos_sharpe,
                "divergence_ratio": round(divergence, 3),
                "metric_id": manifest.get("per_stage_metric_ids", {}).get("walk_forward", ""),
            },
            recommendation="Investigate potential overfitting — large IS-OOS gap suggests the strategy may not generalize.",
        )]
    return []


def _detect_regime_concentration(manifest: dict) -> list[AnomalyFlag]:
    """Performance concentrated in a single regime."""
    regime = manifest.get("per_stage_summaries", {}).get("regime", {})
    if not regime:
        return []

    weakest = regime.get("weakest_sharpe", 0.0)
    strongest = regime.get("strongest_sharpe", 0.0)

    if strongest <= 0:
        return []

    ratio = weakest / strongest if strongest > 0 else 0.0

    if ratio < 0.15:
        severity = Severity.ERROR if ratio < 0.05 else Severity.WARNING
        return [AnomalyFlag(
            type=AnomalyType.REGIME_CONCENTRATION,
            severity=severity,
            description=(
                f"Regime concentration detected: weakest/strongest Sharpe ratio = {ratio:.2f} "
                f"(weakest={weakest:.2f}, strongest={strongest:.2f})"
            ),
            evidence={
                "weakest_sharpe": weakest,
                "strongest_sharpe": strongest,
                "ratio": round(ratio, 3),
                "insufficient_buckets": regime.get("insufficient_buckets", 0),
                "metric_id": manifest.get("per_stage_metric_ids", {}).get("regime", ""),
            },
            recommendation="Strategy performance is concentrated in specific market conditions. Review regime breakdown for session/volatility bias.",
        )]
    return []


def _detect_perturbation_cliff_cluster(manifest: dict) -> list[AnomalyFlag]:
    """Multiple parameters show sensitivity cliffs."""
    pert = manifest.get("per_stage_summaries", {}).get("perturbation", {})
    if not pert:
        return []

    cliff_count = pert.get("cliff_count", 0)
    max_sensitivity = pert.get("max_sensitivity", 0.0)

    if cliff_count >= 2 or max_sensitivity > 0.5:
        severity = Severity.ERROR if cliff_count >= 3 or max_sensitivity > 0.7 else Severity.WARNING
        return [AnomalyFlag(
            type=AnomalyType.PERTURBATION_CLIFF_CLUSTER,
            severity=severity,
            description=(
                f"Perturbation cliff cluster: {cliff_count} parameters show sensitivity cliffs, "
                f"max sensitivity = {max_sensitivity:.3f}"
            ),
            evidence={
                "cliff_count": cliff_count,
                "max_sensitivity": max_sensitivity,
                "mean_sensitivity": pert.get("mean_sensitivity", 0.0),
                "metric_id": manifest.get("per_stage_metric_ids", {}).get("perturbation", ""),
            },
            recommendation="Strategy is fragile to parameter perturbation. Small parameter changes cause large performance drops.",
        )]
    return []


def _detect_walk_forward_degradation(manifest: dict) -> list[AnomalyFlag]:
    """OOS performance degrades across later walk-forward windows."""
    wf = manifest.get("per_stage_summaries", {}).get("walk_forward", {})
    if not wf:
        return []

    window_count = wf.get("window_count", 0)
    negative_windows = wf.get("negative_windows", 0)

    if window_count <= 0:
        return []

    neg_ratio = negative_windows / window_count

    if neg_ratio > 0.4:
        severity = Severity.ERROR if neg_ratio > 0.6 else Severity.WARNING
        return [AnomalyFlag(
            type=AnomalyType.WALK_FORWARD_DEGRADATION,
            severity=severity,
            description=(
                f"Walk-forward degradation: {negative_windows}/{window_count} "
                f"windows have negative OOS Sharpe ({neg_ratio:.0%})"
            ),
            evidence={
                "window_count": window_count,
                "negative_windows": negative_windows,
                "negative_ratio": round(neg_ratio, 3),
                "median_oos_sharpe": wf.get("median_oos_sharpe", 0.0),
                "metric_id": manifest.get("per_stage_metric_ids", {}).get("walk_forward", ""),
            },
            recommendation="Strategy shows inconsistent OOS performance across time periods. Recent windows may perform poorly.",
        )]
    return []


def _detect_monte_carlo_tail_risk(manifest: dict) -> list[AnomalyFlag]:
    """Excessive tail risk in bootstrap distribution."""
    mc = manifest.get("per_stage_summaries", {}).get("monte_carlo", {})
    if not mc:
        return []

    ci_lower = mc.get("bootstrap_ci_lower", 0.0)
    p_value = mc.get("permutation_p_value", 1.0)

    flags: list[AnomalyFlag] = []

    if ci_lower < 0:
        flags.append(AnomalyFlag(
            type=AnomalyType.MONTE_CARLO_TAIL_RISK,
            severity=Severity.ERROR if ci_lower < -0.1 else Severity.WARNING,
            description=(
                f"Monte Carlo tail risk: bootstrap CI lower bound = {ci_lower:.3f} "
                f"(negative — strategy may lose money under resampling)"
            ),
            evidence={
                "bootstrap_ci_lower": ci_lower,
                "permutation_p_value": p_value,
                "stress_survived": mc.get("stress_survived", False),
                "metric_id": manifest.get("per_stage_metric_ids", {}).get("monte_carlo", ""),
            },
            recommendation="Strategy has negative expected returns under bootstrap resampling. Investigate whether edge is robust.",
        ))

    if p_value > 0.10:
        flags.append(AnomalyFlag(
            type=AnomalyType.MONTE_CARLO_TAIL_RISK,
            severity=Severity.WARNING,
            description=(
                f"Permutation test p-value = {p_value:.3f} (not significant at 10% level)"
            ),
            evidence={
                "permutation_p_value": p_value,
                "metric_id": manifest.get("per_stage_metric_ids", {}).get("monte_carlo", ""),
            },
            recommendation="Strategy returns may not be distinguishable from random shuffled returns.",
        ))

    return flags


# ---------------------------------------------------------------------------
# Cross-candidate population tests (gated behind min_population_size)
# ---------------------------------------------------------------------------

def _run_population_tests(
    candidates_manifests: list[dict],
    scores: dict[int, list[AnomalyFlag]],
) -> None:
    """Cross-candidate population-level statistical tests.

    Gated behind min_population_size (default: 20).
    V1 implementation: placeholder for Sharpe distribution shape,
    parameter clustering, OOS return correlation.
    """
    logger.warning(
        f"Cross-population anomaly tests triggered for {len(candidates_manifests)} candidates "
        f"but not yet implemented (V1 placeholder). No population-level flags will be produced.",
        extra={"component": "confidence.anomaly", "ctx": {
            "n_candidates": len(candidates_manifests),
        }},
    )
    # TODO(V2): Implement population tests — Shapiro-Wilk on Sharpe distribution,
    # DBSCAN on parameter clusters, correlation matrix of OOS returns.
    # These run only when len(candidates) >= min_population_size (default 20).
