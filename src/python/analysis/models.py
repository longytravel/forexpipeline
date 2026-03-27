"""Data models for the AI Analysis Layer (Architecture D11).

All models are deterministic dataclasses with JSON serialization.
No stochastic or LLM-dependent components.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AnomalyType(Enum):
    """Anomaly types detected by the analysis layer."""

    LOW_TRADE_COUNT = "LOW_TRADE_COUNT"
    ZERO_TRADES = "ZERO_TRADES"
    PERFECT_EQUITY = "PERFECT_EQUITY"
    SENSITIVITY_CLIFF = "SENSITIVITY_CLIFF"
    EXTREME_PROFIT_FACTOR = "EXTREME_PROFIT_FACTOR"
    TRADE_CLUSTERING = "TRADE_CLUSTERING"
    WIN_RATE_EXTREME = "WIN_RATE_EXTREME"
    # Forward-compatible: Epic 5 implementation
    DSR_BELOW_THRESHOLD = "DSR_BELOW_THRESHOLD"
    PBO_HIGH_PROBABILITY = "PBO_HIGH_PROBABILITY"
    # Story 5.5 — confidence scoring anomaly types
    IS_OOS_DIVERGENCE = "IS_OOS_DIVERGENCE"
    REGIME_CONCENTRATION = "REGIME_CONCENTRATION"
    PERTURBATION_CLIFF_CLUSTER = "PERTURBATION_CLIFF_CLUSTER"
    WALK_FORWARD_DEGRADATION = "WALK_FORWARD_DEGRADATION"
    MONTE_CARLO_TAIL_RISK = "MONTE_CARLO_TAIL_RISK"


class Severity(Enum):
    """Anomaly severity levels."""

    WARNING = "WARNING"
    ERROR = "ERROR"


class AnalysisError(Exception):
    """Raised when analysis processing fails with context."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


@dataclass
class AnomalyFlag:
    """A single anomaly detection finding."""

    type: AnomalyType
    severity: Severity
    description: str
    evidence: dict[str, Any]
    recommendation: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AnomalyFlag:
        return cls(
            type=AnomalyType(data["type"]),
            severity=Severity(data["severity"]),
            description=data["description"],
            evidence=data["evidence"],
            recommendation=data["recommendation"],
        )


@dataclass
class AnomalyReport:
    """Collection of anomaly flags for a backtest run."""

    backtest_id: str
    anomalies: list[AnomalyFlag]
    run_timestamp: str

    def to_json(self) -> dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "anomalies": [a.to_json() for a in self.anomalies],
            "run_timestamp": self.run_timestamp,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AnomalyReport:
        return cls(
            backtest_id=data["backtest_id"],
            anomalies=[AnomalyFlag.from_json(a) for a in data["anomalies"]],
            run_timestamp=data["run_timestamp"],
        )


@dataclass
class NarrativeResult:
    """Structured narrative output — template-driven, not LLM-generated."""

    overview: str
    metrics: dict[str, Any]
    strengths: list[str]
    weaknesses: list[str]
    session_breakdown: dict[str, dict[str, Any]]
    risk_assessment: str

    def to_json(self) -> dict[str, Any]:
        return {
            "overview": self.overview,
            "metrics": self.metrics,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "session_breakdown": self.session_breakdown,
            "risk_assessment": self.risk_assessment,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> NarrativeResult:
        return cls(
            overview=data["overview"],
            metrics=data["metrics"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            session_breakdown=data["session_breakdown"],
            risk_assessment=data["risk_assessment"],
        )


@dataclass
class EvidencePack:
    """Complete evidence pack for operator review (D11 two-pass design)."""

    backtest_id: str
    strategy_id: str
    version: str
    narrative: NarrativeResult
    anomalies: AnomalyReport
    metrics: dict[str, Any]
    equity_curve_summary: list[dict[str, Any]]
    equity_curve_full_path: str
    trade_distribution: dict[str, Any]
    trade_log_path: str
    metadata: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "strategy_id": self.strategy_id,
            "version": self.version,
            "pipeline_stage": "backtest",
            "generated_at": self.metadata.get("generated_at", ""),
            "narrative": self.narrative.to_json(),
            "anomalies": self.anomalies.to_json(),
            "metrics": self.metrics,
            "equity_curve_summary": self.equity_curve_summary,
            "equity_curve_full_path": self.equity_curve_full_path,
            "trade_distribution": self.trade_distribution,
            "trade_log_path": self.trade_log_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EvidencePack:
        return cls(
            backtest_id=data["backtest_id"],
            strategy_id=data["strategy_id"],
            version=data["version"],
            narrative=NarrativeResult.from_json(data["narrative"]),
            anomalies=AnomalyReport.from_json(data["anomalies"]),
            metrics=data["metrics"],
            equity_curve_summary=data["equity_curve_summary"],
            equity_curve_full_path=data["equity_curve_full_path"],
            trade_distribution=data["trade_distribution"],
            trade_log_path=data["trade_log_path"],
            metadata=data["metadata"],
        )

    def to_json_string(self) -> str:
        return json.dumps(self.to_json(), indent=2, default=str)
