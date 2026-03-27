"""Gate manager — operator-gated transitions and precondition checks (D3, FR39)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from logging_setup.setup import get_logger
from orchestrator.pipeline_state import (
    CompletedStage,
    GateDecision,
    PipelineStage,
    PipelineState,
    STAGE_GRAPH,
    STAGE_ORDER,
    TransitionType,
)

logger = get_logger("pipeline.gate_manager")


@dataclass
class PipelineStatus:
    """Snapshot of pipeline state for operator queries (FR40)."""
    stage: str
    progress_pct: float
    last_transition_at: str
    completed: list[CompletedStage]
    pending: list[str]
    gate_status: str | None  # "awaiting_decision" | "accepted" | "rejected" | "refined" | None
    decision_required: bool
    blocking_reason: str | None
    last_outcome: str | None  # outcome of most recent completed stage
    error: dict | None
    config_hash: str
    run_id: str


class GateManager:
    """Manages gated transitions and automatic precondition checks."""

    def advance(
        self, state: PipelineState, decision: GateDecision,
        state_path: Path | None = None,
    ) -> PipelineState:
        """Apply a gate decision to a gated transition.

        Supports:
        - ``accept``: proceed to next stage.
        - ``reject``: stop progression, record reason.
        - ``refine``: re-enter at a prior stage for iteration.

        If ``state_path`` is provided, the updated state is persisted
        automatically after the mutation (AC #11 durability).
        """
        current = PipelineStage(state.current_stage)
        transition = STAGE_GRAPH.get(current)

        if transition is None:
            raise ValueError(f"No transition defined from terminal stage {current.value}")

        if transition.transition_type != TransitionType.GATED:
            raise ValueError(
                f"Stage {current.value} has automatic transition — use run(), not advance()"
            )

        state.gate_decisions.append(decision)

        log_ctx = {
            "component": "pipeline.gate_manager",
            "stage": state.current_stage,
            "strategy_id": state.strategy_id,
            "ctx": {
                "decision": decision.decision,
                "reason": decision.reason,
                "from_stage": current.value,
            },
        }

        if decision.decision == "accept":
            state.current_stage = transition.to_stage.value
            state.last_transition_at = decision.decided_at
            # Update pending stages
            state.pending_stages = self.compute_pending(state.current_stage)
            logger.info(
                f"Gate accepted: {current.value} → {transition.to_stage.value}",
                extra=log_ctx,
            )

        elif decision.decision == "reject":
            logger.info(
                f"Gate rejected at {current.value}: {decision.reason}",
                extra=log_ctx,
            )
            # State stays at current stage — progression halted.

        elif decision.decision == "refine":
            # Re-enter at STRATEGY_READY so the operator can modify the
            # strategy before re-submitting for backtest (AC #6, Task 1.7).
            re_entry = PipelineStage.STRATEGY_READY
            state.current_stage = re_entry.value
            state.last_transition_at = decision.decided_at
            state.pending_stages = self.compute_pending(state.current_stage)
            logger.info(
                f"Gate refined: re-entering at {re_entry.value}",
                extra=log_ctx,
            )

        else:
            raise ValueError(f"Unknown gate decision: {decision.decision}")

        if state_path is not None:
            state.save(state_path)

        return state

    def check_preconditions(
        self, state: PipelineState, stage: PipelineStage,
        artifacts_dir: Path | None = None, executor: object | None = None,
    ) -> tuple[bool, str | None]:
        """Check automatic transition preconditions.

        Returns (met, blocking_reason). Never blocks on profitability (AC #7).

        Args:
            executor: Optional StageExecutor used for manifest hash validation
                      via ``validate_artifact(artifact_path, manifest_ref)``.
        """
        transition = STAGE_GRAPH.get(stage)
        if transition is None:
            return True, None  # Terminal stage — no transition needed.

        if transition.transition_type == TransitionType.GATED:
            # Gated transitions require operator decision — check if one exists.
            last_decision = self._last_gate_decision(state, stage)
            if last_decision is None:
                return False, f"Gated stage {stage.value} requires operator decision"
            if last_decision.decision == "reject":
                return False, f"Gate rejected: {last_decision.reason}"
            return True, None

        # Automatic transition preconditions:
        # 1. Previous stage completed successfully
        last_completed = self._last_completed_for_stage(state, stage)
        if last_completed is None:
            return False, f"Stage {stage.value} has not completed"

        if last_completed.outcome == "failed":
            return False, f"Stage {stage.value} completed with failure"

        # 2. Artifact exists and is valid per manifest hash (AC #2)
        if last_completed.artifact_path and artifacts_dir:
            artifact = Path(last_completed.artifact_path)
            if not artifact.is_absolute():
                artifact = artifacts_dir / artifact
            if not artifact.exists():
                return False, f"Artifact missing: {last_completed.artifact_path}"

            # Validate manifest hash when executor and manifest_ref are available
            if last_completed.manifest_ref and executor is not None:
                manifest = Path(last_completed.manifest_ref)
                if not manifest.is_absolute():
                    manifest = artifacts_dir / manifest
                try:
                    valid = executor.validate_artifact(artifact, manifest)
                except Exception:
                    valid = False
                if not valid:
                    return False, f"Artifact failed manifest hash validation: {last_completed.artifact_path}"

        # 3. No unresolved errors in state
        if state.error is not None:
            return False, f"Unresolved error in state: {state.error.get('msg', 'unknown')}"

        return True, None

    def get_status(self, state: PipelineState) -> PipelineStatus:
        """Build operator-facing pipeline status snapshot (FR40)."""
        current = PipelineStage(state.current_stage)
        transition = STAGE_GRAPH.get(current)

        # Gate status
        gate_status: str | None = None
        decision_required = False
        blocking_reason: str | None = None

        if transition and transition.transition_type == TransitionType.GATED:
            last_decision = self._last_gate_decision(state, current)
            if last_decision is None:
                gate_status = "awaiting_decision"
                decision_required = True
                blocking_reason = f"Operator decision required at {current.value}"
            else:
                _DECISION_PAST_TENSE = {"accept": "accepted", "reject": "rejected", "refine": "refined"}
                gate_status = _DECISION_PAST_TENSE.get(last_decision.decision, last_decision.decision)
                if last_decision.decision == "reject":
                    blocking_reason = last_decision.reason

        # Last outcome
        last_outcome: str | None = None
        if state.completed_stages:
            last_outcome = state.completed_stages[-1].outcome

        # Report error-state blocking reason (Codex M2)
        if state.error is not None and blocking_reason is None:
            blocking_reason = f"Unresolved error: {state.error.get('msg', 'unknown')}"

        # Progress percentage — use unique stage names to avoid overflow after
        # refine cycles that re-add completed_stages entries (BMAD M2 + Codex H4).
        total_stages = len(STAGE_ORDER)
        unique_completed = len({cs.stage for cs in state.completed_stages})
        completed_count = min(unique_completed, total_stages)
        progress_pct = (completed_count / total_stages) * 100.0 if total_stages > 0 else 0.0

        # Terminal stage = 100% (Codex M1)
        if transition is None:
            progress_pct = 100.0

        # Override with within-stage checkpoint progress if available
        elif state.checkpoint and state.checkpoint.stage == state.current_stage:
            stage_idx = min(completed_count, total_stages - 1)
            stage_base_pct = (stage_idx / total_stages) * 100.0
            stage_span_pct = (1.0 / total_stages) * 100.0
            progress_pct = stage_base_pct + stage_span_pct * (state.checkpoint.progress_pct / 100.0)

        return PipelineStatus(
            stage=state.current_stage,
            progress_pct=round(progress_pct, 1),
            last_transition_at=state.last_transition_at,
            completed=state.completed_stages,
            pending=state.pending_stages,
            gate_status=gate_status,
            decision_required=decision_required,
            blocking_reason=blocking_reason,
            last_outcome=last_outcome,
            error=state.error,
            config_hash=state.config_hash,
            run_id=state.run_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _last_gate_decision(state: PipelineState, stage: PipelineStage) -> GateDecision | None:
        for gd in reversed(state.gate_decisions):
            if gd.stage == stage.value:
                return gd
        return None

    @staticmethod
    def _last_completed_for_stage(state: PipelineState, stage: PipelineStage) -> CompletedStage | None:
        for cs in reversed(state.completed_stages):
            if cs.stage == stage.value:
                return cs
        return None

    @staticmethod
    def compute_pending(current_stage_value: str) -> list[str]:
        current = PipelineStage(current_stage_value)
        idx = STAGE_ORDER.index(current)
        return [s.value for s in STAGE_ORDER[idx + 1:]]
