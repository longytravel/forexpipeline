"""Unit tests for gate manager — gated transitions, preconditions, status."""
from pathlib import Path

import pytest

from orchestrator.gate_manager import GateManager, PipelineStatus
from orchestrator.pipeline_state import (
    CompletedStage,
    GateDecision,
    PipelineStage,
    PipelineState,
    STAGE_ORDER,
    TransitionType,
)


def _state_at_review_pending() -> PipelineState:
    return PipelineState(
        strategy_id="gate-test",
        run_id="run-1",
        current_stage=PipelineStage.REVIEW_PENDING.value,
        completed_stages=[
            CompletedStage(
                stage=PipelineStage.DATA_READY.value,
                completed_at="2026-01-01T00:00:00.000Z",
                outcome="success",
            ),
            CompletedStage(
                stage=PipelineStage.STRATEGY_READY.value,
                completed_at="2026-01-01T00:01:00.000Z",
                outcome="success",
            ),
            CompletedStage(
                stage=PipelineStage.BACKTEST_RUNNING.value,
                completed_at="2026-01-01T00:02:00.000Z",
                outcome="success",
            ),
            CompletedStage(
                stage=PipelineStage.BACKTEST_COMPLETE.value,
                completed_at="2026-01-01T00:03:00.000Z",
                outcome="success",
            ),
        ],
        pending_stages=[PipelineStage.REVIEWED.value],
        config_hash="sha256:abc",
    )


class TestGateBlocking:
    def test_gate_blocks_without_decision(self):
        gm = GateManager()
        state = _state_at_review_pending()
        met, reason = gm.check_preconditions(state, PipelineStage.REVIEW_PENDING)
        assert not met
        assert "requires operator decision" in reason

    def test_gate_accept_advances_stage(self):
        gm = GateManager()
        state = _state_at_review_pending()
        decision = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="accept",
            reason="Approved after review",
            decided_at="2026-01-01T01:00:00.000Z",
        )
        state = gm.advance(state, decision)
        assert state.current_stage == PipelineStage.REVIEWED.value

    def test_gate_reject_stops_and_records_reason(self):
        gm = GateManager()
        state = _state_at_review_pending()
        decision = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="reject",
            reason="Drawdown too high",
            decided_at="2026-01-01T01:00:00.000Z",
        )
        state = gm.advance(state, decision)

        # Stage does NOT advance
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value
        # Reason recorded
        assert state.gate_decisions[-1].reason == "Drawdown too high"

    def test_gate_refine_resets_to_prior_stage(self):
        gm = GateManager()
        state = _state_at_review_pending()
        decision = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="refine",
            reason="Adjust SL parameters and re-run",
            decided_at="2026-01-01T01:00:00.000Z",
        )
        state = gm.advance(state, decision)
        assert state.current_stage == PipelineStage.STRATEGY_READY.value

    def test_gate_decisions_accumulate_in_state(self):
        gm = GateManager()
        state = _state_at_review_pending()

        d1 = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="reject",
            reason="First pass: issues found",
            decided_at="2026-01-01T01:00:00.000Z",
        )
        state = gm.advance(state, d1)
        assert len(state.gate_decisions) == 1

        # Move back to review_pending for a second decision
        state.current_stage = PipelineStage.REVIEW_PENDING.value
        d2 = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="accept",
            reason="Second pass: approved",
            decided_at="2026-01-01T02:00:00.000Z",
        )
        state = gm.advance(state, d2)
        assert len(state.gate_decisions) == 2
        assert state.gate_decisions[0].decision == "reject"
        assert state.gate_decisions[1].decision == "accept"


class TestPreconditions:
    def test_preconditions_check_artifact_exists_and_valid(self, tmp_path):
        gm = GateManager()
        state = PipelineState(
            strategy_id="precon-test",
            run_id="run-1",
            current_stage=PipelineStage.STRATEGY_READY.value,
            completed_stages=[
                CompletedStage(
                    stage=PipelineStage.DATA_READY.value,
                    completed_at="2026-01-01T00:00:00.000Z",
                    artifact_path="data.arrow",
                    manifest_ref="manifest.json",
                    outcome="success",
                ),
            ],
        )
        # Artifact does not exist on disk
        met, reason = gm.check_preconditions(
            state, PipelineStage.DATA_READY, artifacts_dir=tmp_path
        )
        assert not met
        assert "Artifact missing" in reason

        # Create the artifact
        (tmp_path / "data.arrow").write_bytes(b"data")
        met, reason = gm.check_preconditions(
            state, PipelineStage.DATA_READY, artifacts_dir=tmp_path
        )
        assert met
        assert reason is None

    def test_preconditions_blocked_by_unresolved_error(self):
        gm = GateManager()
        state = PipelineState(
            strategy_id="error-precon",
            run_id="run-1",
            current_stage=PipelineStage.STRATEGY_READY.value,
            completed_stages=[
                CompletedStage(
                    stage=PipelineStage.DATA_READY.value,
                    completed_at="2026-01-01T00:00:00.000Z",
                    outcome="success",
                ),
            ],
            error={"msg": "Previous error unresolved", "code": "ERR001"},
        )
        met, reason = gm.check_preconditions(state, PipelineStage.DATA_READY)
        assert not met
        assert "Unresolved error" in reason

    def test_preconditions_gated_selection_complete_requires_decision(self):
        """SELECTION_COMPLETE is a gated stage — requires operator decision."""
        gm = GateManager()
        state = PipelineState(
            strategy_id="terminal",
            run_id="run-1",
            current_stage=PipelineStage.SELECTION_COMPLETE.value,
        )
        met, reason = gm.check_preconditions(state, PipelineStage.SELECTION_COMPLETE)
        assert not met
        assert "operator" in reason.lower() or "not completed" in reason.lower()


class TestGetStatus:
    def test_status_at_gated_stage(self):
        gm = GateManager()
        state = _state_at_review_pending()
        status = gm.get_status(state)

        assert status.stage == PipelineStage.REVIEW_PENDING.value
        assert status.gate_status == "awaiting_decision"
        assert status.decision_required is True
        assert status.blocking_reason is not None
        assert status.run_id == "run-1"
        assert status.config_hash == "sha256:abc"
        assert status.last_outcome == "success"
        assert len(status.completed) == 4
        assert PipelineStage.REVIEWED.value in status.pending

    def test_status_progress_pct(self):
        gm = GateManager()
        state = _state_at_review_pending()
        status = gm.get_status(state)
        # 4 of 14 stages completed → ~28.6%
        assert 25.0 < status.progress_pct < 35.0

    def test_advance_on_non_gated_stage_raises(self):
        gm = GateManager()
        state = PipelineState(
            strategy_id="nongated",
            run_id="run-1",
            current_stage=PipelineStage.DATA_READY.value,
        )
        decision = GateDecision(
            stage=PipelineStage.DATA_READY.value,
            decision="accept",
            reason="test",
            decided_at="2026-01-01T00:00:00.000Z",
        )
        with pytest.raises(ValueError, match="automatic transition"):
            gm.advance(state, decision)
