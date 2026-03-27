"""Pipeline orchestrator — state machine, stage execution, crash recovery."""
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
from orchestrator.errors import PipelineError, handle_error
from orchestrator.gate_manager import GateManager, PipelineStatus
from orchestrator.stage_runner import (
    NoOpExecutor,
    PipelineConfig,
    StageExecutor,
    StageResult,
    StageRunner,
)
from orchestrator.recovery import (
    recover_from_checkpoint,
    startup_cleanup,
    verify_last_artifact,
)

__all__ = [
    "CompletedStage",
    "GateDecision",
    "GateManager",
    "NoOpExecutor",
    "PipelineConfig",
    "PipelineError",
    "PipelineStage",
    "PipelineState",
    "PipelineStatus",
    "STAGE_GRAPH",
    "STAGE_ORDER",
    "StageExecutor",
    "StageResult",
    "StageRunner",
    "StageTransition",
    "TransitionType",
    "WithinStageCheckpoint",
    "handle_error",
    "recover_from_checkpoint",
    "startup_cleanup",
    "verify_last_artifact",
]
