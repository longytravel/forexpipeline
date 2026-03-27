# Story Synthesis: 3-3-pipeline-state-machine-checkpoint-infrastructure

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-17
**Story file:** `_bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md`
**Codex review:** `reviews/story-reviews/story-3-3-pipeline-state-machine-checkpoint-infrastructure-codex-review.md`

---

## Codex Observations & Decisions

### 1. Gate Model Too Narrow (System Alignment)
**Codex said:** FR39 requires accept/reject/refine decisions, but story models gate as `operator_approved: bool`. Architecture expects evidence-pack-driven gates.
**Decision:** AGREE
**Reasoning:** FR39 explicitly says "accept, reject, or refine decisions." A boolean is demonstrably insufficient. The gate decision model must support all three outcomes with reason tracking, and include nullable evidence_pack_ref for Story 3.7 to populate.
**Action:** Added `GateDecision` dataclass (accept/reject/refine + reason + timestamp + evidence_pack_ref). Replaced `advance(operator_approved: bool)` with `GateManager.advance(state, decision: GateDecision)`. Added new AC #11 for gate decisions. Added `gate_decisions: list[GateDecision]` to PipelineState. Created `gate_manager.py` per architecture structure.

### 2. Status Missing "What Passed, What Failed, and Why" (PRD Challenge)
**Codex said:** FR40 says status must show "what passed, what failed, and why" but get_status() only returns stage/progress/timestamps.
**Decision:** AGREE
**Reasoning:** The PRD is explicit. Status must be decision-oriented, not just state-oriented.
**Action:** Expanded AC #8 to include gate_status, decision_required, blocking_reason, last_outcome. Created typed `PipelineStatus` dataclass in gate_manager.py with all fields. Added `test_runner_get_status_returns_all_fields()` test to verify presence.

### 3. NFR5 Scope Broadening
**Codex said:** NFR5 is optimization-specific in the PRD but story broadens to any long-running Rust stage.
**Decision:** PARTIALLY AGREE
**Reasoning:** NFR5 says "Long-running optimization runs" but D3 talks about checkpoint/resume for the pipeline generally. The backtest stage is also long-running (5.26M bars at 10 years). Broadening is architecturally sound. However, V1 only has backtest stages — optimization is Epic 5.
**Action:** No change to scope. The within-stage checkpoint contract is correctly defined as a generic interface. V1 will exercise it for backtest stages; Epic 5 extends to optimization.

### 4. Wrong Module Path (Architecture Challenge — CRITICAL)
**Codex said:** Architecture places pipeline under `src/python/orchestrator/` with `pipeline_state.py`, `stage_runner.py`, `gate_manager.py`, `recovery.py`. Story invents `src/python/pipeline/`.
**Decision:** AGREE
**Reasoning:** Architecture L1535-1540 is unambiguous. The story must align.
**Action:** Changed all file paths from `src/python/pipeline/` to `src/python/orchestrator/`. Aligned file names: `stage.py` + `state.py` → `pipeline_state.py`, `orchestrator.py` → `stage_runner.py` + `gate_manager.py`, crash logic → `recovery.py`. Updated test paths to match. Updated Project Structure Notes with architecture line references.

### 5. Untyped Dict Payloads (Architecture Challenge)
**Codex said:** Architecture says contracts/ is SSOT for shared schemas, but story uses untyped `dict` for executor I/O, checkpoints, errors, and context.
**Decision:** PARTIALLY AGREE
**Reasoning:** Cross-runtime types (checkpoint format shared with Rust) must go through `contracts/`. Internal Python types should be proper dataclasses but don't need TOML schemas — that's over-engineering for internal interfaces.
**Action:** Replaced executor return type `dict` with typed `StageResult` dataclass. `PipelineState.checkpoint` now typed as `WithinStageCheckpoint | None` instead of `dict | None`. `error` typed as `PipelineError | None`. Added `contracts/pipeline_checkpoint.toml` for the cross-runtime checkpoint schema. `completed_stages` now uses typed `CompletedStage` dataclass with `outcome` and `manifest_ref` fields.

### 6. Duplicate Artifact Validation
**Codex said:** `executor.validate_artifact()` and `_verify_last_artifact()` both exist, duplicating responsibility.
**Decision:** AGREE
**Reasoning:** Single path for validation avoids divergence. The executor owns domain knowledge of what constitutes a valid artifact.
**Action:** Recovery module's `verify_last_artifact()` now delegates to `executor.validate_artifact()` using artifact_path and manifest_ref from state. Added anti-pattern #11: "Don't duplicate artifact validation." Removed independent verification logic from recovery.

### 7. Hardcoded Retry Counts
**Codex said:** "max 3 retries" conflicts with D7's config-driven retry settings.
**Decision:** AGREE
**Reasoning:** D7 explicitly defines `[pipeline] retry_max_attempts` and `[pipeline] retry_backoff_base_s`. Hardcoding contradicts the architecture.
**Action:** Replaced "max 3 retries" with config-driven values referencing D7 keys. Added bold note in D7 dev notes: "All retry counts and backoff parameters MUST come from config, never hardcoded." Updated anti-pattern #8 to reference specific config keys.

### 8. clean_partial_files() vs partial_artifact_path Conflict (Story Design)
**Codex said:** `clean_partial_files()` called on startup could delete files referenced by `partial_artifact_path` in checkpoints, destroying resumable state.
**Decision:** AGREE
**Reasoning:** This is a real conflict. Startup cleanup must be checkpoint-aware.
**Action:** Defined explicit cleanup ordering in Task 5: (1) load state, (2) read checkpoints to identify referenced partials, (3) clean only unreferenced `.partial` files via exclude set. Added anti-pattern #10: "Don't clean partial files before reading checkpoints."

### 9. Extensible Stage Graph vs Enum "Hardcoding"
**Codex said:** Anti-pattern says "don't hardcode stage definitions" while Task 2 hardcodes them in an enum.
**Decision:** DISAGREE
**Reasoning:** The enum + STAGE_GRAPH IS the non-hardcoded approach — it centralizes definitions instead of scattering string literals. Adding a new stage = add enum value + graph entry. A plugin/config-driven stage system would be over-engineering for V1 (one strategy, one pair/timeframe).
**Action:** Clarified anti-pattern #6 wording: "Don't scatter stage definitions as string literals" with note that "The enum + graph pattern IS the non-hardcoded approach."

### 10. Missing Downstream Contract Fields (Downstream Impact — CRITICAL)
**Codex said:** Stories 3.7 and 3.8 need gate decisions, reasons, evidence-pack refs in state model. Current model lacks these. 3.2 dependency path is wrong. Run lineage is weak.
**Decision:** AGREE on gate fields, evidence refs, 3.2 path fix, run_id. PARTIALLY AGREE on lineage — add run_id, defer full versioning to Growth.
**Reasoning:** If 3.3 doesn't include these fields, 3.7/3.8 will bolt them on or bypass the state file — exactly the drift that hurts reproducibility. But a full versioning/lineage system is beyond V1 scope.
**Action:** Added `run_id` field to PipelineState (UUID per execution attempt). Added AC #12 for run identity. Added `gate_decisions` list and `evidence_pack_ref` in GateDecision and CompletedStage. Fixed 3.2 dependency path from `planning-artifacts/research/` to `implementation-artifacts/`. Changed 3.2 dependency from "optional fallback" to "mandatory dependency." Added gate cycle integration test.

---

## Changes Applied

### Acceptance Criteria
- AC #2: Added explicit precondition definition (artifact exists, manifest valid, no unresolved errors)
- AC #8: Expanded status fields to include gate_status, decision_required, blocking_reason, last_outcome
- Added AC #11: Gate decision model (accept/reject/refine with reason, timestamp, evidence_pack_ref)
- Added AC #12: Run identity (unique run_id per execution attempt for lineage)

### Tasks
- Task 1: Fixed 3.2 dependency path to correct location
- Task 2: Moved to `src/python/orchestrator/pipeline_state.py`, added `GateDecision` dataclass
- Task 3: Expanded `PipelineState` with `run_id`, `gate_decisions`, typed `CompletedStage` (with outcome/manifest_ref), typed checkpoint and error fields, `config_hash`
- Task 4: Restructured into `stage_runner.py` + `gate_manager.py` per architecture. Added typed `StageResult`, `PipelineStatus`. Gate model supports accept/reject/refine. Resume assigns new run_id.
- Task 5: Moved to `recovery.py`. Fixed cleanup ordering (load state → read checkpoints → clean unreferenced partials). Consolidated validation through executor. Added `contracts/pipeline_checkpoint.toml`.
- Task 6: Config-driven retries referencing D7 keys
- Task 8: Restructured all test files to `tests/unit/orchestrator/` and `tests/integration/orchestrator/`. Added 15 new test cases for: gate reject/refine paths, status field presence, run_id assignment, config-hash mismatch warning, cleanup ordering, executor delegation, full gate cycle.

### Dev Notes
- Module path aligned to architecture's `src/python/orchestrator/` (L1535-1540)
- D7 note: bold emphasis that retry params must come from config
- Critical Design Decisions: expanded with gate decision model, run identity, single validation path, mandatory 3.2 dependency, scoped within-stage recovery
- Anti-patterns: added #10 (cleanup ordering), #11 (validation duplication). Clarified #6 (enum is correct approach). Strengthened #8 (config-driven retries with specific keys).
- Project Structure: aligned to architecture with file-by-file mapping and line references
- Added architecture line references to References section

---

## Deferred Items
- **Full lineage/versioning system** — run_id provides basic lineage; full version tracking across strategy reruns deferred to Growth phase
- **Evidence pack assembly logic** — nullable `evidence_pack_ref` fields are placeholders; Story 3.7 implements the assembler
- **Within-stage recovery implementation** — contract defined, but actual recovery logic (re-dispatch to Rust at checkpoint offset) depends on Story 3-4's batch protocol
- **Extensible stage plugin system** — enum + graph is sufficient for V1; if Growth requires dynamic stage registration, revisit then

---

## Verdict
VERDICT: IMPROVED
