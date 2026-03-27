"""Unit tests for structured error handling (D8)."""
import logging
from unittest.mock import MagicMock

import pytest

from orchestrator.errors import PipelineError, handle_error
from orchestrator.pipeline_state import PipelineStage, PipelineState


def _make_state() -> PipelineState:
    return PipelineState(
        strategy_id="error-test",
        run_id="run-1",
        current_stage=PipelineStage.BACKTEST_RUNNING.value,
    )


class TestResourcePressure:
    def test_resource_pressure_throttles_and_continues(self):
        state = _make_state()
        save_fn = MagicMock()
        error = PipelineError(
            code="MEM_HIGH",
            category="resource_pressure",
            severity="warning",
            recoverable=True,
            action="throttle",
            component="pipeline.backtest",
            msg="Memory usage at 90%",
        )

        result = handle_error(error, state, save_fn, retry_max_attempts=3, retry_backoff_base_s=0.01)
        # State saved (checkpointed) before handling
        save_fn.assert_called_once()
        # D8: resource_pressure → throttle and continue — error is cleared
        assert result.error is None


class TestDataLogicError:
    def test_data_logic_error_checkpoints_and_stops(self):
        state = _make_state()
        save_fn = MagicMock()
        error = PipelineError(
            code="BAD_DATA",
            category="data_logic",
            severity="error",
            recoverable=False,
            action="stop_checkpoint",
            component="pipeline.validation",
            msg="Invalid bar timestamps",
        )

        result = handle_error(error, state, save_fn, retry_max_attempts=3, retry_backoff_base_s=0.01)
        save_fn.assert_called_once()
        assert result.error["action"] == "stop_checkpoint"


class TestExternalFailure:
    def test_external_failure_retries_with_config_driven_backoff(self):
        state = _make_state()
        save_fn = MagicMock()
        error = PipelineError(
            code="API_TIMEOUT",
            category="external_failure",
            severity="error",
            recoverable=True,
            action="retry_backoff",
            component="pipeline.download",
            msg="API call timed out",
        )

        result = handle_error(
            error, state, save_fn,
            retry_max_attempts=2,
            retry_backoff_base_s=0.01,  # Very fast for test
        )
        # save_fn called once (at start of handle_error)
        save_fn.assert_called_once()
        assert result.error["action"] == "retry_backoff"


class TestAlwaysCheckpoints:
    def test_error_handling_always_checkpoints_first(self):
        """Every error category must checkpoint state before taking action."""
        for category in ["resource_pressure", "data_logic", "external_failure"]:
            state = _make_state()
            call_order = []

            def save_fn():
                call_order.append("save")

            error = PipelineError(
                code="TEST",
                category=category,
                severity="warning",
                recoverable=True,
                action="throttle",
                component="test",
                msg=f"Test {category}",
            )

            handle_error(error, state, save_fn, retry_max_attempts=1, retry_backoff_base_s=0.01)

            assert call_order[0] == "save", \
                f"Category '{category}' did not checkpoint before handling"


class TestPipelineErrorSerialization:
    def test_error_roundtrip(self):
        error = PipelineError(
            code="TEST_ERR",
            category="data_logic",
            severity="error",
            recoverable=False,
            action="stop_checkpoint",
            component="test",
            context={"detail": "something"},
            msg="Test error message",
        )
        d = error.to_dict()
        restored = PipelineError.from_dict(d)
        assert restored.code == "TEST_ERR"
        assert restored.category == "data_logic"
        assert restored.msg == "Test error message"
        assert restored.context == {"detail": "something"}
