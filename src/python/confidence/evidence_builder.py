"""Two-pass evidence pack builder (Story 5.5, Task 7).

Pass 1: Triage summary card (≤10 headline fields, ≤3 risks, ≤200 words).
Pass 2: Full evidence pack with complete detail.

All artifacts written via crash_safe_write (D2).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from analysis.models import AnomalyReport, NarrativeResult
from artifacts.storage import crash_safe_write_json
from confidence.config import ConfidenceConfig
from confidence.models import (
    ConfidenceScore,
    DecisionTrace,
    TriageSummary,
    ValidationEvidencePack,
)


def build_triage_summary(
    confidence_score: ConfidenceScore,
    gauntlet_manifest: dict,
) -> TriageSummary:
    """Pass 1: triage card for quick operator scanning.

    Headline metrics: OOS Sharpe, PBO, DSR status, max drawdown, win rate, profit factor.
    Top 3 risks from component weaknesses.
    Optional delta_vs_baseline only when baseline exists.
    """
    summaries = gauntlet_manifest.get("per_stage_summaries", {})
    gate_data = gauntlet_manifest.get("gate_results", {})
    wf = summaries.get("walk_forward", {})
    mc = summaries.get("monte_carlo", {})
    backtest = summaries.get("backtest", {})

    headline_metrics = {
        "oos_sharpe": wf.get("median_oos_sharpe", 0.0),
        "pbo": gate_data.get("pbo_value", 1.0),
        "dsr_passed": gate_data.get("dsr_passed", False),
        "max_drawdown": backtest.get("max_drawdown", wf.get("max_drawdown", 0.0)),
        "win_rate": backtest.get("win_rate", wf.get("win_rate", 0.0)),
        "profit_factor": backtest.get("profit_factor", wf.get("profit_factor", 0.0)),
    }

    # Dominant edge from strongest component
    components = confidence_score.breakdown.components
    if components:
        best = max(components, key=lambda c: c.normalized_score)
        dominant_edge = f"{best.component_name} ({best.normalized_score:.2f})"
    else:
        dominant_edge = "No component data available"

    # Top 3 risks from weakest components
    top_risks = []
    if components:
        sorted_weak = sorted(components, key=lambda c: c.normalized_score)
        for c in sorted_weak[:3]:
            if c.normalized_score < 0.7:
                top_risks.append(f"{c.component_name}: {c.normalized_score:.2f}")
    if not top_risks:
        top_risks.append("No significant risks identified")

    return TriageSummary(
        candidate_id=confidence_score.candidate_id,
        rating=confidence_score.rating,
        composite_score=confidence_score.composite_score,
        headline_metrics=headline_metrics,
        dominant_edge=dominant_edge,
        top_risks=top_risks[:3],
        delta_vs_baseline=None,  # Only populated when baseline exists
    )


def build_decision_trace(
    confidence_score: ConfidenceScore,
    config: ConfidenceConfig,
    gauntlet_manifest: dict,
) -> DecisionTrace:
    """Build immutable audit trail of scoring configuration and gate outcomes."""
    gates = confidence_score.breakdown.gates

    # Snapshot all thresholds from config
    thresholds_snapshot = {
        "dsr_pass_required": float(config.hard_gates.dsr_pass_required),
        "pbo_max_threshold": config.hard_gates.pbo_max_threshold,
        "cost_stress_survival_multiplier": config.hard_gates.cost_stress_survival_multiplier,
        "green_minimum": config.thresholds.green_minimum,
        "yellow_minimum": config.thresholds.yellow_minimum,
    }

    # Compute confidence config hash
    config_str = json.dumps({
        "hard_gates": {
            "dsr_pass_required": config.hard_gates.dsr_pass_required,
            "pbo_max_threshold": config.hard_gates.pbo_max_threshold,
            "cost_stress_survival_multiplier": config.hard_gates.cost_stress_survival_multiplier,
        },
        "weights": config.weights.as_dict(),
        "thresholds": {
            "green_minimum": config.thresholds.green_minimum,
            "yellow_minimum": config.thresholds.yellow_minimum,
        },
    }, sort_keys=True)
    confidence_config_hash = "sha256:" + hashlib.sha256(config_str.encode()).hexdigest()[:16]

    return DecisionTrace(
        gates_used=gates,
        thresholds_snapshot=thresholds_snapshot,
        confidence_config_hash=confidence_config_hash,
        validation_config_hash=gauntlet_manifest.get("validation_config_hash", ""),
        research_brief_versions=gauntlet_manifest.get("research_brief_versions", {}),
    )


def build_evidence_pack(
    candidate_id: int,
    confidence_score: ConfidenceScore,
    triage_summary: TriageSummary,
    decision_trace: DecisionTrace,
    gauntlet_manifest: dict,
    anomaly_report: AnomalyReport,
    narrative: NarrativeResult,
    visualization_refs: dict[str, str],
) -> ValidationEvidencePack:
    """Assemble the complete evidence pack with all fields."""
    return ValidationEvidencePack(
        candidate_id=candidate_id,
        optimization_run_id=gauntlet_manifest.get("optimization_run_id", ""),
        strategy_id=gauntlet_manifest.get("strategy_id", "unknown"),
        confidence_score=confidence_score,
        triage_summary=triage_summary,
        decision_trace=decision_trace,
        per_stage_results=gauntlet_manifest.get("per_stage_summaries", {}),
        anomaly_report=anomaly_report,
        narrative=narrative,
        visualization_refs=visualization_refs,
        metadata={
            "optimization_run_id": gauntlet_manifest.get("optimization_run_id", ""),
            "total_optimization_trials": gauntlet_manifest.get("total_optimization_trials", 0),
            "candidate_rank": gauntlet_manifest.get("candidate_rank", 0),
            "confidence_config_hash": decision_trace.confidence_config_hash,
            "validation_config_hash": decision_trace.validation_config_hash,
            "scored_at": confidence_score.scored_at,
        },
    )


def persist_evidence_pack(
    evidence_pack: ValidationEvidencePack,
    output_dir: Path,
) -> Path:
    """Write evidence pack as JSON via crash_safe_write.

    Writes:
    - Full evidence pack: evidence-pack-candidate-{id}.json
    - Triage summary: evidence-triage-candidate-{id}.json
    """
    cid = evidence_pack.candidate_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Full evidence pack
    pack_path = output_dir / f"evidence-pack-candidate-{cid}.json"
    crash_safe_write_json(evidence_pack.to_json(), pack_path)

    # Triage summary separately for fast scanning
    triage_path = output_dir / f"evidence-triage-candidate-{cid}.json"
    crash_safe_write_json(evidence_pack.triage_summary.to_json(), triage_path)

    return pack_path
