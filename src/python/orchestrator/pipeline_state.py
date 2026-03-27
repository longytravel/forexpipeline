"""Pipeline state machine — stage enum, state schema, gate decisions (D3).

Each strategy gets an independent sequential state machine backed by a
``pipeline-state.json`` file.  Every state mutation is persisted before
proceeding to the next operation (NFR15 crash-safe writes).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from artifacts.storage import crash_safe_write
from logging_setup.setup import get_logger

logger = get_logger("pipeline.state")

STATE_VERSION = 1


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStage(str, Enum):
    """Ordered pipeline stages per FR40 / D3."""
    DATA_READY = "data-ready"
    STRATEGY_READY = "strategy-ready"
    BACKTEST_RUNNING = "backtest-running"
    BACKTEST_COMPLETE = "backtest-complete"
    REVIEW_PENDING = "review-pending"
    REVIEWED = "reviewed"
    OPTIMIZING = "optimizing"
    OPTIMIZATION_COMPLETE = "optimization-complete"
    VALIDATING = "validating"
    VALIDATION_COMPLETE = "validation-complete"
    SCORING = "scoring"
    SCORING_COMPLETE = "scoring-complete"
    SELECTING = "selecting"
    SELECTION_COMPLETE = "selection-complete"


class TransitionType(str, Enum):
    AUTOMATIC = "automatic"
    GATED = "gated"


# ---------------------------------------------------------------------------
# Transition graph
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageTransition:
    from_stage: PipelineStage
    to_stage: PipelineStage
    transition_type: TransitionType
    preconditions: list[str]


STAGE_GRAPH: dict[PipelineStage, StageTransition] = {
    PipelineStage.DATA_READY: StageTransition(
        from_stage=PipelineStage.DATA_READY,
        to_stage=PipelineStage.STRATEGY_READY,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["data artifacts exist and valid"],
    ),
    PipelineStage.STRATEGY_READY: StageTransition(
        from_stage=PipelineStage.STRATEGY_READY,
        to_stage=PipelineStage.BACKTEST_RUNNING,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["strategy specification validated"],
    ),
    PipelineStage.BACKTEST_RUNNING: StageTransition(
        from_stage=PipelineStage.BACKTEST_RUNNING,
        to_stage=PipelineStage.BACKTEST_COMPLETE,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["backtest execution completed"],
    ),
    PipelineStage.BACKTEST_COMPLETE: StageTransition(
        from_stage=PipelineStage.BACKTEST_COMPLETE,
        to_stage=PipelineStage.REVIEW_PENDING,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["backtest results stored and indexed"],
    ),
    PipelineStage.REVIEW_PENDING: StageTransition(
        from_stage=PipelineStage.REVIEW_PENDING,
        to_stage=PipelineStage.REVIEWED,
        transition_type=TransitionType.GATED,
        preconditions=["operator gate decision provided"],
    ),
    PipelineStage.REVIEWED: StageTransition(
        from_stage=PipelineStage.REVIEWED,
        to_stage=PipelineStage.OPTIMIZING,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["review approved", "strategy spec exists", "market data exists"],
    ),
    PipelineStage.OPTIMIZING: StageTransition(
        from_stage=PipelineStage.OPTIMIZING,
        to_stage=PipelineStage.OPTIMIZATION_COMPLETE,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["optimization finished or budget exhausted"],
    ),
    PipelineStage.OPTIMIZATION_COMPLETE: StageTransition(
        from_stage=PipelineStage.OPTIMIZATION_COMPLETE,
        to_stage=PipelineStage.VALIDATING,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["optimization artifacts exist", "promoted candidates available"],
    ),
    PipelineStage.VALIDATING: StageTransition(
        from_stage=PipelineStage.VALIDATING,
        to_stage=PipelineStage.VALIDATION_COMPLETE,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["validation gauntlet completed"],
    ),
    PipelineStage.VALIDATION_COMPLETE: StageTransition(
        from_stage=PipelineStage.VALIDATION_COMPLETE,
        to_stage=PipelineStage.SCORING,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["validation artifacts exist"],
    ),
    PipelineStage.SCORING: StageTransition(
        from_stage=PipelineStage.SCORING,
        to_stage=PipelineStage.SCORING_COMPLETE,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["confidence scoring completed"],
    ),
    # SCORING_COMPLETE → SELECTING (gated, operator reviews scores before selection)
    PipelineStage.SCORING_COMPLETE: StageTransition(
        from_stage=PipelineStage.SCORING_COMPLETE,
        to_stage=PipelineStage.SELECTING,
        transition_type=TransitionType.GATED,
        preconditions=["scoring artifacts exist", "operator review decision provided for all candidates"],
    ),
    PipelineStage.SELECTING: StageTransition(
        from_stage=PipelineStage.SELECTING,
        to_stage=PipelineStage.SELECTION_COMPLETE,
        transition_type=TransitionType.AUTOMATIC,
        preconditions=["selection pipeline completed"],
    ),
    # SELECTION_COMPLETE is gated — operator reviews selected candidates
    PipelineStage.SELECTION_COMPLETE: StageTransition(
        from_stage=PipelineStage.SELECTION_COMPLETE,
        to_stage=PipelineStage.SELECTION_COMPLETE,  # self-loop until operator decision
        transition_type=TransitionType.GATED,
        preconditions=["operator review of selected candidates"],
    ),
}

# Ordered list for computing pending stages.
STAGE_ORDER: list[PipelineStage] = list(PipelineStage)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_VALID_DECISIONS = frozenset({"accept", "reject", "refine"})
_VALID_STAGES = frozenset(s.value for s in PipelineStage)


@dataclass
class GateDecision:
    stage: str  # PipelineStage value
    decision: str  # "accept" | "reject" | "refine"
    reason: str
    decided_at: str  # ISO 8601
    evidence_pack_ref: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in _VALID_STAGES:
            raise ValueError(
                f"Invalid gate stage '{self.stage}'. "
                f"Must be one of: {', '.join(sorted(_VALID_STAGES))}"
            )
        if self.decision not in _VALID_DECISIONS:
            raise ValueError(
                f"Invalid gate decision '{self.decision}'. "
                f"Must be one of: {', '.join(sorted(_VALID_DECISIONS))}"
            )

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "decision": self.decision,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "evidence_pack_ref": self.evidence_pack_ref,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GateDecision:
        return cls(
            stage=data["stage"],
            decision=data["decision"],
            reason=data["reason"],
            decided_at=data["decided_at"],
            evidence_pack_ref=data.get("evidence_pack_ref"),
        )


@dataclass
class CompletedStage:
    stage: str  # PipelineStage value
    completed_at: str  # ISO 8601
    artifact_path: str | None = None
    manifest_ref: str | None = None
    duration_s: float = 0.0
    outcome: str = "success"  # "success" | "skipped" | "failed"

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "completed_at": self.completed_at,
            "artifact_path": self.artifact_path,
            "manifest_ref": self.manifest_ref,
            "duration_s": self.duration_s,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CompletedStage:
        return cls(
            stage=data["stage"],
            completed_at=data["completed_at"],
            artifact_path=data.get("artifact_path"),
            manifest_ref=data.get("manifest_ref"),
            duration_s=data.get("duration_s", 0.0),
            outcome=data.get("outcome", "success"),
        )


@dataclass
class WithinStageCheckpoint:
    """Consumer-side interface for within-stage checkpoints.

    The canonical schema lives in ``contracts/pipeline_checkpoint.toml``.
    The Rust batch binary writes these (Story 3-4); Python reads on resume.
    """
    stage: str  # PipelineStage value
    progress_pct: float
    last_completed_batch: int
    total_batches: int
    partial_artifact_path: str | None = None
    checkpoint_at: str = ""  # ISO 8601

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "progress_pct": self.progress_pct,
            "last_completed_batch": self.last_completed_batch,
            "total_batches": self.total_batches,
            "partial_artifact_path": self.partial_artifact_path,
            "checkpoint_at": self.checkpoint_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WithinStageCheckpoint:
        return cls(
            stage=data["stage"],
            progress_pct=data["progress_pct"],
            last_completed_batch=data["last_completed_batch"],
            total_batches=data["total_batches"],
            partial_artifact_path=data.get("partial_artifact_path"),
            checkpoint_at=data.get("checkpoint_at", ""),
        )


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

@dataclass
class PipelineState:
    """Persistent pipeline state for a single strategy.

    State file location: ``artifacts/{strategy_id}/pipeline-state.json``
    """
    strategy_id: str
    run_id: str  # UUID, unique per execution attempt (FR60 lineage)
    current_stage: str  # PipelineStage value
    completed_stages: list[CompletedStage] = field(default_factory=list)
    pending_stages: list[str] = field(default_factory=list)  # PipelineStage values
    gate_decisions: list[GateDecision] = field(default_factory=list)
    created_at: str = ""  # ISO 8601
    last_transition_at: str = ""  # ISO 8601
    checkpoint: WithinStageCheckpoint | None = None
    error: dict | None = None  # PipelineError.to_dict()
    config_hash: str = ""  # hash of pipeline config for reproducibility (FR59)
    version: int = STATE_VERSION

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Persist state using crash-safe write (NFR15)."""
        data = self._to_dict()
        content = json.dumps(data, indent=2, default=str)
        crash_safe_write(path, content)
        logger.info(
            "Pipeline state saved",
            extra={
                "component": "pipeline.state",
                "stage": self.current_stage,
                "strategy_id": self.strategy_id,
                "ctx": {"path": str(path), "run_id": self.run_id},
            },
        )

    @classmethod
    def load(cls, path: Path) -> PipelineState:
        """Load state from JSON with schema version migration support."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = cls._migrate(data)
        state = cls._from_dict(data)
        logger.info(
            "Pipeline state loaded",
            extra={
                "component": "pipeline.state",
                "stage": state.current_stage,
                "strategy_id": state.strategy_id,
                "ctx": {"path": str(path), "run_id": state.run_id, "version": state.version},
            },
        )
        return state

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "run_id": self.run_id,
            "current_stage": self.current_stage,
            "completed_stages": [cs.to_dict() for cs in self.completed_stages],
            "pending_stages": self.pending_stages,
            "gate_decisions": [gd.to_dict() for gd in self.gate_decisions],
            "created_at": self.created_at,
            "last_transition_at": self.last_transition_at,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "error": self.error,
            "config_hash": self.config_hash,
            "version": self.version,
        }

    @classmethod
    def _from_dict(cls, data: dict) -> PipelineState:
        completed = [CompletedStage.from_dict(cs) for cs in data.get("completed_stages", [])]
        gate_decisions = [GateDecision.from_dict(gd) for gd in data.get("gate_decisions", [])]
        cp_data = data.get("checkpoint")
        checkpoint = WithinStageCheckpoint.from_dict(cp_data) if cp_data else None
        return cls(
            strategy_id=data["strategy_id"],
            run_id=data["run_id"],
            current_stage=data["current_stage"],
            completed_stages=completed,
            pending_stages=data.get("pending_stages", []),
            gate_decisions=gate_decisions,
            created_at=data.get("created_at", ""),
            last_transition_at=data.get("last_transition_at", ""),
            checkpoint=checkpoint,
            error=data.get("error"),
            config_hash=data.get("config_hash", ""),
            version=data.get("version", STATE_VERSION),
        )

    @staticmethod
    def _migrate(data: dict) -> dict:
        """Apply schema version migrations."""
        version = data.get("version", 1)
        # Currently at version 1 — no migrations needed.
        # Future migrations would be chained here:
        #   if version < 2: data = _migrate_v1_to_v2(data)
        if version > STATE_VERSION:
            raise ValueError(
                f"State file version {version} is newer than supported version {STATE_VERSION}"
            )
        return data
