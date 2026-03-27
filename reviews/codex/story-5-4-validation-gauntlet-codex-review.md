# Story 5-4-validation-gauntlet: Story 5.4: Validation Gauntlet — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- CPCV does not implement the story’s actual validation logic. `run_cpcv()` computes `purged_train_ranges` and then ignores them, evaluates only one contiguous span from the first test group to the last, and feeds placeholder IS data into a median-based `compute_pbo()`. That makes both purge/embargo handling and the PBO hard gate invalid for AC2/AC3. Refs: [cpcv.py#L56](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/cpcv.py#L56), [cpcv.py#L120](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/cpcv.py#L120), [cpcv.py#L147](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/cpcv.py#L147)
- The Monte Carlo permutation leg is mathematically degenerate. `permutation_test()` shuffles return order and recomputes Sharpe as `mean/std`, which is order-invariant, so the p-value collapses toward 1.0 and cannot satisfy AC5’s intent. The tests currently lock in that wrong behavior. Refs: [monte_carlo.py#L114](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/monte_carlo.py#L114), [test_monte_carlo.py#L168](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_validation/test_monte_carlo.py#L168)
- Checkpointing is only superficial. `run()` writes a file, but it stores almost no resumable state, never reloads it on a later run, and `resume()` only deserializes JSON. AC11 requires resume-from-last-completed-stage; this implementation does not do that. Refs: [gauntlet.py#L93](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L93), [gauntlet.py#L179](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L179), [gauntlet.py#L229](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L229)
- DSR is computed but never enforced as the mandatory hard gate from AC10. The gauntlet calculates a `DSRResult` after candidate processing, but no candidate/stage is failed from it and the executor still returns `success` either way. Refs: [gauntlet.py#L195](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L195), [gauntlet.py#L403](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L403), [executor.py#L82](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L82)
- The gauntlet can fabricate Monte Carlo and regime evidence from synthetic fallback data instead of actual walk-forward outputs. If the caller does not pass `trade_results` or `market_data_table`, `_run_monte_carlo()` and `_run_regime()` silently invent tiny tables. That is a direct data-integrity failure for AC5/AC6/AC7. Refs: [gauntlet.py#L312](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L312), [gauntlet.py#L317](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L317), [gauntlet.py#L346](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L346)
- The artifact contract is incomplete. Walk-forward artifacts omit train/test split boundaries, CPCV artifacts omit train/test groups, and the gauntlet manifest leaves required lineage fields empty (`chart_data_refs`, `config_hash`, `research_brief_versions`). That breaks AC3, AC7, and AC12. Refs: [results.py#L107](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/results.py#L107), [results.py#L145](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/results.py#L145), [arrow_schemas.toml#L117](C:/Users/ROG/Projects/Forex%20Pipeline/contracts/arrow_schemas.toml#L117), [arrow_schemas.toml#L129](C:/Users/ROG/Projects/Forex%20Pipeline/contracts/arrow_schemas.toml#L129)
- Pipeline integration is broken as implemented. `ValidationExecutor` expects `optimization_artifact_path`, in-memory `strategy_spec`, in-memory `cost_model`, and `output_dir`, while `StageRunner` produces `strategy_spec_path`, `cost_model_path`, `output_directory`, and no optimization artifact path. I also found no registration of the validation executor in the reviewed source. Refs: [executor.py#L35](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L35), [executor.py#L42](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L42), [stage_runner.py#L554](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L554)
- Suspicious performance flagging is incomplete. The code records only a Sharpe-based `is_oos_divergence` scalar; AC9 requires quantified IS/OOS divergence for both Sharpe and profit factor plus automatic flagging. Refs: [walk_forward.py#L42](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/walk_forward.py#L42), [walk_forward.py#L198](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/walk_forward.py#L198), [gauntlet.py#L171](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L171)

**MEDIUM Findings**
- Walk-forward embargo is applied before the test segment (`actual_test_start = purge_end + embargo`) rather than after `test_end`, so the leakage-control semantics do not match the story/research wording. Refs: [walk_forward.py#L91](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/walk_forward.py#L91)
- The shipped config and tests contradict the story’s post-validation gating requirement. `base.toml` still gates only `review-pending`, and the validation pipeline-state test explicitly treats `VALIDATION_COMPLETE` as terminal. Refs: [base.toml#L63](C:/Users/ROG/Projects/Forex%20Pipeline/config/base.toml#L63), [stage_runner.py#L87](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L87), [test_pipeline_state_validation.py#L39](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_validation/test_pipeline_state_validation.py#L39)
- Perturbation only partially covers non-continuous parameters: categorical params are skipped outright and there is no conditional-branch handling, so AC4 is only partially satisfied. Refs: [perturbation.py#L50](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/perturbation.py#L50), [perturbation.py#L57](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/perturbation.py#L57)
- Full-output determinism is not achieved because every gauntlet run stamps a fresh UUID-derived `run_id` into the checkpoint and manifest. Numeric metrics may repeat, but serialized results do not. Refs: [gauntlet.py#L93](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L93), [gauntlet.py#L202](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L202)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Partially Met | Rolling windows and per-window metrics exist, but split metadata/persistence and leakage semantics are incomplete. |
| 2 | Not Met | CPCV purge handling and PBO computation are placeholder/incorrect. |
| 3 | Partially Met | CPCV artifact/summary exist, but required per-combination metadata is missing. |
| 4 | Partially Met | Numeric perturbation works; categorical/conditional handling is incomplete. |
| 5 | Partially Met | Bootstrap and stress exist; permutation is invalid and gauntlet may use synthetic trades. |
| 6 | Fully Met | Volatility x session bucketing, minimum-trade checks, and insufficient-bucket flagging are implemented. |
| 7 | Partially Met | Writers exist, but manifest/contract completeness is missing and gauntlet persistence is not end-to-end reliable. |
| 8 | Partially Met | Default stage order and PBO short-circuit exist, but DSR gate and post-validation pipeline behavior are incomplete. |
| 9 | Partially Met | Only Sharpe divergence is captured; PF ratio and explicit flagging are missing. |
| 10 | Not Met | DSR is computed but not enforced as a promotion gate. |
| 11 | Not Met | Checkpoint file creation exists, actual resume semantics do not. |
| 12 | Not Met | Visualization-ready temporal split data is not persisted in artifacts. |
| 13 | Partially Met | Deterministic seeding exists, but full outputs are not identical across runs. |

**Test Coverage Gaps**
- No test proves CPCV uses disjoint non-adjacent test groups correctly or that `purged_train_ranges` affects execution.
- No test exercises a real checkpoint resume path; the live suite only checks that a checkpoint file exists. Ref: [test_live_validation.py#L491](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_validation/test_live_validation.py#L491)
- No test asserts that a failing DSR blocks promotion or causes stage failure; the live DSR test only checks that a value was computed. Ref: [test_live_validation.py#L532](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_validation/test_live_validation.py#L532)
- No test validates walk-forward/CPCV artifact schemas against the story-required boundary/group fields or the downstream manifest contract.
- The Monte Carlo suite currently enshrines the broken permutation behavior instead of catching it. Ref: [test_monte_carlo.py#L168](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_validation/test_monte_carlo.py#L168)
- No test covers PF-based suspicious-performance flagging or explicit flag emission.
- No reviewed test covers `ValidationExecutor` integration through `StageRunner` with the actual context keys used by the orchestrator.

**Summary**
1 of 13 criteria are fully met, 8 are partially met, and 4 are not met. I found 8 high-severity findings and 4 medium-severity findings.

Git-based change auditing was not possible here because `C:\Users\ROG\Projects\Forex Pipeline` is not a git repository in this environment.
