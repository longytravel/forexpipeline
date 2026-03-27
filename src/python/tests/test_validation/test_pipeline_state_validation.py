"""Tests for VALIDATING / VALIDATION_COMPLETE pipeline stages (Task 1)."""
from orchestrator.pipeline_state import (
    PipelineStage,
    STAGE_GRAPH,
    STAGE_ORDER,
    TransitionType,
)


def test_pipeline_state_validating_stages():
    """Verify VALIDATING and VALIDATION_COMPLETE are in enum and stage order."""
    assert PipelineStage.VALIDATING.value == "validating"
    assert PipelineStage.VALIDATION_COMPLETE.value == "validation-complete"

    # Both stages should be in STAGE_ORDER
    assert PipelineStage.VALIDATING in STAGE_ORDER
    assert PipelineStage.VALIDATION_COMPLETE in STAGE_ORDER

    # VALIDATING must come after OPTIMIZATION_COMPLETE
    opt_idx = STAGE_ORDER.index(PipelineStage.OPTIMIZATION_COMPLETE)
    val_idx = STAGE_ORDER.index(PipelineStage.VALIDATING)
    valc_idx = STAGE_ORDER.index(PipelineStage.VALIDATION_COMPLETE)
    assert val_idx == opt_idx + 1
    assert valc_idx == val_idx + 1


def test_pipeline_state_validating_transitions():
    """Verify transition graph for validation stages."""
    # OPTIMIZATION_COMPLETE -> VALIDATING (automatic)
    t1 = STAGE_GRAPH[PipelineStage.OPTIMIZATION_COMPLETE]
    assert t1.to_stage == PipelineStage.VALIDATING
    assert t1.transition_type == TransitionType.AUTOMATIC

    # VALIDATING -> VALIDATION_COMPLETE (automatic)
    t2 = STAGE_GRAPH[PipelineStage.VALIDATING]
    assert t2.to_stage == PipelineStage.VALIDATION_COMPLETE
    assert t2.transition_type == TransitionType.AUTOMATIC

    # VALIDATION_COMPLETE is a gated stage. It may or may not have a
    # STAGE_GRAPH entry depending on whether downstream stages exist yet.
    # Do NOT assert terminality — downstream stories will add transitions.
