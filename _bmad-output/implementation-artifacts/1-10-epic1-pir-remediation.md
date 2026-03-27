# Story 1.10: Epic 1 PIR Remediation

Status: review

## Story

As the **operator**,
I want all integration bugs, dead code, and missing data surfacing identified in the Epic 1 PIR to be resolved,
So that the pipeline stages can be wired together by the orchestrator without silent failures or misleading reports.

## Source

All items sourced from `reviews/pir/epic-1-pir-learnings.md` (2026-03-15 retroactive PIR).

## Acceptance Criteria

### Critical Fixes (blocks Epic 2)

1. **Given** the converter CLI in 1-6 looks for validated data at `raw/.../validated-data.csv`
   **When** the quality checker (1-5) saves to `validated/.../{dataset_id}_validated.csv`
   **Then** the CLI path is corrected so converter finds 1-5's actual output location

2. **Given** `timezone_issues` is computed at quality_checker.py line ~843
   **When** a quality report is generated
   **Then** timezone findings appear in the quality report and are accessible to the orchestrator for re-download decisions

3. **Given** `check_existing_dataset()` in data splitting (1-8) checks only `dataset_id`
   **When** config changes (different parameters, walk-forward windows)
   **Then** the reuse check includes `config_hash` so stale artifacts are not silently reused

4. **Given** three independent crash-safe write implementations exist in 1-5, 1-6, and 1-7
   **When** any stage writes an artifact
   **Then** all stages use a single shared `safe_write()` utility from a common module

### Important Fixes (tracked debt)

5. **Given** `quarantined_periods` in the quality report omits integrity-error quarantines and hardcodes `bar_count: 0` for gaps
   **When** a quality report is generated
   **Then** quarantine counts and `quarantined_percentage` accurately reflect all quarantine sources

6. **Given** `config_hash` is always blank (`""`) in quality reports
   **When** a quality report is generated
   **Then** `config_hash` is populated with the actual hash of the active config

7. **Given** `VALID_SESSIONS` is hardcoded as a frozenset in 1-6/1-7
   **When** session validation runs
   **Then** allowed values are loaded from `arrow_schemas.toml` (single source of truth)

### Dead Code Removal

8. **Given** ~125 lines of dead incremental helpers in 1-4 (`_detect_existing_data`, `_compute_missing_ranges`, `_validate_merge_boundary`, `_merge_data`)
   **When** this story completes
   **Then** dead helpers are removed (not needed for V1 append-only design)

9. **Given** `gap_severity` is computed at quality_checker.py line ~837 but never used
   **When** this story completes
   **Then** `gap_severity` is either wired into the quality report or the computation is removed

10. **Given** `_timeout` and `_backoff_factor` in 1-4 are stored but never passed to `dk.fetch()`
    **When** this story completes
    **Then** these config values are wired into `dk.fetch()` calls or removed from config

### Path Cleanup

11. **Given** 1-6 has a 3-source config path fallback and CWD-walking `_find_contracts_path()`
    **When** this story completes
    **Then** both are replaced with a single config-resolved canonical path

## Tasks / Subtasks

- [x] **Task 1: Fix CLI path mismatch (AC #1)** — Critical
  - [x] 1.1 In `converter_cli.py`, update the input path to match `quality_checker.py`'s actual output location (`validated/.../{dataset_id}_validated.csv`)
  - [x] 1.2 Add an integration test that runs quality_checker output → converter CLI to verify the path chain works end-to-end

- [x] **Task 2: Surface timezone findings in quality report (AC #2)** — Critical
  - [x] 2.1 In `quality_checker.py`, add `timezone_issues` to the quality report dict after it's computed (~line 843)
  - [x] 2.2 Verify the quality report JSON/dict includes timezone findings when timezone issues are detected
  - [x] 2.3 Verify timezone findings are empty/clean when no issues exist

- [x] **Task 3: Config-aware cache invalidation (AC #3, #6)** — Critical
  - [x] 3.1 In `check_existing_dataset()`, add `config_hash` to the dataset identity check
  - [x] 3.2 Populate `config_hash` field in quality reports with actual config hash (fixes AC #6)
  - [x] 3.3 Add test: different config → different dataset_id → no false reuse

- [x] **Task 4: Consolidate crash-safe write (AC #4)** — Critical
  - [x] 4.1 Create `src/python/data_pipeline/utils/safe_write.py` with shared `safe_write()` — atomic write-to-temp-then-rename pattern
  - [x] 4.2 Replace crash-safe write in 1-5 (`quality_checker.py`) with `safe_write()`
  - [x] 4.3 Replace crash-safe write in 1-6 (`converter.py`) with `safe_write()`
  - [x] 4.4 Replace crash-safe write in 1-7 (timeframe converter) with `safe_write()`
  - [x] 4.5 Verify all existing tests still pass after consolidation

- [x] **Task 5: Fix quarantine undercount (AC #5)** — Important
  - [x] 5.1 In quality_checker.py, ensure integrity-error quarantines are included in `quarantined_periods` count
  - [x] 5.2 Fix hardcoded `bar_count: 0` for gap quarantines — compute actual bar count
  - [x] 5.3 Recalculate `quarantined_percentage` from corrected counts

- [x] **Task 6: Contract-loaded enum values (AC #7)** — Important
  - [x] 6.1 Add a utility to load valid session values from `arrow_schemas.toml`
  - [x] 6.2 Replace hardcoded `VALID_SESSIONS` frozenset in 1-6 with contract-loaded values
  - [x] 6.3 Replace hardcoded `VALID_SESSIONS` frozenset in 1-7 with contract-loaded values

- [x] **Task 7: Dead code removal (AC #8, #9, #10)** — Cleanup
  - [x] 7.1 Remove dead incremental helpers from 1-4 downloader (~125 lines)
  - [x] 7.2 Wire `gap_severity` into quality report OR remove the computation (decide based on whether it adds operator value)
  - [x] 7.3 Wire `_timeout` and `_backoff_factor` into `dk.fetch()` calls OR remove from config
  - [x] 7.4 Remove cosmetic config keys that don't influence runtime

- [x] **Task 8: Path cleanup (AC #11)** — Cleanup
  - [x] 8.1 Replace 3-source config path fallback in 1-6 with single canonical config-resolved path
  - [x] 8.2 Replace CWD-walking `_find_contracts_path()` with config-resolved path
  - [x] 8.3 Verify converter still resolves paths correctly in CLI and API modes

## Dev Agent Record

### Implementation Plan
Many PIR items (Tasks 1, 2, 4, 5, 6, and parts of 7) were already addressed in prior story implementations. This run verified they were complete, then implemented the remaining items:
- **Task 3 (AC #6)**: Auto-compute config_hash in quality_checker.validate() when caller doesn't provide one, using compute_config_hash() from config_loader.hasher.
- **Task 7 (AC #10)**: Removed dead config keys (timeout_seconds, max_retries, retry_delay_seconds) from [data.download] in base.toml and schema.toml. Kept `source` key which is used by data_splitter.py.
- **Task 8 (AC #11)**: Removed `_find_contracts_path()` directory-walking from both arrow_converter.py and timeframe_converter.py. Replaced with fail-fast FileNotFoundError when `data_pipeline.contracts_path` not set. Added `contracts_path` to base.toml and schema.toml.

### Debug Log
- 276 unit tests pass, 0 failures
- 6 live integration tests pass
- Updated all test files that relied on monkeypatch.chdir for contracts path discovery

### Completion Notes
All 11 ACs satisfied. Tasks 1, 2, 4, 5, 6 were already implemented in prior stories (verified via code review). Tasks 3, 7, 8 required new code changes. Full regression suite green.

## File List

### Modified
- `src/python/data_pipeline/quality_checker.py` — Added config_hash auto-computation (AC #6)
- `src/python/data_pipeline/arrow_converter.py` — Removed _find_contracts_path(), fail-fast on missing config (AC #11)
- `src/python/data_pipeline/timeframe_converter.py` — Renamed _find_contracts_path to _resolve_contracts_path, removed directory walking (AC #11)
- `config/base.toml` — Removed dead [data.download] keys, added contracts_path (AC #10, #11)
- `config/schema.toml` — Removed dead schema entries, added contracts_path schema (AC #10, #11)
- `src/python/tests/test_data_pipeline/test_quality_checker.py` — Added config_hash auto-computation tests (AC #6)
- `src/python/tests/test_data_pipeline/test_arrow_converter.py` — Updated contracts_path tests (AC #11)
- `src/python/tests/test_data_pipeline/test_timeframe_converter.py` — Updated to use config contracts_path (AC #11)
- `src/python/tests/test_data_pipeline/test_pir_remediation_live.py` — Added 3 new live tests (AC #6, #10, #11)
- `src/python/tests/test_data_pipeline/test_arrow_converter_live.py` — Updated to set contracts_path in config (AC #11)
- `src/python/tests/test_data_pipeline/test_pipeline_integration.py` — Updated to set contracts_path in config (AC #11)

## Change Log

- 2026-03-15: Implemented remaining PIR remediation items (Tasks 3, 7, 8). Verified Tasks 1, 2, 4, 5, 6 already complete from prior stories. 276 unit tests + 6 live tests pass.

## Dev Notes

### Architecture Constraints
- All fixes must preserve existing test suites — no regressions
- `safe_write()` utility goes in `src/python/data_pipeline/utils/` alongside existing shared code
- Config hash should use the same hashing approach used elsewhere in the pipeline (check 1-8's `dataset_id` generation for pattern)

### Task Ordering
- Tasks 1-4 are **critical** and block orchestrator wiring (Epic 2). Do these first.
- Tasks 5-6 are **important** but non-blocking. Do after critical tasks.
- Tasks 7-8 are **cleanup**. Safe to do last since they remove code rather than change behavior.

### Anti-Pattern Rules (from PIR)
- If a method is called and its return value unused, either wire it in or remove the call
- Every config key must influence runtime behavior
- CLI integration tests must cover CLI-to-CLI stage chaining
- Idempotent skip needs hash-aware staleness detection

### Testing Strategy
- Task 1 specifically needs a CLI-to-CLI integration test (the gap that let this bug through)
- Tasks 2, 3, 5: unit tests verifying report contents
- Task 4: existing tests must pass after refactor (behavioral equivalence)
- Tasks 7, 8: verify no test failures after removal
