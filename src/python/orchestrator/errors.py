"""Structured error handling for pipeline orchestrator (D8).

Error categories:
- resource_pressure → throttle, continue
- data_logic → stop, checkpoint, alert
- external_failure → retry with exponential backoff, then alert
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from logging_setup.setup import get_logger

if TYPE_CHECKING:
    from orchestrator.pipeline_state import PipelineState

logger = get_logger("pipeline.errors")


@dataclass
class PipelineError:
    code: str
    category: str  # "resource_pressure" | "data_logic" | "external_failure"
    severity: str  # "warning" | "error" | "critical"
    recoverable: bool
    action: str  # "throttle" | "stop_checkpoint" | "retry_backoff"
    component: str
    runtime: str = "python"
    context: dict = field(default_factory=dict)
    msg: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "recoverable": self.recoverable,
            "action": self.action,
            "component": self.component,
            "runtime": self.runtime,
            "context": self.context,
            "msg": self.msg,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineError:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def handle_error(
    error: PipelineError,
    state: PipelineState,
    save_fn: callable,
    retry_max_attempts: int = 3,
    retry_backoff_base_s: float = 2.0,
    attempt: int = 0,
    is_last_attempt: bool = False,
) -> PipelineState:
    """Handle a pipeline error per D8 categorization.

    Always checkpoints state before taking action.

    Args:
        error: The structured error to handle.
        state: Current pipeline state (mutated in place with error info).
        save_fn: Callable to persist state (takes no args, checkpoints current state).
        retry_max_attempts: From config [pipeline] retry_max_attempts.
        retry_backoff_base_s: From config [pipeline] retry_backoff_base_s.
        attempt: Current retry attempt number (0-based, used for external_failure backoff).
        is_last_attempt: If True, skip the backoff sleep (no point sleeping before giving up).

    Returns:
        Updated PipelineState with error recorded.
    """
    state.error = error.to_dict()
    save_fn()

    log_extra = {
        "component": "pipeline.errors",
        "stage": state.current_stage,
        "strategy_id": state.strategy_id,
        "ctx": {
            "error_code": error.code,
            "category": error.category,
            "severity": error.severity,
            "action": error.action,
            "msg": error.msg,
        },
    }

    if error.category == "resource_pressure":
        logger.warning(
            f"Resource pressure: {error.msg} — throttling",
            extra=log_extra,
        )
        # D8: throttle and continue — clear error so pipeline can proceed
        state.error = None
        return state

    if error.category == "data_logic":
        logger.error(
            f"Data/logic error: {error.msg} — stopped and checkpointed",
            extra=log_extra,
        )
        return state

    if error.category == "external_failure":
        total_attempts = retry_max_attempts + 1
        delay = retry_backoff_base_s * (2 ** attempt)
        logger.warning(
            f"External failure: {error.msg} — attempt {attempt + 1}/{total_attempts} "
            f"backoff {delay:.1f}s",
            extra={
                **log_extra,
                "ctx": {
                    **log_extra["ctx"],
                    "attempt": attempt + 1,
                    "total_attempts": total_attempts,
                    "delay_s": delay,
                },
            },
        )
        if not is_last_attempt:
            time.sleep(delay)
        # Caller is responsible for the retry loop.
        # This function handles per-attempt backoff delay, logging, and checkpointing.
        return state

    logger.error(f"Unknown error category '{error.category}': {error.msg}", extra=log_extra)
    return state
