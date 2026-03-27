"""Integration tests for full pipeline orchestration flows."""
import json
from pathlib import Path

import pytest

from orchestrator.gate_manager import GateManager
from orchestrator.pipeline_state import (
    CompletedStage,
    GateDecision,
    PipelineStage,
    PipelineState,
    STAGE_ORDER,
)
from orchestrator.stage_runner import (
    NoOpExecutor,
    PipelineConfig,
    StageResult,
    StageRunner,
)


def _make_config(**overrides) -> PipelineConfig:
    defaults = {
        "artifacts_dir": "artifacts",
        "checkpoint_enabled": True,
        "retry_max_attempts": 3,
        "retry_backoff_base_s": 0.01,
        "gated_stages": ["review-pending"],
        "checkpoint_granularity": 1000,
    }
    defaults.update(overrides)
    return PipelineConfig(**defaults)


def _full_config() -> dict:
    return {
        "pipeline": {
            "artifacts_dir": "artifacts",
            "checkpoint_enabled": True,
            "retry_max_attempts": 3,
            "retry_backoff_base_s": 0.01,
            "gated_stages": ["review-pending"],
            "checkpoint_granularity": 1000,
        }
    }


def _noop_executors():
    return {stage: NoOpExecutor() for stage in PipelineStage}


class TestFullPipelineProgression:
    def test_full_pipeline_progression_with_mock_stages(self, tmp_path):
        """Run → gate accept → verify REVIEWED terminal state."""
        config = _make_config()
        runner = StageRunner(
            strategy_id="e2e-full",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )

        # Phase 1: Run until gated
        state = runner.run()
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value

        # Phase 2: Accept the gate
        gm = GateManager()
        decision = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="accept",
            reason="E2E test approval",
            decided_at="2026-01-01T05:00:00.000Z",
        )
        state = gm.advance(state, decision)
        assert state.current_stage == PipelineStage.REVIEWED.value

        # All stages accounted for
        completed_stages = {cs.stage for cs in state.completed_stages}
        expected = {
            PipelineStage.DATA_READY.value,
            PipelineStage.STRATEGY_READY.value,
            PipelineStage.BACKTEST_RUNNING.value,
            PipelineStage.BACKTEST_COMPLETE.value,
        }
        assert completed_stages == expected


class TestCrashResumeRoundtrip:
    def test_pipeline_crash_resume_roundtrip(self, tmp_path):
        """Simulate crash mid-pipeline and resume from checkpoint."""
        # Phase 1: Start and "crash" after first stage
        class CrashAfterFirstStage:
            def __init__(self):
                self.call_count = 0

            def execute(self, strategy_id, context):
                self.call_count += 1
                if self.call_count == 2:
                    raise RuntimeError("Simulated crash")
                return StageResult(outcome="success")

            def validate_artifact(self, artifact_path, manifest_ref):
                return True

        crasher = CrashAfterFirstStage()
        executors = {stage: crasher for stage in PipelineStage}

        config = _make_config()
        runner = StageRunner(
            strategy_id="crash-e2e",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=executors,
        )

        state = runner.run()
        # Should have error from the crash
        assert state.error is not None

        # Phase 2: Resume with working executors
        runner2 = StageRunner(
            strategy_id="crash-e2e",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )

        resumed = runner2.resume()
        # Should progress further after resume
        assert resumed.run_id != state.run_id


class TestCrashSafePattern:
    def test_pipeline_state_file_survives_crash_safe_pattern(self, tmp_path):
        """State file uses atomic write — no .partial leftovers."""
        config = _make_config()
        runner = StageRunner(
            strategy_id="safe-e2e",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        runner.run()

        state_path = tmp_path / "safe-e2e" / "pipeline-state.json"
        assert state_path.exists()

        # No partial files left
        partials = list((tmp_path / "safe-e2e").glob("*.partial"))
        assert len(partials) == 0

        # State file is valid JSON
        with open(state_path) as f:
            data = json.load(f)
        assert data["strategy_id"] == "safe-e2e"


class TestGateFullCycle:
    def test_gate_reject_then_refine_then_accept_full_cycle(self, tmp_path):
        """Full gate decision cycle: reject → refine → re-run → accept."""
        config = _make_config()
        runner = StageRunner(
            strategy_id="gate-cycle",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )

        # Phase 1: Run to gate
        state = runner.run()
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value

        gm = GateManager()

        # Phase 2: Reject
        d1 = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="reject",
            reason="Drawdown too high",
            decided_at="2026-01-01T01:00:00.000Z",
        )
        state = gm.advance(state, d1)
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value
        assert len(state.gate_decisions) == 1

        # Phase 3: Refine (re-enter at strategy-ready for modification, AC #6)
        d2 = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="refine",
            reason="Adjusted SL and re-running",
            decided_at="2026-01-01T02:00:00.000Z",
        )
        state = gm.advance(state, d2)
        assert state.current_stage == PipelineStage.STRATEGY_READY.value
        assert len(state.gate_decisions) == 2

        # Phase 4: Save refined state and resume pipeline
        state_path = tmp_path / "gate-cycle" / "pipeline-state.json"
        state.save(state_path)

        runner2 = StageRunner(
            strategy_id="gate-cycle",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        state = runner2.resume()
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value

        # Phase 5: Accept
        d3 = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="accept",
            reason="Looks good after adjustments",
            decided_at="2026-01-01T03:00:00.000Z",
        )
        state = gm.advance(state, d3)
        assert state.current_stage == PipelineStage.REVIEWED.value
        assert len(state.gate_decisions) == 3
