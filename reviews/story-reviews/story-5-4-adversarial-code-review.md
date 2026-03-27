# Story 5.4 Adversarial Code Review

**Reviewer:** Claude Opus 4.6 (adversarial)
**Date:** 2026-03-22
**Scope:** `__init__.py`, `config.py`, `walk_forward.py`, `cpcv.py`, `perturbation.py`, `dsr.py`

---

## CRITICAL Findings

### C1. PBO computation is fundamentally wrong — does not implement Bailey et al.
**File:** `src/python/validation/cpcv.py:56-71`
**Severity:** CRITICAL

The `compute_pbo` function accepts `is_returns` and `oos_returns` but never actually uses `is_returns`. It simply counts what fraction of OOS returns fall below the median OOS return. This is **not** the Bailey et al. PBO algorithm.

**Bailey et al. PBO requires:**
1. For each CPCV combination, identify the IS-best strategy/configuration.
2. Find that same strategy's rank in the OOS results.
3. PBO = proportion of combinations where the IS-best strategy's OOS rank falls in the bottom half.

Since this is single-candidate CPCV, the classical PBO definition does not directly apply. The code's "below median" heuristic is a placeholder that will always produce PBO near 0.50 for symmetric distributions — making it a coin flip that has no real diagnostic power. The PBO hard gate (AC #2, D11) is effectively random.

**Should be:** Either implement proper multi-strategy PBO using the optimization trial population, or clearly document that single-candidate PBO uses a well-defined proxy (e.g., logit of relative OOS rank distribution) with a recalibrated threshold.

---

### C2. `is_returns` list is populated with OOS data — train/test leakage in PBO
**File:** `src/python/validation/cpcv.py:147`
**Severity:** CRITICAL

```python
is_returns.append(oos_sharpe)  # Placeholder for IS tracking
```

The `is_returns` list is filled with OOS Sharpe values (identical to `oos_returns`), then passed to `compute_pbo()`. Even if `compute_pbo` used `is_returns`, it would be computing with leaked OOS data. The in-sample evaluation is never dispatched for CPCV combinations — the code only calls `dispatcher.evaluate_candidate` once per combination for the test ranges, never for train ranges.

**Should be:** Dispatch an IS evaluation on `purged_train_ranges` for each combination, collect IS Sharpe separately, and pass genuine IS metrics to `compute_pbo`.

---

### C3. Purged train ranges computed but never used in CPCV evaluation
**File:** `src/python/validation/cpcv.py:120-128`
**Severity:** CRITICAL

`_apply_purge_embargo` returns `purged_train_ranges`, but this variable is never passed to the dispatcher. The dispatcher call at line 125-129 uses `test_ranges[0][0]` and `test_ranges[-1][1]` — the raw test boundaries. The purged train ranges are dead code.

**Should be:** Pass purged train ranges to the dispatcher for IS evaluation. The test evaluation should also use the individual test ranges (not just first-start to last-end, which may include train group bars in between if test groups are non-contiguous).

---

### C4. CPCV test evaluation spans non-contiguous groups as one range
**File:** `src/python/validation/cpcv.py:127-128`
**Severity:** CRITICAL

```python
window_start=test_ranges[0][0],
window_end=test_ranges[-1][1],
```

When k_test_groups=3 and the selected test groups are e.g. [1, 4, 7], this spans from group 1 start to group 7 end — **including train groups 2, 3, 5, 6 in the "test" evaluation**. This is a direct train-test contamination bug.

**Should be:** Either dispatch multiple evaluations (one per test group) and aggregate, or the dispatcher must accept a list of non-contiguous ranges.

---

## HIGH Findings

### H1. `_apply_purge_embargo` iterates bar-by-bar — O(N) memory and time per bar
**File:** `src/python/validation/cpcv.py:193-218`
**Severity:** HIGH

The function builds a `set()` of individual excluded bar indices, then iterates bar-by-bar through every train range. With purge_bars=1440 and embargo_bars=720, each test boundary adds ~2160 bars to the set. With 10 groups and 3 test groups, this is manageable. But if data_length is large (millions of M1 bars) and train ranges span most of the data, the bar-by-bar loop in lines 208-217 becomes extremely slow (O(data_length) per combination, times C(10,3)=120 combinations).

**Should be:** Use interval arithmetic (sort excluded intervals, merge overlaps, then clip train ranges against merged exclusion intervals) — O(N log N) in number of intervals, not O(data_length).

---

### H2. Walk-forward window generation produces degenerate windows for early indices
**File:** `src/python/validation/walk_forward.py:86-113`
**Severity:** HIGH

For window `i=0`: `test_start = 0 * window_size + int(window_size * 0.80)`, `purge_end = test_start`, `purge_start = max(0, purge_end - 1440)`, `train_end = purge_start`. With window_size smaller than purge+embargo, `train_end` could be 0 or negative (clamped to 0), producing a zero-length training window. The function does skip windows where `actual_test_start >= test_end`, but it doesn't check for empty train windows (`train_end <= train_start`).

Additionally, the "anchored" comment says `train_start=0`, but the train range `[0, train_end]` for window 0 may be tiny (e.g., `0.80 * window_size - 1440` bars), while for later windows it grows. This is inconsistent with proper anchored walk-forward where train should grow monotonically.

**Should be:** Validate `train_end > train_start` with a minimum training window size, and skip/warn on degenerate windows.

---

### H3. Walk-forward `rng` created but never used (FR18 gap)
**File:** `src/python/validation/walk_forward.py:146`
**Severity:** HIGH

```python
rng = np.random.Generator(np.random.PCG64(seed))
```

The RNG is created but never referenced again. If any stochastic behavior is later added to walk-forward, there's no guarantee it'll use this seeded RNG. Currently it's dead code.

**Should be:** Either remove the unused variable (clean code), or use it where seed is passed to dispatcher calls (currently `seed + w.window_id` is arithmetic, not RNG-derived — which is fine but makes the RNG object pointless).

---

### H4. CPCV `rng` created but never used (FR18 gap)
**File:** `src/python/validation/cpcv.py:98`
**Severity:** HIGH

Same issue as H3. `rng = np.random.Generator(np.random.PCG64(seed))` is created but never used.

---

### H5. DSR returns `passed=True` and `p_value=0.0` when num_trials <= 1
**File:** `src/python/validation/dsr.py:81-85`
**Severity:** HIGH

When `num_trials <= 1`, the function returns `passed=True` with `p_value=0.0`. A p-value of 0.0 means "infinitely significant" which contradicts the intent — with 1 trial there's no multiple testing, so the test is inapplicable, not maximally significant. The AC says DSR is "only computed when >10 candidates evaluated", but the function doesn't enforce this — it happily returns a misleading "passed" result for any trial count.

**Should be:** Return `p_value=1.0` (not significant) or `float('nan')` when num_trials <= 1, and/or raise ValueError when num_trials < minimum threshold. The `passed` field should be `True` only because DSR is inapplicable (and the caller should gate on >10 trials per AC #10).

---

### H6. DSR skewness/kurtosis correction formula inverts the adjustment
**File:** `src/python/validation/dsr.py:49-52`
**Severity:** HIGH

```python
correction = 1.0 - skew * sr / 3.0 + (kurt - 3.0) * sr**2 / 24.0
if correction > 0:
    e_max_sr = e_max_sr / correction
```

The Bailey & Lopez de Prado correction adjusts the *observed* Sharpe ratio, not the expected max Sharpe. The standard DSR formula adjusts SR_observed for non-normality:

```
SR_adjusted = SR * sqrt(1 - skew*SR/3 + (kurt-3)*SR^2/24)^(-1)
```

Applying this correction to `e_max_sr` instead of `observed_sharpe` in `compute_dsr()` is mathematically incorrect — it inflates the benchmark rather than adjusting the observation. Also, the correction term should be under a square root per the original paper.

**Should be:** Apply the non-normality adjustment to `observed_sharpe` in `compute_dsr`, not to `e_max_sr` in `compute_expected_max_sharpe`. Use the square root form from the paper.

---

## MEDIUM Findings

### M1. `from_dict` duplicates all defaults — single source of truth violation
**File:** `src/python/validation/config.py:70-123`
**Severity:** MEDIUM

Every default value appears twice: once in the dataclass field definitions and once in the `from_dict` method's `.get()` fallbacks. If a default changes in one place but not the other, behavior diverges silently.

**Should be:** Use `defaults = cls()` (already created at line 73) to source fallback values:
```python
n_windows=wf.get("n_windows", defaults.walk_forward.n_windows)
```

---

### M2. Perturbation sensitivity key uses negative float for "minus" direction
**File:** `src/python/validation/perturbation.py:152`
**Severity:** MEDIUM

```python
key = level if variant["direction"] == "plus" else -level
```

The `sensitivities` dict signature is `dict[str, dict[float, float]]` where the inner key is the perturbation level. Using negative floats as dict keys (e.g., `-0.05`) is unconventional and fragile with float equality. Also, if both +5% and -5% are stored under different keys, the downstream consumer must know about this encoding. The story spec says "sensitivity per param per level" — not per direction.

**Should be:** Either store max sensitivity per level (collapsing +/-), or use a tuple key `(level, direction)`, or a dedicated dataclass.

---

### M3. Perturbation `_infer_param_ranges` always returns type="float" even for int params
**File:** `src/python/validation/perturbation.py:181-193`
**Severity:** MEDIUM

The fallback range inference checks `isinstance(value, (int, float))` but always sets `"type": "float"`. Integer parameters will be treated as continuous, violating the story's requirement for integer rounding on int params (Task 5).

**Should be:** Check `isinstance(value, int)` separately and set `"type": "int"`.

---

### M4. Walk-forward divergence ratio is IS/OOS, not IS-OOS divergence magnitude
**File:** `src/python/validation/walk_forward.py:200`
**Severity:** MEDIUM

```python
is_oos_divergence = (mean_is / agg_sharpe) if agg_sharpe != 0.0 else 0.0
```

When `agg_sharpe` (OOS) is slightly negative, the ratio flips sign and can be extremely large/misleading. A ratio of `1.5` means IS is 50% higher than OOS, but a ratio of `-3.0` when OOS is slightly negative is not meaningful.

**Should be:** Use absolute difference or a bounded metric. Also handle the case where OOS Sharpe is near zero more gracefully (e.g., cap the ratio or use difference instead).

---

### M5. No input validation on config values
**File:** `src/python/validation/config.py` (all dataclasses)
**Severity:** MEDIUM

No `__post_init__` validation. Invalid configurations like `n_windows=0`, `train_ratio=1.5`, `pbo_red_threshold=-1.0`, `n_groups=0`, `k_test_groups > n_groups`, or `significance_level=2.0` are silently accepted and will cause downstream errors or nonsensical results.

**Should be:** Add `__post_init__` validation on each frozen dataclass (frozen dataclasses support `__post_init__`). Validate ranges: `n_windows >= 1`, `0 < train_ratio < 1`, `0 <= pbo_red_threshold <= 1`, `k_test_groups < n_groups`, etc.

---

### M6. `__init__.py` exports nothing
**File:** `src/python/validation/__init__.py`
**Severity:** MEDIUM

The `__init__.py` has only a docstring and no `__all__` or imports. This means consumers must import from submodules directly, and there's no public API definition for the validation package.

**Should be:** Define `__all__` and re-export key symbols: `ValidationConfig`, `WalkForwardResult`, `CPCVResult`, `PerturbationResult`, `DSRResult`, and the `run_*`/`compute_*` functions.

---

## LOW Findings

### L1. Perturbation uses `copy.copy` (shallow) instead of `copy.deepcopy`
**File:** `src/python/validation/perturbation.py:80`
**Severity:** LOW

If candidate dict contains nested structures (e.g., a param value that's a list or dict), shallow copy will share references. Currently candidate values are scalars, so this is not an active bug, but it's a latent issue.

**Should be:** Use `copy.deepcopy(candidate)` for safety.

---

### L2. Walk-forward reads entire Arrow file into memory for data_length
**File:** `src/python/validation/walk_forward.py:134-137`
**Severity:** LOW

When `data_length` is not provided, the code reads the entire Arrow IPC file into a PyArrow table just to get `len(table)`. For large datasets this is wasteful.

**Should be:** Use `reader.num_record_batches` and batch metadata to get row count without materializing the full table, or read just the metadata.

---

### L3. Same Arrow file read pattern duplicated in CPCV
**File:** `src/python/validation/cpcv.py:91-95`
**Severity:** LOW

Same issue as L2 — full table materialization just for row count. Should be extracted to a shared utility.

---

### L4. Fragile params detection hardcodes 0.30 threshold
**File:** `src/python/validation/perturbation.py:157`
**Severity:** LOW

The 30% sensitivity threshold for flagging fragile params is hardcoded. The story spec says "5% perturbation causes >30% performance drop", so this matches spec, but it should be configurable in `PerturbationConfig` for consistency with the config-driven design.

---

### L5. DSR `significance_level` parameter in `compute_dsr` shadows config
**File:** `src/python/validation/dsr.py:63`
**Severity:** LOW

`compute_dsr` accepts `significance_level` as a function parameter with default `0.05`, which could diverge from `DSRConfig.significance_level`. The caller must remember to pass the config value.

**Should be:** Accept `DSRConfig` directly, or document that the caller is responsible for passing the config value.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| CRITICAL | 4     | PBO algorithm wrong, IS data never collected, train-test contamination in CPCV |
| HIGH     | 6     | Degenerate windows, unused RNGs, DSR math errors, misleading edge cases |
| MEDIUM   | 6     | Config defaults duplication, no input validation, fragile API conventions |
| LOW      | 5     | Shallow copy, wasteful I/O, hardcoded thresholds |

**Top 3 action items:**
1. **Fix CPCV completely** (C1-C4): The entire CPCV module has no working IS evaluation, a broken PBO algorithm, and train-test contamination from spanning non-contiguous test groups. This is the highest-risk area.
2. **Fix DSR non-normality correction** (H6): The skewness/kurtosis adjustment is applied to the wrong variable and missing the square root.
3. **Add config validation** (M5): Invalid configs will produce silent garbage throughout the pipeline.
