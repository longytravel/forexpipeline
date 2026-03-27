# Story 3-3-pipeline-state-machine-checkpoint-infrastructure: Story 3.3: Pipeline State Machine & Checkpoint Infrastructure — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

Static review only; I did not run `pytest`, and git-based change auditing was not possible because this workspace is not a git repo.

**HIGH findings**
- AC #2 is only partially implemented because automatic-transition preconditions never validate artifact integrity via manifest hash. `check_preconditions()` only checks that the artifact path exists and ignores `manifest_ref` contents entirely, so a corrupt artifact or missing manifest still passes. [gate_manager.py:147](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L147) [gate_manager.py:151](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L151) [test_gate_manager.py:125](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_gate_manager.py#L125)
- AC #4 is only partially implemented because `resume()` validates the last artifact with the executor for `current_stage`, not the stage that produced the artifact, and skips validation entirely if no executor is registered for the current stage. A paused pipeline at `review-pending` can therefore resume without validating the `backtest-complete` artifact at all. [stage_runner.py:190](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L190) [stage_runner.py:191](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L191) [stage_runner.py:192](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L192) [test_stage_runner.py:206](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_stage_runner.py#L206)
- AC #5 is not met. `resume()` loads a checkpoint into `state.checkpoint`, but stage execution never consumes that checkpoint or `last_completed_batch`; executors only receive `artifacts_dir`, so there is no within-stage resume path. The checkpoint reader also accepts any syntactically valid JSON without enforcing the contract bounds. [stage_runner.py:216](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L216) [stage_runner.py:218](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L218) [stage_runner.py:386](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L386) [recovery.py:96](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/recovery.py#L96) [pipeline_checkpoint.toml:20](C:/Users/ROG/Projects/Forex Pipeline/contracts/pipeline_checkpoint.toml#L20)
- `refine` corrupts status accounting. Re-entry moves `current_stage` back to `backtest-running` but leaves superseded `completed_stages` intact; `get_status()` then computes progress from raw history length, so a refined-and-rerun strategy can report 100% progress while still waiting at `review-pending`, with stale manifests/outcomes still shown as completed. That breaks AC #8 accuracy and weakens AC #11 semantics. [gate_manager.py:96](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L96) [gate_manager.py:103](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L103) [gate_manager.py:191](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L191) [gate_manager.py:203](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L203) [test_pipeline_e2e.py:165](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_pipeline_e2e.py#L165)

**MEDIUM findings**
- Gate decisions are only durably stored if the caller explicitly passes `state_path` or manually saves afterward. The core `advance()` API does not persist by default, so AC #11 depends on caller discipline rather than the orchestrator itself. [gate_manager.py:43](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L43) [gate_manager.py:112](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L112) [test_pipeline_live.py:99](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_pipeline_live.py#L99)
- Retry budgeting is probably off by one. `_execute_stage()` loops over `range(max_attempts + 1)`, while logging formats attempts as `{attempt + 1}/{retry_max_attempts}`, so a configured value of `3` can produce a fourth attempt and a misleading `4/3` log line. No test covers exhaustion. [stage_runner.py:384](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L384) [errors.py:110](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/errors.py#L110)
- The orchestrator itself does not load or validate TOML config as the story/task text claims; it relies on prebuilt `PipelineConfig` and `full_config` injection. That is story/task drift and leaves schema enforcement outside this module boundary. [stage_runner.py:111](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L111) [stage_runner.py:125](C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L125)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | `run()` creates per-strategy `pipeline-state.json` with stage, completed/pending stages, and timestamps. |
| 2 | Partially Met | Gated vs automatic behavior exists, but artifact validity is not checked per manifest hash. |
| 3 | Fully Met | Stage enum and graph match the required sequence. |
| 4 | Partially Met | Resume loads state and continues, but last-artifact validation can use the wrong executor or be skipped. |
| 5 | Not Met | Checkpoints are read, but not validated semantically or used to resume within the stage. |
| 6 | Partially Met | `PipelineState.save()` uses crash-safe writes; within-stage checkpoint writing is not implemented here end-to-end. |
| 7 | Fully Met | No profitability gate is enforced. |
| 8 | Partially Met | Status shape is present, but refine/rerun flows can make progress and completed-stage reporting inaccurate. |
| 9 | Fully Met | D8 categories, checkpoint-before-action, and backoff handling are implemented. |
| 10 | Fully Met | Structured logging uses the unified D6 schema. |
| 11 | Partially Met | Accept/reject/refine decisions exist, but persistence is opt-in and refine bookkeeping is incomplete. |
| 12 | Fully Met | New UUID `run_id` values are assigned for new runs and resumes. |

**Test Coverage Gaps**
- No test proves `resume()` validates with the executor for the last completed stage, or that resume blocks when the current stage has no executor. [test_stage_runner.py:206](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_stage_runner.py#L206)
- No test covers manifest presence/hash validation in either `check_preconditions()` or `verify_last_artifact()`; current tests only exercise existence and delegation. [test_gate_manager.py:125](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_gate_manager.py#L125) [test_recovery.py:22](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_recovery.py#L22)
- No test verifies that a recovered checkpoint changes execution behavior, passes resume context into an executor, or resumes from `last_completed_batch`. [test_recovery.py:102](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_recovery.py#L102) [test_regression.py:159](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_regression.py#L159)
- No test checks status correctness after a `refine` followed by rerun, so the progress/data-integrity bug is currently unguarded. [test_pipeline_e2e.py:165](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_pipeline_e2e.py#L165)
- No test covers retry exhaustion semantics, so the configured-attempt-budget behavior is still ambiguous. [test_errors.py:60](C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_orchestrator/test_errors.py#L60)

**Summary**
6 of 12 criteria are fully met, 5 are partially met, and 1 is not met.

The main blockers are artifact-integrity enforcement, correct resume-time validation, real within-stage checkpoint resume, and refine-cycle state/status correctness.
