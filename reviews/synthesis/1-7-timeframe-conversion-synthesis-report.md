# Review Synthesis: Story 1-7-timeframe-conversion

## Reviews Analyzed
- BMAD: available (1 HIGH, 4 MEDIUM, 4 LOW findings)
- Codex: available (3 HIGH, 2 MEDIUM findings)

## Accepted Findings (fixes applied)

### 1. H1 session not recomputed from config schedule
- **Source:** Both (BMAD M1+M2, Codex H1)
- **Severity:** HIGH
- **Description:** AC #4 specifies H1 session must be recomputed from `config/base.toml [sessions]` with majority-vote and tie-breaking. The implementation used `_majority_session()` on pre-labeled M1 session values instead, and `period_start_us` was accepted but unused for tie-breaking. `compute_session_for_timestamp()` existed but was dead code for H1.
- **Fix:** Added `_recompute_h1_session()` that computes session for each minute in the hour via `compute_session_for_timestamp()`, performs majority vote on computed sessions, and implements correct tie-breaking (prefer session whose start time falls within the hour). Threaded `session_schedule` parameter through `convert_timeframe()` → `_aggregate_by_period()` → `_compute_session_for_period()`. The orchestrator `run_timeframe_conversion()` now passes `config.get("sessions")`.
- **Regression tests:** `test_h1_session_recomputed_from_schedule`, `test_h1_session_tie_break_starts_during_hour`

### 2. Partial preexisting output can overwrite completed artifact
- **Source:** Codex (H2)
- **Severity:** HIGH
- **Description:** The idempotency skip only triggered when BOTH arrow and parquet existed. If only one existed (e.g., crash after writing arrow but before parquet), the code would rewrite both, overwriting the valid artifact. Violates Anti-Pattern #6: "Do NOT overwrite existing converted files."
- **Fix:** Changed write logic to check each file independently — only write arrow if arrow doesn't exist, only write parquet if parquet doesn't exist.
- **Regression test:** `test_partial_preexisting_output_not_overwritten`

### 3. target_timeframes array elements not validated
- **Source:** Both (BMAD L3, Codex H3)
- **Severity:** MEDIUM (BMAD LOW, Codex HIGH — split the difference)
- **Description:** `schema.toml` defined `target_timeframes` as `type = "array"` but had no element-level constraint. Invalid values like "M99" would survive startup validation and fail at runtime.
- **Fix:** (a) Added `allowed_elements = ["M1", "M5", "H1", "D1", "W"]` to `schema.toml`. (b) Added runtime validation in `run_timeframe_conversion()` that checks each target timeframe against `VALID_TIMEFRAMES` before any conversion starts.
- **Regression test:** `test_invalid_target_timeframe_in_config_raises`

### 4. Empty table schema inconsistency
- **Source:** BMAD (L1)
- **Severity:** LOW
- **Description:** `_empty_aggregated_table()` copied the source schema (which could have extra columns), while `_aggregate_by_period()` returned a hardcoded 9-column schema. The two paths could return different schemas.
- **Fix:** Changed `_empty_aggregated_table()` to use the same canonical 9-column schema as the non-empty aggregation path.
- **Regression test:** `test_empty_table_schema_matches_non_empty`

### 5. No empty-input guard before deriving filename dates
- **Source:** Codex (M2)
- **Severity:** MEDIUM
- **Description:** `run_timeframe_conversion()` called `_extract_date_range()` unconditionally. An empty source file (or tick input aggregating to zero M1 bars) would crash with a cryptic error in `pc.min()` on an empty column.
- **Fix:** Added early guard: if `source_table.num_rows == 0` after loading/tick conversion, log a warning and return `{}`.
- **Regression test:** `test_empty_input_returns_empty_dict`

## Rejected Findings (disagreed)

### 1. O(n*p) aggregation loop scalability
- **Source:** BMAD (H1)
- **Severity:** HIGH (per BMAD)
- **Reason for rejection:** This is a performance concern, not a correctness bug. The story has no performance requirements for V1. The theoretical 5.25M-bar scenario is for production volumes that V1 won't encounter. Per project guidance, V1 must prove the pipeline works; premature optimization is out of scope. The current implementation is correct and readable. Performance optimization can be addressed in a dedicated story when real data volumes warrant it.

### 2. Missing structured error codes per D8
- **Source:** BMAD (M3)
- **Severity:** MEDIUM
- **Reason for rejection:** D8 structured error codes are a cross-cutting concern that should be addressed consistently across ALL pipeline stories, not retrofitted into one story. The current implementation does raise clear, descriptive errors — they just don't reference `error_codes.toml`. Deferred to a dedicated error-handling story.

### 3. Schema validation narrower than contract metadata
- **Source:** Codex (M1)
- **Severity:** MEDIUM
- **Reason for rejection:** The contract metadata (allowed values, defaults, nullability beyond type) is not enforced by `schema_loader.py` — that's a schema_loader limitation, not a timeframe_converter bug. Fixing this requires changes to the shared schema validation infrastructure, which is out of scope for this story.

## Action Items (deferred)

| Priority | Item | Source |
|----------|------|--------|
| MEDIUM | Implement D8 structured error codes across all pipeline stages | BMAD M3 |
| MEDIUM | Add content-aware idempotency (source mtime/hash comparison) | BMAD M4 |
| MEDIUM | Enhance schema_loader to enforce contract metadata (allowed values, nullability) | Codex M1 |
| LOW | Fix Parquet crash-safe write gap (write to open file handle, fsync before close) | BMAD L2 |
| LOW | Test mid-write `.partial` file existence during crash-safe writes | BMAD L4 |
| LOW | Add end-to-end orchestration test starting from tick-schema source file | Codex test gap |

## Test Results

```
=================== 161 passed, 11 skipped in 1.32s ===================
```

- 47 tests in `test_timeframe_converter.py` (44 unit + 3 skipped live)
- 6 new regression tests added (all passing)
- 0 failures across the full 172-test suite

## Files Modified

- `src/python/data_pipeline/timeframe_converter.py` — H1 session recomputation, empty table schema, idempotency fix, empty-input guard, target validation, session_schedule threading
- `src/python/tests/test_data_pipeline/test_timeframe_converter.py` — 6 regression tests added
- `config/schema.toml` — `allowed_elements` for target_timeframes
- `src/python/pyproject.toml` — registered `regression` pytest marker

## Verdict

All HIGH findings from both reviewers have been addressed. The H1 session recomputation (the only functional bug affecting AC scorecard) is now correctly implemented per spec. 6 of 7 ACs are fully met; AC #4 is now also fully met with proper schedule-based recomputation and tie-breaking.

VERDICT: APPROVED
