# Review Synthesis: Story 2-3-strategy-specification-schema-contracts

## Reviews Analyzed
- BMAD: available (1 Critical, 3 High, 5 Medium, 2 Low)
- Codex: available (3 High, 2 Medium)

## Accepted Findings (fixes applied)

### 1. C1 — MA Crossover reference spec cannot express cross-indicator comparison
- **Source:** Both (BMAD C1 + Codex H-AC8)
- **Severity:** CRITICAL
- **Description:** The `EntryCondition` model only supported comparing an indicator against a numeric `threshold`. The MA crossover reference spec used two separate SMA conditions with `threshold=0.0`, which is semantically broken — SMA of FX prices (~1.08 for EURUSD) will never cross above/below 0.0. There was no mechanism for cross-indicator comparison (SMA(20) vs SMA(50)).
- **Fix:** Added `sma_crossover` indicator to `contracts/indicator_registry.toml` (following the existing `ema_crossover` pattern with `fast_period`/`slow_period` params). Rewrote `artifacts/strategies/ma-crossover/v001.toml` and test fixture to use a single `sma_crossover` condition. The `threshold=0.0` with `comparator=crosses_above` now has correct semantics: the crossover difference crosses above zero.
- **Files changed:** `contracts/indicator_registry.toml`, `artifacts/strategies/ma-crossover/v001.toml`, `src/python/tests/test_strategy/fixtures/valid_ma_crossover.toml`
- **Regression tests:** `test_ma_crossover_uses_single_crossover_indicator`, `test_sma_crossover_in_indicator_registry`

### 2. H-AC4 — No `extra="forbid"` on Pydantic models
- **Source:** Codex
- **Severity:** HIGH
- **Description:** All Pydantic models had `strict=True` but not `extra="forbid"`, so unknown/extra fields in TOML specs were silently ignored instead of rejected. This violated AC4 ("fails loud on non-conforming specs").
- **Fix:** Added `extra="forbid"` to all 15 `ConfigDict` declarations in `specification.py`.
- **Files changed:** `src/python/strategy/specification.py`
- **Regression tests:** `test_extra_fields_rejected_at_top_level`, `test_extra_fields_rejected_in_metadata`

### 3. H2 — Indicator parameter names not validated against registry
- **Source:** Both (BMAD H2 + Codex H-AC5)
- **Severity:** HIGH
- **Description:** `validate_strategy_spec()` checked that indicator types were known but never validated that parameter names matched the registry's `required_params`/`optional_params`. A spec could declare `sma` with `{window: 20}` instead of `{period: 20}` and pass validation.
- **Fix:** Added parameter name validation in `loader.py` — for each indicator reference, verifies all `required_params` are present and no unknown params are passed. Applied to both conditions and confirmations.
- **Files changed:** `src/python/strategy/loader.py`
- **Regression tests:** `test_indicator_missing_required_param_caught`

### 4. H1 — Dead code: optimization parameter cross-validation never executed
- **Source:** Both (BMAD H1 + Codex H-AC8)
- **Severity:** HIGH
- **Description:** `validate_strategy_spec()` built an `entry_indicator_params` set from entry conditions but never used it. The optimization plan could reference parameters that don't exist in any entry condition.
- **Fix:** Completed the cross-validation — `optimizable_params` set now collects params from entry conditions, confirmations, and trailing exit params. Each optimization parameter group is validated against this set.
- **Files changed:** `src/python/strategy/loader.py`
- **Regression tests:** `test_optimization_param_not_in_entry_conditions_caught`

### 5. H3 — Incomplete numeric validation for filter/trailing params
- **Source:** Both (BMAD H3 + Codex M)
- **Severity:** HIGH/MEDIUM
- **Description:** Volatility filter `period`, trailing stop `distance_pips`, chandelier `atr_period` and `atr_multiplier` were checked for presence but not validated as > 0.
- **Fix:** Added `> 0` range checks in `EntryFilter.validate_filter_params()` (volatility period) and `ExitTrailing.validate_trailing_params()` (distance_pips, atr_period, atr_multiplier).
- **Files changed:** `src/python/strategy/specification.py`
- **Regression tests:** `test_volatility_filter_period_zero_rejected`, `test_volatility_filter_period_negative_rejected`, `test_trailing_stop_distance_pips_zero_rejected`, `test_chandelier_atr_period_zero_rejected`, `test_chandelier_atr_multiplier_negative_rejected`

### 6. H-AC6 — Version not updated in metadata when saving new version
- **Source:** Codex
- **Severity:** HIGH
- **Description:** `save_strategy_spec()` computed the new version string for the filename but dumped the original model unchanged, so `v002.toml` could contain `metadata.version = "v001"`. This broke self-consistency of persisted artifacts.
- **Fix:** Added `spec_dict["metadata"]["version"] = version_str` before TOML serialization in `storage.py`.
- **Files changed:** `src/python/strategy/storage.py`
- **Regression tests:** `test_saved_version_updates_metadata_version`

### 7. M-Codex — group_dependencies unchecked free-form strings
- **Source:** Codex
- **Severity:** MEDIUM
- **Description:** `group_dependencies` accepted arbitrary strings, so typos or references to nonexistent groups were silently accepted.
- **Fix:** Added `validate_group_dependencies()` model validator to `OptimizationPlan` that parses `"group_a -> group_b"` format and verifies each referenced name exists in `parameter_groups`.
- **Files changed:** `src/python/strategy/specification.py`
- **Regression tests:** `test_group_dependency_references_nonexistent_group`, `test_group_dependency_valid_references_accepted`

### 8. M1 — `__init__.py` exports only StrategySpecification
- **Source:** BMAD
- **Severity:** MEDIUM
- **Description:** Package only exported `StrategySpecification`, requiring callers to use deep imports.
- **Fix:** Added key public functions to `__all__`: `load_strategy_spec`, `validate_strategy_spec`, `validate_or_die_strategy`, `compute_spec_hash`, `verify_spec_hash`, `save_strategy_spec`, `load_latest_version`, `list_versions`, `is_indicator_known`, `get_indicator_params`.
- **Files changed:** `src/python/strategy/__init__.py`

### 9. M3 — Indicator registry count mismatch in documentation
- **Source:** BMAD
- **Severity:** MEDIUM
- **Description:** Registry header comment said "18 indicators" but actual count was 19 (now 20 with sma_crossover). Test comment also mismatched.
- **Fix:** Updated comment to "20 indicators" and updated test assertion and docstring.
- **Files changed:** `contracts/indicator_registry.toml`, `src/python/tests/test_strategy/test_indicator_registry.py`

## Rejected Findings (disagreed)

### M2 — Stop loss 1.5x ATR overrides chandelier 3x ATR (BMAD, MEDIUM)
- **Reason:** This is a strategy design choice, not a schema bug. The stop loss (1.5x ATR) serves as an absolute safety floor while the chandelier (3x ATR) is the trailing mechanism. Both can coexist meaningfully — different instruments for different purposes. Strategy design is the operator's domain, not schema enforcement scope.

### M4 — Redundant cost model regex in semantic validator (BMAD, MEDIUM)
- **Reason:** Defense-in-depth is acceptable and near zero-cost. The semantic validator acts as a safety net in case `CostModelReference` is constructed programmatically, bypassing Pydantic parsing.

### M5 — Confirmation schema section incomplete in TOML contract (BMAD, MEDIUM)
- **Reason:** The confirmation section is explicitly optional and follows the same structural pattern as conditions (indicator + parameters + threshold + comparator). The TOML contract documents the structure; confirmation is not a separate discriminated type requiring its own `element_fields`.

### L1 — Contract schema vocabulary differs from Arrow schema (BMAD, LOW)
- **Reason:** Strategy specifications and Arrow schemas describe fundamentally different domain objects. Different vocabulary (`fields` vs `columns`, `required` vs `nullable`) is appropriate domain modeling, not inconsistency.

### L2 — Hasher handles nested lists better than source pattern (BMAD, LOW)
- **Reason:** Not a bug — noted as an improvement over the config_loader hasher pattern. No action required.

## Action Items (deferred)
- None. All MEDIUM+ accepted findings were fixed.

## Test Results
```
src/python/tests/ (full suite, excluding live):
378 passed, 43 deselected in 2.50s

src/python/tests/test_strategy/ (including live):
53 passed in 0.31s

Regression tests (new): 14 tests, all passing
```

## Verdict
All critical, high, and medium accepted findings have been fixed with corresponding regression tests. The full test suite passes with zero regressions. The MA crossover reference spec now correctly expresses cross-indicator comparison. Schema validation is now fail-loud on unknown fields. Indicator parameter names are validated against the registry. Optimization parameters are cross-validated against entry/exit params. Saved versions update embedded metadata.

VERDICT: APPROVED
