# Review Synthesis: Story 1-8-data-splitting-consistent-sourcing

## Reviews Analyzed
- BMAD: **unavailable** (log contains only mode selection prompt — no review was executed)
- Codex: **available** (GPT-5.4, static analysis, 2 HIGH + 2 MEDIUM findings)

## Accepted Findings (fixes applied)

### 1. Split filenames lack data hash — stale artifact reuse (AC #5)
- **Source:** Codex
- **Severity:** HIGH
- **Description:** Split output filenames used `{pair}_{start}_{end}_{TF}_{split}.{ext}` without the data hash. When a new download for the same pair/date range produced different data, `ensure_no_overwrite()` (called without `expected_hash`) would see the old file and skip writing. The new manifest then pointed at stale split files from the previous download, violating AC #5 ("new downloads create new versioned artifacts, never overwrite existing").
- **Fix:** Modified `_build_split_filename()` to accept a `data_hash8` parameter and embed it in the filename: `{pair}_{start}_{end}_{hash8}_{TF}_{split}.{ext}`. Updated `run_data_splitting()` to pass the truncated hash. Updated all live tests that referenced old filename patterns.
- **Files changed:** `data_splitter.py` (lines 283-296, 422-443), `test_data_splitter_live.py` (3 test methods)
- **Regression test:** `TestRegressionHashInFilenames` (2 tests)

### 2. Ratio mode does not sort by timestamp before slicing (AC #1/#2)
- **Source:** Codex
- **Severity:** HIGH
- **Description:** `_split_by_ratio()` called `table.slice()` at the ratio index without sorting first. The story spec explicitly requires "Sort table by timestamp (ascending) — must be sorted before splitting." If input was unsorted (e.g., from a failed upstream stage or manual data), the 70/30 split would not correspond to the earliest/latest bars chronologically. `_verify_temporal_guarantee()` catches some cases but not all (e.g., nearly-sorted data with minor disorder within partitions).
- **Fix:** Added `pc.sort_indices(table, sort_keys=[("timestamp", "ascending")])` + `table.take()` at the top of `_split_by_ratio()`.
- **Files changed:** `data_splitter.py` (lines 129-137)
- **Regression test:** `TestRegressionUnsortedInput` (2 tests: reversed and shuffled input)

### 3. Date-mode metadata omits configured split boundary
- **Source:** Codex
- **Severity:** MEDIUM
- **Description:** When using `split_mode="date"`, metadata recorded only the actual last-train timestamp (which may differ from the configured date by up to one bar). The configured date was lost from metadata, reducing traceability. For multi-timeframe splitting, this actual timestamp was propagated but the user-configured intent was not recorded.
- **Fix:** Added `configured_split_date` field to `split_metadata` when `split_mode="date"`. Field is absent in ratio mode (not applicable).
- **Files changed:** `data_splitter.py` (lines 89-99, 116-118)
- **Regression test:** `TestRegressionDateModeMetadata` (2 tests)

## Rejected Findings (disagreed)

### 1. Schema/validator doesn't enforce split_mode="date" => valid ISO date
- **Source:** Codex
- **Severity:** MEDIUM
- **Description:** The TOML schema validator only performs basic checks (required/allowed/min/max) and doesn't have conditional validation logic. An invalid `split_date` would pass config validation and fail later at runtime.
- **Rejection reason:** The runtime code already handles this robustly: `SplitError` is raised if `split_date` is empty (line 96), and `datetime.fromisoformat()` raises a clear error for invalid date formats (line 157). The validator's design (min/max/allowed/required checks) was established in Story 1.3; adding conditional cross-field validation is a separate concern. The fail-fast at split time with descriptive error messages provides adequate defense. This could be a future enhancement but is not an AC requirement for Story 1.8.

## Action Items (deferred)
- Consider adding conditional cross-field validation to the config validator (e.g., `split_mode="date"` requires valid ISO date in `split_date`). This is a Story 1.3 validator enhancement, not Story 1.8 scope.
- Consider adding a test that exercises `run_data_splitting()` with two different M1 source files for the same pair/date range to verify the hash-in-filename fix end-to-end in a live integration test.

## Test Results
```
232 passed, 23 skipped in 2.01s
```
- 23 skipped = `@pytest.mark.live` integration tests (require `-m live` flag)
- 6 new `@pytest.mark.regression` tests all pass
- 0 regressions introduced

## Verdict
All HIGH findings fixed with regression tests. The one MEDIUM fix (configured_split_date) improves traceability. The rejected MEDIUM finding is adequately handled by runtime error handling. Full test suite passes with zero regressions.

VERDICT: APPROVED
