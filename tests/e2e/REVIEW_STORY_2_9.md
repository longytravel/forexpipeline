# Adversarial Code Review: Story 2.9 (E2E Pipeline Proof)

**Reviewer**: Claude Opus 4.6
**Date**: 2026-03-17
**Files reviewed**:
- `tests/e2e/test_epic2_pipeline_proof.py`
- `tests/e2e/conftest.py`
- `tests/e2e/fixtures/ma_crossover_dialogue.json`
- `tests/e2e/fixtures/expected_ma_crossover_spec.toml`
- `pytest.ini`

---

## CRITICAL Findings

### C1. `test_rerun_determinism_identical_hashes` references undefined `pipeline` fixture
**File**: `test_epic2_pipeline_proof.py:641-659`
**Severity**: CRITICAL
The function `test_rerun_determinism_identical_hashes` has signature `(e2e_workspace, dialogue_input)` but at line 653 calls `pipeline_capture_only(dialogue_input, ws["strategy_artifacts_dir"], ws["defaults_path"])` for `result1`, reusing the *same* `ws["strategy_artifacts_dir"]` that the module-scoped `pipeline` fixture already wrote v001 into. Since `pipeline` is module-scoped and ran first (other tests depend on it), the strategy_artifacts_dir already contains the v001 spec from the first run. Running `capture_strategy_intent` again into the same directory may fail or produce `v002` instead of `v001`, corrupting the determinism check. The test compares hashes from two runs but the first run writes into a potentially dirty directory.

### C2. `expected_ma_crossover_spec.toml` fixture is never used
**File**: `tests/e2e/fixtures/expected_ma_crossover_spec.toml`
**Severity**: CRITICAL
The expected spec fixture exists but is never loaded or compared against in any test. AC #2 requires validating that the generated spec matches expected output, but no test does a structural comparison against this reference fixture. The fixture is dead weight, and there is no golden-file regression test.

---

## HIGH Findings

### H1. Structured log test (AC #10) uses weak substring matching, no required fields check
**File**: `test_epic2_pipeline_proof.py:602-636`
**Severity**: HIGH
AC #10 requires "structured logs emitted at each stage with required fields." The test only checks that *some* log message contains substrings like "intent", "capture", "modif", "confirm". It does not verify:
- Logs are actually structured (JSON or ctx dict format)
- Required fields are present (stage, timestamp, correlation_id, version, etc.)
- The `StructuredLogCapture.get_ctx_events()` method in conftest.py is never called despite being purpose-built for this

### H2. Cost model schema validation is conditional / silently skipped
**File**: `test_epic2_pipeline_proof.py:469-472` and `834-842`
**Severity**: HIGH
Both `test_cost_model_artifact_loads_with_all_sessions` (line 469) and `test_error_path_incomplete_cost_model_rejected` (line 834) guard schema validation behind `if schema_path.exists()`. If `cost_model_schema.toml` is missing from the contracts directory, these validations silently pass. For an E2E proof test, this should be a hard failure, not a conditional skip.

### H3. Error path version mismatch test is a tautology
**File**: `test_epic2_pipeline_proof.py:847-867`
**Severity**: HIGH
`test_error_path_cost_model_version_mismatch` asserts `spec.cost_model_reference.version == cm.version` (which the pipeline fixture already ensures) and then asserts `spec.cost_model_reference.version != "v999"` (a trivially true statement). This test does not actually exercise any error detection logic. It never constructs a mismatched reference and verifies the system rejects it.

### H4. Modification replaces entire `exit_rules.trailing` dict instead of single field
**File**: `test_epic2_pipeline_proof.py:136-144`
**Severity**: HIGH
AC #4 states "deterministic modification (atr_multiplier 3.0 -> 4.0)". The test creates a `ModificationIntent` with `action="set"` and `new_value` being the entire trailing exit dict (including `atr_period: 14` which didn't change). This is a wholesale replacement, not a surgical field edit. If `apply_modifications` only supports dict-level replacement, the diff would show the entire trailing block changed, not just `atr_multiplier`. The test then searches the diff for `atr_multiplier` which may mask that the diff is coarser than intended.

### H5. No verification that `defaults_path` actually exists
**File**: `conftest.py:128-134`
**Severity**: HIGH
If `config/strategies/defaults.toml` does not exist in the project, `defaults_dest` is `None`. This is passed to `capture_strategy_intent` which may silently use hardcoded defaults or crash. The test should assert the defaults file exists, or explicitly test the no-defaults path.

---

## MEDIUM Findings

### M1. `log_capture` fixture never tears down logger levels
**File**: `conftest.py:57-84`
**Severity**: MEDIUM
The fixture sets all target loggers to `DEBUG` level but only removes the handler on teardown -- it never restores the original log levels. This could pollute other test modules sharing the same process.

### M2. Dataset linkage check is best-effort with no assertion
**File**: `test_epic2_pipeline_proof.py:568-574`
**Severity**: MEDIUM
AC #9 requires "all artifacts present, versioned, linked." The test looks for Arrow/Parquet files but stores the result in `has_dataset` which is never asserted on. The dataset linkage is silently ignored.

### M3. Reference artifact test saves to source fixtures directory
**File**: `test_epic2_pipeline_proof.py:679-730`
**Severity**: MEDIUM
`test_reference_artifacts_saved_and_loadable` writes `reference_ma_crossover_v001.toml`, `reference_eurusd_cost_model.json`, and `epic2_proof_manifest.json` into `ws["fixtures_dir"]` which resolves to `tests/e2e/fixtures/` (the actual source tree, not a temp dir). This mutates the source tree as a side effect of running tests, which is an anti-pattern. Repeated test runs overwrite these files.

### M4. `pytest_collection_modifyitems` skip logic may conflict with marker expressions
**File**: `conftest.py:19-27`
**Severity**: MEDIUM
The function checks `if requested and ("live" in requested or "e2e" in requested)` using substring matching. Running `pytest -m "not live"` would match `"live" in requested` and NOT skip e2e tests, which is the opposite of the user's intent.

### M5. Enrichment step masks spec_generator gap instead of documenting it
**File**: `test_epic2_pipeline_proof.py:93-101, 120-123`
**Severity**: MEDIUM
The `_enrich_spec_file` function manually injects `optimization_plan` and `cost_model_reference` into the spec. This is a known gap (spec_generator.py doesn't produce these). The code has a comment at line 67 but neither the test file nor any skip marker explicitly documents this as a known gap that must be resolved. The enrichment uses `crash_safe_write` which is good, but it means the "generated spec" in AC #2 is actually a *manually enriched* spec, partially undermining the E2E claim.

### M6. Rust subprocess tests have 120s timeout but no skip on missing cargo
**File**: `test_epic2_pipeline_proof.py:482-542`
**Severity**: MEDIUM
The Rust crate tests (`test_rust_cost_model_crate_builds`, etc.) call `subprocess.run(["cargo", ...])` with a 120s timeout. If `cargo` is not installed, the test fails with a confusing `FileNotFoundError` rather than a clean skip. These should use `pytest.importorskip` equivalent or `shutil.which("cargo")`.

---

## LOW Findings

### L1. Magic string "v001" repeated throughout
**File**: `test_epic2_pipeline_proof.py` (lines 90, 163, 224, 335, 433, 458, etc.)
**Severity**: LOW
The version string `"v001"` appears 15+ times as a magic string. A constant would improve maintainability.

### L2. `_COST_MODEL_REFERENCE` is minimal
**File**: `test_epic2_pipeline_proof.py:90`
**Severity**: LOW
`_COST_MODEL_REFERENCE = {"version": "v001"}` only has a version field. The expected spec TOML also only has `version`. If the schema adds required fields (e.g., `pair`, `path`), this will silently pass until someone adds schema enforcement.

### L3. `test_error_path_invalid_spec_rejected` catches bare `Exception`
**File**: `test_epic2_pipeline_proof.py:783`
**Severity**: LOW
`pytest.raises(Exception)` is too broad -- it would pass even on `FileNotFoundError` or `KeyboardInterrupt`. Should catch the specific validation error type.

### L4. Import inside test function
**File**: `test_epic2_pipeline_proof.py:689, 793-805`
**Severity**: LOW
`from strategy.storage import _clean_none_values` (line 689) and `from strategy.dialogue_parser import ...` (lines 793, 805) are imported inside test functions. The `_clean_none_values` is a private function being used in test code, coupling to internal implementation.

---

## Known Gap Verification

| Known Gap | Status | Notes |
|-----------|--------|-------|
| `sma_crossover` not in Rust registry | PARTIALLY HANDLED | Rust tests (AC #7/#8) run via subprocess but the test doesn't verify `sma_crossover` specifically. If the Rust registry rejects it, `cargo test` would fail, which is correct. But no Python-side test documents this gap. |
| `group_dependencies` arrow notation | NOT TESTED | `_OPTIMIZATION_PLAN` uses `"entry_timing -> exit_levels"` (line 86) and the expected TOML has it (line 46), but no test verifies the Rust engine can parse this notation. The Python schema validation presumably passes it as a string. |
| Cost model path format mismatch | NOT TESTED | No test verifies that the Rust cost model crate can load artifacts from the Python-generated path format. The subprocess tests run the crate's own tests, which may use different fixture paths. |
| `optimization_plan` / `cost_model_reference` not from spec_generator | WORKED AROUND | `_enrich_spec_file()` manually adds them (line 93-101). Comment at line 67 explains the workaround. No `pytest.xfail` or tracking marker. |

---

## AC Coverage Summary

| AC | Covered? | Quality | Notes |
|----|----------|---------|-------|
| #1 Dialogue -> spec | Yes | Good | Tests fixture-driven, checks pair/timeframe/indicators/filters/exits |
| #2 Schema validation | Yes | Medium | Validates but uses enriched (not raw generated) spec; no golden-file comparison |
| #3 Operator review | Yes | Good | Checks summary content and provenance tracking |
| #4 Deterministic modification | Yes | Medium | Replaces entire trailing dict, not surgical; diff check is adequate |
| #5 Locked + versioned | Yes | Good | Checks status, hashes, timestamps, manifest |
| #6 Cost model 5 sessions | Yes | Good | Thorough session validation |
| #7 Rust cost model | Yes | Medium | Subprocess only; no cargo skip guard |
| #8 Rust strategy engine | Yes | Medium | Subprocess only; no cargo skip guard |
| #9 Artifacts linked | Partial | Medium | Dataset linkage not asserted (M2) |
| #10 Structured logs | Yes | Poor | Substring matching only, no field validation (H1) |
| #11 Reference fixtures | Yes | Medium | Writes to source tree (M3) |
| #12 Rerun determinism | Yes | Risky | Directory contamination risk (C1) |
