"""Template-driven narrative engine for confidence scoring (Story 5.5, Task 6).

All narratives are deterministic templates — NOT LLM-generated (D11).
Every claim cites an exact metric ID or chart ID from the gauntlet manifest.
"""
from __future__ import annotations

from analysis.models import AnomalyReport, NarrativeResult, Severity
from confidence.models import CandidateRating, ConfidenceScore


def generate_confidence_narrative(
    confidence_score: ConfidenceScore,
    gauntlet_manifest: dict,
    anomaly_report: AnomalyReport,
) -> NarrativeResult:
    """Generate a structured narrative from confidence score and anomaly data.

    Template-driven, following the pattern from analysis/narrative.py.
    Every string references a specific per_stage_metric_id or chart_data_ref.
    """
    metric_ids = gauntlet_manifest.get("per_stage_metric_ids", {})
    chart_refs = gauntlet_manifest.get("chart_data_refs", {})
    summaries = gauntlet_manifest.get("per_stage_summaries", {})

    overview = _build_overview(confidence_score, summaries, metric_ids)
    metrics = _build_metrics_section(confidence_score, metric_ids)
    strengths = _build_strengths(confidence_score, metric_ids)
    weaknesses = _build_weaknesses(confidence_score, anomaly_report, metric_ids)
    session_breakdown = _build_session_breakdown(summaries, chart_refs)
    risk_assessment = _build_risk_assessment(anomaly_report, metric_ids)

    return NarrativeResult(
        overview=overview,
        metrics=metrics,
        strengths=strengths,
        weaknesses=weaknesses,
        session_breakdown=session_breakdown,
        risk_assessment=risk_assessment,
    )


def _build_overview(
    score: ConfidenceScore,
    summaries: dict,
    metric_ids: dict,
) -> str:
    """Overview: rating, composite, dominant edge, top risk."""
    cid = score.candidate_id
    rating = score.rating.value
    composite = score.composite_score

    # Find dominant edge (highest scoring component)
    components = score.breakdown.components
    if components:
        best = max(components, key=lambda c: c.normalized_score)
        best_mid = _component_to_metric_id(best.component_name, metric_ids)
        edge = f"Strongest dimension: {best.component_name} ({best.normalized_score:.2f}) [metric:{best_mid}]"
    else:
        edge = "No component scores available [metric:n/a]"

    # Find top risk
    if components:
        worst = min(components, key=lambda c: c.normalized_score)
        worst_mid = _component_to_metric_id(worst.component_name, metric_ids)
        risk = f"Weakest dimension: {worst.component_name} ({worst.normalized_score:.2f}) [metric:{worst_mid}]"
    else:
        risk = "No component scores available [metric:n/a]"

    return (
        f"Candidate {cid} rated {rating} (composite: {composite:.2f}). "
        f"{edge}. {risk}."
    )


def _build_metrics_section(
    score: ConfidenceScore,
    metric_ids: dict,
) -> dict:
    """Include all component scores with weights and interpretations."""
    metrics = {}
    for c in score.breakdown.components:
        component_metric_id = _component_to_metric_id(c.component_name, metric_ids)
        metrics[c.component_name] = {
            "raw_value": c.raw_value,
            "normalized_score": c.normalized_score,
            "weight": c.weight,
            "weighted_contribution": c.weighted_contribution,
            "interpretation": c.interpretation,
            "metric_ref": f"[metric:{component_metric_id}]",
        }
    metrics["composite_score"] = score.composite_score
    metrics["rating"] = score.rating.value
    metrics["hard_gates_passed"] = score.breakdown.hard_gate_passed
    return metrics


def _build_strengths(
    score: ConfidenceScore,
    metric_ids: dict,
) -> list[str]:
    """Components scoring above 0.8 with their metric IDs."""
    strengths = []
    for c in score.breakdown.components:
        if c.normalized_score > 0.8:
            mid = _component_to_metric_id(c.component_name, metric_ids)
            strengths.append(
                f"{c.component_name}: {c.normalized_score:.2f} — {c.interpretation} "
                f"[metric:{mid}]"
            )
    if not strengths:
        strengths.append("No components scored above 0.8 threshold [metric:composite]")
    return strengths


def _build_weaknesses(
    score: ConfidenceScore,
    anomaly_report: AnomalyReport,
    metric_ids: dict,
) -> list[str]:
    """Components scoring below 0.5 or with surfaced anomaly flags."""
    weaknesses = []

    for c in score.breakdown.components:
        if c.normalized_score < 0.5:
            mid = _component_to_metric_id(c.component_name, metric_ids)
            weaknesses.append(
                f"{c.component_name}: {c.normalized_score:.2f} — {c.interpretation} "
                f"[metric:{mid}]"
            )

    for flag in anomaly_report.anomalies:
        flag_metric = flag.evidence.get("metric_id", "n/a")
        weaknesses.append(
            f"Anomaly [{flag.severity.value}]: {flag.description} [metric:{flag_metric}]"
        )

    if not weaknesses:
        weaknesses.append("No significant weaknesses identified [metric:composite]")
    return weaknesses


def _build_session_breakdown(
    summaries: dict,
    chart_refs: dict,
) -> dict:
    """Regime × session performance matrix."""
    regime = summaries.get("regime", {})
    if not regime:
        return {"note": "Regime analysis stage was skipped [chart:n/a]"}

    chart_ref = chart_refs.get("regime_results", "n/a")
    return {
        "weakest_sharpe": regime.get("weakest_sharpe", 0.0),
        "strongest_sharpe": regime.get("strongest_sharpe", 0.0),
        "insufficient_buckets": regime.get("insufficient_buckets", 0),
        "chart_ref": f"[chart:{chart_ref}]",
    }


def _build_risk_assessment(
    anomaly_report: AnomalyReport,
    metric_ids: dict,
) -> str:
    """Surfaced anomaly flags with severity and recommendation."""
    if not anomaly_report.anomalies:
        return "Low risk — no anomalies surfaced by Layer B detection [metric:anomaly_layer]."

    lines = []
    error_count = sum(1 for a in anomaly_report.anomalies if a.severity == Severity.ERROR)
    warning_count = sum(1 for a in anomaly_report.anomalies if a.severity == Severity.WARNING)

    lines.append(
        f"Risk assessment: {error_count} ERROR-level, "
        f"{warning_count} WARNING-level anomalies detected "
        f"[metric:anomaly_layer]."
    )

    for flag in anomaly_report.anomalies:
        flag_metric = flag.evidence.get("metric_id", "n/a")
        lines.append(
            f"  [{flag.severity.value}] {flag.type.value}: {flag.description} "
            f"→ {flag.recommendation} [metric:{flag_metric}]"
        )

    return "\n".join(lines)


def _component_to_metric_id(component_name: str, metric_ids: dict) -> str:
    """Map component name to the relevant gauntlet manifest metric ID."""
    mapping = {
        "walk_forward_oos_consistency": "walk_forward",
        "cpcv_pbo_margin": "cpcv",
        "parameter_stability": "perturbation",
        "monte_carlo_stress_survival": "monte_carlo",
        "regime_uniformity": "regime",
        "in_sample_oos_coherence": "walk_forward",
    }
    stage = mapping.get(component_name, "")
    return metric_ids.get(stage, "n/a")
