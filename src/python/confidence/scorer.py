"""Weighted composite scorer for confidence scoring (Story 5.5, Task 4).

Normalizes gauntlet manifest metrics to 0.0–1.0 range, applies configured
weights, computes composite score, and assigns RED/YELLOW/GREEN rating.
"""
from __future__ import annotations

from datetime import datetime, timezone

from confidence.config import ConfidenceConfig, HardGateConfig, ThresholdConfig, WeightConfig
from confidence.gates import any_gate_failed, evaluate_hard_gates
from confidence.models import (
    CandidateRating,
    ComponentScore,
    ConfidenceBreakdown,
    ConfidenceScore,
    GateResult,
)

# Normalization floor/ceiling constants — documented, not operator-configurable.
# These define the range for mapping raw values to 0.0–1.0.
_SHARPE_FLOOR = -0.5
_SHARPE_CEILING = 2.0
_MAX_SENSITIVITY_CEILING = 1.0


def compute_component_scores(
    gauntlet_manifest: dict,
    config: WeightConfig,
    hard_gate_config: "HardGateConfig | None" = None,
    gate_results: "list[GateResult] | None" = None,
) -> list[ComponentScore]:
    """Compute normalized and weighted scores for each component.

    Reads per_stage_summaries from the gauntlet manifest.
    Missing stages (short-circuited candidates) score 0.0.

    Args:
        hard_gate_config: Used for PBO threshold (avoids hardcoded value).
        gate_results: Used to populate per-component gate_result and
            identify which gate caused a short-circuit.
    """
    summaries = gauntlet_manifest.get("per_stage_summaries", {})
    short_circuited = gauntlet_manifest.get("gate_results", {}).get("short_circuited", False)
    weights = config.as_dict()
    components: list[ComponentScore] = []

    # Build gate lookup by name for per-component attribution
    gate_by_name: dict[str, GateResult] = {}
    failing_gate_name = ""
    if gate_results:
        for gr in gate_results:
            gate_by_name[gr.gate_name] = gr
            if not gr.passed and not failing_gate_name:
                failing_gate_name = gr.gate_name

    # PBO threshold from config — must match hard_gates.pbo_max_threshold
    if hard_gate_config is not None:
        pbo_threshold = hard_gate_config.pbo_max_threshold
    else:
        # Fallback only for standalone calls without full config;
        # mirrors the default in config/base.toml [confidence.hard_gates]
        from confidence.config import DEFAULT_PBO_MAX_THRESHOLD
        pbo_threshold = DEFAULT_PBO_MAX_THRESHOLD

    # Walk-forward OOS consistency
    wf = summaries.get("walk_forward", {})
    wf_raw = wf.get("median_oos_sharpe", 0.0)
    wf_norm = _normalize_sharpe(wf_raw)
    wf_weight = weights["walk_forward_oos_consistency"]
    components.append(ComponentScore(
        component_name="walk_forward_oos_consistency",
        raw_value=wf_raw,
        normalized_score=wf_norm,
        weight=wf_weight,
        weighted_contribution=wf_norm * wf_weight,
        interpretation=_interpret_wf(wf_raw, wf_norm, wf, short_circuited, failing_gate_name),
    ))

    # CPCV PBO margin
    cpcv = summaries.get("cpcv", {})
    pbo_raw = cpcv.get("pbo", 1.0)
    # Use the actual PBO from cpcv summary, fall back to gate_results
    if "pbo" in cpcv:
        pbo_raw = cpcv["pbo"]
    pbo_norm = _normalize_pbo_margin(pbo_raw, pbo_threshold)
    pbo_weight = weights["cpcv_pbo_margin"]
    components.append(ComponentScore(
        component_name="cpcv_pbo_margin",
        raw_value=pbo_raw,
        normalized_score=pbo_norm,
        weight=pbo_weight,
        weighted_contribution=pbo_norm * pbo_weight,
        interpretation=_interpret_pbo(pbo_raw, pbo_norm, short_circuited, failing_gate_name),
        gate_result=gate_by_name.get("pbo_threshold"),
    ))

    # Parameter stability
    pert = summaries.get("perturbation", {})
    mean_sens = pert.get("mean_sensitivity", 1.0)
    param_norm = _normalize_parameter_stability(mean_sens)
    param_weight = weights["parameter_stability"]
    components.append(ComponentScore(
        component_name="parameter_stability",
        raw_value=mean_sens,
        normalized_score=param_norm,
        weight=param_weight,
        weighted_contribution=param_norm * param_weight,
        interpretation=_interpret_param(mean_sens, param_norm, short_circuited, failing_gate_name),
    ))

    # Monte Carlo stress survival
    mc = summaries.get("monte_carlo", {})
    mc_raw = _compute_mc_survival_fraction(mc)
    mc_norm = max(0.0, min(1.0, mc_raw))
    mc_weight = weights["monte_carlo_stress_survival"]
    components.append(ComponentScore(
        component_name="monte_carlo_stress_survival",
        raw_value=mc_raw,
        normalized_score=mc_norm,
        weight=mc_weight,
        weighted_contribution=mc_norm * mc_weight,
        interpretation=_interpret_mc(mc_raw, mc_norm, short_circuited, failing_gate_name),
        gate_result=gate_by_name.get("cost_stress_survival"),
    ))

    # Regime uniformity
    regime = summaries.get("regime", {})
    regime_raw = _compute_regime_uniformity(regime)
    regime_norm = max(0.0, min(1.0, regime_raw))
    regime_weight = weights["regime_uniformity"]
    components.append(ComponentScore(
        component_name="regime_uniformity",
        raw_value=regime_raw,
        normalized_score=regime_norm,
        weight=regime_weight,
        weighted_contribution=regime_norm * regime_weight,
        interpretation=_interpret_regime(regime_raw, regime_norm, regime, short_circuited, failing_gate_name),
    ))

    # IS-OOS coherence (FR35)
    coherence_raw = _compute_is_oos_coherence(summaries)
    coherence_norm = max(0.0, min(1.0, coherence_raw))
    coherence_weight = weights["in_sample_oos_coherence"]
    components.append(ComponentScore(
        component_name="in_sample_oos_coherence",
        raw_value=coherence_raw,
        normalized_score=coherence_norm,
        weight=coherence_weight,
        weighted_contribution=coherence_norm * coherence_weight,
        interpretation=_interpret_coherence(coherence_raw, coherence_norm, short_circuited, failing_gate_name),
    ))

    return components


def compute_composite_score(components: list[ComponentScore]) -> float:
    """Sum of weighted contributions."""
    return sum(c.weighted_contribution for c in components)


def assign_rating(
    composite: float,
    hard_gates_passed: bool,
    config: ThresholdConfig,
) -> CandidateRating:
    """Map composite score + gate status to RED/YELLOW/GREEN."""
    if not hard_gates_passed:
        return CandidateRating.RED
    if composite >= config.green_minimum:
        return CandidateRating.GREEN
    if composite >= config.yellow_minimum:
        return CandidateRating.YELLOW
    return CandidateRating.RED


def score_candidate(
    gauntlet_manifest: dict,
    config: ConfidenceConfig,
) -> ConfidenceScore:
    """Full scoring pipeline for a single candidate.

    Orchestrates: evaluate_hard_gates → compute_component_scores →
    compute_composite → assign_rating → build ConfidenceScore.
    """
    gates = evaluate_hard_gates(gauntlet_manifest, config.hard_gates)
    hard_gates_passed = not any_gate_failed(gates)

    components = compute_component_scores(
        gauntlet_manifest, config.weights,
        hard_gate_config=config.hard_gates,
        gate_results=gates,
    )
    composite = compute_composite_score(components)
    rating = assign_rating(composite, hard_gates_passed, config.thresholds)

    breakdown = ConfidenceBreakdown(
        components=components,
        gates=gates,
        hard_gate_passed=hard_gates_passed,
        composite_score=composite,
    )

    return ConfidenceScore(
        candidate_id=gauntlet_manifest.get("candidate_id", 0),
        optimization_run_id=gauntlet_manifest.get("optimization_run_id", ""),
        rating=rating,
        composite_score=composite,
        breakdown=breakdown,
        scored_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_sharpe(raw: float) -> float:
    """Normalize Sharpe to 0.0–1.0 using floor/ceiling."""
    return max(0.0, min(1.0, (raw - _SHARPE_FLOOR) / (_SHARPE_CEILING - _SHARPE_FLOOR)))


def _normalize_pbo_margin(pbo: float, threshold: float) -> float:
    """Normalize PBO margin: (threshold - actual) / threshold → 0.0–1.0."""
    if threshold <= 0:
        return 0.0
    margin = (threshold - pbo) / threshold
    return max(0.0, min(1.0, margin))


def _normalize_parameter_stability(mean_sensitivity: float) -> float:
    """Lower sensitivity is better: 1.0 - (mean / ceiling)."""
    return max(0.0, min(1.0, 1.0 - (mean_sensitivity / _MAX_SENSITIVITY_CEILING)))


def _compute_mc_survival_fraction(mc_summary: dict) -> float:
    """Fraction of Monte Carlo simulations passing."""
    if not mc_summary:
        return 0.0
    stress_survived = 1.0 if mc_summary.get("stress_survived", False) else 0.0
    p_value = mc_summary.get("permutation_p_value", 1.0)
    # p_value < 0.05 means significant → good
    permutation_pass = 1.0 if p_value < 0.05 else 0.0
    ci_lower = mc_summary.get("bootstrap_ci_lower", 0.0)
    bootstrap_pass = 1.0 if ci_lower > 0.0 else 0.0
    return (stress_survived + permutation_pass + bootstrap_pass) / 3.0


def _compute_regime_uniformity(regime_summary: dict) -> float:
    """1.0 - coefficient of variation across regime Sharpe values."""
    if not regime_summary:
        return 0.0
    weakest = regime_summary.get("weakest_sharpe", 0.0)
    strongest = regime_summary.get("strongest_sharpe", 0.0)
    if strongest <= 0:
        return 0.0
    # Simple spread metric: weakest/strongest as uniformity proxy
    return max(0.0, min(1.0, weakest / strongest))


def _compute_is_oos_coherence(summaries: dict) -> float:
    """IS vs OOS coherence: 1.0 - normalized divergence."""
    wf = summaries.get("walk_forward", {})
    cpcv = summaries.get("cpcv", {})

    # Compare CPCV mean IS Sharpe vs walk-forward median OOS Sharpe (FR35)
    oos_sharpe = wf.get("median_oos_sharpe", 0.0)
    is_sharpe = cpcv.get("mean_is_sharpe", oos_sharpe)

    if abs(is_sharpe) < 1e-9 and abs(oos_sharpe) < 1e-9:
        return 1.0  # Both zero — no divergence

    # Normalized absolute divergence
    max_val = max(abs(is_sharpe), abs(oos_sharpe), 0.01)
    divergence = abs(is_sharpe - oos_sharpe) / max_val
    return max(0.0, min(1.0, 1.0 - divergence))


# ---------------------------------------------------------------------------
# Interpretation helpers
# ---------------------------------------------------------------------------

def _interpret_wf(raw: float, norm: float, wf: dict, short_circuited: bool, failing_gate: str = "") -> str:
    if short_circuited and not wf:
        return f"Stage skipped due to {failing_gate or 'unknown'} gate failure — scored as 0.0"
    n_windows = wf.get("window_count", 0)
    neg = wf.get("negative_windows", 0)
    return (
        f"Median OOS Sharpe {raw:.2f} across {n_windows} windows "
        f"({neg} negative) — normalized to {norm:.2f}"
    )


def _interpret_pbo(raw: float, norm: float, short_circuited: bool, failing_gate: str = "") -> str:
    if short_circuited and raw >= 1.0:
        return f"Stage skipped due to {failing_gate or 'unknown'} gate failure — scored as 0.0"
    return f"PBO {raw:.3f} — margin score {norm:.2f}"


def _interpret_param(raw: float, norm: float, short_circuited: bool, failing_gate: str = "") -> str:
    if short_circuited and raw >= 1.0:
        return f"Stage skipped due to {failing_gate or 'unknown'} gate failure — scored as 0.0"
    return f"Mean perturbation sensitivity {raw:.3f} — stability score {norm:.2f}"


def _interpret_mc(raw: float, norm: float, short_circuited: bool, failing_gate: str = "") -> str:
    if short_circuited and raw == 0.0:
        return f"Stage skipped due to {failing_gate or 'unknown'} gate failure — scored as 0.0"
    return f"Monte Carlo survival fraction {raw:.2f} — normalized {norm:.2f}"


def _interpret_regime(raw: float, norm: float, regime: dict, short_circuited: bool, failing_gate: str = "") -> str:
    if short_circuited and not regime:
        return f"Stage skipped due to {failing_gate or 'unknown'} gate failure — scored as 0.0"
    insuff = regime.get("insufficient_buckets", 0)
    suffix = f" ({insuff} insufficient-trade buckets)" if insuff else ""
    return f"Regime uniformity {raw:.2f} — normalized {norm:.2f}{suffix}"


def _interpret_coherence(raw: float, norm: float, short_circuited: bool, failing_gate: str = "") -> str:
    if short_circuited and raw == 0.0:
        return f"Stage skipped due to {failing_gate or 'unknown'} gate failure — scored as 0.0"
    return f"IS-OOS coherence {raw:.2f} — low divergence" if norm > 0.7 else f"IS-OOS coherence {raw:.2f} — notable divergence"
