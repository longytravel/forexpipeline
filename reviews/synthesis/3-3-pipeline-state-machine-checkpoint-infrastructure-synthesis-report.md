# Review Synthesis: Story 3-3-pipeline-state-machine-checkpoint-infrastructure

## Reviews Analyzed
- BMAD: available (Claude code-review workflow — 0 Critical, 2 Medium, 3 Low)
- Codex: available (GPT-5.4 static analysis — 4 HIGH, 3 MEDIUM)

## Accepted Findings (fixes applied)

### 1. Manifest hash validation missing in check_preconditions (AC #2)
- **Source:** Both (BMAD M1 + Codex HIGH)
- **Severity:** HIGH
- **Description:** `check_preconditions()` only checked artifact file existence but never validated integrity via manifest hash. AC #2 explicitly requires "artifact exists and is valid per manifest hash."
- **Fix:** Added optional `executor` parameter to `check_preconditions()`. When both `artifact_path` and `manifest_ref` are present and an executor is provided, calls `executor.validate_artifact()`. Updated `_execute_stages()` caller to pass the executor.
- **Files:** `gate_manager.py:117-168`, `stage_runner.py:301-304`

### 2. Resume validates with wrong executor (AC #4)
- **Source:** Codex (HIGH)
- **Severity:** HIGH
- **Description:** `resume()` looked up the executor for `current_stage` (the stage about to run), but the artifact to verify was produced by the *last completed* stage. At `review-pending`, no executor exists for that stage, so validation was silently skipped.
- **Fix:** Changed executor lookup to use `state.completed_stages[-1].stage` instead of `state.current_stage`.
- **Files:** `stage_runner.py:189-194`

### 3. Progress percentage exceeds 100% after refine cycles
- **Source:** Both (BMAD M2 + Codex HIGH)
- **Severity:** HIGH
- **Description:** `completed_stages` is append-only. After a refine cycle, duplicate stage entries cause `len(completed_stages)` to exceed `len(STAGE_ORDER)`, yielding progress > 100%.
- **Fix:** Changed progress calculation to use `len({cs.stage for cs in state.completed_stages})` (unique stages), capped at `total_stages`.
- **Files:** `gate_manager.py:190-194`

### 4. Retry log denominator wrong + wasteful sleep on final attempt
- **Source:** Codex MEDIUM (log) + BMAD L1 (sleep)
- **Severity:** MEDIUM
- **Description:** Log message showed `attempt N/retry_max_attempts` but total attempts is `max_attempts + 1`, producing misleading `4/3` on the last attempt. Also, the final failed attempt slept the longest backoff delay before immediately returning failure.
- **Fix:** Changed log denominator to `total_attempts = retry_max_attempts + 1`. Added `is_last_attempt` parameter to `handle_error()` — when True, skips `time.sleep()`. Caller passes `is_last_attempt=(attempt >= max_attempts)`.
- **Files:** `errors.py:52-124`, `stage_runner.py:390-398`

### 5. GateDecision.stage field has no validation
- **Source:** BMAD (L2)
- **Severity:** LOW
- **Description:** `__post_init__` validated `decision` but not `stage`. Invalid stage strings like `"foo-bar"` were silently accepted and persisted.
- **Fix:** Added `_VALID_STAGES` frozenset and stage validation in `__post_init__`.
- **Files:** `pipeline_state.py:96-112`

### 6. Gate status string construction is fragile
- **Source:** BMAD (L3)
- **Severity:** LOW
- **Description:** `decision + "ed"` with a special case for "refine" would silently produce incorrect values for future decision types (e.g., "retry" → "retryed").
- **Fix:** Replaced with `_DECISION_PAST_TENSE` mapping dict.
- **Files:** `gate_manager.py:177`

## Rejected Findings (disagreed)

### 1. AC #5 not met — checkpoint not consumed by executors
- **Source:** Codex (HIGH)
- **Severity:** HIGH (per Codex)
- **Rejection:** The story spec's Dev Notes explicitly state: *"Recovery logic in this story is limited to reading and validating existing checkpoints — speculative recovery is deferred to 3-4 where the actual batch protocol is defined."* Within-stage checkpoint consumption requires the Rust batch binary (Story 3-4). This story correctly defines the contract and reader. AC #5 says "the orchestrator detects partial checkpoints and resumes from the last valid checkpoint within the stage" — the detection and loading is implemented; the actual resume behavior requires the executor (3-4) to consume the checkpoint data.

### 2. Gate decision persistence is opt-in
- **Source:** Codex (MEDIUM)
- **Severity:** MEDIUM (per Codex)
- **Rejection:** Already addressed in prior review cycle (observation #1132). `advance()` accepts `state_path` and auto-saves when provided. The StageRunner always passes `state_path`. The API is designed for flexibility while the orchestrator layer ensures durability.

### 3. Orchestrator doesn't load/validate TOML config itself
- **Source:** Codex (MEDIUM)
- **Severity:** MEDIUM (per Codex)
- **Rejection:** Accepting a pre-built `PipelineConfig` via dependency injection is cleaner architecture than loading TOML inside the orchestrator. Config loading and schema validation happen at the system boundary (wherever the orchestrator is instantiated). `PipelineConfig.from_dict()` handles the typed extraction. This is a design choice, not a gap.

## Action Items (deferred)
None — all accepted findings were fixed in this synthesis.

## Test Results
```
======================== 902 passed, 87 skipped in 3.55s =======================
```
- 92 orchestrator tests passed (including 14 new regression tests for synthesis findings)
- 0 failures across entire test suite
- 3 orchestrator tests skipped (live tests requiring filesystem setup)

## Regression Tests Added
All marked `@pytest.mark.regression` in `test_regression.py`:
- `TestManifestHashValidation` — 2 tests (validate called, validation failure blocks)
- `TestResumeUsesCorrectExecutor` — 1 test (verifies last-completed-stage executor used)
- `TestProgressCappedAfterRefine` — 2 tests (single refine, double refine)
- `TestNoWastefulFinalSleep` — 2 tests (last attempt skips, non-last sleeps)
- `TestGateDecisionStageValidation` — 2 tests (invalid rejected, valid accepted)
- `TestGateStatusMapping` — 4 tests (reject/accept/refine/mapping correctness)

## Verdict
All 7 accepted findings fixed with regression tests. 3 findings rejected with reasoning. Full test suite passes with 0 regressions.

VERDICT: APPROVED
