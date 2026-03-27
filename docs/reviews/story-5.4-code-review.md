# Story 5.4 Adversarial Code Review

**Date:** 2026-03-22
**Reviewer:** Claude (adversarial)
**Files:** monte_carlo.py, regime_analysis.py, gauntlet.py, results.py, executor.py

---

## CRITICAL

### C1. NFR4 violation: bootstrap holds ALL iterations in memory
- **File:** `src/python/validation/monte_carlo.py:74-97`
- **Issue:** `bootstrap_equity_curves` appends every iteration's Sharpe, drawdown, and PnL to Python lists (`sharpes`, `drawdowns`, `pnls`). With `n_samples=10000` this is fine, but NFR4 requires streaming Monte Carlo so that memory does not scale linearly with iteration count. The story spec says "streaming Monte Carlo, not holding all iterations."
- **Fix:** Use Welford online algorithm for running quantiles, or pre-allocate numpy arrays and compute percentiles at the end (pre-allocated arrays are acceptable since size is known). At minimum, replace the 3 Python lists with pre-allocated `np.empty(n_samples)` arrays to avoid Python object overhead and signal intent.

### C2. Manifest missing required fields: `candidate_rank`, `per_stage_metric_ids`, `research_brief_versions` are empty stubs
- **File:** `src/python/validation/results.py:119-122`
- **Issue:** The story requires the manifest to include `candidate_rank`, `per_stage_metric_ids`, `chart_data_refs`, `config_hash`, and `research_brief_versions`. Currently `chart_data_refs` is `{}`, `config_hash` is `""`, and `research_brief_versions` is `{}`. Worse, `candidate_rank` and `per_stage_metric_ids` are **completely absent** from the manifest dict.
- **Fix:** Add `candidate_rank` (ordinal from optimization) to each candidate summary. Add `per_stage_metric_ids` mapping stage names to their artifact metric identifiers. Populate `config_hash` from a hash of the validation config. `chart_data_refs` and `research_brief_versions` can remain empty but `candidate_rank` and `per_stage_metric_ids` must be present.

---

## HIGH

### H1. DSR cannot short-circuit candidates because it runs AFTER all candidates complete
- **File:** `src/python/validation/gauntlet.py:194-197`
- **Issue:** DSR is computed once after all candidates complete (line 194-197), which is correct per spec. However, the `_should_short_circuit` method (line 381-389) claims to gate on DSR, yet DSR is never added to any candidate's `hard_gate_failures` list during the per-candidate loop. DSR results are not fed back to mark candidates as failing the DSR gate. The story says "Short-circuit on validity gates ONLY (PBO, DSR)." DSR gating is effectively non-functional.
- **Fix:** After DSR is computed, iterate over candidates and mark those that fail DSR. Alternatively, document that DSR is a population-level gate (not per-candidate), and ensure the manifest reflects DSR gate failure at the run level.

### H2. Executor does not register for `PipelineStage.VALIDATING`
- **File:** `src/python/validation/executor.py` (entire file)
- **Issue:** The story requires "Must register for PipelineStage.VALIDATING." The executor class never references `PipelineStage.VALIDATING` nor provides a `stage` attribute or registration mechanism. The stage_runner expects executors keyed by `PipelineStage` enum but nothing in this file wires `ValidationExecutor` to that enum.
- **Fix:** Add a class attribute `stage = PipelineStage.VALIDATING` or provide a registration factory/classmethod (consistent with how other stage executors register).

### H3. `validate_artifact` missing checks for `total_optimization_trials`, `chart_data_refs`, `config_hash`
- **File:** `src/python/validation/executor.py:117-124`
- **Issue:** `required_fields` list is `["optimization_run_id", "n_candidates", "stages", "gate_results", "dsr", "candidates"]`. It omits `total_optimization_trials`, `chart_data_refs`, `config_hash`, and `research_brief_versions` which the manifest is supposed to contain per spec.
- **Fix:** Add the missing fields to the validation list.

### H4. Permutation test p-value has off-by-one: does not include the observed statistic
- **File:** `src/python/validation/monte_carlo.py:129-138`
- **Issue:** Standard permutation test p-value should be `(count_exceeding + 1) / (n_permutations + 1)` to include the observed value in the null distribution. Current formula `count_exceeding / n_permutations` can produce p=0.0 exactly, which is statistically incorrect for a permutation test.
- **Fix:** `p_value = (count_exceeding + 1) / (n_permutations + 1)`

---

## MEDIUM

### M1. Checkpoint only saves latest candidate progress, not all prior candidates
- **File:** `src/python/validation/gauntlet.py:181-190`
- **Issue:** The `GauntletState` passed to `_checkpoint` only includes the current candidate's progress (`{cid: {s: "complete" ...}}`). All previously completed candidates are lost from the checkpoint. If the process crashes mid-gauntlet, `resume()` would only know about the last candidate.
- **Fix:** Accumulate all candidates' progress in the checkpoint state, not just the current one. Also serialize `completed_results` for already-finished candidates.

### M2. `resume()` loads state but is never called from `run()`
- **File:** `src/python/validation/gauntlet.py:229-239`
- **Issue:** The `resume()` method exists and can load a checkpoint, but `run()` never calls it. There is no code path that checks for an existing checkpoint before starting. The checkpoint/resume cycle is broken.
- **Fix:** At the start of `run()`, check for existing checkpoint via `resume()` and skip already-completed (candidate, stage) pairs.

### M3. `_run_monte_carlo` and `_run_regime` fabricate dummy data when inputs are None
- **File:** `src/python/validation/gauntlet.py:317-325, 352-363`
- **Issue:** When `trade_results` or `market_data_table` is None, hardcoded dummy data is created (5 fake trades, 100 fake bars). This silently produces meaningless validation results instead of raising an error or returning a clear "skipped" status.
- **Fix:** Raise a clear error or return a StageOutput with `passed=False` and a "missing input" reason. Never fabricate data in a validation pipeline.

### M4. `_get_pnl` fallback returns zeros instead of raising on missing column
- **File:** `src/python/validation/regime_analysis.py:176-179`
- **Issue:** When `pnl_pips` is not in column names, it returns `np.zeros(len(trades))`. This silently produces 100% win_rate=0%, avg_pnl=0, sharpe=0 for all regimes. The `_get_pnl_column` in `monte_carlo.py` (line 259-271) has a better fallback that searches for floating columns.
- **Fix:** Align with `monte_carlo.py` fallback logic, or raise ValueError when no PnL column is found.

### M5. D6 compliance: f-string logging instead of structured format
- **File:** `src/python/validation/monte_carlo.py:239-241`, `gauntlet.py:97-98`, `regime_analysis.py:155-157`
- **Issue:** All log messages use f-string interpolation for the message parameter (e.g., `f"Monte Carlo complete: bootstrap CI=[{bootstrap.sharpe_ci_lower:.3f}..."`). D6 requires structured JSON logging. While `extra={"ctx": {...}}` provides structured data, the message itself is eagerly formatted even if the log level is disabled.
- **Fix:** Use `%s` style formatting or move all variable data exclusively into `extra["ctx"]`.

---

## LOW

### L1. `_compute_kurtosis` returns raw kurtosis, not excess kurtosis
- **File:** `src/python/validation/gauntlet.py:467-478`
- **Issue:** Docstring says "excess kurtosis + 3 (to get regular kurtosis)" but the formula `m4 / std^4` computes raw (non-excess) kurtosis directly. For a normal distribution this returns 3.0 (correct), but the docstring is misleading. The DSR formula typically expects excess kurtosis. If `compute_dsr` expects excess kurtosis, passing raw kurtosis would inflate the DSR estimate.
- **Fix:** Clarify whether `compute_dsr` expects raw or excess kurtosis. If excess, return `m4 / std^4 - 3.0`. If raw, fix the docstring.

### L2. `StageResult.error` type mismatch
- **File:** `src/python/validation/executor.py:103`
- **Issue:** `StageResult.error` is typed as `PipelineError | None` in the protocol, but `executor.py` passes `error=str(e)` (a string). This would fail type checking.
- **Fix:** Wrap the exception in a `PipelineError` instance.

### L3. Regime analysis: `np.convolve(..., mode='same')` produces edge artifacts
- **File:** `src/python/validation/regime_analysis.py:69`
- **Issue:** `mode='same'` zero-pads at boundaries, causing the first ~720 bars to have artificially low ATR and get classified as "low" volatility regardless of actual conditions.
- **Fix:** Use `mode='valid'` and pad the beginning with NaN or the first valid ATR value, or use a proper rolling mean (e.g., `np.cumsum` trick or pandas rolling).

### L4. Walk-forward Sharpe==0.0 filtered out of DSR computation
- **File:** `src/python/validation/gauntlet.py:417`
- **Issue:** `if wf_result and wf_result.aggregate_sharpe != 0.0` filters out candidates whose true OOS Sharpe is exactly 0.0. This biases DSR upward by excluding neutral-performing candidates.
- **Fix:** Change to `if wf_result is not None` (remove the != 0.0 filter).

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 4     |
| MEDIUM   | 5     |
| LOW      | 4     |
| **Total**| **15**|

**Blockers for merge:** C1 (NFR4 memory), C2 (missing manifest fields), H1 (DSR gate non-functional), H2 (no stage registration), H4 (permutation p-value bias).
