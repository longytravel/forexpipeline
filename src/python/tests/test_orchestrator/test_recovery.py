"""Unit tests for crash recovery — artifact verification, checkpoint resume, cleanup."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.pipeline_state import (
    CompletedStage,
    PipelineStage,
    PipelineState,
    WithinStageCheckpoint,
)
from orchestrator.recovery import (
    recover_from_checkpoint,
    startup_cleanup,
    verify_last_artifact,
)


class TestVerifyLastArtifact:
    def test_resume_from_crash_reads_state_and_continues(self, tmp_path):
        """verify_last_artifact delegates to executor's validate_artifact."""
        mock_executor = MagicMock()
        mock_executor.validate_artifact.return_value = True

        state = PipelineState(
            strategy_id="crash-test",
            run_id="run-1",
            current_stage=PipelineStage.BACKTEST_RUNNING.value,
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

        result = verify_last_artifact(state, mock_executor)
        assert result is True
        mock_executor.validate_artifact.assert_called_once_with(
            Path("data.arrow"), Path("manifest.json")
        )

    def test_verify_artifact_delegates_to_executor(self, tmp_path):
        """Verification goes through executor only — no duplicate logic."""
        mock_executor = MagicMock()
        mock_executor.validate_artifact.return_value = False

        state = PipelineState(
            strategy_id="delegate-test",
            run_id="run-1",
            current_stage=PipelineStage.STRATEGY_READY.value,
            completed_stages=[
                CompletedStage(
                    stage=PipelineStage.DATA_READY.value,
                    completed_at="2026-01-01T00:00:00.000Z",
                    artifact_path="bad.arrow",
                    manifest_ref="bad-manifest.json",
                    outcome="success",
                ),
            ],
        )
        result = verify_last_artifact(state, mock_executor)
        assert result is False

    def test_verify_returns_true_when_no_completed_stages(self):
        mock_executor = MagicMock()
        state = PipelineState(
            strategy_id="empty",
            run_id="run-1",
            current_stage=PipelineStage.DATA_READY.value,
        )
        result = verify_last_artifact(state, mock_executor)
        assert result is True
        mock_executor.validate_artifact.assert_not_called()

    def test_verify_returns_true_when_no_artifact_path(self):
        mock_executor = MagicMock()
        state = PipelineState(
            strategy_id="no-artifact",
            run_id="run-1",
            current_stage=PipelineStage.STRATEGY_READY.value,
            completed_stages=[
                CompletedStage(
                    stage=PipelineStage.DATA_READY.value,
                    completed_at="2026-01-01T00:00:00.000Z",
                    artifact_path=None,
                    manifest_ref=None,
                    outcome="skipped",
                ),
            ],
        )
        result = verify_last_artifact(state, mock_executor)
        assert result is True


class TestRecoverFromCheckpoint:
    def test_recover_from_valid_checkpoint(self, tmp_path):
        strategy_dir = tmp_path / "test-strat"
        strategy_dir.mkdir()

        checkpoint_data = {
            "stage": "backtest-running",
            "progress_pct": 50.0,
            "last_completed_batch": 500,
            "total_batches": 1000,
            "partial_artifact_path": "results.arrow.partial",
            "checkpoint_at": "2026-01-01T00:03:00.000Z",
        }
        (strategy_dir / "checkpoint-backtest-running.json").write_text(
            json.dumps(checkpoint_data)
        )

        cp = recover_from_checkpoint("test-strat", tmp_path)
        assert cp is not None
        assert cp.stage == "backtest-running"
        assert cp.progress_pct == 50.0
        assert cp.last_completed_batch == 500

    def test_recover_returns_none_when_no_checkpoint(self, tmp_path):
        strategy_dir = tmp_path / "empty-strat"
        strategy_dir.mkdir()
        cp = recover_from_checkpoint("empty-strat", tmp_path)
        assert cp is None

    def test_recover_returns_none_for_invalid_json(self, tmp_path):
        strategy_dir = tmp_path / "bad-strat"
        strategy_dir.mkdir()
        (strategy_dir / "checkpoint-backtest-running.json").write_text("not json")
        cp = recover_from_checkpoint("bad-strat", tmp_path)
        assert cp is None

    def test_recover_returns_none_when_strategy_dir_missing(self, tmp_path):
        cp = recover_from_checkpoint("nonexistent", tmp_path)
        assert cp is None


class TestStartupCleanup:
    def test_cleanup_excludes_checkpoint_referenced_partials(self, tmp_path):
        strategy_dir = tmp_path / "cleanup-test"
        strategy_dir.mkdir()

        # Create two partial files
        referenced = strategy_dir / "results.arrow.partial"
        referenced.write_bytes(b"partial data")
        orphan = strategy_dir / "old-output.arrow.partial"
        orphan.write_bytes(b"stale data")

        # Create a checkpoint referencing the first partial
        checkpoint_data = {
            "stage": "backtest-running",
            "progress_pct": 50.0,
            "last_completed_batch": 500,
            "total_batches": 1000,
            "partial_artifact_path": "results.arrow.partial",
            "checkpoint_at": "2026-01-01T00:03:00.000Z",
        }
        (strategy_dir / "checkpoint-backtest-running.json").write_text(
            json.dumps(checkpoint_data)
        )

        deleted = startup_cleanup("cleanup-test", tmp_path)

        # Referenced partial should survive
        assert referenced.exists()
        # Orphan should be deleted
        assert not orphan.exists()
        assert len(deleted) == 1
        assert "old-output.arrow.partial" in deleted[0]

    def test_cleanup_removes_unreferenced_partials(self, tmp_path):
        strategy_dir = tmp_path / "clean-all"
        strategy_dir.mkdir()

        (strategy_dir / "a.partial").write_bytes(b"x")
        (strategy_dir / "b.partial").write_bytes(b"y")

        deleted = startup_cleanup("clean-all", tmp_path)
        assert len(deleted) == 2
        assert not (strategy_dir / "a.partial").exists()
        assert not (strategy_dir / "b.partial").exists()

    def test_cleanup_with_state_checkpoint_excludes_partial(self, tmp_path):
        strategy_dir = tmp_path / "state-cp"
        strategy_dir.mkdir()

        referenced = strategy_dir / "state-referenced.partial"
        referenced.write_bytes(b"data")

        state = PipelineState(
            strategy_id="state-cp",
            run_id="run-1",
            current_stage=PipelineStage.BACKTEST_RUNNING.value,
            checkpoint=WithinStageCheckpoint(
                stage=PipelineStage.BACKTEST_RUNNING.value,
                progress_pct=25.0,
                last_completed_batch=250,
                total_batches=1000,
                partial_artifact_path="state-referenced.partial",
                checkpoint_at="2026-01-01T00:01:00.000Z",
            ),
        )

        deleted = startup_cleanup("state-cp", tmp_path, state=state)
        assert referenced.exists()
        assert len(deleted) == 0
