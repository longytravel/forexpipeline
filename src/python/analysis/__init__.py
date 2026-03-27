"""AI Analysis Layer — Narrative, Anomaly Detection & Evidence Packs (D11).

Public interfaces:
- generate_narrative(backtest_id, db_path) -> NarrativeResult
- detect_anomalies(backtest_id, db_path) -> AnomalyReport
- assemble_evidence_pack(backtest_id, db_path, artifacts_root) -> EvidencePack
- compute_metrics(trades, run_meta) -> dict
"""
from analysis.anomaly_detector import detect_anomalies
from analysis.evidence_pack import assemble_evidence_pack
from analysis.metrics_builder import compute_metrics
from analysis.models import (
    AnalysisError,
    AnomalyFlag,
    AnomalyReport,
    AnomalyType,
    EvidencePack,
    NarrativeResult,
    Severity,
)
from analysis.narrative import generate_narrative

__all__ = [
    "AnalysisError",
    "AnomalyFlag",
    "AnomalyReport",
    "AnomalyType",
    "EvidencePack",
    "NarrativeResult",
    "Severity",
    "assemble_evidence_pack",
    "compute_metrics",
    "detect_anomalies",
    "generate_narrative",
]
