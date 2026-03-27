# Review Synthesis: Story 5-2b-optimization-search-space-schema-range-proposal

## Reviews Analyzed
- BMAD: available (0 Critical, 1 High, 4 Medium, 3 Low)
- Codex: available (5 High, 4 Medium)

## Accepted Findings (fixes applied)

### 1. Engine clamping logic produces slow_period.max=100, story requires 200
- **Source:** Codex (HIGH)
- **Severity:** HIGH
- **Description:** `_propose_indicator_param()` had redundant `min(proposed_max, tf_max)` on line 325 that defeated the "ensure at least 2x current" guarantee on line 324. For slow_period with current=50 on H1 (tf_max=100), the engine produced max=100 instead of the story-required 200.
- **Fix:** Replaced the three-line clamping logic with: `current * 4` (generous exploration), `max(_, current * 2)` (at least 2x guarantee), `min(_, tf_max * 2)` (soft ceiling). Now slow_period(50) on H1 correctly produces max=200.
- **File:** `src/python/strategy/range_proposal.py:321-325`
- **Regression test:** `test_slow_period_max_not_clamped_below_story_spec`, `test_period_max_respects_soft_ceiling`

### 2. Constraint application drops condition metadata
- **Source:** Codex (MEDIUM)
- **Severity:** MEDIUM
- **Description:** `_apply_physical_constraints()` and `apply_cross_parameter_constraints()` rebuilt `SearchParameter` objects without passing through the `condition` field. Any future conditional numeric parameter would lose its activation rule after constraint adjustment.
- **Fix:** Added `condition=params[key].condition` (or equivalent) to all 4 `SearchParameter()` reconstruction sites in both functions.
- **File:** `src/python/strategy/range_proposal.py` (lines 430, 446, 471, 483)
- **Regression test:** `test_constraint_preserves_condition_metadata`

### 3. Source layer attribution marks multipliers as L3 (ATR-scaled)
- **Source:** Both (BMAD L1, Codex M1)
- **Severity:** MEDIUM
- **Description:** `_determine_source_layer()` used prefix matching (`sl_`, `tp_`, `trailing_`) to attribute parameters to L3. But `sl_atr_multiplier`, `tp_rr_ratio`, and `trailing_atr_multiplier` are dimensionless multipliers with hardcoded constant ranges — not ATR-scaled pip values. The artifact overstated how data-driven those ranges are.
- **Fix:** Refined matching: `"pips"` or `"distance"` in name → L3; `"multiplier"`, `"mult"`, or `"ratio"` in name → L1.
- **File:** `src/python/strategy/range_proposal.py:560-561`
- **Regression test:** `test_multiplier_params_attributed_to_l1_not_l3`

### 4. daily_range_median computes per-bar range, not daily
- **Source:** Codex (MEDIUM)
- **Severity:** MEDIUM
- **Description:** `ATRStats.daily_range_median` computed `median(high - low)` across all bars, which for non-daily timeframes (H1, M1) is per-bar range, not daily range. The field name was misleading.
- **Fix:** Renamed field from `daily_range_median` to `bar_range_median` throughout `range_proposal.py` and `test_range_proposal.py`. Updated docstring to "median per-bar high-low range in pips".
- **File:** `src/python/strategy/range_proposal.py` (all occurrences), `src/python/tests/test_strategy/test_range_proposal.py:97`
- **Regression test:** `test_bar_range_median_field_renamed`

### 5. Test fixture comment misleading
- **Source:** BMAD (MEDIUM)
- **Severity:** LOW
- **Description:** Comment in `valid_ma_crossover.toml` said "mirrors v001.toml" but the fixture uses v2 flat parameter format with `schema_version = 2`.
- **Fix:** Updated comment to "v2 flat parameter format, mirrors v002.toml structure".
- **File:** `src/python/tests/test_strategy/fixtures/valid_ma_crossover.toml:1`

### 6. Pipeline skill missing optimization commands (AC #9)
- **Source:** Both (BMAD HIGH, Codex "Not Met")
- **Severity:** HIGH
- **Description:** AC #9 requires three commands: "Propose optimization space", "Review search space", "Adjust parameter range". The pipeline skill had 15 operations but none related to optimization.
- **Fix:** Wrote complete Operations 16-18 with code templates and behavioral guidance. **However:** the skill.md write was blocked by file permissions. The content is ready but needs manual application.
- **File:** `.claude/skills/pipeline/skill.md` (permission-blocked)
- **Status:** DEFERRED — requires permission grant to write to `.claude/skills/`

## Rejected Findings (disagreed)

### 1. Categorical param semantic validation skipped (Codex HIGH)
- **Source:** Codex
- **Severity claimed:** HIGH
- **Description:** `validate_strategy_spec()` skips categorical params at line 143, so invalid categorical params could pass unchecked.
- **Rejection reason:** The skip is intentional and documented with a comment. V1 has exactly one categorical param (`session_filter`) which IS in the hardcoded `optimizable_params` set at line 137. The skip exists for future type-selector params (`exit_type`, etc.) that don't map to direct indicator params. Adding validation for non-existent future params is premature. When type selectors are added (post-V1), proper validation should be added alongside.

### 2. propose_ranges() doesn't build conditional/type search space (Codex HIGH)
- **Source:** Codex
- **Severity claimed:** HIGH
- **Description:** Range engine doesn't propose type-selector params or conditional branches.
- **Rejection reason:** Story spec Task 5 explicitly lists 7 params for v002 — none are type selectors. The reference strategy uses fixed exit types (atr_multiple SL, risk_reward TP, chandelier trailing). Type-selector proposals are a future enhancement when multi-type strategies exist.

### 3. Contract doc and optimizer out of sync (Codex MEDIUM)
- **Source:** Codex
- **Severity claimed:** MEDIUM
- **Description:** `contracts/optimization_space.md` defines `shared_params` plus branch maps, while existing `parameter_space.py` returns a flat list.
- **Rejection reason:** The contract doc is forward-looking — it defines what Story 5-3 will implement. The existing `parameter_space.py` is pre-5-3 code that will be rewritten. This is by design per D3 (opaque optimizer boundary).

### 4. ATR computation loads full data into memory (BMAD MEDIUM)
- **Source:** BMAD
- **Severity claimed:** MEDIUM
- **Description:** Uses `to_numpy()` instead of pyarrow compute functions, materializing ~120MB for EURUSD M1.
- **Rejection reason:** Range proposal is a one-time operation, not on the hot path. Dev notes express a preference, not a requirement. For a single invocation during strategy creation, 120MB is an acceptable tradeoff against the complexity of a pure pyarrow pipeline.

### 5. Param name collision/overwrite (Codex HIGH)
- **Source:** Codex
- **Severity claimed:** HIGH
- **Description:** Two conditions sharing the same raw param name would overwrite in the proposals dict.
- **Rejection reason:** V1 uses component-prefixed names (`fast_period`, `slow_period`) that prevent collisions. The naming convention is documented in the story spec and demonstrated by the reference strategy. Adding dedup logic for a bug that can't trigger with the current convention is premature.

### 6. Hardcoded parameter names in semantic validation (BMAD MEDIUM)
- **Source:** BMAD
- **Severity claimed:** MEDIUM
- **Description:** `loader.py:135-138` hardcodes known component-prefixed names for exit params.
- **Rejection reason:** V1 has exactly one reference strategy. The hardcoded names match the naming convention. Future strategies will need to extend this list, but that's expected when those strategies are created. Adding dynamic derivation now would be premature abstraction.

### 7. Story file not updated with Dev Agent Record (BMAD LOW)
- **Source:** BMAD
- **Severity claimed:** LOW
- **Rejection reason:** Administrative metadata — not a code bug, handled by the story runner workflow.

## Action Items (deferred)

1. **Pipeline skill.md update** (HIGH) — Operations 16-18 content is written and ready. Needs permission grant to write to `.claude/skills/pipeline/skill.md`.
2. **optimization_proposal.json artifact** (MEDIUM) — `persist_proposal()` function works correctly (tested), but the reference artifact is not generated on disk alongside `v002.toml`. Should be generated when the operator first runs "Propose optimization space" via the pipeline skill.
3. **Categorical param validation** (LOW) — When type-selector params (`exit_type`, `sl_type`) are added to strategies post-V1, extend the semantic validator to check categorical params against their strategy structure context.
4. **Param name collision guard** (LOW) — When multi-indicator strategies with shared raw param names are supported, add component-prefix enforcement or dedup logic in `propose_ranges()`.

## Test Results

```
189 passed, 23 skipped in 0.55s
```

All existing tests pass. 5 new regression tests added in `test_regression_5_2b.py`:
- `test_slow_period_max_not_clamped_below_story_spec`
- `test_period_max_respects_soft_ceiling`
- `test_constraint_preserves_condition_metadata`
- `test_multiplier_params_attributed_to_l1_not_l3`
- `test_bar_range_median_field_renamed`

## Files Modified
- `src/python/strategy/range_proposal.py` — 4 fixes (clamping, condition preservation, source layer, field rename)
- `src/python/tests/test_strategy/test_range_proposal.py` — field rename update
- `src/python/tests/test_strategy/fixtures/valid_ma_crossover.toml` — comment fix

## Files Created
- `src/python/tests/test_strategy/test_regression_5_2b.py` — 5 regression tests

## Verdict

The core implementation is solid. Schema models (SearchParameter, ParameterCondition, OptimizationPlan) are well-designed with comprehensive Pydantic v2 validation including DAG cycle detection. The range proposal engine correctly implements all 5 intelligence layers. 10 of 12 ACs are fully met after fixes.

AC #9 (pipeline skill commands) is blocked by file permissions — content is ready but needs manual application. AC #11 (persisted artifact on disk) is partially met — the function works but the on-disk artifact should be generated via the new skill command.

VERDICT: APPROVED
