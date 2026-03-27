"""Data models for advanced candidate selection (Story 5.6, Task 1).

All models are deterministic dataclasses with JSON serialization following
the pattern established in confidence/models.py and analysis/models.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClusterAssignment:
    """HDBSCAN cluster assignment for a single candidate."""

    candidate_id: int
    cluster_id: int  # -1 for noise
    is_noise: bool
    membership_prob: float

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "cluster_id": self.cluster_id,
            "is_noise": self.is_noise,
            "membership_prob": self.membership_prob,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ClusterAssignment:
        return cls(
            candidate_id=data["candidate_id"],
            cluster_id=data["cluster_id"],
            is_noise=data["is_noise"],
            membership_prob=data["membership_prob"],
        )


@dataclass
class EquityCurveQuality:
    """Five equity curve quality metrics per candidate (FR27)."""

    candidate_id: int
    k_ratio: float
    ulcer_index: float
    dsr: float
    gain_to_pain: float
    serenity_ratio: float

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "k_ratio": self.k_ratio,
            "ulcer_index": self.ulcer_index,
            "dsr": self.dsr,
            "gain_to_pain": self.gain_to_pain,
            "serenity_ratio": self.serenity_ratio,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EquityCurveQuality:
        return cls(
            candidate_id=data["candidate_id"],
            k_ratio=data["k_ratio"],
            ulcer_index=data["ulcer_index"],
            dsr=data["dsr"],
            gain_to_pain=data["gain_to_pain"],
            serenity_ratio=data["serenity_ratio"],
        )


@dataclass
class RankedCandidate:
    """Candidate after multi-objective ranking through the 4-stage funnel."""

    candidate_id: int
    topsis_score: float
    pareto_rank: int
    cluster_id: int
    stability_pass: bool
    funnel_stage: str  # "hard_gates" | "topsis" | "stability" | "pareto" | "selected"
    selection_reason: str

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "topsis_score": self.topsis_score,
            "pareto_rank": self.pareto_rank,
            "cluster_id": self.cluster_id,
            "stability_pass": self.stability_pass,
            "funnel_stage": self.funnel_stage,
            "selection_reason": self.selection_reason,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RankedCandidate:
        return cls(
            candidate_id=data["candidate_id"],
            topsis_score=data["topsis_score"],
            pareto_rank=data["pareto_rank"],
            cluster_id=data["cluster_id"],
            stability_pass=data["stability_pass"],
            funnel_stage=data["funnel_stage"],
            selection_reason=data["selection_reason"],
        )


@dataclass
class DiversityCell:
    """MAP-Elites archive cell — stores best candidate per behavior bin."""

    dimensions: dict[str, str]  # {dimension_name: bin_label}
    best_candidate_id: int
    best_score: float

    def to_json(self) -> dict[str, Any]:
        return {
            "dimensions": self.dimensions,
            "best_candidate_id": self.best_candidate_id,
            "best_score": self.best_score,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DiversityCell:
        return cls(
            dimensions=data["dimensions"],
            best_candidate_id=data["best_candidate_id"],
            best_score=data["best_score"],
        )


@dataclass
class ClusterSummary:
    """Summary statistics for a single cluster."""

    cluster_id: int
    size: int
    centroid_params: dict[str, float]
    representative_id: int
    robustness_score: float
    metrics_summary: dict[str, float]

    def to_json(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "size": self.size,
            "centroid_params": self.centroid_params,
            "representative_id": self.representative_id,
            "robustness_score": self.robustness_score,
            "metrics_summary": self.metrics_summary,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ClusterSummary:
        return cls(
            cluster_id=data["cluster_id"],
            size=data["size"],
            centroid_params=data["centroid_params"],
            representative_id=data["representative_id"],
            robustness_score=data["robustness_score"],
            metrics_summary=data["metrics_summary"],
        )


@dataclass
class FunnelStats:
    """Counts at each stage of the 4-stage filtering funnel."""

    total_input: int
    after_hard_gates: int
    after_topsis: int
    after_stability: int
    after_pareto: int
    final_selected: int

    def to_json(self) -> dict[str, Any]:
        return {
            "total_input": self.total_input,
            "after_hard_gates": self.after_hard_gates,
            "after_topsis": self.after_topsis,
            "after_stability": self.after_stability,
            "after_pareto": self.after_pareto,
            "final_selected": self.final_selected,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FunnelStats:
        return cls(
            total_input=data["total_input"],
            after_hard_gates=data["after_hard_gates"],
            after_topsis=data["after_topsis"],
            after_stability=data["after_stability"],
            after_pareto=data["after_pareto"],
            final_selected=data["final_selected"],
        )


@dataclass
class UpstreamRefs:
    """Provenance links to upstream artifacts for reproducibility."""

    candidates_path: str
    candidates_hash: str
    scoring_manifest_path: str | None = None
    scoring_manifest_hash: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "candidates_path": self.candidates_path,
            "candidates_hash": self.candidates_hash,
            "scoring_manifest_path": self.scoring_manifest_path,
            "scoring_manifest_hash": self.scoring_manifest_hash,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UpstreamRefs:
        return cls(
            candidates_path=data["candidates_path"],
            candidates_hash=data["candidates_hash"],
            scoring_manifest_path=data.get("scoring_manifest_path"),
            scoring_manifest_hash=data.get("scoring_manifest_hash"),
        )


@dataclass
class SelectionManifest:
    """Complete output manifest for the selection pipeline."""

    strategy_id: str
    optimization_run_id: str
    selected_candidates: list[RankedCandidate]
    clusters: list[ClusterSummary]
    diversity_archive: list[DiversityCell]
    funnel_stats: FunnelStats
    config_hash: str
    selected_at: str  # ISO 8601
    upstream_refs: UpstreamRefs
    critic_weights: dict[str, float]
    gate_failure_summary: dict[str, int]
    random_seed_used: int

    def to_json(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "optimization_run_id": self.optimization_run_id,
            "selected_candidates": [c.to_json() for c in self.selected_candidates],
            "clusters": [c.to_json() for c in self.clusters],
            "diversity_archive": [d.to_json() for d in self.diversity_archive],
            "funnel_stats": self.funnel_stats.to_json(),
            "config_hash": self.config_hash,
            "selected_at": self.selected_at,
            "upstream_refs": self.upstream_refs.to_json(),
            "critic_weights": self.critic_weights,
            "gate_failure_summary": self.gate_failure_summary,
            "random_seed_used": self.random_seed_used,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SelectionManifest:
        return cls(
            strategy_id=data["strategy_id"],
            optimization_run_id=data["optimization_run_id"],
            selected_candidates=[
                RankedCandidate.from_json(c) for c in data["selected_candidates"]
            ],
            clusters=[ClusterSummary.from_json(c) for c in data["clusters"]],
            diversity_archive=[DiversityCell.from_json(d) for d in data["diversity_archive"]],
            funnel_stats=FunnelStats.from_json(data["funnel_stats"]),
            config_hash=data["config_hash"],
            selected_at=data["selected_at"],
            upstream_refs=UpstreamRefs.from_json(data["upstream_refs"]),
            critic_weights=data["critic_weights"],
            gate_failure_summary=data["gate_failure_summary"],
            random_seed_used=data["random_seed_used"],
        )
