# Story 3.3: Pipeline State Machine & Checkpoint Infrastructure

Status: review

## Research Update Note (2026-03-18)

This story has been updated to reflect architecture research findings from Stories 3-1/3-2, Research Briefs 3A-3C, and optimization methodology research.

**Key alignment confirmations:**
- **D3 (Opaque Optimization):** Current stage definitions (DATA_READY → STRATEGY_READY → BACKTEST_RUNNING → BACKTEST_COMPLETE → REVIEW_PENDING → REVIEWED) are correct for Epic 3. When optimization is added in Epic 5, it will be a single opaque `OPTIMIZING` state added to `PipelineStage` — the state machine does NOT model optimization sub-stages. The optimizer manages its own internal state behind a pluggable interface.
- **D1 (Fold-Aware Evaluation):** Within-stage checkpoint contract must accommodate fold-aware batch evaluation (multiple fold boundaries per run) introduced by Stories 3-4/3-5.

**References:** architecture.md Research Updates to D1, D3; optimization-methodology-research-summary.md

## Story

As the **operator**,
I want **a pipeline orchestrator that tracks strategy progression through stages with checkpoint/resume support**,
so that **I can see where each strategy is in the pipeline, and interrupted runs resume without data loss**.

## Acceptance Criteria

1. **Given** a strategy entering the pipeline, **When** the orchestrator initializes, **Then** a `pipeline-state.json` file is created per strategy tracking current stage, completed stages, pending stages, and transition timestamps.
   [Source: D3, FR40]

2. **Given** a stage transition, **When** the transition type is evaluated, **Then** `gated` transitions require operator review and `automatic` transitions proceed when preconditions are met. Preconditions for automatic transitions are: previous stage completed successfully, artifact exists and is valid per manifest hash, and no unresolved errors in state.
   [Source: D3, FR39]

3. **Given** the pipeline stage definitions, **When** a strategy progresses, **Then** stages follow: `data-ready` → `strategy-ready` → `backtest-running` → `backtest-complete` → `review-pending` (gated) → `reviewed`.
   [Source: FR40]

4. **Given** the orchestrator crashes mid-pipeline, **When** it restarts, **Then** it reads the state file, verifies the last completed artifact is valid, and continues from the next stage.
   [Source: FR42, NFR11]

5. **Given** a long-running Rust batch stage, **When** the Rust binary writes incremental checkpoints, **Then** the orchestrator detects partial checkpoints and resumes from the last valid checkpoint within the stage.
   [Source: NFR5]

6. **Given** any checkpoint or state write, **When** the write executes, **Then** the crash-safe write pattern is used: write → flush → fsync → atomic rename (`.partial` → final).
   [Source: NFR15]

7. **Given** a strategy that produces unprofitable backtest results, **When** the operator requests pipeline progression, **Then** the system allows progression without blocking on profitability.
   [Source: FR41]

8. **Given** an operator query for pipeline status, **When** the status function is called, **Then** it returns current stage, progress percentage, last transition timestamp, completed stages (with outcome and manifest ref), pending stages, gate status, decision required (if any), blocking reason (if any), and last error.
   [Source: FR40]

11. **Given** a gated stage transition, **When** the operator makes a gate decision, **Then** the system records the decision as `accept`, `reject`, or `refine` — with a reason string and timestamp — and stores the decision in the pipeline state file. `reject` stops progression and records why. `refine` marks the strategy for re-entry at a prior stage.
    [Source: FR39]

12. **Given** a pipeline run, **When** the orchestrator initializes or resumes, **Then** a unique `run_id` (UUID) is assigned per execution attempt and recorded in state, enabling lineage tracking across reruns of the same strategy.
    [Source: FR60]

9. **Given** an error during pipeline execution, **When** the error is categorized, **Then** structured error handling follows D8: resource pressure → throttle, data/logic error → stop and checkpoint, external failure → retry with backoff.
   [Source: D8, NFR10]

10. **Given** any state transition, **When** the transition completes, **Then** it is logged with the unified log schema (ts, level, runtime, component, stage, strategy_id, msg, ctx).
    [Source: D6]

## Tasks / Subtasks

- [x] **Task 1: Consume Story 3-2 Research Output** (AC: #1, #4, #5)
  - [x] Read `_bmad-output/implementation-artifacts/3-2-python-rust-ipc-deterministic-backtesting-research.md` for checkpoint/resume patterns, crash-safe write semantics, and build plan for 3-3
  - [x] Extract the checkpoint schema, resume verification protocol, and within-stage vs cross-stage checkpoint distinction
  - [x] Incorporate any architecture updates proposed by 3-2 into implementation

- [x] **Task 2: Define Pipeline Stage Enum, State Schema, and Gate Decision Model** (AC: #1, #3, #11)
  - [x] Create `src/python/orchestrator/pipeline_state.py` with `PipelineStage` enum: `DATA_READY`, `STRATEGY_READY`, `BACKTEST_RUNNING`, `BACKTEST_COMPLETE`, `REVIEW_PENDING`, `REVIEWED`
  - [x] Define `TransitionType` enum: `AUTOMATIC`, `GATED`
  - [x] Define `StageTransition` dataclass with `from_stage`, `to_stage`, `transition_type`, `preconditions: list[str]`
  - [x] Define `STAGE_GRAPH: dict[PipelineStage, StageTransition]` mapping each stage to its successor and transition type
  - [x] `review-pending → reviewed` is `GATED`; all others are `AUTOMATIC`
  - [x] Define `GateDecision` dataclass:
    ```python
    @dataclass
    class GateDecision:
        stage: PipelineStage
        decision: str  # "accept" | "reject" | "refine"
        reason: str
        decided_at: str  # ISO 8601
        evidence_pack_ref: str | None  # path to evidence pack artifact (populated by Story 3.7)
    ```

- [x] **Task 3: Implement Pipeline State File** (AC: #1, #6, #10, #12)
  - [x] Extend `src/python/orchestrator/pipeline_state.py` with `PipelineState` dataclass:
    ```python
    @dataclass
    class CompletedStage:
        stage: str
        completed_at: str  # ISO 8601
        artifact_path: str | None
        manifest_ref: str | None  # path to manifest for artifact integrity verification
        duration_s: float
        outcome: str  # "success" | "skipped" | "failed"

    @dataclass
    class PipelineState:
        strategy_id: str
        run_id: str  # UUID, unique per execution attempt (FR60 lineage)
        current_stage: PipelineStage
        completed_stages: list[CompletedStage]
        pending_stages: list[PipelineStage]
        gate_decisions: list[GateDecision]  # history of operator gate decisions
        created_at: str  # ISO 8601
        last_transition_at: str  # ISO 8601
        checkpoint: WithinStageCheckpoint | None  # within-stage checkpoint data
        error: PipelineError | None  # last error if any
        config_hash: str  # hash of pipeline config for reproducibility (FR59)
        version: int  # state schema version
    ```
  - [x] Implement `save(path: Path) -> None` using `crash_safe_write` from `src/python/artifacts/storage.py`
  - [x] Implement `load(path: Path) -> PipelineState` with schema version migration support
  - [x] State file location: `artifacts/{strategy_id}/pipeline-state.json`
  - [x] Log every state mutation via unified log schema (D6)

- [x] **Task 4: Implement Stage Runner and Gate Manager** (AC: #2, #3, #4, #7, #8, #11)
  - [x] Define `StageExecutor` Protocol in `src/python/orchestrator/stage_runner.py`:
    ```python
    from typing import Protocol

    @dataclass
    class StageResult:
        artifact_path: str | None
        manifest_ref: str | None
        outcome: str  # "success" | "failed"
        metrics: dict  # stage-specific metrics
        error: PipelineError | None

    class StageExecutor(Protocol):
        def execute(self, strategy_id: str, context: dict) -> StageResult:
            """Execute a pipeline stage. Returns typed StageResult."""
            ...
        def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
            """Verify artifact integrity via manifest hash after crash."""
            ...
    ```
  - [x] Create `StageRunner` class in `src/python/orchestrator/stage_runner.py`:
    ```python
    class StageRunner:
        def __init__(self, strategy_id: str, artifacts_dir: Path, config: PipelineConfig,
                     executors: dict[PipelineStage, StageExecutor] | None = None): ...
        def run(self) -> PipelineState: ...
        def resume(self) -> PipelineState: ...
        def get_status(self) -> PipelineStatus: ...
    ```
  - [x] Create `GateManager` class in `src/python/orchestrator/gate_manager.py`:
    ```python
    @dataclass
    class PipelineStatus:
        stage: str
        progress_pct: float
        last_transition_at: str
        completed: list[CompletedStage]
        pending: list[str]
        gate_status: str | None  # "awaiting_decision" | "accepted" | "rejected" | "refined" | None
        decision_required: bool
        blocking_reason: str | None
        last_outcome: str | None  # outcome of most recent completed stage
        error: dict | None
        config_hash: str
        run_id: str

    class GateManager:
        def advance(self, state: PipelineState, decision: GateDecision) -> PipelineState:
            """Handle gated transitions with accept/reject/refine decisions."""
            ...
        def check_preconditions(self, state: PipelineState, stage: PipelineStage) -> tuple[bool, str | None]:
            """Check automatic transition preconditions. Returns (met, blocking_reason)."""
            ...
    ```
  - [x] `StageRunner.__init__()` loads pipeline config from TOML (D7), computes and stores `config_hash` in state for reproducibility (FR59), generates `run_id` (UUID)
  - [x] `run()` initializes state, executes stages sequentially via `_execute_stage(stage)` using registered `StageExecutor`
  - [x] `resume()` loads existing state file, verifies last artifact via executor's `validate_artifact()`, continues from next incomplete stage. Assigns new `run_id` for the resume attempt.
  - [x] `GateManager.advance()` supports `accept` (proceed), `reject` (stop + record reason), `refine` (re-enter at prior stage). All decisions recorded in `state.gate_decisions`.
  - [x] `get_status()` returns typed `PipelineStatus` including gate_status, decision_required, blocking_reason, last_outcome (FR40: "what passed, what failed, and why")
  - [x] No profitability gate: `check_preconditions()` never blocks on backtest P&L results (AC #7)
  - [x] Provide `NoOpExecutor` stub implementation for testing — returns synthetic StageResult so the orchestrator can be tested end-to-end without real compute

- [x] **Task 5: Implement Crash Recovery** (AC: #4, #5, #6)
  - [x] Create `src/python/orchestrator/recovery.py` with crash recovery logic
  - [x] Implement `verify_last_artifact(state: PipelineState, executor: StageExecutor) -> bool` — delegates to executor's `validate_artifact()` using the artifact_path and manifest_ref from the last completed stage. Single validation path, no duplication.
  - [x] Implement `recover_from_checkpoint(state: PipelineState) -> WithinStageCheckpoint | None` — reads within-stage checkpoint, validates, returns typed checkpoint or None
  - [x] **Cleanup ordering** (resolves clean_partial vs checkpoint conflict): On startup: (1) load pipeline state, (2) read any within-stage checkpoint to identify referenced partial files, (3) call `clean_partial_files()` from `src/python/artifacts/storage.py` with an `exclude` set of paths referenced by valid checkpoints. Only unreferenced `.partial` files are deleted.
  - [x] Within-stage checkpoint contract (consumer-side interface for Rust batch binary, Story 3-4 implements the writer):
    ```python
    @dataclass
    class WithinStageCheckpoint:
        stage: PipelineStage
        progress_pct: float
        last_completed_batch: int
        total_batches: int
        partial_artifact_path: str | None
        checkpoint_at: str  # ISO 8601
    ```
  - [x] Checkpoint file location: `artifacts/{strategy_id}/checkpoint-{stage}.json`
  - [x] Add corresponding schema to `contracts/pipeline_checkpoint.toml` so the Rust-side writer (Story 3-4) and Python-side reader share a single source of truth for checkpoint fields

- [x] **Task 6: Implement Structured Error Handling** (AC: #9, #10)
  - [x] Create `src/python/orchestrator/errors.py` with structured error types per D8:
    ```python
    @dataclass
    class PipelineError:
        code: str
        category: str  # "resource_pressure" | "data_logic" | "external_failure"
        severity: str  # "warning" | "error" | "critical"
        recoverable: bool
        action: str  # "throttle" | "stop_checkpoint" | "retry_backoff"
        component: str
        runtime: str  # "python"
        context: dict
        msg: str
    ```
  - [x] Implement `handle_error(error: PipelineError, state: PipelineState) -> PipelineState`:
    - `resource_pressure`: log warning, throttle, continue
    - `data_logic`: log error, checkpoint current state, stop stage, alert
    - `external_failure`: retry with exponential backoff (max attempts and backoff base from D7 config: `[pipeline] retry_max_attempts`, `[pipeline] retry_backoff_base_s`), then alert
  - [x] All error handling checkpoints state before taking action

- [x] **Task 7: Implement Transition Logging** (AC: #10)
  - [x] Use existing structured logging pattern (D6 unified schema)
  - [x] Log format: `{"ts": ..., "level": "INFO", "runtime": "python", "component": "pipeline.orchestrator", "stage": ..., "strategy_id": ..., "msg": "Stage transition: X → Y", "ctx": {"from_stage": ..., "to_stage": ..., "transition_type": ..., "duration_s": ...}}`
  - [x] Log at minimum: stage entry, stage completion, stage error, checkpoint write, checkpoint resume, gated transition wait, gated transition approval

- [x] **Task 8: Write Tests** (AC: #1-#10)
  - [x] `tests/test_orchestrator/test_pipeline_state.py`:
    - `test_stage_enum_has_all_pipeline_stages()`
    - `test_stage_graph_is_sequential()`
    - `test_review_pending_is_gated()`
    - `test_all_other_transitions_are_automatic()`
    - `test_state_save_load_roundtrip()`
    - `test_state_save_uses_crash_safe_write()`
    - `test_state_tracks_completed_stages_with_outcome_and_manifest()`
    - `test_state_tracks_pending_stages()`
    - `test_state_includes_run_id()`
    - `test_checkpoint_save_load_roundtrip()`
    - `test_gate_decision_serialization_roundtrip()`
  - [x] `tests/test_orchestrator/test_stage_runner.py`:
    - `test_runner_initializes_state_file()`
    - `test_runner_sequential_stage_progression()`
    - `test_runner_no_profitability_gate()`
    - `test_runner_get_status_returns_all_fields()` — verify gate_status, decision_required, blocking_reason, last_outcome are present
    - `test_runner_assigns_unique_run_id()`
    - `test_runner_resume_assigns_new_run_id()`
    - `test_runner_resume_verifies_last_artifact_via_executor()`
    - `test_runner_config_hash_mismatch_on_resume_warns()` — resuming with changed config logs a warning
  - [x] `tests/test_orchestrator/test_gate_manager.py`:
    - `test_gate_blocks_without_decision()`
    - `test_gate_accept_advances_stage()`
    - `test_gate_reject_stops_and_records_reason()`
    - `test_gate_refine_resets_to_prior_stage()`
    - `test_gate_decisions_accumulate_in_state()`
    - `test_preconditions_check_artifact_exists_and_valid()`
  - [x] `tests/test_orchestrator/test_recovery.py`:
    - `test_resume_from_crash_reads_state_and_continues()`
    - `test_cleanup_excludes_checkpoint_referenced_partials()`
    - `test_cleanup_removes_unreferenced_partials()`
    - `test_verify_artifact_delegates_to_executor()`
  - [x] `tests/test_orchestrator/test_errors.py`:
    - `test_resource_pressure_throttles_and_continues()`
    - `test_data_logic_error_checkpoints_and_stops()`
    - `test_external_failure_retries_with_config_driven_backoff()`
    - `test_error_handling_always_checkpoints_first()`
  - [x] `tests/test_orchestrator/test_pipeline_e2e.py`:
    - `test_full_pipeline_progression_with_mock_stages()`
    - `test_pipeline_crash_resume_roundtrip()`
    - `test_pipeline_state_file_survives_crash_safe_pattern()`
    - `test_gate_reject_then_refine_then_accept_full_cycle()`

## Dev Notes

### Architecture Constraints

- **D3 (Sequential State Machine):** Each strategy gets an independent sequential state machine. Pipeline state is a JSON file per strategy. Parallelism lives *within* stages (Rayon inside Rust), not *between* stages. Resume after crash = read state file → verify last artifact → continue from next stage. **Research Update:** Optimization is opaque to the pipeline state machine — when added in Epic 5, it will be a single `OPTIMIZING` state. The optimizer manages its own internal state behind a pluggable interface. Do NOT model optimization sub-stages in the state machine.
- **D1 (Multi-Process):** Python orchestrates, Rust computes. The orchestrator is Python; it spawns Rust batch binary for compute-heavy stages (Stories 3-4, 3-5). This story builds the Python orchestration layer only.
- **D2 (Artifact Storage):** Arrow IPC for compute output, SQLite for query, Parquet for archival. The orchestrator doesn't handle compute artifacts directly — it tracks their existence and validity via manifest files.
- **D6 (Unified Log Schema):** All state transitions must use structured JSON logging: `{ts, level, runtime, component, stage, strategy_id, msg, ctx}`.
- **D8 (Error Handling):** Three categories: resource_pressure → throttle, data_logic → stop+checkpoint, external_failure → retry+backoff. Every error handler must checkpoint state before taking action.
- **D7 (TOML Configuration):** Pipeline config loaded from TOML at `config/base.toml` (or environment overlay). Config hash embedded in state file for reproducibility verification (FR59). Pipeline-specific config keys: `[pipeline]` section with `checkpoint_granularity`, `retry_max_attempts`, `retry_backoff_base_s`, `gated_stages`. Schema validated at startup — fail loud before any stage runs. **All retry counts and backoff parameters MUST come from config, never hardcoded.**
- **NFR10 (Crash Prevention):** Highest-priority NFR. Resource exhaustion → throttle/reduce, never process termination.
- **NFR5 (Incremental Checkpoint):** Long-running stages checkpoint at configurable granularity. Resume from last checkpoint, not from zero.
- **NFR11 (Graceful Recovery):** Resume from last checkpoint with no data corruption.
- **NFR15 (Crash-Safe Writes):** All state/checkpoint writes use write-then-rename pattern. Partial files never overwrite complete ones.

### Critical Design Decisions

- **Stage stubs only:** The stage runner defines stage hooks (`_execute_stage`) but this story does NOT implement the actual stage logic (backtest execution, result storage, etc.). Those are Stories 3-4 through 3-7. The runner calls stage executors via a pluggable `StageExecutor` protocol. Executor returns typed `StageResult`, not untyped dicts.
- **Within-stage checkpoint contract:** Define the `WithinStageCheckpoint` dataclass as the consumer-side interface. The canonical schema lives in `contracts/pipeline_checkpoint.toml` (cross-runtime SSOT). This story defines the Python-side reader; Story 3-4 implements the Rust-side writer. Recovery logic in this story is limited to reading and validating existing checkpoints — speculative recovery is deferred to 3-4 where the actual batch protocol is defined.
- **Gate decision model:** Per FR39, gated stages support `accept`, `reject`, and `refine` decisions — not a simple boolean. Gate decisions are recorded with reason and timestamp in `PipelineState.gate_decisions` for downstream use by Story 3.7 (evidence packs) and Story 3.8 (operator skills). Evidence pack references are nullable fields populated by 3.7.
- **No profitability gate:** Per FR41, the pipeline MUST NOT block progression based on backtest results. This is a deliberate design choice, not an oversight.
- **Run identity:** Each pipeline execution attempt gets a unique `run_id` (UUID). Resumes get a new run_id. This enables lineage tracking (FR60) without a full versioning system (deferred to Growth).
- **Single validation path:** Artifact integrity is verified through `StageExecutor.validate_artifact()` only. The recovery module delegates to the executor — no duplicate validation logic.
- **Story 3-2 dependency:** This story assumes Story 3-2 research has been completed and its output artifact exists at `_bmad-output/implementation-artifacts/3-2-python-rust-ipc-deterministic-backtesting-research.md`. Task 1 consumes that research. This is a mandatory dependency — the dev agent must read 3-2's output before proceeding.

### Data Volume Context (from Story 3-2)

- 1 year EURUSD M1: ~525K bars, ~40 MB Arrow IPC
- 10 years EURUSD M1: ~5.26M bars, ~400 MB Arrow IPC
- Single backtest result: ~80 KB Arrow IPC
- 10K optimization backtests: ~800 MB total
- State files: negligible (<10 KB per strategy)
- Checkpoint files: negligible (<50 KB per checkpoint)

### What to Reuse from Existing Codebase

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| `crash_safe_write()` | `src/python/artifacts/storage.py` | **Use directly** — already implements write → flush → fsync → rename pattern |
| `crash_safe_write_bytes()` | `src/python/artifacts/storage.py` | **Use directly** — binary variant |
| `clean_partial_files()` | `src/python/artifacts/storage.py` | **Use directly** — startup crash recovery scan |
| `StageResult` dataclass | `src/python/data_pipeline/pipeline_proof.py` | **Study pattern** — similar stage result tracking, but pipeline orchestrator needs richer state |
| `PipelineProofResult` | `src/python/data_pipeline/pipeline_proof.py` | **Study pattern** — result aggregation pattern, but orchestrator state is persistent (file-backed) not ephemeral |
| `PipelineProof.run()` stage flow | `src/python/data_pipeline/pipeline_proof.py` | **Study pattern** — sequential stage execution model. New orchestrator must add resume, gated transitions, checkpoint |
| `ValidationResult.rating` | `src/python/data_pipeline/quality_checker.py` | **Reference** — GREEN/YELLOW/RED rating states are a precondition pattern |
| Inter-stage state via instance vars | `src/python/data_pipeline/pipeline_proof.py` | **Anti-pattern** — do NOT use instance variables for state. Use persistent `pipeline-state.json` via `src/python/orchestrator/pipeline_state.py` |

### What to Reuse from ClaudeBackTester

| Component | Verdict | Notes |
|-----------|---------|-------|
| Checkpoint logic | **Adapt patterns** | ClaudeBackTester has proven checkpoint patterns in Python; adapt the granularity and resume-verification concepts |
| Pipeline flow | **Study only** | ClaudeBackTester's pipeline is simpler (no gated transitions, no structured error handling); study for flow patterns but implement fresh |

### Anti-Patterns to Avoid

1. **Don't use instance variables for pipeline state** — PipelineProof stores inter-stage data as `self._df`, `self._data_hash`, etc. The new orchestrator MUST persist all state to `pipeline-state.json` so crashes don't lose progress.
2. **Don't implement actual stage executors** — This story builds the orchestration framework. The actual backtest execution (3-4, 3-5), result storage (3-6), and analysis (3-7) are separate stories. Use a pluggable `StageExecutor` protocol.
3. **Don't add a profitability gate** — FR41 explicitly prohibits blocking progression on backtest P&L. Any precondition check must exclude profitability metrics.
4. **Don't skip crash-safe writes for "small" files** — Even state files and checkpoint files MUST use the atomic write pattern. A corrupted 10 KB state file is as catastrophic as a corrupted 800 MB artifact.
5. **Don't conflate within-stage and cross-stage checkpoints** — Cross-stage checkpoints are `pipeline-state.json` (Python orchestrator manages). Within-stage checkpoints are `checkpoint-{stage}.json` (Rust batch binary writes, Python reads on resume).
6. **Don't scatter stage definitions as string literals** — Use the `PipelineStage` enum and `STAGE_GRAPH` so future epics can extend the pipeline by adding enum values and graph entries. When Epic 5 adds optimization, it will be a single opaque `OPTIMIZING` state — do NOT pre-model optimization sub-stages (per architecture D3 Research Update). The enum + graph pattern IS the non-hardcoded approach.
7. **Don't use in-memory-only state** — Every state mutation must be persisted before proceeding to the next operation. The orchestrator is crash-safe by construction.
8. **Don't hardcode retry counts or backoff parameters** — D7 mandates config-driven values. D8 mandates exponential backoff for external failures. Use `[pipeline] retry_max_attempts` and `[pipeline] retry_backoff_base_s` from config.
9. **Don't log unstructured text** — D6 requires structured JSON logs. Every log entry must include all schema fields.
10. **Don't clean partial files before reading checkpoints** — On startup, always load pipeline state and read checkpoint files FIRST to identify referenced partial artifacts, then clean only unreferenced `.partial` files. Cleaning first can destroy resumable state.
11. **Don't duplicate artifact validation** — Artifact integrity verification goes through `StageExecutor.validate_artifact()` only. The recovery module delegates to executors, never implements its own validation logic.

### Project Structure Notes

New files to create:
```
src/python/orchestrator/
  __init__.py
  pipeline_state.py   # PipelineStage enum, TransitionType, STAGE_GRAPH, GateDecision, CompletedStage, PipelineState
  stage_runner.py     # StageExecutor protocol, StageResult, StageRunner (orchestration), NoOpExecutor
  gate_manager.py     # GateManager, PipelineStatus, precondition checks
  recovery.py         # Crash recovery: verify_last_artifact, recover_from_checkpoint, cleanup orchestration
  errors.py           # PipelineError, handle_error()

contracts/
  pipeline_checkpoint.toml  # Within-stage checkpoint schema (cross-runtime: Python reads, Rust writes)

tests/unit/orchestrator/
  __init__.py
  test_pipeline_state.py
  test_stage_runner.py
  test_gate_manager.py
  test_recovery.py
  test_errors.py

tests/integration/orchestrator/
  __init__.py
  test_pipeline_e2e.py
```

Existing files to import from (do not modify):
```
src/python/artifacts/storage.py    # crash_safe_write, crash_safe_write_bytes, clean_partial_files
```

Alignment: The `src/python/orchestrator/` directory matches the architecture's approved module structure (architecture.md L1535). It sits alongside `src/python/data_pipeline/` (Epic 1) and `src/python/strategy/` (Epic 2). File names match architecture: `pipeline_state.py`, `stage_runner.py`, `gate_manager.py`, `recovery.py`.

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — Decision D3: Pipeline Orchestration]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision D1: System Topology]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision D2: Artifact Schema & Storage]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision D6: Logging & Observability]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision D7: Configuration]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision D8: Error Handling]
- [Source: _bmad-output/planning-artifacts/prd.md — FR38-FR42: Pipeline Control]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58-FR61: Artifact & Reproducibility]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR5: Incremental Checkpoint]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR10: Crash Prevention]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR11: Graceful Recovery]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR15: Crash-Safe Writes]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3: Backtesting & Pipeline Operations]
- [Source: src/python/artifacts/storage.py — crash_safe_write functions]
- [Source: src/python/data_pipeline/pipeline_proof.py — PipelineProof orchestration pattern]
- [Source: _bmad-output/implementation-artifacts/3-2-python-rust-ipc-deterministic-backtesting-research.md — Previous story context (mandatory dependency)]
- [Source: _bmad-output/planning-artifacts/architecture.md — L1535-1540: orchestrator/ module structure]
- [Source: _bmad-output/planning-artifacts/architecture.md — L1151: contracts/ as SSOT for cross-runtime types]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- All 60 tests pass (57 unit/integration + 3 live): 867 total suite pass, 0 regressions

### Completion Notes List
- ✅ Task 1: Consumed Story 3-2 research — extracted checkpoint schema, resume verification protocol, within-stage vs cross-stage distinction
- ✅ Task 2: Created PipelineStage enum (6 stages), TransitionType enum, StageTransition dataclass, STAGE_GRAPH, GateDecision dataclass with accept/reject/refine support
- ✅ Task 3: Implemented PipelineState with save/load using crash_safe_write, schema version migration, JSON serialization roundtrip
- ✅ Task 4: Implemented StageRunner (run/resume/get_status), GateManager (advance/check_preconditions), StageExecutor Protocol, NoOpExecutor, PipelineConfig from TOML. Config hash computed via compute_config_hash. run_id UUID per execution. No profitability gate.
- ✅ Task 5: Implemented recovery.py with verify_last_artifact (delegates to executor), recover_from_checkpoint, startup_cleanup with safe partial cleanup ordering (read checkpoints first, then clean unreferenced partials). Added `exclude` parameter to clean_partial_files in storage.py.
- ✅ Task 6: Implemented PipelineError dataclass and handle_error with D8 categories. All retry counts and backoff from config (never hardcoded). Always checkpoints before handling.
- ✅ Task 7: All transition logging uses D6 unified schema via existing JsonFormatter/get_logger/LogContext. Logs: stage entry, stage completion, stage error, checkpoint write/resume, gated transition wait/approval, config hash mismatch warning.
- ✅ Task 8: 57 unit/integration tests + 3 live tests across 6 test files. All specified tests implemented plus additional coverage (schema version migration, error serialization, edge cases).
- ✅ Added pipeline config keys (retry_max_attempts, retry_backoff_base_s, gated_stages, checkpoint_granularity) to base.toml and schema.toml per lessons-learned rule about config schema entries.
- ✅ Created contracts/pipeline_checkpoint.toml as cross-runtime SSOT for within-stage checkpoint schema.

### Change Log
- 2026-03-18: Story 3-3 implemented — pipeline state machine, checkpoint infrastructure, crash recovery, error handling, gate management, transition logging. All 8 tasks complete, 60 tests passing, 0 regressions in full suite (867 pass).

### File List
**New files:**
- `src/python/orchestrator/pipeline_state.py` — PipelineStage enum, state schema, save/load
- `src/python/orchestrator/stage_runner.py` — StageRunner, StageExecutor protocol, NoOpExecutor, PipelineConfig
- `src/python/orchestrator/gate_manager.py` — GateManager, PipelineStatus, precondition checks
- `src/python/orchestrator/recovery.py` — Crash recovery, checkpoint resume, startup cleanup
- `src/python/orchestrator/errors.py` — PipelineError, handle_error (D8)
- `contracts/pipeline_checkpoint.toml` — Cross-runtime checkpoint schema SSOT
- `src/python/tests/test_orchestrator/__init__.py`
- `src/python/tests/test_orchestrator/test_pipeline_state.py` — 15 unit tests
- `src/python/tests/test_orchestrator/test_stage_runner.py` — 10 unit tests
- `src/python/tests/test_orchestrator/test_gate_manager.py` — 11 unit tests
- `src/python/tests/test_orchestrator/test_recovery.py` — 11 unit tests
- `src/python/tests/test_orchestrator/test_errors.py` — 6 unit tests
- `src/python/tests/test_orchestrator/test_pipeline_e2e.py` — 4 integration tests
- `src/python/tests/test_orchestrator/test_pipeline_live.py` — 3 live tests

**Modified files:**
- `src/python/orchestrator/__init__.py` — Public API exports
- `src/python/artifacts/storage.py` — Added `exclude` parameter to `clean_partial_files`
- `config/base.toml` — Added [pipeline] retry_max_attempts, retry_backoff_base_s, gated_stages, checkpoint_granularity
- `config/schema.toml` — Added schema validation entries for new pipeline config keys
