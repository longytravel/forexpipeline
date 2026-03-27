"""Data models for Confidence Scoring & Evidence Packs (Story 5.5).

All models are deterministic dataclasses with JSON serialization following
the pattern in analysis/models.py. No stochastic or LLM-dependent components.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from analysis.models import AnomalyReport, NarrativeResult


class CandidateRating(str, Enum):
    """Confidence rating for a candidate."""

    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


@dataclass
class GateResult:
    """Individual hard gate outcome."""

    gate_name: str
    threshold: float
    actual_value: float
    passed: bool
    description: str

    def to_json(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "threshold": self.threshold,
            "actual_value": self.actual_value,
            "passed": self.passed,
            "description": self.description,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> GateResult:
        return cls(
            gate_name=data["gate_name"],
            threshold=data["threshold"],
            actual_value=data["actual_value"],
            passed=data["passed"],
            description=data["description"],
        )


@dataclass
class ComponentScore:
    """Per-component score in the composite."""

    component_name: str
    raw_value: float
    normalized_score: float
    weight: float
    weighted_contribution: float
    interpretation: str
    gate_result: GateResult | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "component_name": self.component_name,
            "raw_value": self.raw_value,
            "normalized_score": self.normalized_score,
            "weight": self.weight,
            "weighted_contribution": self.weighted_contribution,
            "interpretation": self.interpretation,
            "gate_result": self.gate_result.to_json() if self.gate_result else None,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ComponentScore:
        gr = data.get("gate_result")
        return cls(
            component_name=data["component_name"],
            raw_value=data["raw_value"],
            normalized_score=data["normalized_score"],
            weight=data["weight"],
            weighted_contribution=data["weighted_contribution"],
            interpretation=data["interpretation"],
            gate_result=GateResult.from_json(gr) if gr else None,
        )


@dataclass
class ConfidenceBreakdown:
    """Full scoring breakdown with components and gates."""

    components: list[ComponentScore]
    gates: list[GateResult]
    hard_gate_passed: bool
    composite_score: float

    def to_json(self) -> dict[str, Any]:
        return {
            "components": [c.to_json() for c in self.components],
            "gates": [g.to_json() for g in self.gates],
            "hard_gate_passed": self.hard_gate_passed,
            "composite_score": self.composite_score,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ConfidenceBreakdown:
        return cls(
            components=[ComponentScore.from_json(c) for c in data["components"]],
            gates=[GateResult.from_json(g) for g in data["gates"]],
            hard_gate_passed=data["hard_gate_passed"],
            composite_score=data["composite_score"],
        )


@dataclass
class ConfidenceScore:
    """Top-level confidence scoring result per candidate."""

    candidate_id: int
    optimization_run_id: str
    rating: CandidateRating
    composite_score: float
    breakdown: ConfidenceBreakdown
    scored_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "optimization_run_id": self.optimization_run_id,
            "rating": self.rating.value,
            "composite_score": self.composite_score,
            "breakdown": self.breakdown.to_json(),
            "scored_at": self.scored_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ConfidenceScore:
        return cls(
            candidate_id=data["candidate_id"],
            optimization_run_id=data["optimization_run_id"],
            rating=CandidateRating(data["rating"]),
            composite_score=data["composite_score"],
            breakdown=ConfidenceBreakdown.from_json(data["breakdown"]),
            scored_at=data["scored_at"],
        )


@dataclass
class TriageSummary:
    """Pass 1 triage card — quick operator scanning (≤200 words)."""

    candidate_id: int
    rating: CandidateRating
    composite_score: float
    headline_metrics: dict[str, Any]
    dominant_edge: str
    top_risks: list[str]
    delta_vs_baseline: dict[str, float] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "rating": self.rating.value,
            "composite_score": self.composite_score,
            "headline_metrics": self.headline_metrics,
            "dominant_edge": self.dominant_edge,
            "top_risks": self.top_risks,
            "delta_vs_baseline": self.delta_vs_baseline,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TriageSummary:
        return cls(
            candidate_id=data["candidate_id"],
            rating=CandidateRating(data["rating"]),
            composite_score=data["composite_score"],
            headline_metrics=data["headline_metrics"],
            dominant_edge=data["dominant_edge"],
            top_risks=data["top_risks"],
            delta_vs_baseline=data.get("delta_vs_baseline"),
        )


@dataclass
class DecisionTrace:
    """Immutable audit trail of scoring configuration and gate outcomes."""

    gates_used: list[GateResult]
    thresholds_snapshot: dict[str, float]
    confidence_config_hash: str
    validation_config_hash: str
    research_brief_versions: dict[str, str]

    def to_json(self) -> dict[str, Any]:
        return {
            "gates_used": [g.to_json() for g in self.gates_used],
            "thresholds_snapshot": self.thresholds_snapshot,
            "confidence_config_hash": self.confidence_config_hash,
            "validation_config_hash": self.validation_config_hash,
            "research_brief_versions": self.research_brief_versions,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DecisionTrace:
        return cls(
            gates_used=[GateResult.from_json(g) for g in data["gates_used"]],
            thresholds_snapshot=data["thresholds_snapshot"],
            confidence_config_hash=data["confidence_config_hash"],
            validation_config_hash=data["validation_config_hash"],
            research_brief_versions=data["research_brief_versions"],
        )


@dataclass
class ValidationEvidencePack:
    """Complete evidence pack for operator review — validation stage."""

    candidate_id: int
    optimization_run_id: str
    strategy_id: str
    confidence_score: ConfidenceScore
    triage_summary: TriageSummary
    decision_trace: DecisionTrace
    per_stage_results: dict[str, Any]
    anomaly_report: AnomalyReport
    narrative: NarrativeResult
    visualization_refs: dict[str, str]
    metadata: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "optimization_run_id": self.optimization_run_id,
            "strategy_id": self.strategy_id,
            "confidence_score": self.confidence_score.to_json(),
            "triage_summary": self.triage_summary.to_json(),
            "decision_trace": self.decision_trace.to_json(),
            "per_stage_results": self.per_stage_results,
            "anomaly_report": self.anomaly_report.to_json(),
            "narrative": self.narrative.to_json(),
            "visualization_refs": self.visualization_refs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ValidationEvidencePack:
        return cls(
            candidate_id=data["candidate_id"],
            optimization_run_id=data["optimization_run_id"],
            strategy_id=data["strategy_id"],
            confidence_score=ConfidenceScore.from_json(data["confidence_score"]),
            triage_summary=TriageSummary.from_json(data["triage_summary"]),
            decision_trace=DecisionTrace.from_json(data["decision_trace"]),
            per_stage_results=data["per_stage_results"],
            anomaly_report=AnomalyReport.from_json(data["anomaly_report"]),
            narrative=NarrativeResult.from_json(data["narrative"]),
            visualization_refs=data["visualization_refs"],
            metadata=data["metadata"],
        )


_VALID_REVIEW_DECISIONS = frozenset({"accept", "reject", "refine"})


@dataclass
class OperatorReview:
    """Separate append-only artifact for human review decisions.

    NOT part of immutable evidence pack — stored in a separate file.
    """

    candidate_id: int
    decision: str  # "accept" | "reject" | "refine"
    rationale: str
    operator_notes: str
    decision_timestamp: str
    evidence_pack_path: str

    def __post_init__(self) -> None:
        if self.decision not in _VALID_REVIEW_DECISIONS:
            raise ValueError(
                f"Invalid review decision '{self.decision}'. "
                f"Must be one of: {sorted(_VALID_REVIEW_DECISIONS)}"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "decision": self.decision,
            "rationale": self.rationale,
            "operator_notes": self.operator_notes,
            "decision_timestamp": self.decision_timestamp,
            "evidence_pack_path": self.evidence_pack_path,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> OperatorReview:
        return cls(
            candidate_id=data["candidate_id"],
            decision=data["decision"],
            rationale=data["rationale"],
            operator_notes=data["operator_notes"],
            decision_timestamp=data["decision_timestamp"],
            evidence_pack_path=data["evidence_pack_path"],
        )
