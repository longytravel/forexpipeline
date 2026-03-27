# Story 3-3-pipeline-state-machine-checkpoint-infrastructure: Story 3.3: Pipeline State Machine & Checkpoint Infrastructure — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**  
Assessment: `ADEQUATE`

- Reproducibility is materially better. The story persists per-strategy state with crash-safe writes, stores a `run_id` per execution attempt, and records `config_hash` on run/resume, which directly supports FR59-FR61 and the PRD’s deterministic-behavior goal. [pipeline_state.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L233) [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L127) [storage.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/artifacts/storage.py#L10) [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551)

- Operator confidence is improved structurally. `PipelineStatus` exposes stage, progress, blocking reason, gate status, error, `run_id`, and `config_hash`, which gives a non-coder a clearer “where am I / why am I blocked” view. [gate_manager.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/gate_manager.py#L21) [gate_manager.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/gate_manager.py#L177) [test_stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_orchestrator/test_stage_runner.py#L150) [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L518)

- Artifact integrity is advanced, but artifact completeness is not enforced by this layer. Preconditions validate artifacts and manifests when present, but the orchestrator also allows success with no artifact at all; `NoOpExecutor` returns success without artifacts, and a missing executor is marked `skipped` while the pipeline still advances. That works against the system’s “every stage emits a persisted, reviewable artifact” objective if this behavior escapes test-only use. [gate_manager.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/gate_manager.py#L151) [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L61) [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L355) [test_stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_orchestrator/test_stage_runner.py#L172) [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L99)

- Fidelity/recovery is only partially realized today. The runner does recover checkpoint files into state and does safe partial-file cleanup, but true within-stage “resume from last batch” is not wired through execution yet; executors are only called with `artifacts_dir`, and the story doc explicitly defers real batch resume behavior to Story 3-4. [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L219) [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L391) [recovery.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/recovery.py#L71) [3-3-pipeline-state-machine-checkpoint-infrastructure.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md#L286)

- V1 scope is mostly right-sized. The state machine is intentionally simple and architecture-aligned: one sequential graph, one gated review stage, no optimization sub-state explosion. That fits V1 better than a richer workflow engine would. [pipeline_state.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L53) [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L412) [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L425)

**2. Simplification**  
Assessment: `ADEQUATE`

- The main structure is not obviously over-engineered. Separate modules for persistent state, gate/status logic, recovery, and D8 error handling are coherent and map cleanly to the architecture. [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L108) [gate_manager.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/gate_manager.py#L38) [recovery.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/recovery.py#L26) [errors.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/errors.py#L52)

- The clearest simplification opportunity is unused config surface. `checkpoint_enabled`, `gated_stages`, and `checkpoint_granularity` are loaded and schema-validated, but the orchestrator does not consume them. `gated_stages` in particular duplicates `STAGE_GRAPH`, which is the real source of transition behavior. [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L80) [config/base.toml](/c/Users/ROG/Projects/Forex%20Pipeline/config/base.toml#L58) [config/schema.toml](/c/Users/ROG/Projects/Forex%20Pipeline/config/schema.toml#L130)

- There are two testing escape hatches doing similar work: `NoOpExecutor` and “missing executor => skipped.” Keeping both increases flexibility, but also increases the chance of a pipeline appearing healthy without producing real evidence. A fail-loud default plus explicit test doubles would be simpler and safer. [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L61) [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L355)

- The two-checkpoint model is justified, not redundant. `pipeline-state.json` and `checkpoint-{stage}.json` represent different layers of recovery and match the architecture’s “cross-stage vs within-stage” separation. [3-3-pipeline-state-machine-checkpoint-infrastructure.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md#L328) [recovery.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/recovery.py#L71) [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L421)

**3. Forward Look**  
Assessment: `CONCERN`

- The output contract is a good foundation for downstream stories. `CompletedStage` carries artifact/manifests/outcome, `GateDecision` already has a placeholder for `evidence_pack_ref`, and the checkpoint schema is in `contracts/` as shared SSOT. [pipeline_state.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L99) [pipeline_state.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L139) [pipeline_checkpoint.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/pipeline_checkpoint.toml#L1)

- The biggest downstream gap is resume handoff. The runner recovers a checkpoint into state, but does not pass that checkpoint into `executor.execute()`. As built, Story 3-4 will need either a StageRunner contract change or executor-side state reloading to do real within-stage resume. [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L219) [stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L391) [3-3-pipeline-state-machine-checkpoint-infrastructure.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md#L35)

- The checkpoint contract is stronger than the reader implementation. The TOML contract defines allowed values and bounds, but Python recovery only deserializes JSON into a dataclass. If downstream Rust code assumes those invariants are enforced, that assumption does not yet hold. [pipeline_checkpoint.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/pipeline_checkpoint.toml#L14) [pipeline_state.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L194) [recovery.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/recovery.py#L92)

- `refine` is hard-coded to re-enter `backtest-running`. That is acceptable for the current slice, but it bakes in one re-entry policy that may not hold once optimization, validation, and live-monitoring loops exist. [gate_manager.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/gate_manager.py#L96) [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L425)

- Operator-facing evidence is still only a placeholder. The architecture expects evidence-pack assembly and gate UI, and the PRD expects coherent evidence at each gate; this story sets a slot for that, but not the operator-ready contract yet. [pipeline_state.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L105) [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L825) [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517)

**Overall**  
`OBSERVE`

The story is aligned as infrastructure for reproducibility, crash safety, and a V1-sized sequential pipeline. The main observations are that artifact completeness is not enforced by the orchestrator itself, and true within-stage resume plus evidence-backed operator gating are still deferred to downstream stories.
