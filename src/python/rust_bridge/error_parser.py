"""Parse structured D8 JSON errors from Rust binary stderr (AC #4, #8).

The Rust binary writes ``{error_type, category, message, context}`` JSON to
stderr on failure. This module parses that JSON and maps it to the
orchestrator's ``PipelineError`` type from Story 3-3.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from logging_setup.setup import get_logger
from orchestrator.errors import PipelineError

logger = get_logger("pipeline.rust_bridge")


@dataclass
class RustError:
    """Parsed structured error from Rust binary stderr."""

    error_type: str        # e.g., "validation_error", "resource_exhaustion"
    category: str          # "resource_pressure" | "data_logic" | "external_failure"
    message: str           # Human-readable description
    context: dict = field(default_factory=dict)


# Mapping from D8 error categories to orchestrator recovery actions (Story 3-3 Task 6).
_CATEGORY_TO_ACTION = {
    "resource_pressure": "throttle",
    "data_logic": "stop_checkpoint",
    "external_failure": "retry_backoff",
}

_CATEGORY_TO_SEVERITY = {
    "resource_pressure": "warning",
    "data_logic": "error",
    "external_failure": "error",
}

_CATEGORY_TO_RECOVERABLE = {
    "resource_pressure": True,
    "data_logic": False,
    "external_failure": True,
}


def parse_rust_error(stderr: str) -> RustError | None:
    """Parse structured JSON error from Rust stderr.

    The Rust binary writes one JSON object per line to stderr. Error JSON
    has the D8 schema: ``{error_type, category, message, context}``.
    Info/warn lines are structured logs, not errors.

    Handles malformed stderr gracefully (Rust panic output, non-JSON).
    Returns None if no structured error is found.
    """
    if not stderr or not stderr.strip():
        return None

    # Try each line in reverse order — the error JSON is typically last
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Must have error_type and category to be a D8 error
        if "error_type" not in data or "category" not in data:
            continue

        return RustError(
            error_type=data["error_type"],
            category=data["category"],
            message=data.get("message", ""),
            context=data.get("context", {}),
        )

    # No structured error found — wrap raw stderr as a fallback
    logger.warning(
        "No structured D8 error found in Rust stderr; wrapping as raw error",
        extra={
            "component": "pipeline.rust_bridge",
            "ctx": {"stderr_length": len(stderr)},
        },
    )
    return RustError(
        error_type="unstructured_error",
        category="data_logic",
        message=stderr[:500],
        context={"raw_stderr": True},
    )


def map_to_pipeline_error(rust_error: RustError) -> PipelineError:
    """Map a Rust error to the orchestrator's PipelineError type (Story 3-3).

    Category mapping per Story 3-3 Task 6:
    - resource_pressure → throttle (reduce concurrency/batch size)
    - data_logic → stop + checkpoint (no retry)
    - external_failure → retry with backoff
    """
    category = rust_error.category
    action = _CATEGORY_TO_ACTION.get(category, "stop_checkpoint")
    severity = _CATEGORY_TO_SEVERITY.get(category, "error")
    recoverable = _CATEGORY_TO_RECOVERABLE.get(category, False)

    return PipelineError(
        code=rust_error.error_type.upper(),
        category=category,
        severity=severity,
        recoverable=recoverable,
        action=action,
        component="pipeline.rust_backtester",
        runtime="rust",
        context={
            **rust_error.context,
            "rust_error_type": rust_error.error_type,
        },
        msg=rust_error.message,
    )
