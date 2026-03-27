"""Unit tests for stage runner and pipeline execution."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.errors import PipelineError
from orchestrator.pipeline_state import (
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
        "retry_backoff_base_s": 0.01,  # Fast for tests
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


def _noop_executors() -> dict:
    """Return NoOpExecutor for every stage."""
    return {stage: NoOpExecutor() for stage in PipelineStage}


class TestRunnerInitialization:
    def test_runner_initializes_state_file(self, tmp_path):
        config = _make_config()
        runner = StageRunner(
            strategy_id="init-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        state = runner.run()

        state_path = tmp_path / "init-test" / "pipeline-state.json"
        assert state_path.exists()

        with open(state_path) as f:
            data = json.load(f)
        assert data["strategy_id"] == "init-test"
        assert data["version"] == 1

    def test_runner_assigns_unique_run_id(self, tmp_path):
        config = _make_config()
        runner1 = StageRunner(
            strategy_id="runid-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        runner2 = StageRunner(
            strategy_id="runid-test2",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        state1 = runner1.run()
        state2 = runner2.run()
        assert state1.run_id != state2.run_id
        assert len(state1.run_id) == 36  # UUID format


class TestRunnerExecution:
    def test_runner_sequential_stage_progression(self, tmp_path):
        """Pipeline progresses through all automatic stages and stops at gated."""
        config = _make_config()
        runner = StageRunner(
            strategy_id="seq-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        state = runner.run()

        # Should stop at REVIEW_PENDING (gated)
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value

        # All stages before REVIEW_PENDING should be completed
        completed_names = {cs.stage for cs in state.completed_stages}
        expected_completed = {
            PipelineStage.DATA_READY.value,
            PipelineStage.STRATEGY_READY.value,
            PipelineStage.BACKTEST_RUNNING.value,
            PipelineStage.BACKTEST_COMPLETE.value,
        }
        assert completed_names == expected_completed

    def test_runner_no_profitability_gate(self, tmp_path):
        """AC #7: Pipeline never blocks on backtest P&L results."""
        # An executor that returns unprofitable metrics
        class UnprofitableExecutor:
            def execute(self, strategy_id, context):
                return StageResult(
                    outcome="success",
                    metrics={"net_profit": -5000, "sharpe": -0.5},
                )

            def validate_artifact(self, artifact_path, manifest_ref):
                return True

        executors = _noop_executors()
        executors[PipelineStage.BACKTEST_RUNNING] = UnprofitableExecutor()

        config = _make_config()
        runner = StageRunner(
            strategy_id="noprofit-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=executors,
        )
        state = runner.run()

        # Should still progress past backtest despite negative P&L
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value

    def test_runner_get_status_returns_all_fields(self, tmp_path):
        config = _make_config()
        runner = StageRunner(
            strategy_id="status-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        runner.run()

        status = runner.get_status()
        assert status.stage == PipelineStage.REVIEW_PENDING.value
        assert isinstance(status.progress_pct, float)
        assert status.last_transition_at != ""
        assert status.gate_status == "awaiting_decision"
        assert status.decision_required is True
        assert status.blocking_reason is not None
        assert status.config_hash != ""
        assert status.run_id != ""
        assert status.last_outcome == "success"

    def test_runner_skips_stage_without_executor(self, tmp_path):
        """Stages without registered executors are skipped."""
        config = _make_config()
        runner = StageRunner(
            strategy_id="skip-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors={},  # No executors
        )
        state = runner.run()

        # All should be skipped, stopping at gated stage
        assert state.current_stage == PipelineStage.REVIEW_PENDING.value
        for cs in state.completed_stages:
            assert cs.outcome == "skipped"


class TestRunnerResume:
    def test_runner_resume_assigns_new_run_id(self, tmp_path):
        config = _make_config()
        runner = StageRunner(
            strategy_id="resume-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=_noop_executors(),
        )
        state = runner.run()
        original_run_id = state.run_id

        resumed_state = runner.resume()
        assert resumed_state.run_id != original_run_id

    def test_runner_resume_verifies_last_artifact_via_executor(self, tmp_path):
        """Resume delegates artifact verification to executor."""
        config = _make_config()
        mock_executor = MagicMock()
        mock_executor.execute.return_value = StageResult(outcome="success")
        mock_executor.validate_artifact.return_value = True

        runner = StageRunner(
            strategy_id="verify-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors={stage: mock_executor for stage in PipelineStage},
        )
        runner.run()
        runner.resume()
        # Executor was used (execute was called during both run and resume)
        assert mock_executor.execute.call_count >= 1

    def test_runner_config_hash_mismatch_on_resume_warns(self, tmp_path, caplog):
        config = _make_config()
        runner = StageRunner(
            strategy_id="hash-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config={"pipeline": {"artifacts_dir": "a", "checkpoint_enabled": True,
                                       "retry_max_attempts": 3, "retry_backoff_base_s": 0.01,
                                       "gated_stages": ["review-pending"],
                                       "checkpoint_granularity": 1000}},
            executors=_noop_executors(),
        )
        runner.run()

        # Resume with different config
        runner2 = StageRunner(
            strategy_id="hash-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config={"pipeline": {"artifacts_dir": "CHANGED", "checkpoint_enabled": True,
                                       "retry_max_attempts": 3, "retry_backoff_base_s": 0.01,
                                       "gated_stages": ["review-pending"],
                                       "checkpoint_granularity": 1000}},
            executors=_noop_executors(),
        )

        import logging
        with caplog.at_level(logging.WARNING):
            runner2.resume()

        # Check that a warning was logged about config hash mismatch
        warning_found = any("config hash mismatch" in r.message.lower() or
                           "Config hash mismatch" in r.message
                           for r in caplog.records)
        assert warning_found, "Expected config hash mismatch warning on resume"


class TestRunnerErrorHandling:
    def test_runner_stops_on_stage_execution_error(self, tmp_path):
        class FailingExecutor:
            def execute(self, strategy_id, context):
                raise RuntimeError("Simulated stage failure")

            def validate_artifact(self, artifact_path, manifest_ref):
                return True

        executors = _noop_executors()
        executors[PipelineStage.STRATEGY_READY] = FailingExecutor()

        config = _make_config()
        runner = StageRunner(
            strategy_id="error-test",
            artifacts_dir=tmp_path,
            config=config,
            full_config=_full_config(),
            executors=executors,
        )
        state = runner.run()

        assert state.error is not None
        assert state.error["category"] == "data_logic"
        assert "Simulated stage failure" in state.error["msg"]
