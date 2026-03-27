"""Live integration tests for pipeline orchestrator.

These tests exercise real system behavior — writing real files,
running real pipeline flows, verifying real outputs on disk.
Run with: pytest -m live
"""
import json
from pathlib import Path

import pytest

from orchestrator.gate_manager import GateManager
from orchestrator.pipeline_state import (
    GateDecision,
    PipelineStage,
    PipelineState,
    STAGE_ORDER,
    WithinStageCheckpoint,
)
from orchestrator.recovery import recover_from_checkpoint, startup_cleanup
from orchestrator.stage_runner import (
    NoOpExecutor,
    PipelineConfig,
    StageRunner,
)


def _make_config() -> PipelineConfig:
    return PipelineConfig(
        artifacts_dir="artifacts",
        checkpoint_enabled=True,
        retry_max_attempts=3,
        retry_backoff_base_s=0.01,
        gated_stages=["review-pending"],
        checkpoint_granularity=1000,
    )


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


@pytest.mark.live
class TestLiveFullPipelineRun:
    """Live test: full pipeline run with real file I/O."""

    def test_live_full_pipeline_run_and_gate_cycle(self, tmp_path):
        """Run pipeline end-to-end, exercise gate decisions, verify all output files."""
        strategy_id = "live-e2e-test"
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        executors = {stage: NoOpExecutor() for stage in PipelineStage}
        config = _make_config()

        runner = StageRunner(
            strategy_id=strategy_id,
            artifacts_dir=artifacts_dir,
            config=config,
            full_config=_full_config(),
            executors=executors,
        )

        # Run until gated
        state = runner.run()
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value

        # Verify state file exists on disk
        state_path = artifacts_dir / strategy_id / "pipeline-state.json"
        assert state_path.exists(), f"State file missing: {state_path}"

        # Verify state file content
        with open(state_path) as f:
            data = json.load(f)
        assert data["strategy_id"] == strategy_id
        assert data["current_stage"] == "review-pending"
        assert len(data["completed_stages"]) == 4
        assert data["config_hash"] != ""
        assert data["run_id"] != ""
        assert data["version"] == 1

        # Gate accept
        gm = GateManager()
        decision = GateDecision(
            stage=PipelineStage.REVIEW_PENDING.value,
            decision="accept",
            reason="Live test approval",
            decided_at="2026-01-01T05:00:00.000Z",
        )
        state = gm.advance(state, decision)
        state.save(state_path)

        # Verify final state on disk
        with open(state_path) as f:
            final = json.load(f)
        assert final["current_stage"] == "reviewed"
        assert len(final["gate_decisions"]) == 1
        assert final["gate_decisions"][0]["decision"] == "accept"


@pytest.mark.live
class TestLiveCrashSafeWrite:
    """Live test: verify crash-safe write pattern produces valid files."""

    def test_live_crash_safe_state_persistence(self, tmp_path):
        """Write state multiple times and verify no corruption or partial files."""
        strategy_id = "live-crash-safe"
        strategy_dir = tmp_path / strategy_id
        strategy_dir.mkdir(parents=True)
        state_path = strategy_dir / "pipeline-state.json"

        # Write state 10 times to exercise the crash-safe pattern
        for i in range(10):
            state = PipelineState(
                strategy_id=strategy_id,
                run_id=f"run-{i}",
                current_stage=PipelineStage.DATA_READY.value,
                config_hash=f"hash-{i}",
            )
            state.save(state_path)

        # Verify final state
        assert state_path.exists()
        with open(state_path) as f:
            data = json.load(f)
        assert data["run_id"] == "run-9"
        assert data["config_hash"] == "hash-9"

        # No partial files left behind
        partials = list(strategy_dir.glob("*.partial"))
        assert len(partials) == 0, f"Partial files found: {partials}"


@pytest.mark.live
class TestLiveCheckpointRecovery:
    """Live test: verify checkpoint recovery reads real files."""

    def test_live_checkpoint_recovery_and_cleanup(self, tmp_path):
        """Write checkpoint files, verify recovery reads them, cleanup works."""
        strategy_id = "live-recovery"
        strategy_dir = tmp_path / strategy_id
        strategy_dir.mkdir(parents=True)

        # Write a within-stage checkpoint file
        checkpoint_data = {
            "stage": "backtest-running",
            "progress_pct": 75.0,
            "last_completed_batch": 750,
            "total_batches": 1000,
            "partial_artifact_path": "results.arrow.partial",
            "checkpoint_at": "2026-01-01T00:05:00.000Z",
        }
        cp_file = strategy_dir / "checkpoint-backtest-running.json"
        cp_file.write_text(json.dumps(checkpoint_data))

        # Write partial files (one referenced, one orphan)
        referenced_partial = strategy_dir / "results.arrow.partial"
        referenced_partial.write_bytes(b"partial backtest data")
        orphan_partial = strategy_dir / "stale-output.arrow.partial"
        orphan_partial.write_bytes(b"orphaned data")

        # Verify checkpoint recovery
        cp = recover_from_checkpoint(strategy_id, tmp_path)
        assert cp is not None
        assert cp.stage == "backtest-running"
        assert cp.progress_pct == 75.0
        assert cp.last_completed_batch == 750

        # Verify cleanup preserves referenced partial
        deleted = startup_cleanup(strategy_id, tmp_path)

        assert referenced_partial.exists(), "Referenced partial should survive cleanup"
        assert not orphan_partial.exists(), "Orphan partial should be deleted"
        assert len(deleted) == 1
        assert "stale-output" in deleted[0]

        # Checkpoint file itself is preserved
        assert cp_file.exists()
