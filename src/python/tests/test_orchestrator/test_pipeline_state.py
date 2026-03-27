"""Unit tests for pipeline state, stage enum, graph, and serialization."""
import json
from pathlib import Path

import pytest

from orchestrator.pipeline_state import (
    CompletedStage,
    GateDecision,
    PipelineStage,
    PipelineState,
    STAGE_GRAPH,
    STAGE_ORDER,
    StageTransition,
    TransitionType,
    WithinStageCheckpoint,
)


class TestPipelineStageEnum:
    def test_stage_enum_has_all_pipeline_stages(self):
        expected = {
            "data-ready", "strategy-ready", "backtest-running",
            "backtest-complete", "review-pending", "reviewed",
            "optimizing", "optimization-complete",
            "validating", "validation-complete",
            "scoring", "scoring-complete",
            "selecting", "selection-complete",
        }
        actual = {s.value for s in PipelineStage}
        assert actual == expected

    def test_stage_enum_values_are_kebab_case(self):
        for stage in PipelineStage:
            assert "-" in stage.value or stage.value.isalpha()
            assert stage.value == stage.value.lower()


class TestStageGraph:
    def test_stage_graph_is_sequential(self):
        """Each stage (except OPTIMIZATION_COMPLETE) maps to the next stage in order."""
        for i, stage in enumerate(STAGE_ORDER[:-1]):
            transition = STAGE_GRAPH[stage]
            assert transition.from_stage == stage
            assert transition.to_stage == STAGE_ORDER[i + 1]

    def test_review_pending_is_gated(self):
        transition = STAGE_GRAPH[PipelineStage.REVIEW_PENDING]
        assert transition.transition_type == TransitionType.GATED

    def test_all_other_transitions_are_automatic(self):
        gated_stages = {PipelineStage.REVIEW_PENDING, PipelineStage.SCORING_COMPLETE, PipelineStage.SELECTION_COMPLETE}
        for stage, transition in STAGE_GRAPH.items():
            if stage not in gated_stages:
                assert transition.transition_type == TransitionType.AUTOMATIC, \
                    f"{stage.value} should be automatic"

    def test_selection_complete_is_gated(self):
        assert PipelineStage.SELECTION_COMPLETE in STAGE_GRAPH
        transition = STAGE_GRAPH[PipelineStage.SELECTION_COMPLETE]
        assert transition.transition_type == TransitionType.GATED

    def test_every_non_terminal_stage_has_transition(self):
        for stage in STAGE_ORDER[:-1]:
            assert stage in STAGE_GRAPH

    def test_all_transitions_have_preconditions(self):
        for stage, transition in STAGE_GRAPH.items():
            assert len(transition.preconditions) > 0, \
                f"{stage.value} transition has no preconditions"


class TestStateSaveLoadRoundtrip:
    def test_state_save_load_roundtrip(self, tmp_path):
        state = PipelineState(
            strategy_id="test-strat",
            run_id="abc-123",
            current_stage=PipelineStage.BACKTEST_RUNNING.value,
            completed_stages=[
                CompletedStage(
                    stage=PipelineStage.DATA_READY.value,
                    completed_at="2026-01-01T00:00:00.000Z",
                    artifact_path="artifacts/test/data.arrow",
                    manifest_ref="artifacts/test/manifest.json",
                    duration_s=1.5,
                    outcome="success",
                ),
            ],
            pending_stages=[
                PipelineStage.BACKTEST_COMPLETE.value,
                PipelineStage.REVIEW_PENDING.value,
                PipelineStage.REVIEWED.value,
            ],
            gate_decisions=[],
            created_at="2026-01-01T00:00:00.000Z",
            last_transition_at="2026-01-01T00:01:00.000Z",
            config_hash="sha256:abc123",
        )

        path = tmp_path / "test-strat" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)

        loaded = PipelineState.load(path)

        assert loaded.strategy_id == state.strategy_id
        assert loaded.run_id == state.run_id
        assert loaded.current_stage == state.current_stage
        assert loaded.config_hash == state.config_hash
        assert loaded.created_at == state.created_at
        assert loaded.last_transition_at == state.last_transition_at
        assert len(loaded.completed_stages) == 1
        assert loaded.completed_stages[0].stage == PipelineStage.DATA_READY.value
        assert loaded.completed_stages[0].outcome == "success"
        assert loaded.completed_stages[0].artifact_path == "artifacts/test/data.arrow"
        assert loaded.pending_stages == state.pending_stages

    def test_state_save_uses_crash_safe_write(self, tmp_path):
        """Verify atomic write pattern — no .partial file left behind."""
        state = PipelineState(
            strategy_id="safe-write-test",
            run_id="run-1",
            current_stage=PipelineStage.DATA_READY.value,
        )
        path = tmp_path / "safe-write-test" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)

        assert path.exists()
        partial = path.with_name(path.name + ".partial")
        assert not partial.exists()

    def test_state_tracks_completed_stages_with_outcome_and_manifest(self, tmp_path):
        state = PipelineState(
            strategy_id="outcome-test",
            run_id="run-1",
            current_stage=PipelineStage.BACKTEST_COMPLETE.value,
            completed_stages=[
                CompletedStage(
                    stage=PipelineStage.BACKTEST_RUNNING.value,
                    completed_at="2026-01-01T00:05:00.000Z",
                    artifact_path="results.arrow",
                    manifest_ref="manifest.json",
                    duration_s=120.0,
                    outcome="success",
                ),
            ],
        )
        path = tmp_path / "outcome-test" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)
        loaded = PipelineState.load(path)

        cs = loaded.completed_stages[0]
        assert cs.outcome == "success"
        assert cs.manifest_ref == "manifest.json"
        assert cs.duration_s == 120.0

    def test_state_tracks_pending_stages(self, tmp_path):
        state = PipelineState(
            strategy_id="pending-test",
            run_id="run-1",
            current_stage=PipelineStage.DATA_READY.value,
            pending_stages=[s.value for s in STAGE_ORDER[1:]],
        )
        path = tmp_path / "pending-test" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)
        loaded = PipelineState.load(path)
        assert loaded.pending_stages == [s.value for s in STAGE_ORDER[1:]]

    def test_state_includes_run_id(self, tmp_path):
        state = PipelineState(
            strategy_id="runid-test",
            run_id="unique-run-id-abc",
            current_stage=PipelineStage.DATA_READY.value,
        )
        path = tmp_path / "runid-test" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)

        with open(path) as f:
            data = json.load(f)
        assert data["run_id"] == "unique-run-id-abc"


class TestCheckpointSerialization:
    def test_checkpoint_save_load_roundtrip(self, tmp_path):
        checkpoint = WithinStageCheckpoint(
            stage=PipelineStage.BACKTEST_RUNNING.value,
            progress_pct=45.5,
            last_completed_batch=450,
            total_batches=1000,
            partial_artifact_path="results.arrow.partial",
            checkpoint_at="2026-01-01T00:03:00.000Z",
        )
        state = PipelineState(
            strategy_id="cp-test",
            run_id="run-1",
            current_stage=PipelineStage.BACKTEST_RUNNING.value,
            checkpoint=checkpoint,
        )
        path = tmp_path / "cp-test" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)
        loaded = PipelineState.load(path)

        assert loaded.checkpoint is not None
        assert loaded.checkpoint.stage == PipelineStage.BACKTEST_RUNNING.value
        assert loaded.checkpoint.progress_pct == 45.5
        assert loaded.checkpoint.last_completed_batch == 450
        assert loaded.checkpoint.total_batches == 1000
        assert loaded.checkpoint.partial_artifact_path == "results.arrow.partial"
        assert loaded.checkpoint.checkpoint_at == "2026-01-01T00:03:00.000Z"


class TestGateDecisionSerialization:
    def test_gate_decision_serialization_roundtrip(self, tmp_path):
        decisions = [
            GateDecision(
                stage=PipelineStage.REVIEW_PENDING.value,
                decision="reject",
                reason="Need more analysis",
                decided_at="2026-01-01T01:00:00.000Z",
                evidence_pack_ref="evidence/pack-001.json",
            ),
            GateDecision(
                stage=PipelineStage.REVIEW_PENDING.value,
                decision="accept",
                reason="Looks good after revision",
                decided_at="2026-01-01T02:00:00.000Z",
                evidence_pack_ref=None,
            ),
        ]
        state = PipelineState(
            strategy_id="gate-test",
            run_id="run-1",
            current_stage=PipelineStage.REVIEWED.value,
            gate_decisions=decisions,
        )
        path = tmp_path / "gate-test" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        state.save(path)
        loaded = PipelineState.load(path)

        assert len(loaded.gate_decisions) == 2
        gd0 = loaded.gate_decisions[0]
        assert gd0.decision == "reject"
        assert gd0.reason == "Need more analysis"
        assert gd0.evidence_pack_ref == "evidence/pack-001.json"
        gd1 = loaded.gate_decisions[1]
        assert gd1.decision == "accept"
        assert gd1.evidence_pack_ref is None


class TestSchemaVersionMigration:
    def test_future_version_raises(self, tmp_path):
        path = tmp_path / "future" / "pipeline-state.json"
        path.parent.mkdir(parents=True)
        data = {
            "strategy_id": "test",
            "run_id": "run-1",
            "current_stage": "data-ready",
            "version": 999,
        }
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="newer than supported"):
            PipelineState.load(path)
